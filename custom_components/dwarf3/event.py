"""A capture finished."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import Dwarf3ConfigEntry, Dwarf3Coordinator
from .entity import Dwarf3Entity

TERMINAL = {"done": "capture_done", "failed": "capture_failed"}


async def async_setup_entry(
    hass: HomeAssistant, entry: Dwarf3ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([Dwarf3CaptureEvent(entry.runtime_data)])


def _finished_job(data: dict[str, Any]) -> dict[str, Any] | None:
    job = data.get("job") or {}
    return job if job.get("id") and job.get("state") in TERMINAL else None


class Dwarf3CaptureEvent(Dwarf3Entity, EventEntity):
    """Fires once for each job the relay reports as done or failed.

    A job that was already finished when Home Assistant started does not fire.
    """

    _attr_translation_key = "capture_finished"
    _attr_event_types = list(TERMINAL.values())

    def __init__(self, coordinator: Dwarf3Coordinator) -> None:
        super().__init__(coordinator, "capture_finished")
        job = _finished_job(coordinator.data)
        self._handled = job["id"] if job else None

    def _handle_coordinator_update(self) -> None:
        job = _finished_job(self.coordinator.data)
        if job and job["id"] != self._handled:
            self._handled = job["id"]
            self._trigger_event(
                TERMINAL[job["state"]],
                {k: job[k] for k in ("frames", "captured", "failed", "session", "error") if job.get(k) is not None},
            )
        super()._handle_coordinator_update()
