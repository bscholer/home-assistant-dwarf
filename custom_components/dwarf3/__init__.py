"""The DWARF 3 smart telescope, through the dwarf3 relay."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RelayClient, RelayError, RelayUnreachable
from .const import CONF_MODE, CONF_TOKEN, DOMAIN, MODE_DIRECT, MODE_RELAY
from .coordinator import Dwarf3ConfigEntry, Dwarf3Coordinator, Dwarf3DirectCoordinator
from .direct import ScopeDirectClient
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.CAMERA, Platform.EVENT, Platform.SENSOR]
DIRECT_PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]



async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: Dwarf3ConfigEntry) -> bool:
    """Create the entities at once, in an unknown state, and read the scope in the background.

    The first read of a scope can take 30 seconds or more, and waiting for it left the device page empty or
    "unavailable" the whole time. A relay that does not answer at all is still reported as not ready.
    """
    session = async_get_clientsession(hass)
    if entry.data.get(CONF_MODE, MODE_RELAY) == MODE_DIRECT:
        direct = Dwarf3DirectCoordinator(hass, entry, ScopeDirectClient(session, entry.data[CONF_HOST]))
        direct.data = {}
        direct.platforms = DIRECT_PLATFORMS
        entry.runtime_data = direct
        await hass.config_entries.async_forward_entry_setups(entry, DIRECT_PLATFORMS)
        entry.async_on_unload(entry.add_update_listener(_reload))
        entry.async_create_background_task(hass, direct.async_refresh(), "dwarf3 first read")
        return True

    client = RelayClient(session, entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data.get(CONF_TOKEN))
    try:
        capabilities = await client.capabilities()
    except RelayUnreachable as err:
        raise ConfigEntryNotReady(f"The relay did not answer: {err}") from err
    except RelayError:
        capabilities = {}
    coordinator = Dwarf3Coordinator(hass, entry, client)
    coordinator.relay_version = (capabilities.get("service") or {}).get("version")
    coordinator.data = {}
    coordinator.platforms = PLATFORMS
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    entry.async_create_background_task(hass, _first_read(coordinator), "dwarf3 first read")
    return True


async def _first_read(coordinator: Dwarf3Coordinator) -> None:
    await coordinator.async_refresh()
    await coordinator.sessions.async_refresh()  # slow, so after the status


async def _reload(hass: HomeAssistant, entry: Dwarf3ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: Dwarf3ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, entry.runtime_data.platforms)
