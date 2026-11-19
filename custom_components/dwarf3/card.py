"""The dashboard card: served by the integration and added to the dashboard resources, so the card picker lists it.

The resource URL carries a hash of the file, so browsers fetch the card again after every update.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

URL_BASE = "/dwarf3_frontend"
CARD_FILE = "dwarf3-card.js"
CARD_URL = f"{URL_BASE}/{CARD_FILE}"
FRONTEND_DIR = Path(__file__).parent / "frontend"


def _version() -> str:
    return hashlib.sha256((FRONTEND_DIR / CARD_FILE).read_bytes()).hexdigest()[:10]


def _resources(hass: HomeAssistant):
    """The storage-mode resource collection, or None when resources are in YAML or the dashboards are not loaded."""
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return None
    mode = getattr(lovelace, "resource_mode", None) or getattr(lovelace, "mode", None)
    return lovelace.resources if mode == "storage" else None


async def async_setup_card(hass: HomeAssistant) -> None:
    """Serve the card and register it. A failure here is logged and never stops the integration."""
    try:
        version = await hass.async_add_executor_job(_version)
        await hass.http.async_register_static_paths([StaticPathConfig(URL_BASE, str(FRONTEND_DIR), True)])
        url = f"{CARD_URL}?v={version}"
        resources = _resources(hass)
        if resources is None:
            from homeassistant.components.frontend import add_extra_js_url

            add_extra_js_url(hass, url)
            return
        if not resources.loaded:
            await resources.async_load()
            resources.loaded = True
        ours = [r for r in resources.async_items() if str(r["url"]).split("?")[0] == CARD_URL]
        if not ours:
            await resources.async_create_item({"res_type": "module", "url": url})
            _LOGGER.debug("Added the DWARF 3 card to the dashboard resources")
            return
        first, *extra = ours
        if first["url"] != url:
            await resources.async_update_item(first["id"], {"res_type": "module", "url": url})
        for item in extra:
            await resources.async_delete_item(item["id"])
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Could not add the DWARF 3 card to the dashboards", exc_info=True)


async def async_remove_card(hass: HomeAssistant) -> None:
    """Take the card out of the dashboard resources, when the last DWARF 3 is removed."""
    try:
        resources = _resources(hass)
        if resources is None:
            return
        if not resources.loaded:
            await resources.async_load()
            resources.loaded = True
        for item in list(resources.async_items()):
            if str(item["url"]).split("?")[0] == CARD_URL:
                await resources.async_delete_item(item["id"])
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Could not remove the DWARF 3 card from the dashboards", exc_info=True)
