"""Wide camera snapshots."""

from __future__ import annotations

import asyncio
import time

from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import RelayError
from .coordinator import Dwarf3ConfigEntry, Dwarf3Coordinator
from .entity import Dwarf3Entity

# Home Assistant gives a camera about 10 s to answer, and a frame from the scope can take 20 s or more.
# So a request waits this long, then falls back to the last frame while the fetch carries on.
WAIT_S = 8
FRESH_S = 20


async def async_setup_entry(
    hass: HomeAssistant, entry: Dwarf3ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([Dwarf3WideCamera(entry.runtime_data)])


class Dwarf3WideCamera(Dwarf3Entity, Camera):
    """A still from the wide camera. The tele camera waits for a keyframe, so it is not offered.

    The scope only streams after Prepare, so before that there is no image to show.
    """

    _attr_translation_key = "wide_camera"

    def __init__(self, coordinator: Dwarf3Coordinator) -> None:
        Dwarf3Entity.__init__(self, coordinator, "wide_camera")
        Camera.__init__(self)
        self._image: bytes | None = None
        self._image_time = 0.0
        self._task: asyncio.Task[None] | None = None
        self._error: str | None = None

    async def _fetch(self) -> None:
        try:
            self._image = await self.coordinator.client.frame("wide")
            self._image_time = time.monotonic()
            self._error = None
        except RelayError as err:
            self._error = str(err)

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        if self._image and time.monotonic() - self._image_time < FRESH_S:
            return self._image
        if self._task is None or self._task.done():
            self._task = self.hass.async_create_task(self._fetch())
        await asyncio.wait({self._task}, timeout=WAIT_S)
        if self._image:
            return self._image
        if self._task.done():
            raise HomeAssistantError(f"Could not read a frame: {self._error}. The scope streams after Prepare.")
        raise HomeAssistantError("The scope is slow to send a frame. Try again in a moment.")

    async def async_will_remove_from_hass(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
