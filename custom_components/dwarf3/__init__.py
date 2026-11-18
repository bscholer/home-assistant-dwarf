"""The DWARF 3 smart telescope, through the dwarf3 relay."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RelayClient, RelayError
from .const import CONF_MODE, CONF_TOKEN, MODE_DIRECT, MODE_RELAY
from .coordinator import Dwarf3ConfigEntry, Dwarf3Coordinator, Dwarf3DirectCoordinator
from .direct import ScopeDirectClient
from .services import async_setup_services

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.CAMERA, Platform.EVENT, Platform.SENSOR]
DIRECT_PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]



async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: Dwarf3ConfigEntry) -> bool:
    if entry.data.get(CONF_MODE, MODE_RELAY) == MODE_DIRECT:
        direct = Dwarf3DirectCoordinator(
            hass, entry, ScopeDirectClient(async_get_clientsession(hass), entry.data[CONF_HOST])
        )
        await direct.async_config_entry_first_refresh()
        direct.platforms = DIRECT_PLATFORMS
        entry.runtime_data = direct
        await hass.config_entries.async_forward_entry_setups(entry, DIRECT_PLATFORMS)
        entry.async_on_unload(entry.add_update_listener(_reload))
        return True
    client = RelayClient(
        async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data.get(CONF_TOKEN)
    )
    coordinator = Dwarf3Coordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    try:
        coordinator.relay_version = ((await client.capabilities()).get("service") or {}).get("version")
    except RelayError:
        pass  # an older relay, or a hiccup: the version sensor stays unknown
    await coordinator.sessions.async_refresh()  # a failure leaves the sessions sensor unavailable, not setup
    coordinator.platforms = PLATFORMS
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: Dwarf3ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: Dwarf3ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, entry.runtime_data.platforms)
