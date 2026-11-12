"""Configuration and reconfiguration of the two MCZ connection transports.

Reconfigure the SAME entry instead of adding a second stove. Its unique_id
(and therefore every entity_id, dashboard and automation) is preserved.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MaestroClient, MaestroConnectionError, MaestroProtocolError
from .const import (
    CONF_CONNECTION_TYPE,
    CONF_DEFAULT_HOST,
    CONF_DEFAULT_PORT,
    CONF_RELAY_HOST,
    CONF_RELAY_MAC,
    CONF_RELAY_PORT,
    CONF_RELAY_SERIAL,
    CONNECTION_DIRECT,
    CONNECTION_RELAY,
    DEFAULT_NAME,
    DEFAULT_RELAY_PORT,
    DOMAIN,
)
from .relay_api import MaestroRelayClient


class MczMaestroConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up or switch one existing stove between two exclusive transports."""

    VERSION = 1

    def __init__(self) -> None:
        self._selected_transport = CONNECTION_DIRECT

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a mode for a new integration entry."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        return await self._async_select_transport("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Switch transport while keeping the current entry and entity IDs."""
        return await self._async_select_transport("reconfigure", user_input)

    async def _async_select_transport(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._selected_transport = user_input[CONF_CONNECTION_TYPE]
            if self._selected_transport == CONNECTION_DIRECT:
                return await self.async_step_direct()
            return await self.async_step_relay()

        active = CONNECTION_DIRECT
        if self.source == SOURCE_RECONFIGURE:
            active = self._get_reconfigure_entry().data.get(
                CONF_CONNECTION_TYPE, CONNECTION_DIRECT
            )
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CONNECTION_TYPE, default=active): vol.In(
                        {
                            CONNECTION_DIRECT: "Direct (Maestro WebSocket)",
                            CONNECTION_RELAY: "MCZ Cloud Local (Socket.IO)",
                        }
                    )
                }
            ),
        )

    async def async_step_direct(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate direct 192.168.120.1:81-style Maestro WebSocket."""
        errors: dict[str, str] = {}
        entry_data = (
            self._get_reconfigure_entry().data
            if self.source == SOURCE_RECONFIGURE
            else {}
        )
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            client = MaestroClient(async_get_clientsession(self.hass), host, port)
            errors = await self._async_check_client(client)
            if not errors:
                updates = {
                    CONF_CONNECTION_TYPE: CONNECTION_DIRECT,
                    CONF_HOST: host,
                    CONF_PORT: port,
                }
                return await self._async_finish(updates, f"{host}:{port}")

        return self.async_show_form(
            step_id="direct",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=entry_data.get(CONF_HOST, CONF_DEFAULT_HOST),
                    ): str,
                    vol.Required(
                        CONF_PORT,
                        default=entry_data.get(CONF_PORT, CONF_DEFAULT_PORT),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                }
            ),
            errors=errors,
        )

    async def async_step_relay(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate local MCZ Socket.IO relay with Android-App identity."""
        errors: dict[str, str] = {}
        entry_data = (
            self._get_reconfigure_entry().data
            if self.source == SOURCE_RECONFIGURE
            else {}
        )
        if user_input is not None:
            host = user_input[CONF_RELAY_HOST].strip()
            port = user_input[CONF_RELAY_PORT]
            serial = user_input[CONF_RELAY_SERIAL].strip()
            mac = user_input[CONF_RELAY_MAC].strip()
            if not (host and serial and mac):
                errors["base"] = "invalid_identity"
            else:
                client = MaestroRelayClient(host, port, serial, mac)
                errors = await self._async_check_client(client)
                if not errors:
                    updates = {
                        CONF_CONNECTION_TYPE: CONNECTION_RELAY,
                        CONF_RELAY_HOST: host,
                        CONF_RELAY_PORT: port,
                        CONF_RELAY_SERIAL: serial,
                        CONF_RELAY_MAC: mac,
                    }
                    if self.source != SOURCE_RECONFIGURE:
                        # Keep sensible direct settings for a future mode switch.
                        updates[CONF_HOST] = CONF_DEFAULT_HOST
                        updates[CONF_PORT] = CONF_DEFAULT_PORT
                    return await self._async_finish(
                        updates, f"relay:{serial}:{mac}"
                    )

        return self.async_show_form(
            step_id="relay",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_RELAY_HOST,
                        default=entry_data.get(CONF_RELAY_HOST, ""),
                    ): str,
                    vol.Required(
                        CONF_RELAY_PORT,
                        default=entry_data.get(
                            CONF_RELAY_PORT, DEFAULT_RELAY_PORT
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                    vol.Required(
                        CONF_RELAY_SERIAL,
                        default=entry_data.get(CONF_RELAY_SERIAL, ""),
                    ): str,
                    vol.Required(
                        CONF_RELAY_MAC,
                        default=entry_data.get(CONF_RELAY_MAC, ""),
                    ): str,
                }
            ),
            errors=errors,
        )

    async def _async_check_client(
        self, client: MaestroClient | MaestroRelayClient
    ) -> dict[str, str]:
        try:
            await client.async_request_parameters()
            await client.async_request_info()
            return {}
        except MaestroConnectionError:
            return {"base": "cannot_connect"}
        except MaestroProtocolError:
            return {"base": "invalid_response"}
        finally:
            await client.async_close()

    async def _async_finish(
        self, updates: dict[str, Any], new_unique_id: str
    ) -> ConfigFlowResult:
        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            # The physical stove did not change: NEVER rename registry IDs.
            await self.async_set_unique_id(entry.unique_id)
            self._abort_if_unique_id_mismatch()
            return self.async_update_reload_and_abort(
                entry, data_updates=updates
            )
        await self.async_set_unique_id(new_unique_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=DEFAULT_NAME, data=updates)
