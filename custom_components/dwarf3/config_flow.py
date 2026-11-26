"""Config flow: a relay host, port, and token."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components import network
from homeassistant.config_entries import SOURCE_RECONFIGURE, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from . import app_setup
from .api import RelayClient, RelayError, RelayUnauthorized, RelayUnreachable
from .app_setup import AppSetupError
from .const import (
    CONF_MAC,
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
        self._mac: str | None = None  # the MAC of a scope found by DHCP
        self._relay: dict[str, Any] | None = None  # a relay found on this Home Assistant
        self._install_task: asyncio.Task[None] | None = None
        self._install_error = ""

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
            entry = self._get_reconfigure_entry()
            if (
                data.get(CONF_MODE) == MODE_DIRECT
                and entry.data.get(CONF_MODE) == MODE_DIRECT
                and entry.data.get(CONF_MAC)
                and entry.data[CONF_HOST] == data[CONF_HOST]
            ):
                # Same scope, same address: keep the MAC we learned and the identity built on it.
                data, unique_id = {**data, CONF_MAC: entry.data[CONF_MAC]}, entry.unique_id or unique_id
            other = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, unique_id)
            if other is not None and other.entry_id != entry.entry_id:
                return self.async_abort(reason="already_configured")  # another entry already is this scope or relay
            for other in self.hass.config_entries.async_entries(DOMAIN):
                if other.entry_id != entry.entry_id and all(
                    other.data.get(k) == data.get(k) for k in (CONF_HOST, CONF_PORT, CONF_MODE)
                ):
                    return self.async_abort(reason="already_configured")  # same address, whatever its identity
            return self.async_update_reload_and_abort(entry, unique_id=unique_id, title=title, data=data)
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        # A scope added by hand has no MAC to match on, so also compare the address.
        self._async_abort_entries_match({k: data[k] for k in (CONF_HOST, CONF_PORT, CONF_MODE) if k in data})
        return self.async_create_entry(title=title, data=data)

    def _known_scope_host(self) -> str | None:
        """The scope's address when something already told us: discovery, or the read-only entry being switched."""
        if self._scope_host:
            return self._scope_host
        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            if entry.data.get(CONF_MODE) == MODE_DIRECT:
                return entry.data[CONF_HOST]
        return None

    # ---- first setup

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=[MODE_DIRECT, MODE_RELAY])

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """The scope showed up on the network. Only offer it when it answers like a DWARF 3."""
        host, mac = discovery_info.ip, dr.format_mac(discovery_info.macaddress)
        for entry in self._async_current_entries():
            if entry.data.get(CONF_MODE) != MODE_DIRECT:
                continue
            known_mac = entry.data.get(CONF_MAC)
            # The same scope: found again by its MAC, or an entry added by hand at this very address, whose MAC we
            # now learn. Either way follow the address, so a new DHCP lease does not strand the entry.
            if known_mac == mac or (known_mac is None and entry.data[CONF_HOST] == host):
                if known_mac == mac and entry.data[CONF_HOST] == host:
                    return self.async_abort(reason="already_configured")  # nothing changed, so no probe
                if await self._check_scope(host):
                    return self.async_abort(reason="not_a_scope")
                taken = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, f"direct:{mac}")
                if taken is not None and taken.entry_id != entry.entry_id:
                    return self.async_abort(reason="already_configured")  # e.g. an ignored discovery of this scope
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=f"direct:{mac}",
                    data_updates={CONF_HOST: host, CONF_MAC: mac},
                    reason="already_configured",
                )
        if self._async_current_entries():
            # One scope is the usual case, and a relay entry already covers the scope it fronts, so stay quiet.
            return self.async_abort(reason="already_configured")
        if await self._check_scope(host):
            return self.async_abort(reason="not_a_scope")
        self._scope_host, self._mac = host, mac
        await self.async_set_unique_id(f"direct:{mac}")
        self._abort_if_unique_id_configured()
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """A scope was found. Offer read-only, or full control, which sets up the relay right from here."""
        assert self._scope_host
        self.context["title_placeholders"] = {"host": self._scope_host}
        return self.async_show_menu(
            step_id="discovery_confirm",
            menu_options=["discovery_readonly", "discovery_full"],
            description_placeholders={"host": self._scope_host},
        )

    async def async_step_discovery_readonly(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._scope_host
        data: dict[str, Any] = {CONF_HOST: self._scope_host, CONF_MODE: MODE_DIRECT}
        if self._mac:
            data[CONF_MAC] = self._mac
        return await self._finish(data=data, unique_id=f"direct:{self._mac or self._scope_host}", title="DWARF 3")

    async def async_step_discovery_full(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """They picked full control, and we know the scope's address, so there is nothing left to ask.

        Use a relay already on this Home Assistant, else install one, else (no Supervisor) ask for its address.
        """
        local = await self._local_ip()
        if local and await self._check(local, DEFAULT_PORT, None) is None:
            self._relay = {CONF_HOST: local, CONF_PORT: DEFAULT_PORT, CONF_TOKEN: None, CONF_MODE: MODE_RELAY}
            return await self.async_step_relay_ready()
        if local and app_setup.has_supervisor(self.hass):
            return await self.async_step_relay_install()
        return await self.async_step_relay_manual()

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
        """Full control, through the relay. Use one already on this Home Assistant, so it is one click."""
        local = await self._local_ip()
        if local and await self._check(local, DEFAULT_PORT, None) is None:
            self._relay = {CONF_HOST: local, CONF_PORT: DEFAULT_PORT, CONF_TOKEN: None, CONF_MODE: MODE_RELAY}
            return await self.async_step_relay_found()
        if local and app_setup.has_supervisor(self.hass):
            return self.async_show_menu(step_id="relay", menu_options=["relay_install", "relay_manual"])
        return await self.async_step_relay_manual()

    async def async_step_relay_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """A relay at an address the person types, for example one running in Docker elsewhere."""
        local = await self._local_ip()
        errors: dict[str, str] = {}
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
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(min=1, max=65535)),
                vol.Optional(CONF_TOKEN): str,
            }
        )
        return self.async_show_form(step_id="relay_manual", data_schema=schema, errors=errors)

    async def async_step_relay_install(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Install and set up the relay app for the person. Ask for the scope's address only if we do not know it."""
        errors: dict[str, str] = {}
        if self._known_scope_host() is None:
            if user_input is not None:
                host = user_input[CONF_HOST].strip()
                if error := await self._check_scope(host):
                    errors["base"] = error
                else:
                    self._scope_host = host
            if self._scope_host is None:
                default = (user_input or {}).get(CONF_HOST, vol.UNDEFINED)
                schema = vol.Schema({vol.Required(CONF_HOST, default=default): str})
                return self.async_show_form(step_id="relay_install", data_schema=schema, errors=errors)
        self._install_task = None  # a fresh attempt
        return await self.async_step_relay_install_run()

    async def _install_relay_app(self, scope_host: str) -> None:
        local = await self._local_ip()
        if not local:
            raise AppSetupError("Could not work out this Home Assistant's address.")

        async def ready() -> str | None:
            return await self._check(local, DEFAULT_PORT, None)

        await app_setup.install_relay_app(self.hass, scope_host, ready)
        self._relay = {CONF_HOST: local, CONF_PORT: DEFAULT_PORT, CONF_TOKEN: None, CONF_MODE: MODE_RELAY}

    async def async_step_relay_install_run(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._install_task is None:
            scope = self._known_scope_host()
            assert scope
            self._install_task = self.hass.async_create_task(self._install_relay_app(scope))
        if not self._install_task.done():
            return self.async_show_progress(
                step_id="relay_install_run", progress_action="install_app", progress_task=self._install_task
            )
        task, self._install_task = self._install_task, None
        try:
            await task
        except AppSetupError as err:
            self._install_error = str(err)
            return self.async_show_progress_done(next_step_id="relay_install_failed")
        return self.async_show_progress_done(next_step_id="relay_ready")

    async def async_step_relay_install_failed(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="relay_install_failed",
            menu_options=["relay_install", "relay_manual"],
            description_placeholders={"error": self._install_error},
        )

    async def async_step_relay_ready(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The relay app is running. Nothing more to ask."""
        assert self._relay
        host, port = self._relay[CONF_HOST], self._relay[CONF_PORT]
        return await self._finish(data=self._relay, unique_id=f"{host}:{port}", title=f"DWARF 3 relay ({host})")

    async def async_step_relay_found(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._relay
        if user_input is not None:
            host, port = self._relay[CONF_HOST], self._relay[CONF_PORT]
            return await self._finish(data=self._relay, unique_id=f"{host}:{port}", title=f"DWARF 3 relay ({host})")
        self._set_confirm_only()
        return self.async_show_form(step_id="relay_found", description_placeholders={"host": self._relay[CONF_HOST]})

    @callback
    def async_remove(self) -> None:
        if self._install_task and not self._install_task.done():
            self._install_task.cancel()

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
    def async_get_options_flow(config_entry: Dwarf3ConfigEntry) -> OptionsFlowWithReload:
        return Dwarf3OptionsFlow()


class Dwarf3OptionsFlow(OptionsFlowWithReload):
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
