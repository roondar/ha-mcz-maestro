"""Data coordinator for MCZ Maestro."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from math import ceil
from time import monotonic

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MaestroClient, MaestroData, MaestroError, MaestroParameters
from .const import (
    ALARM_STATES,
    COMMAND_CONFIRMATION_POLL_INTERVAL_SECONDS,
    COMMAND_CONFIRMATION_TIMEOUT_SECONDS,
    DIAGNOSTIC_STATES,
    DOMAIN,
    MAX_DATA_AGE_SECONDS,
    POLL_INTERVAL,
    POWER_ADJUSTMENT_STATES,
    TEMPERATURE_STATUS_DISCONNECTED,
    TEMPERATURE_STATUS_FAULT,
)

_LOGGER = logging.getLogger(__name__)


class MaestroCoordinator(DataUpdateCoordinator[MaestroData]):
    """Poll and expose one MCZ Maestro stove."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: MaestroClient,
        parameters: MaestroParameters,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=POLL_INTERVAL,
        )
        self.client = client
        self.parameters = parameters
        self._parameters_generation = client.connection_generation
        self._last_success_at: float | None = None
        self._command_lock = asyncio.Lock()

    async def _async_update_data(self) -> MaestroData:
        try:
            if (
                not self.client.connected
                or self.client.connection_generation != self._parameters_generation
            ):
                self.parameters = await self.client.async_request_parameters()
                self._parameters_generation = self.client.connection_generation
            data = await self.client.async_request_info()
            self._last_success_at = monotonic()
            return data
        except MaestroError as err:
            raise UpdateFailed(str(err)) from err

    def _ensure_fresh_safe_state(self) -> int:
        """Fail closed unless the latest full state is recent and non-critical."""
        if (
            not self.last_update_success
            or self._last_success_at is None
            or monotonic() - self._last_success_at > MAX_DATA_AGE_SECONDS
        ):
            raise HomeAssistantError(
                "Commande refusée : l'état du poêle est absent ou périmé"
            )
        state = self.data.values.get("stove_state")
        if not isinstance(state, int):
            raise HomeAssistantError("Commande refusée : état du poêle invalide")
        if state in ALARM_STATES:
            raise HomeAssistantError(
                f"Commande refusée : le poêle est en alarme (état {state})"
            )
        if state in DIAGNOSTIC_STATES:
            raise HomeAssistantError(
                f"Commande refusée : le poêle est en diagnostic (état {state})"
            )
        return state

    @property
    def current_power_level(self) -> int | None:
        """Return P1–P5 from either the stored or live Maestro representation."""
        raw = self.data.values.get("power_level")
        if not isinstance(raw, int):
            return None
        value = raw - 10 if 11 <= raw <= 15 else raw
        return value if 1 <= value <= 5 else None

    def maximum_safe_power(self, proposed_fans: list[int] | None = None) -> int:
        """Apply the official MCZ fan/power rule for this stove model."""
        fans = proposed_fans or [
            self.data.values.get("fan_front"),
            self.data.values.get("fan_ducted_1"),
            self.data.values.get("fan_ducted_2"),
        ]
        normalized: list[int] = []
        for present, value in zip(self.parameters.fan_present, fans, strict=True):
            if not present:
                normalized.append(0)
                continue
            if not isinstance(value, int) or not 0 <= value <= 6:
                raise HomeAssistantError(
                    "Commande refusée : état d'un ventilateur invalide"
                )
            normalized.append(value)
        calculated = ceil(
            sum(normalized) / (self.parameters.fan_coefficient / 2)
        )
        return max(0, min(self.parameters.power_max, calculated))

    def validate_turn_on(self) -> None:
        state = self._ensure_fresh_safe_state()
        if state != 0:
            raise HomeAssistantError(
                f"Allumage refusé : état {state}, seul l'état éteint est autorisé"
            )
        probe_status = self.data.temperature_statuses.get("ambient_temperature")
        if probe_status in {
            TEMPERATURE_STATUS_FAULT,
            TEMPERATURE_STATUS_DISCONNECTED,
        }:
            raise HomeAssistantError(
                "Allumage refusé : la sonde de température ambiante est en défaut"
            )
        power = self.current_power_level
        maximum = self.maximum_safe_power()
        if power is None or power > maximum:
            raise HomeAssistantError(
                f"Allumage refusé : puissance mémorisée incompatible (maximum P{maximum})"
            )

    def validate_turn_off(self) -> None:
        self._ensure_fresh_safe_state()

    def validate_target_temperature(self, temperature: float) -> None:
        self._ensure_fresh_safe_state()
        minimum = self.parameters.target_temperature_min
        maximum = self.parameters.target_temperature_max
        if not minimum <= temperature <= maximum:
            raise HomeAssistantError(
                f"Consigne refusée : valeur autorisée entre {minimum:g} et {maximum:g} °C"
            )
        step = self.parameters.target_temperature_step
        if round(temperature / step) * step != temperature:
            raise HomeAssistantError(
                f"Consigne refusée : seuls les pas de {step:g} °C sont validés"
            )

    def validate_power_level(self, level: int) -> None:
        state = self._ensure_fresh_safe_state()
        control_mode = self.data.values.get("control_mode")
        if control_mode != 0:
            raise HomeAssistantError(
                "La puissance est gérée automatiquement en mode Dynamic ; "
                "passer en mode manuel pour la modifier"
            )
        if state not in POWER_ADJUSTMENT_STATES:
            raise HomeAssistantError(
                f"Puissance refusée pendant l'état transitoire {state}"
            )
        maximum = self.maximum_safe_power()
        if not self.parameters.power_min <= level <= maximum:
            raise HomeAssistantError(
                f"Puissance P{level} refusée : maximum sûr P{maximum} pour la ventilation actuelle"
            )

    def validate_fan_speed(self, data_key: str, value: int) -> None:
        state = self._ensure_fresh_safe_state()
        if state not in POWER_ADJUSTMENT_STATES:
            raise HomeAssistantError(
                f"Ventilation refusée pendant l'état transitoire {state}"
            )
        keys = ("fan_front", "fan_ducted_1", "fan_ducted_2")
        fan_index = keys.index(data_key)
        if not self.parameters.fan_present[fan_index]:
            raise HomeAssistantError("Commande refusée : ventilateur absent")
        if not self.parameters.fan_enabled[fan_index]:
            raise HomeAssistantError("Commande refusée : ventilateur non activable")
        if value == 0 and not self.parameters.fan_supports_off[fan_index]:
            raise HomeAssistantError(
                "Commande refusée : arrêt non supporté par ce ventilateur"
            )
        if value == 6 and not self.parameters.fan_supports_auto[fan_index]:
            raise HomeAssistantError(
                "Commande refusée : mode automatique non supporté"
            )
        if value not in {0, 6} and not (
            self.parameters.fan_min[fan_index]
            <= value
            <= self.parameters.fan_max[fan_index]
        ):
            raise HomeAssistantError(
                "Commande refusée : vitesse hors des limites du modèle"
            )
        fans = [self.data.values.get(key) for key in keys]
        if value == 0 and sum(
            isinstance(current, int) and current > 0 for current in fans
        ) <= 1:
            raise HomeAssistantError(
                "Commande refusée : le dernier ventilateur actif ne peut pas être arrêté"
            )
        fans[fan_index] = value
        maximum = self.maximum_safe_power(fans)
        power = self.current_power_level
        if power is None or power > maximum:
            raise HomeAssistantError(
                f"Ventilation refusée : elle limiterait le poêle à P{maximum} alors que P{power or '?'} est mémorisé"
            )

    def validate_mode_change(self) -> None:
        state = self._ensure_fresh_safe_state()
        if state != 0:
            raise HomeAssistantError(
                "Changement de mode refusé : il est autorisé uniquement poêle éteint"
            )

    def validate_control_mode_change(self) -> None:
        """Allow Dynamic/manual changes while off or at a stable power level."""
        state = self._ensure_fresh_safe_state()
        if state not in POWER_ADJUSTMENT_STATES:
            raise HomeAssistantError(
                "Changement Automatique/Manuel refusé pendant l'état transitoire "
                f"{state} ; attendre l'arrêt ou un régime stable P1 à P5"
            )

    async def async_execute_parameter(
        self,
        cell: int,
        value: int,
        validator: Callable[[], None],
        confirmation: Callable[[], bool],
    ) -> None:
        """Validate, serialize, send and confirm one parameter write."""
        async with self._command_lock:
            if (
                not self.client.connected
                or self.client.connection_generation != self._parameters_generation
            ):
                await self.async_refresh()
            validator()
            await self.client.async_write_parameter(cell, value)
            loop = asyncio.get_running_loop()
            confirmation_deadline = (
                loop.time() + COMMAND_CONFIRMATION_TIMEOUT_SECONDS
            )
            while loop.time() < confirmation_deadline:
                await asyncio.sleep(COMMAND_CONFIRMATION_POLL_INTERVAL_SECONDS)
                # Command confirmation must bypass DataUpdateCoordinator's
                # debouncer; otherwise no new frame may be read before timeout.
                await self.async_refresh()
                if self.last_update_success and confirmation():
                    return
            raise HomeAssistantError(
                "Commande envoyée, mais la valeur attendue n'a pas été confirmée ; vérifier le poêle"
            )

    async def async_execute_datetime(self) -> None:
        """Synchronize time only while the stove is safely off."""
        async with self._command_lock:
            if (
                not self.client.connected
                or self.client.connection_generation != self._parameters_generation
            ):
                await self.async_refresh()
            self.validate_mode_change()
            await self.client.async_set_datetime()
            await asyncio.sleep(1)
            await self.async_refresh()
