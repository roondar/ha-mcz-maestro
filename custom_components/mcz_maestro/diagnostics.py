"""Diagnostics support for MCZ Maestro."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CLOUD_HOST,
    CONF_CLOUD_PORT,
    CONF_DEFAULT_CLOUD_HOST,
    CONF_DEFAULT_CLOUD_PORT,
    CONF_DIRECT_HOST,
    CONF_DIRECT_PORT,
    CONF_TRANSPORT,
    DOMAIN,
    TRANSPORT_CLOUD,
    TRANSPORT_DIRECT,
)
from .coordinator import MaestroCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return protocol state without credentials or command history."""
    coordinator: MaestroCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data
    transport = entry.options.get(CONF_TRANSPORT, TRANSPORT_DIRECT)
    host = (
        entry.options.get(CONF_CLOUD_HOST, CONF_DEFAULT_CLOUD_HOST)
        if transport == TRANSPORT_CLOUD
        else entry.options.get(CONF_DIRECT_HOST, entry.data["host"])
    )
    port = (
        entry.options.get(CONF_CLOUD_PORT, CONF_DEFAULT_CLOUD_PORT)
        if transport == TRANSPORT_CLOUD
        else entry.options.get(CONF_DIRECT_PORT, entry.data["port"])
    )
    return {
        "entry": {
            "title": entry.title,
            "transport": transport,
            "host": host,
            "port": port,
        },
        "connected": coordinator.client.connected,
        "last_update_success": coordinator.last_update_success,
        "values": data.values,
        "temperature_statuses": data.temperature_statuses,
        "safety": {
            "target_temperature_min": coordinator.parameters.target_temperature_min,
            "target_temperature_max": coordinator.parameters.target_temperature_max,
            "fan_coefficient": coordinator.parameters.fan_coefficient,
            "fan_present": coordinator.parameters.fan_present,
            "maximum_safe_power": coordinator.maximum_safe_power(),
        },
    }
