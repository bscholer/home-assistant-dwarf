"""The dashboard card: served from /local and added to the dashboard resources, so the card picker lists it.

The card is copied to config/www/dwarf3, which Home Assistant serves from the moment it starts. A route of our own
only exists once this integration has loaded, and a dashboard opened before that (right after a restart) gets a 404
and has no card until the next reload. When www did not exist at startup, /local is not served yet, so the card uses
our own route until the next restart.

The resource URL carries a hash of the file, so browsers fetch the card again after every update.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

URL_BASE = "/dwarf3_frontend"
LOCAL_BASE = "/local/dwarf3"
CARD_FILE = "dwarf3-card.js"
CARD_URL = f"{URL_BASE}/{CARD_FILE}"
LOCAL_CARD_URL = f"{LOCAL_BASE}/{CARD_FILE}"
FRONTEND_DIR = Path(__file__).parent / "frontend"


def _is_ours(url: str) -> bool:
    return str(url).split("?")[0] in (CARD_URL, LOCAL_CARD_URL)


def _install(www: Path) -> tuple[str, bool]:
    """Copy the card and its fonts into www/dwarf3. Returns the file hash and whether /local serves it already."""
    served = www.is_dir()  # /local is only set up when www exists at startup
    version = hashlib.sha256((FRONTEND_DIR / CARD_FILE).read_bytes()).hexdigest()[:10]
    target = www / "dwarf3"
    for source in [FRONTEND_DIR / CARD_FILE, *sorted((FRONTEND_DIR / "fonts").iterdir())]:
        dest = target / source.relative_to(FRONTEND_DIR)
        if dest.exists() and dest.read_bytes() == source.read_bytes():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    return version, served


def _www(hass: HomeAssistant) -> Path:
    return Path(hass.config.path("www"))


def _resources(hass: HomeAssistant):
    """The storage-mode resource collection, or None when resources are in YAML or the dashboards are not loaded."""
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return None
    mode = getattr(lovelace, "resource_mode", None) or getattr(lovelace, "mode", None)
    return lovelace.resources if mode == "storage" else None


async def _loaded(resources) -> None:
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True


async def async_setup_card(hass: HomeAssistant) -> None:
    """Install the card and register it. Entries of a domain set up together, so this runs one at a time."""
    lock = hass.data.setdefault(DOMAIN, {}).setdefault("card_lock", asyncio.Lock())
    async with lock:
        await _setup_card(hass)


async def _setup_card(hass: HomeAssistant) -> None:
    """A failure here is logged and never stops the integration."""
    try:
        version, served = await hass.async_add_executor_job(_install, _www(hass))
        domain_data = hass.data.setdefault(DOMAIN, {})
        if not domain_data.get("card_path"):
            await hass.http.async_register_static_paths([StaticPathConfig(URL_BASE, str(FRONTEND_DIR), True)])
            domain_data["card_path"] = True
        url = f"{LOCAL_CARD_URL if served else CARD_URL}?v={version}"
        resources = _resources(hass)
        if resources is None:
            from homeassistant.components.frontend import add_extra_js_url

            add_extra_js_url(hass, url)
            hass.data[DOMAIN]["extra_js_url"] = url
            return
        await _loaded(resources)
        ours = [r for r in resources.async_items() if _is_ours(r["url"])]
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
    """Take the card out of the dashboard resources and www, when the last DWARF 3 is removed."""
    try:
        await hass.async_add_executor_job(shutil.rmtree, _www(hass) / "dwarf3", True)
        if url := hass.data.get(DOMAIN, {}).pop("extra_js_url", None):
            from homeassistant.components.frontend import remove_extra_js_url

            remove_extra_js_url(hass, url)
        resources = _resources(hass)
        if resources is None:
            return
        await _loaded(resources)
        for item in list(resources.async_items()):
            if _is_ours(item["url"]):
                await resources.async_delete_item(item["id"])
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Could not remove the DWARF 3 card from the dashboards", exc_info=True)
