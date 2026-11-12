"""Config flow and in-place transport selection for MCZ Maestro."""

from __future__ import annotations

import re
from typing import Any

try:
    from homeassistant.data_entry_flow import probatio as vol
except ImportError:  # Home Assistant versions before the schema migration.
    import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MaestroClient, MaestroConnectionError, MaestroProtocolError
from .const import (
    CONF_CLOUD_HOST,
    CONF_CLOUD_MAC,
    CONF_CLOUD_PORT,
    CONF_CLOUD_SERIAL,
    CONF_DEFAULT_CLOUD_HOST,
    CONF_DEFAULT_CLOUD_PORT,
    CONF_DEFAULT_HOST,
    CONF_DEFAULT_PORT,
    CONF_DIRECT_HOST,
    CONF_DIRECT_PORT,
    CONF_TRANSPORT,
    DEFAULT_NAME,
    DOMAIN,
    TRANSPORT_CLOUD,
    TRANSPORT_DIRECT,
)

_HOST_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_SERIAL_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MAC_PATTERN = re.compile(
    r"^(?:[0-9a-f]{12}|[0-9a-f]{2}(?:[:-][0-9a-f]{2}){5})$",
    re.IGNORECASE,
)


class MczMaestroConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a new, backward-compatible direct connection."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> MczMaestroOptionsFlow:
        """Edit the current config entry, never create a second stove."""
        return MczMaestroOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a native Maestro WebSocket connection."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            client = MaestroClient(async_get_clientsession(self.hass), host, port)
            try:
                await client.async_request_parameters()
                await client.async_request_info()
            except MaestroConnectionError:
                errors["base"] = "cannot_connect"
            except MaestroProtocolError:
                errors["base"] = "invalid_response"
            else:
                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data={CONF_HOST: host, CONF_PORT: port},
                )
            finally:
                await client.async_close()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=(
                        user_input[CONF_HOST]
                        if user_input is not None
                        else CONF_DEFAULT_HOST
                    ),
                ): str,
                vol.Required(
                    CONF_PORT,
                    default=(
                        user_input[CONF_PORT]
                        if user_input is not None
                        else CONF_DEFAULT_PORT
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )


class MczMaestroOptionsFlow(OptionsFlowWithReload):
    """Switch transports by reloading the SAME entry after the old one unloads."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the transport. No second HA client is connected here."""
        if user_input is not None:
            if user_input[CONF_TRANSPORT] == TRANSPORT_CLOUD:
                return await self.async_step_cloud()
            return await self.async_step_direct()
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TRANSPORT,
                        default=self.config_entry.options.get(
                            CONF_TRANSPORT, TRANSPORT_DIRECT
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[TRANSPORT_DIRECT, TRANSPORT_CLOUD],
                            translation_key="transport",
                        )
                    ),
                }
            ),
        )

    async def async_step_direct(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Save direct settings without touching stored cloud credentials."""
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_DIRECT_HOST].strip()
            if not _HOST_PATTERN.fullmatch(host):
                errors["base"] = "invalid_host"
            else:
                return self.async_create_entry(
                    data={
                        **entry.options,
                        CONF_TRANSPORT: TRANSPORT_DIRECT,
                        CONF_DIRECT_HOST: host,
                        CONF_DIRECT_PORT: user_input[CONF_DIRECT_PORT],
                    }
                )

        return self.async_show_form(
            step_id="direct",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DIRECT_HOST,
                        default=(
                            user_input[CONF_DIRECT_HOST]
                            if user_input is not None
                            else entry.options.get(
                                CONF_DIRECT_HOST, entry.data[CONF_HOST]
                            )
                        ),
                    ): str,
                    vol.Required(
                        CONF_DIRECT_PORT,
                        default=(
                            user_input[CONF_DIRECT_PORT]
                            if user_input is not None
                            else entry.options.get(
                                CONF_DIRECT_PORT, entry.data[CONF_PORT]
                            )
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                }
            ),
            errors=errors,
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Save cloud settings; blank password fields retain saved credentials.

        Connection and full read validation happen during the exclusive reload:
        probing here would open a second client while the first one is active.
        """
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_CLOUD_HOST].strip()
            serial = (
                user_input.get(CONF_CLOUD_SERIAL, "").strip()
                or entry.options.get(CONF_CLOUD_SERIAL, "")
            )
            mac = (
                user_input.get(CONF_CLOUD_MAC, "").strip()
                or entry.options.get(CONF_CLOUD_MAC, "")
            )
            if not _HOST_PATTERN.fullmatch(host):
                errors["base"] = "invalid_host"
            elif not serial or not mac:
                errors["base"] = "missing_identity"
            elif (
                not _SERIAL_PATTERN.fullmatch(serial)
                or not _MAC_PATTERN.fullmatch(mac)
            ):
                errors["base"] = "invalid_identity"
            else:
                return self.async_create_entry(
                    data={
                        **entry.options,
                        CONF_TRANSPORT: TRANSPORT_CLOUD,
                        CONF_CLOUD_HOST: host,
                        CONF_CLOUD_PORT: user_input[CONF_CLOUD_PORT],
                        CONF_CLOUD_SERIAL: serial,
                        CONF_CLOUD_MAC: mac,
                    }
                )

        password = selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        )
        return self.async_show_form(
            step_id="cloud",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CLOUD_HOST,
                        default=(
                            user_input[CONF_CLOUD_HOST]
                            if user_input is not None
                            else entry.options.get(
                                CONF_CLOUD_HOST, CONF_DEFAULT_CLOUD_HOST
                            )
                        ),
                    ): str,
                    vol.Required(
                        CONF_CLOUD_PORT,
                        default=(
                            user_input[CONF_CLOUD_PORT]
                            if user_input is not None
                            else entry.options.get(
                                CONF_CLOUD_PORT, CONF_DEFAULT_CLOUD_PORT
                            )
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                    vol.Optional(CONF_CLOUD_SERIAL): password,
                    vol.Optional(CONF_CLOUD_MAC): password,
                }
            ),
            errors=errors,
        )
