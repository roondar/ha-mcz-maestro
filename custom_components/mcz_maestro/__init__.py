"""MCZ Maestro local integration with one selectable transport."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MaestroClient
from .cloud import MaestroCloudClient
from .const import (
    CONF_CLOUD_HOST,
    CONF_CLOUD_MAC,
    CONF_CLOUD_PORT,
    CONF_CLOUD_SERIAL,
    CONF_DEFAULT_CLOUD_HOST,
    CONF_DEFAULT_CLOUD_PORT,
    CONF_DIRECT_HOST,
    CONF_DIRECT_PORT,
    CONF_TRANSPORT,
    DOMAIN,
    PLATFORMS,
    TRANSPORT_CLOUD,
    TRANSPORT_DIRECT,
)
from .coordinator import MaestroCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up only the transport selected by this existing config entry."""
    options = entry.options
    transport = options.get(CONF_TRANSPORT, TRANSPORT_DIRECT)
    if transport == TRANSPORT_CLOUD:
        client = MaestroCloudClient(
            options.get(CONF_CLOUD_HOST, CONF_DEFAULT_CLOUD_HOST),
            options.get(CONF_CLOUD_PORT, CONF_DEFAULT_CLOUD_PORT),
            options[CONF_CLOUD_SERIAL],
            options[CONF_CLOUD_MAC],
        )
    elif transport == TRANSPORT_DIRECT:
        client = MaestroClient(
            async_get_clientsession(hass),
            options.get(CONF_DIRECT_HOST, entry.data[CONF_HOST]),
            options.get(CONF_DIRECT_PORT, entry.data[CONF_PORT]),
        )
    else:
        raise ValueError("Unknown MCZ transport")

    try:
        parameters = await client.async_request_parameters()
        coordinator = MaestroCoordinator(hass, client, parameters)
        await coordinator.async_config_entry_first_refresh()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await client.async_close()
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the old client completely before a mode-switch reload."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    coordinator: MaestroCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.client.async_close()
    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)
    return True
