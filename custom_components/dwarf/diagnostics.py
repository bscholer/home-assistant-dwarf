"""Diagnostics download, with anything that identifies the scope or your network removed."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_MAC, CONF_MODE, CONF_TOKEN, MODE_DIRECT, MODE_RELAY
from .coordinator import Dwarf3ConfigEntry

REDACT = {CONF_TOKEN, CONF_MAC, "host", "sessions", "session"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: Dwarf3ConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    out: dict[str, Any] = {
        "mode": entry.data.get(CONF_MODE, MODE_RELAY),
        "entry": async_redact_data(dict(entry.data), REDACT),
        "data": async_redact_data(coordinator.data, REDACT),
    }
    if entry.data.get(CONF_MODE, MODE_RELAY) == MODE_DIRECT:
        # The key names of deviceInfo, never its values: the reply holds the Wi-Fi password.
        try:
            out["device_info_keys"] = sorted((await coordinator.client.device_info()).keys())
        except Exception as err:  # noqa: BLE001
            out["device_info_keys"] = f"unavailable: {err}"
    return out
