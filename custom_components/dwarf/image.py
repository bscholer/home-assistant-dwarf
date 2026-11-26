"""The latest stack as an image, so a dashboard or a smart display can show it."""

from __future__ import annotations

from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import Dwarf3ConfigEntry
from .entity import Dwarf3Entity
from .stack import StackTracker, describe


async def async_setup_entry(
    hass: HomeAssistant, entry: Dwarf3ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([Dwarf3LatestStack(entry)])


def _capturing(data: dict[str, Any]) -> bool:
    """True while a capture runs, so the stack is changing. Read-only mode cannot tell, so it checks slowly."""
    return bool(
        data.get("busy_elsewhere")
        or (data.get("job") or {}).get("state") == "running"
        or data.get("capture_state") == 1
    )


class Dwarf3LatestStack(Dwarf3Entity, ImageEntity):
    """The newest session's stacked.jpg, at most 1280 px wide.

    It is cast with media-source://image/image.dwarf_3_latest_stack
    """

    _attr_translation_key = "latest_stack"
    _attr_content_type = "image/jpeg"

    def __init__(self, entry: Dwarf3ConfigEntry) -> None:
        coordinator = entry.runtime_data
        Dwarf3Entity.__init__(self, coordinator, "latest_stack")
        ImageEntity.__init__(self, coordinator.hass)
        self._entry = entry
        self._tracker: StackTracker = coordinator.stack
        self._was_capturing = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._tracker.add_listener(self._stack_changed))
        self._schedule_check()  # the first look, without holding up setup

    @callback
    def _stack_changed(self) -> None:
        self._attr_image_last_updated = self._tracker.updated
        self.async_write_ha_state()

    def _schedule_check(self) -> None:
        self._entry.async_create_background_task(self.hass, self._tracker.async_check(), "dwarf latest stack")

    @callback
    def _handle_coordinator_update(self) -> None:
        capturing = _capturing(self.coordinator.data)
        finished = self._was_capturing and not capturing  # one last look at the finished stack
        self._was_capturing = capturing
        if finished or self._tracker.due(capturing):
            self._schedule_check()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        return self._tracker.jpeg

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return describe(self._tracker.session) if self._tracker.session else None
