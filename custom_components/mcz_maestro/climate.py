"""Climate platform for MCZ Maestro."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CELL_POWER,
    CELL_TARGET_TEMPERATURE,
    DOMAIN,
    POWER_OFF,
    POWER_ON,
    STOVE_ON_STATES,
)
from .coordinator import MaestroCoordinator
from .entity import MaestroEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the MCZ Maestro climate entity."""
    coordinator: MaestroCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MaestroClimate(coordinator, entry)])


class MaestroClimate(MaestroEntity, ClimateEntity):
    """Represent the stove as a Home Assistant climate entity."""

    _attr_translation_key = "stove"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_min_temp = 5
    _attr_max_temp = 35
    _attr_target_temperature_step = 0.5
    _attr_precision = 0.5
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )

    def __init__(self, coordinator: MaestroCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "climate")
        self._attr_min_temp = coordinator.parameters.target_temperature_min
        self._attr_max_temp = coordinator.parameters.target_temperature_max
        self._attr_target_temperature_step = (
            coordinator.parameters.target_temperature_step
        )
        self._attr_precision = coordinator.parameters.target_temperature_step

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.data.values.get("ambient_temperature")

    @property
    def target_temperature(self) -> float | None:
        return self.coordinator.data.values.get("target_temperature")

    @property
    def hvac_mode(self) -> HVACMode:
        state = self.coordinator.data.values.get("stove_state", 0)
        return HVACMode.HEAT if state in STOVE_ON_STATES else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        state = self.coordinator.data.values.get("stove_state", 0)
        if state not in STOVE_ON_STATES:
            return HVACAction.OFF
        if state in {40, 41}:
            return HVACAction.IDLE
        return HVACAction.HEATING

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode is HVACMode.HEAT:
            await self.async_turn_on()
        else:
            await self.async_turn_off()

    async def async_turn_on(self) -> None:
        await self.async_write_parameter(
            CELL_POWER,
            POWER_ON,
            self.coordinator.validate_turn_on,
            lambda: self.coordinator.data.values.get("stove_state")
            in STOVE_ON_STATES,
        )

    async def async_turn_off(self) -> None:
        await self.async_write_parameter(
            CELL_POWER,
            POWER_OFF,
            self.coordinator.validate_turn_off,
            lambda: self.coordinator.data.values.get("stove_state") in {0, 40, 41},
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        requested = float(temperature)
        await self.async_write_parameter(
            CELL_TARGET_TEMPERATURE,
            round(requested * 2),
            lambda: self.coordinator.validate_target_temperature(requested),
            lambda: self.coordinator.data.values.get("target_temperature")
            == requested,
        )

    @property
    def extra_state_attributes(self) -> dict[str, int | str]:
        """Expose the active fail-closed safety decision."""
        return {
            "maximum_safe_power": self.coordinator.maximum_safe_power(),
            "fan_safety_coefficient": self.coordinator.parameters.fan_coefficient,
            "ambient_probe_status": self.coordinator.data.temperature_statuses.get(
                "ambient_temperature", "unknown"
            ),
        }
