"""Switch platform for MCZ Maestro."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CELL_CONTROL_MODE,
    CELL_ECO_MODE,
    CELL_SILENT_MODE,
    DOMAIN,
)
from .coordinator import MaestroCoordinator
from .entity import MaestroEntity


@dataclass(frozen=True, kw_only=True)
class MaestroSwitchDescription:
    key: str
    translation_key: str
    data_key: str
    cell: int
    enabled_default: bool = True


SWITCHES = (
    MaestroSwitchDescription(
        key="control_mode",
        translation_key="control_mode",
        data_key="control_mode",
        cell=CELL_CONTROL_MODE,
    ),
    MaestroSwitchDescription(
        key="eco_mode",
        translation_key="eco_mode",
        data_key="eco_mode",
        cell=CELL_ECO_MODE,
        enabled_default=False,
    ),
    MaestroSwitchDescription(
        key="silent_mode",
        translation_key="silent_mode",
        data_key="silent_mode",
        cell=CELL_SILENT_MODE,
        enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: MaestroCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MaestroSwitch(coordinator, entry, description) for description in SWITCHES
    )


class MaestroSwitch(MaestroEntity, SwitchEntity):
    """Represent a boolean Maestro parameter."""

    def __init__(
        self,
        coordinator: MaestroCoordinator,
        entry: ConfigEntry,
        description: MaestroSwitchDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self._description = description
        self._attr_translation_key = description.translation_key
        self._attr_entity_registry_enabled_default = description.enabled_default

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.values.get(self._description.data_key) == 1

    async def async_turn_on(self, **kwargs: object) -> None:
        validator = (
            self.coordinator.validate_control_mode_change
            if self._description.data_key == "control_mode"
            else self.coordinator.validate_mode_change
        )
        await self.async_write_parameter(
            self._description.cell,
            1,
            validator,
            lambda: self.coordinator.data.values.get(self._description.data_key) == 1,
        )

    async def async_turn_off(self, **kwargs: object) -> None:
        validator = (
            self.coordinator.validate_control_mode_change
            if self._description.data_key == "control_mode"
            else self.coordinator.validate_mode_change
        )
        await self.async_write_parameter(
            self._description.cell,
            0,
            validator,
            lambda: self.coordinator.data.values.get(self._description.data_key) == 0,
        )
