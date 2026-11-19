"""The newest capture's stack, kept up to date for the image entity.

The scope writes `stacked.jpg` into each session's folder and, as far as astrolab's live page assumes, rewrites it as
frames are stacked. So while a capture runs this checks every poll, and otherwise every few minutes. A check lists the
newest session and compares the file's size, and only downloads when it changed.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import time
from collections.abc import Callable
from typing import Any, Protocol

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .api import RelayClient, RelayError
from .direct import STACK_FILE, THUMBNAIL_FILE, ScopeDirectClient, ScopeUnreachable, session_order

_LOGGER = logging.getLogger(__name__)

WIDTH = 1280  # a cast display does not need the scope's full 4 to 5 MB
RUNNING_EVERY_S = 30
IDLE_EVERY_S = 600

SESSION = re.compile(
    r"^DWARF_RAW_(?P<camera>TELE|WIDE)_(?:(?P<target>.+)_)?EXP_(?P<exposure>\d+)_GAIN_(?P<gain>\d+)_"
    r"(?P<started>\d{4}-\d\d-\d\d-\d\d-\d\d-\d\d)-\d+$"
)


def describe(session: str) -> dict[str, Any]:
    """What the folder name says: target, camera, exposure, gain and start time (the scope's own clock)."""
    found = SESSION.match(session)
    if not found:
        return {"session": session}
    year, month, day, hour, minute, second = found["started"].split("-")
    info: dict[str, Any] = {
        "session": session,
        "camera": found["camera"].lower(),
        "exposure_s": int(found["exposure"]),
        "gain": int(found["gain"]),
        "started": f"{year}-{month}-{day} {hour}:{minute}:{second}",
    }
    if found["target"]:
        info["target"] = found["target"]
    return info


def downscale(raw: bytes, width: int = WIDTH) -> bytes:
    """A JPEG no wider than `width`. Runs in an executor."""
    from PIL import Image

    image = Image.open(io.BytesIO(raw))
    if image.width > width:
        image = image.resize((width, round(image.height * width / image.width)))
    out = io.BytesIO()
    image.convert("RGB").save(out, "JPEG", quality=85)
    return out.getvalue()


Index = dict[str, dict[str, int | None]]  # session -> {"stack": size or None, "thumb": size or None}


class StackSource(Protocol):
    async def fetch(self, known: tuple[str, int] | None) -> tuple[str, int, bytes | None] | None: ...

    async def index(self, known: Index) -> Index: ...

    async def read(self, session: str, name: str) -> bytes: ...


class RelayStackSource:
    def __init__(self, client: RelayClient) -> None:
        self._client = client

    async def fetch(self, known: tuple[str, int] | None) -> tuple[str, int, bytes | None] | None:
        sessions = await self._client.sessions()
        if not sessions:
            return None
        session = max(sessions, key=session_order)
        stack = next((e for e in await self._client.files(session) if e["name"] == STACK_FILE and not e["dir"]), None)
        if stack is None:
            return None
        if known == (session, stack["size"]):
            return session, stack["size"], None
        return session, stack["size"], await self._client.download(f"{session}/{STACK_FILE}", stack["size"])


    async def index(self, known: Index) -> Index:
        sessions = await self._client.sessions()
        newest = max(sessions, key=session_order, default=None)
        todo = [name for name in sessions if name not in known or name == newest]
        gate = asyncio.Semaphore(4)

        async def look(name: str) -> tuple[str, dict[str, int | None]]:
            async with gate:
                sizes = {e["name"]: e["size"] for e in await self._client.files(name) if not e["dir"]}
            return name, {"stack": sizes.get(STACK_FILE), "thumb": sizes.get(THUMBNAIL_FILE)}

        found = dict(await asyncio.gather(*(look(name) for name in todo)))
        return {name: found.get(name) or known[name] for name in sessions}

    async def read(self, session: str, name: str) -> bytes:
        entries = await self._client.files(session)
        size = next((e["size"] for e in entries if e["name"] == name and not e["dir"]), None)
        if size is None:
            raise FileNotFoundError(name)
        return await self._client.download(f"{session}/{name}", size)


class DirectStackSource:
    def __init__(self, hass: HomeAssistant, client: ScopeDirectClient) -> None:
        self._hass, self._client = hass, client

    async def fetch(self, known: tuple[str, int] | None) -> tuple[str, int, bytes | None] | None:
        return await self._hass.async_add_executor_job(self._client.fetch_stack_blocking, known)

    async def index(self, known: Index) -> Index:
        return await self._hass.async_add_executor_job(self._client.index_stacks_blocking, known)

    async def read(self, session: str, name: str) -> bytes:
        return await self._hass.async_add_executor_job(self._client.read_file_blocking, session, name)


class StackTracker:
    def __init__(self, hass: HomeAssistant, source: StackSource) -> None:
        self.hass = hass
        self._source = source
        self.session: str | None = None
        self.size: int | None = None
        self.jpeg: bytes | None = None
        self.updated = None
        self.last_check = float("-inf")
        self._busy = False
        self._listeners: list[Callable[[], None]] = []

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def due(self, running: bool) -> bool:
        wait = RUNNING_EVERY_S if running else IDLE_EVERY_S
        return not self._busy and time.monotonic() - self.last_check >= wait

    async def async_check(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.last_check = time.monotonic()
        try:
            known = (self.session, self.size) if self.session is not None and self.size is not None else None
            found = await self._source.fetch(known)
            if found is None or found[2] is None:
                return
            session, size, raw = found
            self.jpeg = await self.hass.async_add_executor_job(downscale, raw)
            self.session, self.size, self.updated = session, size, dt_util.utcnow()
            for listener in list(self._listeners):
                listener()
        except Exception as err:  # noqa: BLE001 - a best-effort background refresh must never raise
            _LOGGER.debug("Could not read the latest stack: %s", err, exc_info=not isinstance(
                err, (RelayError, ScopeUnreachable, OSError, ValueError)
            ))
        finally:
            self._busy = False


class StackLibrary:
    """Every session on the scope that has a stack, for the Media browser, and the pictures to show.

    The listing is cached for a few minutes and older sessions are never listed twice, since they do not change.
    """

    LIST_FOR_S = 300
    KEEP_IMAGES = 12

    def __init__(self, hass: HomeAssistant, source: StackSource) -> None:
        self.hass = hass
        self._source = source
        self._index: Index = {}
        self._listed = float("-inf")
        self._images: dict[tuple[str, bool], bytes] = {}

    async def async_sessions(self) -> list[tuple[str, dict[str, int | None]]]:
        """Sessions with a stack, newest first."""
        if time.monotonic() - self._listed >= self.LIST_FOR_S:
            self._index = await self._source.index(self._index)
            self._listed = time.monotonic()
        have = [(name, info) for name, info in self._index.items() if info.get("stack")]
        return sorted(have, key=lambda item: session_order(item[0]), reverse=True)

    async def async_image(self, session: str, thumbnail: bool = False) -> bytes:
        """The stack (scaled to 1280 px) or its thumbnail. Raises FileNotFoundError when there is none."""
        key = (session, thumbnail)
        if key in self._images:
            return self._images[key]
        raw = await self._source.read(session, THUMBNAIL_FILE if thumbnail else STACK_FILE)
        image = raw if thumbnail else await self.hass.async_add_executor_job(downscale, raw)
        self._images[key] = image
        while len(self._images) > self.KEEP_IMAGES:
            self._images.pop(next(iter(self._images)))
        return image
