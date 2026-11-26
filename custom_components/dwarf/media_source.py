"""Browse the stacks on the scope in Home Assistant's Media, and play them on a speaker or display.

media-source://dwarf/<entry id>/<session> resolves to a picture served by this integration, so Home Assistant can
sign the address and a smart display can fetch it.
"""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.components.media_player import BrowseError, MediaClass
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import Dwarf3ConfigEntry
from .stack import describe

VIEW_URL = "/api/dwarf/stack/{entry_id}/{session}"
THUMBNAIL_URL = VIEW_URL + "/thumb"
THUMBNAIL_VALID = timedelta(hours=1)


def stack_path(entry_id: str, session: str, thumbnail: bool = False) -> str:
    path = f"/api/dwarf/stack/{entry_id}/{quote(session, safe='')}"
    return path + "/thumb" if thumbnail else path


def title(session: str) -> str:
    """For example "M 81, 30 s, 18 Nov 03:11". The time is the scope's own clock."""
    info = describe(session)
    parts = [info.get("target") or ("Wide" if info.get("camera") == "wide" else "Capture")]
    if "exposure_s" in info:
        parts.append(f"{info['exposure_s']} s")
    if "started" in info:
        date, clock = info["started"].split(" ")
        parts.append(f"{date} {clock[:5]}")
    return ", ".join(parts)


def _entries(hass: HomeAssistant) -> list[Dwarf3ConfigEntry]:
    return [e for e in hass.config_entries.async_loaded_entries(DOMAIN) if getattr(e.runtime_data, "library", None)]


async def async_get_media_source(hass: HomeAssistant) -> Dwarf3MediaSource:
    return Dwarf3MediaSource(hass)


class Dwarf3MediaSource(MediaSource):
    name = "DWARF 3"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        entry_id, _, session = item.identifier.partition("/")
        if not session or not any(e.entry_id == entry_id for e in _entries(self.hass)):
            raise Unresolvable(f"No such stack: {item.identifier}")
        return PlayMedia(stack_path(entry_id, session), "image/jpeg")

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        entries = _entries(self.hass)
        if not item.identifier:
            if len(entries) == 1:  # the usual case: no need for a folder per scope
                return await self._browse_entry(entries[0], root=True)
            return BrowseMediaSource(
                domain=DOMAIN,
                identifier=None,
                media_class=MediaClass.DIRECTORY,
                media_content_type="",
                title=self.name,
                can_play=False,
                can_expand=True,
                children=[
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=e.entry_id,
                        media_class=MediaClass.DIRECTORY,
                        media_content_type="",
                        title=e.title,
                        can_play=False,
                        can_expand=True,
                    )
                    for e in entries
                ],
            )
        entry = next((e for e in entries if e.entry_id == item.identifier), None)
        if entry is None:
            raise BrowseError(f"Unknown item: {item.identifier}")
        return await self._browse_entry(entry)

    async def _browse_entry(self, entry: Dwarf3ConfigEntry, root: bool = False) -> BrowseMediaSource:
        try:
            sessions = await entry.runtime_data.library.async_sessions()
        except Exception as err:  # noqa: BLE001
            raise BrowseError(f"Could not read the scope: {err}") from err
        children = []
        for session, info in sessions:
            thumbnail = None
            if info.get("thumb"):
                thumbnail = async_sign_path(self.hass, stack_path(entry.entry_id, session, True), THUMBNAIL_VALID)
            children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{entry.entry_id}/{session}",
                    media_class=MediaClass.IMAGE,
                    media_content_type="image/jpeg",
                    title=title(session),
                    can_play=True,
                    can_expand=False,
                    thumbnail=thumbnail,
                )
            )
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None if root else entry.entry_id,
            media_class=MediaClass.DIRECTORY,
            media_content_type="",
            title=self.name if root else entry.title,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.IMAGE,
            children=children,
        )


class StackView(HomeAssistantView):
    """Serves a stack, or its thumbnail, to a browser or a display. The address is signed by Home Assistant."""

    url = VIEW_URL
    extra_urls = [THUMBNAIL_URL]
    name = "api:dwarf:stack"

    async def get(self, request: web.Request, entry_id: str, session: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entry = next((e for e in _entries(hass) if e.entry_id == entry_id), None)
        if entry is None or not session.startswith("DWARF_RAW_") or "/" in session or "\\" in session:
            raise web.HTTPNotFound
        thumbnail = request.path.endswith("/thumb")
        try:
            body = await entry.runtime_data.library.async_image(session, thumbnail)
        except (FileNotFoundError, OSError) as err:
            raise web.HTTPNotFound from err
        except Exception as err:  # noqa: BLE001
            raise web.HTTPBadGateway(text=str(err)) from err
        return web.Response(body=body, content_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
