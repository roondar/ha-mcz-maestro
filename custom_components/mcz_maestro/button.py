"""Button platform for MCZ Maestro."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
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
            MaestroRefreshButton(coordinator, entry),
            MaestroSyncTimeButton(coordinator, entry),
        ]
    )


class MaestroRefreshButton(MaestroEntity, ButtonEntity):
    """Request an immediate information frame."""

    _attr_translation_key = "refresh"

    def __init__(self, coordinator: MaestroCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "refresh")

    async def async_press(self) -> None:
        # An explicit button press must not be delayed by the coordinator debouncer.
        await self.coordinator.async_refresh()


class MaestroSyncTimeButton(MaestroEntity, ButtonEntity):
    """Synchronize the stove clock with Home Assistant."""

    _attr_translation_key = "sync_time"

    def __init__(self, coordinator: MaestroCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "sync_time")

    async def async_press(self) -> None:
        await self.coordinator.async_execute_datetime()
