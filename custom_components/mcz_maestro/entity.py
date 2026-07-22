"""Shared MCZ Maestro entity helpers."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MaestroCoordinator


class MaestroEntity(CoordinatorEntity[MaestroCoordinator]):
    """Base entity for one MCZ Maestro stove."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MaestroCoordinator,
        entry: ConfigEntry,
        entity_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_{entity_key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the common stove device information."""
        data = self.coordinator.data
        firmware = data.values.get("firmware_version") if data else None
        database = data.values.get("database_id") if data else None
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.unique_id or self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="MCZ",
            model="Dynamic (Maestro)",
            sw_version=str(firmware) if firmware is not None else None,
            hw_version=f"Database {database}" if database is not None else None,
        )

    async def async_write_parameter(
        self,
        cell: int,
        value: int,
        validator: Callable[[], None],
        confirmation: Callable[[], bool],
    ) -> None:
        """Write a parameter and refresh the state after the stove applies it."""
        await self.coordinator.async_execute_parameter(
            cell, value, validator, confirmation
        )
