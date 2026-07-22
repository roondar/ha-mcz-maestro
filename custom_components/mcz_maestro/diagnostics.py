"""Diagnostics support for MCZ Maestro."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import MaestroCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return protocol state without credentials or command history."""
    coordinator: MaestroCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data
    return {
        "entry": {
            "title": entry.title,
            "host": entry.data["host"],
            "port": entry.data["port"],
        },
        "connected": coordinator.client.connected,
        "last_update_success": coordinator.last_update_success,
        "values": data.values,
        "raw": data.raw,
        "temperature_statuses": data.temperature_statuses,
        "safety": {
            "target_temperature_min": coordinator.parameters.target_temperature_min,
            "target_temperature_max": coordinator.parameters.target_temperature_max,
            "fan_coefficient": coordinator.parameters.fan_coefficient,
            "fan_present": coordinator.parameters.fan_present,
            "maximum_safe_power": coordinator.maximum_safe_power(),
        },
    }
