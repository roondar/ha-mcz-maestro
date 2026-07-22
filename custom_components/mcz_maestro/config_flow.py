"""Config flow for MCZ Maestro."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MaestroClient, MaestroConnectionError, MaestroProtocolError
from .const import CONF_DEFAULT_HOST, CONF_DEFAULT_PORT, DEFAULT_NAME, DOMAIN


class MczMaestroConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle an MCZ Maestro config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a local MCZ Maestro module."""
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
