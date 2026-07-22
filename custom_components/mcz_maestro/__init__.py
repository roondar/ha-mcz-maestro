"""MCZ Maestro local integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MaestroClient
from .const import DOMAIN, PLATFORMS
from .coordinator import MaestroCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MCZ Maestro from a config entry."""
    client = MaestroClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
    )
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
