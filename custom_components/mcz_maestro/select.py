"""Select platform for MCZ Maestro."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CELL_FAN_DUCTED_1,
    CELL_FAN_DUCTED_2,
    CELL_FAN_FRONT,
    CELL_POWER_LEVEL,
    DOMAIN,
)
from .coordinator import MaestroCoordinator
from .entity import MaestroEntity

POWER_OPTIONS = ["power_1", "power_2", "power_3", "power_4", "power_5"]
FAN_OPTIONS = ["off", "level_1", "level_2", "level_3", "level_4", "level_5", "auto"]


@dataclass(frozen=True, kw_only=True)
class MaestroSelectDescription:
    key: str
    translation_key: str
    data_key: str
    cell: int
    options: list[str]
    power_level: bool = False


SELECTS = (
    MaestroSelectDescription(
        key="power_level",
        translation_key="power_level",
        data_key="power_level",
        cell=CELL_POWER_LEVEL,
        options=POWER_OPTIONS,
        power_level=True,
    ),
    MaestroSelectDescription(
        key="fan_front",
        translation_key="fan_front",
        data_key="fan_front",
        cell=CELL_FAN_FRONT,
        options=FAN_OPTIONS,
    ),
    MaestroSelectDescription(
        key="fan_ducted_1",
        translation_key="fan_ducted_1",
        data_key="fan_ducted_1",
        cell=CELL_FAN_DUCTED_1,
        options=FAN_OPTIONS,
    ),
    MaestroSelectDescription(
        key="fan_ducted_2",
        translation_key="fan_ducted_2",
        data_key="fan_ducted_2",
        cell=CELL_FAN_DUCTED_2,
        options=FAN_OPTIONS,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: MaestroCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[MaestroSelect] = []
    fan_keys = ("fan_front", "fan_ducted_1", "fan_ducted_2")
    for description in SELECTS:
        if not description.power_level:
            fan_index = fan_keys.index(description.data_key)
            if not (
                coordinator.parameters.fan_present[fan_index]
                and coordinator.parameters.fan_enabled[fan_index]
            ):
                continue
        entities.append(MaestroSelect(coordinator, entry, description))
    async_add_entities(entities)


class MaestroSelect(MaestroEntity, SelectEntity):
    """Represent a selectable Maestro parameter."""

    def __init__(
        self,
        coordinator: MaestroCoordinator,
        entry: ConfigEntry,
        description: MaestroSelectDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self._description = description
        self._attr_translation_key = description.translation_key
        if description.power_level:
            self._attr_options = [
                f"power_{level}"
                for level in range(
                    coordinator.parameters.power_min,
                    coordinator.parameters.power_max + 1,
                )
            ]
        else:
            fan_keys = ("fan_front", "fan_ducted_1", "fan_ducted_2")
            fan_index = fan_keys.index(description.data_key)
            options: list[str] = []
            if coordinator.parameters.fan_supports_off[fan_index]:
                options.append("off")
            options.extend(
                f"level_{level}"
                for level in range(
                    coordinator.parameters.fan_min[fan_index],
                    coordinator.parameters.fan_max[fan_index] + 1,
                )
            )
            if coordinator.parameters.fan_supports_auto[fan_index]:
                options.append("auto")
            self._attr_options = options

    @property
    def current_option(self) -> str | None:
        description = self._description
        raw_value = self.coordinator.data.values.get(description.data_key)
        if not isinstance(raw_value, int):
            return None
        if description.power_level:
            level = raw_value - 10 if 11 <= raw_value <= 15 else raw_value
            return f"power_{level}" if 1 <= level <= 5 else None
        if raw_value == 0:
            return "off"
        if raw_value == 6:
            return "auto"
        return f"level_{raw_value}" if 1 <= raw_value <= 5 else None

    async def async_select_option(self, option: str) -> None:
        description = self._description
        if description.power_level:
            value = int(option.removeprefix("power_"))
            validator = lambda: self.coordinator.validate_power_level(value)
        elif option == "off":
            value = 0
            validator = lambda: self.coordinator.validate_fan_speed(
                description.data_key, value
            )
        elif option == "auto":
            value = 6
            validator = lambda: self.coordinator.validate_fan_speed(
                description.data_key, value
            )
        else:
            value = int(option.removeprefix("level_"))
            validator = lambda: self.coordinator.validate_fan_speed(
                description.data_key, value
            )
        await self.async_write_parameter(
            description.cell,
            value,
            validator,
            (
                (lambda: self.coordinator.current_power_level == value)
                if description.power_level
                else lambda: self.coordinator.data.values.get(description.data_key)
                == value
            ),
        )

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        return {
            "maximum_safe_power": self.coordinator.maximum_safe_power(),
            "fan_safety_coefficient": self.coordinator.parameters.fan_coefficient,
        }
