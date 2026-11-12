"""MCZ Maestro local integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MaestroClient
from .const import (
    CONF_CONNECTION_TYPE,
    CONF_RELAY_HOST,
    CONF_RELAY_MAC,
    CONF_RELAY_PORT,
    CONF_RELAY_SERIAL,
    CONNECTION_DIRECT,
    CONNECTION_RELAY,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import MaestroCoordinator
from .relay_api import MaestroRelayClient


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MCZ Maestro from a config entry."""
    transport = entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_DIRECT)
    if transport == CONNECTION_RELAY:
        client = MaestroRelayClient(
            entry.data[CONF_RELAY_HOST],
            entry.data[CONF_RELAY_PORT],
            entry.data[CONF_RELAY_SERIAL],
            entry.data[CONF_RELAY_MAC],
        )
    elif transport == CONNECTION_DIRECT:
        client = MaestroClient(
            async_get_clientsession(hass),
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
        )
    else:
        raise ValueError("Unknown MCZ transport")

    parameters = await client.async_request_parameters()
    coordinator = MaestroCoordinator(hass, client, parameters)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an MCZ Maestro config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    coordinator: MaestroCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.client.async_close()
    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)
    return True
