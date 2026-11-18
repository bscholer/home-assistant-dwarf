"""Config flow: a relay host, port, and token."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RelayClient, RelayError, RelayUnauthorized, RelayUnreachable
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    SUPPORTED_SPEC_MAJOR,
)
from .coordinator import Dwarf3ConfigEntry


class Dwarf3ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _check(self, host: str, port: int, token: str | None) -> str | None:
        """Return an error key, or None when the relay is usable."""
        client = RelayClient(async_get_clientsession(self.hass), host, port, token)
        try:
            caps = await client.capabilities()
            if str(caps.get("spec_version", "")).split(".")[0] != str(SUPPORTED_SPEC_MAJOR):
                return "unsupported_version"
            if "status" not in caps.get("capabilities", []):
                return "unsupported_version"
            await client.check_token()
        except RelayUnauthorized:
            return "invalid_auth"
        except RelayUnreachable:
            return "cannot_connect"
        except RelayError:
            return "unknown"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host, port = user_input[CONF_HOST].strip(), user_input[CONF_PORT]
            token = user_input.get(CONF_TOKEN) or None
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()
            if error := await self._check(host, port, token):
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=f"DWARF 3 ({host})", data={CONF_HOST: host, CONF_PORT: port, CONF_TOKEN: token}
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, vol.UNDEFINED)): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_TOKEN): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN]
            if error := await self._check(entry.data[CONF_HOST], entry.data[CONF_PORT], token):
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: token})
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Dwarf3ConfigEntry) -> OptionsFlow:
        return Dwarf3OptionsFlow()


class Dwarf3OptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        schema = vol.Schema(
            {vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL))}
        )
        return self.async_show_form(step_id="init", data_schema=schema)
