"""Config flow: a relay host, port, and token."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components import network
from homeassistant.config_entries import SOURCE_RECONFIGURE, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .api import RelayClient, RelayError, RelayUnauthorized, RelayUnreachable
from .const import (
    CONF_MODE,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DIRECT_DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    MODE_DIRECT,
    MODE_RELAY,
    SUPPORTED_SPEC_MAJOR,
)
from .coordinator import Dwarf3ConfigEntry
from .direct import ScopeDirectClient, ScopeUnreachable


class Dwarf3ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._scope_host: str | None = None  # a scope found by DHCP, or the one a read-only entry was using
        self._relay: dict[str, Any] | None = None  # a relay found on this Home Assistant

    # ---- helpers

    async def _local_ip(self) -> str | None:
        """This Home Assistant's own address. The relay app runs on the same host."""
        try:
            return await network.async_get_source_ip(self.hass)
        except Exception:  # noqa: BLE001
            return None

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

    async def _check_scope(self, host: str) -> str | None:
        try:
            info = await ScopeDirectClient(async_get_clientsession(self.hass), host).device_info()
        except ScopeUnreachable:
            return "cannot_connect"
        return None if "sdCardInfo" in info else "not_a_scope"

    async def _finish(self, *, data: dict[str, Any], unique_id: str, title: str) -> ConfigFlowResult:
        """Create the entry, or on reconfigure change the existing one in place.

        An entry keeps its id when its mode changes, so entity ids and dashboards survive a switch.
        """
        if self.source == SOURCE_RECONFIGURE:
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(), unique_id=unique_id, title=title, data=data
            )
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=title, data=data)

    def _previous_scope_host(self) -> str:
        """The scope's address, for the text that tells people what to enter in the app."""
        if self._scope_host:
            return self._scope_host
        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            if entry.data.get(CONF_MODE) == MODE_DIRECT:
                return entry.data[CONF_HOST]
        return "your scope's IP address"

    # ---- first setup

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=[MODE_DIRECT, MODE_RELAY])

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """The scope showed up on the network. Only offer it when it answers like a DWARF 3."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")  # one scope is the usual case
        if await self._check_scope(discovery_info.ip):
            return self.async_abort(reason="not_a_scope")
        self._scope_host = discovery_info.ip
        await self.async_set_unique_id(f"direct:{discovery_info.ip}")
        self._abort_if_unique_id_configured()
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._scope_host
        if user_input is not None:
            return await self._finish(
                data={CONF_HOST: self._scope_host, CONF_MODE: MODE_DIRECT},
                unique_id=f"direct:{self._scope_host}",
                title="DWARF 3",
            )
        self.context["title_placeholders"] = {"host": self._scope_host}
        self._set_confirm_only()
        return self.async_show_form(step_id="discovery_confirm", description_placeholders={"host": self._scope_host})

    async def async_step_direct(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Read-only, straight from the scope. It never touches the scope's one control connection."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if error := await self._check_scope(host):
                errors["base"] = error
            else:
                return await self._finish(
                    data={CONF_HOST: host, CONF_MODE: MODE_DIRECT}, unique_id=f"direct:{host}", title="DWARF 3"
                )
        default = (user_input or {}).get(CONF_HOST) or self._scope_host or vol.UNDEFINED
        if self.source == SOURCE_RECONFIGURE and default is vol.UNDEFINED:
            entry = self._get_reconfigure_entry()
            default = entry.data[CONF_HOST] if entry.data.get(CONF_MODE) == MODE_DIRECT else vol.UNDEFINED
        schema = vol.Schema({vol.Required(CONF_HOST, default=default): str})
        return self.async_show_form(step_id="direct", data_schema=schema, errors=errors)

    async def async_step_relay(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Full control, through the relay. Look for it on this Home Assistant first, so it is one click."""
        local = await self._local_ip()
        errors: dict[str, str] = {}
        if user_input is None and local:
            if await self._check(local, DEFAULT_PORT, None) is None:
                self._relay = {CONF_HOST: local, CONF_PORT: DEFAULT_PORT, CONF_TOKEN: None, CONF_MODE: MODE_RELAY}
                return await self.async_step_relay_found()
        if user_input is not None:
            host, port = user_input[CONF_HOST].strip(), user_input[CONF_PORT]
            token = user_input.get(CONF_TOKEN) or None
            if error := await self._check(host, port, token):
                errors["base"] = error
            else:
                return await self._finish(
                    data={CONF_HOST: host, CONF_PORT: port, CONF_TOKEN: token, CONF_MODE: MODE_RELAY},
                    unique_id=f"{host}:{port}",
                    title=f"DWARF 3 relay ({host})",
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST) or local or vol.UNDEFINED): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_TOKEN): str,
            }
        )
        return self.async_show_form(
            step_id="relay",
            data_schema=schema,
            errors=errors,
            description_placeholders={"scope": self._previous_scope_host()},
        )

    async def async_step_relay_found(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._relay
        if user_input is not None:
            host, port = self._relay[CONF_HOST], self._relay[CONF_PORT]
            return await self._finish(data=self._relay, unique_id=f"{host}:{port}", title=f"DWARF 3 relay ({host})")
        self._set_confirm_only()
        return self.async_show_form(step_id="relay_found", description_placeholders={"host": self._relay[CONF_HOST]})

    # ---- change an existing entry

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Switch between read-only and the relay, or change an address. The entry keeps its entity ids."""
        mode = self._get_reconfigure_entry().data.get(CONF_MODE, MODE_RELAY)
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=[MODE_RELAY, MODE_DIRECT],
            description_placeholders={"current": "read-only" if mode == MODE_DIRECT else "full control"},
        )

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
        default = (
            DIRECT_DEFAULT_SCAN_INTERVAL
            if self.config_entry.data.get(CONF_MODE, MODE_RELAY) == MODE_DIRECT
            else DEFAULT_SCAN_INTERVAL
        )
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, default)
        schema = vol.Schema(
            {vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL))}
        )
        return self.async_show_form(step_id="init", data_schema=schema)
