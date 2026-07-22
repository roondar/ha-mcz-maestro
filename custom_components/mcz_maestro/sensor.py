"""Sensor platform for MCZ Maestro."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, STOVE_STATES
from .coordinator import MaestroCoordinator
from .entity import MaestroEntity


@dataclass(frozen=True, kw_only=True)
class MaestroSensorDescription:
    key: str
    translation_key: str
    data_key: str
    device_class: SensorDeviceClass | None = None
    native_unit: str | None = None
    state_class: SensorStateClass | None = None


SENSORS = (
    MaestroSensorDescription(
        key="stove_state", translation_key="stove_state", data_key="stove_state"
    ),
    MaestroSensorDescription(
        key="ambient_temperature",
        translation_key="ambient_temperature",
        data_key="ambient_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MaestroSensorDescription(
        key="fume_temperature",
        translation_key="fume_temperature",
        data_key="fume_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MaestroSensorDescription(
        key="motherboard_temperature",
        translation_key="motherboard_temperature",
        data_key="motherboard_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    MaestroSensorDescription(
        key="total_operating_hours",
        translation_key="total_operating_hours",
        data_key="total_operating_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    MaestroSensorDescription(
        key="hours_to_service",
        translation_key="hours_to_service",
        data_key="hours_to_service",
        device_class=SensorDeviceClass.DURATION,
        native_unit=UnitOfTime.HOURS,
    ),
    MaestroSensorDescription(
        key="number_of_ignitions",
        translation_key="number_of_ignitions",
        data_key="number_of_ignitions",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: MaestroCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MaestroSensor(coordinator, entry, description) for description in SENSORS
    )


class MaestroSensor(MaestroEntity, SensorEntity):
    """Represent one decoded Maestro value."""

    def __init__(
        self,
        coordinator: MaestroCoordinator,
        entry: ConfigEntry,
        description: MaestroSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self._description = description
        self._attr_translation_key = description.translation_key
        self._attr_device_class = description.device_class
        self._attr_native_unit_of_measurement = description.native_unit
        self._attr_state_class = description.state_class

    @property
    def native_value(self) -> Any:
        value = self.coordinator.data.values.get(self._description.data_key)
        if self._description.data_key == "stove_state":
            return STOVE_STATES.get(value, f"État inconnu ({value})")
        return value
