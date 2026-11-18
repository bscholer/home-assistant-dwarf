"""Wide camera snapshots."""

from __future__ import annotations

from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import RelayError
from .coordinator import Dwarf3ConfigEntry, Dwarf3Coordinator
from .entity import Dwarf3Entity


async def async_setup_entry(
    hass: HomeAssistant, entry: Dwarf3ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([Dwarf3WideCamera(entry.runtime_data)])


class Dwarf3WideCamera(Dwarf3Entity, Camera):
    """A still from the wide camera. The tele camera waits for a keyframe, so it is not offered."""

    _attr_translation_key = "wide_camera"

    def __init__(self, coordinator: Dwarf3Coordinator) -> None:
        Dwarf3Entity.__init__(self, coordinator, "wide_camera")
        Camera.__init__(self)

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        try:
            return await self.coordinator.client.frame("wide")
        except RelayError as err:
            raise HomeAssistantError(f"Could not read a frame: {err}") from err
