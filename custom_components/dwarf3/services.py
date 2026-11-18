"""Services that need arguments: goto and start_capture."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_extract_config_entry_ids

from .api import RelayError
from .const import DOMAIN, EXPOSURES, FILTERS
from .coordinator import Dwarf3Coordinator

GOTO_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required("name"): cv.string,
        vol.Required("ra_hours"): vol.All(vol.Coerce(float), vol.Range(min=0, max=24)),
        vol.Required("dec_degrees"): vol.All(vol.Coerce(float), vol.Range(min=-90, max=90)),
    }
)
CAPTURE_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required("frames"): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
        vol.Optional("exposure", default="15"): vol.All(vol.Coerce(str), vol.In(EXPOSURES)),
        vol.Optional("gain", default=60): vol.Coerce(int),
        vol.Optional("filter", default="duo"): vol.In(FILTERS),
    }
)


async def _coordinators(hass: HomeAssistant, call: ServiceCall) -> list[Dwarf3Coordinator]:
    ids = await async_extract_config_entry_ids(call)
    found = [
        entry.runtime_data
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if entry.entry_id in ids
    ]
    if not found:
        raise ServiceValidationError("Pick a DWARF 3 device or entity as the target.")
    return found


def async_setup_services(hass: HomeAssistant) -> None:
    async def goto(call: ServiceCall) -> None:
        for coordinator in await _coordinators(hass, call):
            try:
                await coordinator.client.goto(call.data["name"], call.data["ra_hours"], call.data["dec_degrees"])
            except RelayError as err:
                raise HomeAssistantError(f"goto failed: {err}") from err
            await coordinator.async_request_refresh()

    async def start_capture(call: ServiceCall) -> None:
        for coordinator in await _coordinators(hass, call):
            try:
                await coordinator.client.start_capture(
                    call.data["frames"], call.data["exposure"], call.data["gain"], call.data["filter"]
                )
            except RelayError as err:
                raise HomeAssistantError(f"start_capture failed: {err}") from err
            await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "goto", goto, schema=GOTO_SCHEMA)
    hass.services.async_register(DOMAIN, "start_capture", start_capture, schema=CAPTURE_SCHEMA)
