"""Services that need arguments: goto and start_capture."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_extract_config_entry_ids

from .api import RelayError
from .const import CONF_MODE, DOMAIN, FILTERS, MODE_DIRECT, MODE_RELAY
from .coordinator import Dwarf3Coordinator

# Seconds, as the scope names them ("15", "1.3"). Which ones a scope has depends on the model, and the relay
# refuses one its model lacks with a message that lists the right ones.
EXPOSURE = vol.All(vol.Coerce(str), vol.Match(r"^\d+(\.\d+)?$"))

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
        vol.Optional("exposure", default="15"): EXPOSURE,
        vol.Optional("gain", default=60): vol.Coerce(int),
        vol.Optional("filter", default="duo"): vol.In(FILTERS),
    }
)


DARK_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required("frames"): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
        vol.Optional("exposure", default="15"): EXPOSURE,
        vol.Optional("wide", default=False): cv.boolean,
    }
)
MOVE_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required("angle"): vol.All(vol.Coerce(float), vol.Range(min=0, max=360)),
        vol.Optional("length", default=0.3): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
        vol.Optional("seconds", default=1): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=5)),
    }
)
POINT_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required("pitch"): vol.All(vol.Coerce(float), vol.Range(min=0, max=175)),
        vol.Optional("rotation"): vol.All(vol.Coerce(float), vol.Range(min=0, max=360)),
    }
)
DELETE_SCHEMA = cv.make_entity_service_schema({vol.Required("session"): vol.Match(r"^DWARF_RAW_[^/\\]+$")})


async def _coordinators(hass: HomeAssistant, call: ServiceCall) -> list[Dwarf3Coordinator]:
    ids = await async_extract_config_entry_ids(call)
    entries = [e for e in hass.config_entries.async_loaded_entries(DOMAIN) if e.entry_id in ids]
    if not entries:
        raise ServiceValidationError("Pick a DWARF 3 device or entity as the target.")
    if any(e.data.get(CONF_MODE, MODE_RELAY) == MODE_DIRECT for e in entries):
        raise ServiceValidationError("This DWARF 3 is set up in read-only mode. Controls need the relay.")
    return [e.runtime_data for e in entries]


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

    async def start_dark(call: ServiceCall) -> None:
        for coordinator in await _coordinators(hass, call):
            try:
                await coordinator.client.start_dark(call.data["frames"], call.data["exposure"], call.data["wide"])
            except RelayError as err:
                raise HomeAssistantError(f"start_dark failed: {err}") from err
            await coordinator.async_request_refresh()

    async def move(call: ServiceCall) -> None:
        for coordinator in await _coordinators(hass, call):
            try:
                await coordinator.client.move(call.data["angle"], call.data["length"], call.data["seconds"])
            except RelayError as err:
                raise HomeAssistantError(f"move failed: {err}") from err
            await coordinator.async_request_refresh()

    async def point(call: ServiceCall) -> None:
        for coordinator in await _coordinators(hass, call):
            try:
                await coordinator.client.point(call.data["pitch"], call.data.get("rotation"))
            except RelayError as err:
                raise HomeAssistantError(f"point failed: {err}") from err
            await coordinator.async_request_refresh()

    async def delete_session(call: ServiceCall) -> None:
        for coordinator in await _coordinators(hass, call):
            try:
                await coordinator.client.delete_session(call.data["session"])
            except RelayError as err:
                raise HomeAssistantError(f"delete_session failed: {err}") from err
            coordinator.library.forget(call.data["session"])
            coordinator.stack.forget(call.data["session"])
            await coordinator.sessions.async_refresh()
            await coordinator.stack.async_check()  # show the newest stack left, now rather than in 10 minutes

    hass.services.async_register(DOMAIN, "start_dark", start_dark, schema=DARK_SCHEMA)
    hass.services.async_register(DOMAIN, "move", move, schema=MOVE_SCHEMA)
    hass.services.async_register(DOMAIN, "point", point, schema=POINT_SCHEMA)
    hass.services.async_register(DOMAIN, "delete_session", delete_session, schema=DELETE_SCHEMA)
    hass.services.async_register(DOMAIN, "goto", goto, schema=GOTO_SCHEMA)
    hass.services.async_register(DOMAIN, "start_capture", start_capture, schema=CAPTURE_SCHEMA)
