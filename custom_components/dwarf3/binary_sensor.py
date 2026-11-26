"""Connection and busy flags."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_MODE, MODE_DIRECT, MODE_RELAY
from .coordinator import Dwarf3ConfigEntry
from .entity import Dwarf3Entity


@dataclass(frozen=True, kw_only=True)
class Dwarf3BinaryDescription(BinarySensorEntityDescription):
    value: Callable[[dict[str, Any]], bool | None]


def _needs_prepare(data: dict[str, Any]) -> bool | None:
    """True while the scope has not been prepared since it was last switched on.

    Until it has, it cannot report its motor positions, so pitch and rotation come back empty. The camera,
    calibrate, goto and capture do not work in that state either. Unknown when the scope is not answering.
    """
    if not data.get("scope_reachable") or "pitch" not in data:
        return None
    if data.get("busy_elsewhere") or (data.get("job") or {}).get("state") == "running":
        return False  # something is capturing, so it is clearly set up
    return data["pitch"] is None and data.get("rotation") is None


BINARY_SENSORS: tuple[Dwarf3BinaryDescription, ...] = (
    Dwarf3BinaryDescription(
        key="needs_prepare",
        translation_key="needs_prepare",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value=_needs_prepare,
    ),
    Dwarf3BinaryDescription(
        key="scope_reachable",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda d: d.get("scope_reachable"),
    ),
    Dwarf3BinaryDescription(
        key="tracking",
        translation_key="tracking",
        value=lambda d: None if d.get("tracking_state") is None else d["tracking_state"] == 1,
    ),
    Dwarf3BinaryDescription(
        key="app_connected",
        translation_key="app_connected",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda d: d.get("app_connected"),
    ),
    Dwarf3BinaryDescription(
        key="busy_elsewhere",
        translation_key="busy_elsewhere",
        device_class=BinarySensorDeviceClass.RUNNING,
        value=lambda d: d.get("busy_elsewhere"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: Dwarf3ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    direct = entry.data.get(CONF_MODE, MODE_RELAY) == MODE_DIRECT
    async_add_entities(
        Dwarf3Binary(coordinator, description)
        for description in BINARY_SENSORS
        if not direct or description.key == "scope_reachable"
    )


class Dwarf3Binary(Dwarf3Entity, BinarySensorEntity):
    entity_description: Dwarf3BinaryDescription

    def __init__(
        self, coordinator: DataUpdateCoordinator[dict[str, Any]], description: Dwarf3BinaryDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key == "scope_reachable":
            # The card reads the model's choices here. Read-only mode has no capture, so only the model.
            capture = getattr(self.coordinator, "capture", None)
            return {"model": getattr(self.coordinator, "model", None), **(capture or {})}
        if self.entity_description.key == "needs_prepare" and self.is_on:
            return {"hint": "Press Prepare. The camera, calibrate, goto and capture work only after it."}
        return None
