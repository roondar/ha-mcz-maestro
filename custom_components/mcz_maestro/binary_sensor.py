"""Binary sensor platform for MCZ Maestro."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ALARM_STATES,
    DOMAIN,
    TEMPERATURE_STATUS_DISCONNECTED,
    TEMPERATURE_STATUS_FAULT,
)
from .coordinator import MaestroCoordinator
from .entity import MaestroEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: MaestroCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            MaestroConnectionBinarySensor(coordinator, entry),
            MaestroAlarmBinarySensor(coordinator, entry),
            MaestroProbeBinarySensor(coordinator, entry),
        ]
    )


class MaestroConnectionBinarySensor(MaestroEntity, BinarySensorEntity):
    """Expose coordinator freshness even while other entities are unavailable."""

    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: MaestroCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "connection")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


class MaestroAlarmBinarySensor(MaestroEntity, BinarySensorEntity):
    """Report stove alarm states."""

    _attr_translation_key = "alarm"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: MaestroCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "alarm")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.values.get("stove_state") in ALARM_STATES


class MaestroProbeBinarySensor(MaestroEntity, BinarySensorEntity):
    """Report an absent or failed ambient probe."""

    _attr_translation_key = "ambient_probe_problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: MaestroCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "ambient_probe_problem")

    @property
    def is_on(self) -> bool:
        status = self.coordinator.data.temperature_statuses.get(
            "ambient_temperature"
        )
        return status in {
            TEMPERATURE_STATUS_FAULT,
            TEMPERATURE_STATUS_DISCONNECTED,
        }

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        return {
            "maestro_status": self.coordinator.data.temperature_statuses.get(
                "ambient_temperature"
            )
        }
