"""The wide and tele cameras: a live stream, and a still while the stream is not playing."""

from __future__ import annotations

import asyncio
import time

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import RelayClient, RelayError
from .const import RTSP_PATHS, RTSP_PORT
from .coordinator import Dwarf3ConfigEntry
from .entity import Dwarf3Entity

# Home Assistant gives a camera about 10 s to answer, and a still from the scope can take 20 s or more (the tele
# camera waits for a keyframe, about 40 s). So a request waits this long, then falls back to the last still
# while the fetch carries on.
WAIT_S = 8
FRESH_S = 20


async def async_setup_entry(
    hass: HomeAssistant, entry: Dwarf3ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    host = entry.data[CONF_HOST]
    async_add_entities([Dwarf3Camera(coordinator, "wide", host), Dwarf3Camera(coordinator, "tele", host)])


class Dwarf3Camera(Dwarf3Entity, Camera):
    """Live video over RTSP, which Home Assistant plays as HLS or WebRTC, and a still image.

    The scope only streams after Prepare. The host is the relay in full control mode, because the relay forwards
    port 554 to the scope, and the scope itself in read-only mode, where the DWARFLAB app has to have started the
    camera.
    """

    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, coordinator: DataUpdateCoordinator, kind: str, host: str) -> None:
        Dwarf3Entity.__init__(self, coordinator, f"{kind}_camera")
        Camera.__init__(self)
        self._attr_translation_key = f"{kind}_camera"
        self._kind = kind
        self._host = host
        # The scope's video runs over TCP. UDP drops frames across a Wi-Fi hop.
        self.stream_options["rtsp_transport"] = "tcp"
        self._image: bytes | None = None
        self._image_time = 0.0
        self._task: asyncio.Task[None] | None = None
        self._error: str | None = None

    async def stream_source(self) -> str | None:
        return f"rtsp://{self._host}:{RTSP_PORT}/{RTSP_PATHS[self._kind]}"

    async def _fetch(self) -> None:
        try:
            self._image = await self.coordinator.client.frame(self._kind)
            self._image_time = time.monotonic()
            self._error = None
        except RelayError as err:
            self._error = str(err)

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        if not isinstance(getattr(self.coordinator, "client", None), RelayClient):
            return None  # read-only mode has no relay to take a still from, so only the stream shows
        if self._image and time.monotonic() - self._image_time < FRESH_S:
            return self._image
        if self._task is None or self._task.done():
            self._task = self.coordinator.config_entry.async_create_background_task(
                self.hass, self._fetch(), f"dwarf {self._kind} frame"
            )
        await asyncio.wait({self._task}, timeout=WAIT_S)
        if self._image:
            return self._image
        if self._task.done():
            raise HomeAssistantError(f"Could not read a frame: {self._error}. The scope streams after Prepare.")
        raise HomeAssistantError("The scope is slow to send a frame. Try again in a moment.")

    async def async_will_remove_from_hass(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
