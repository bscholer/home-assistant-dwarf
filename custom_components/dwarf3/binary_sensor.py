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

from .coordinator import Dwarf3ConfigEntry, Dwarf3Coordinator
from .entity import Dwarf3Entity


@dataclass(frozen=True, kw_only=True)
class Dwarf3BinaryDescription(BinarySensorEntityDescription):
    value: Callable[[dict[str, Any]], bool | None]


BINARY_SENSORS: tuple[Dwarf3BinaryDescription, ...] = (
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
    async_add_entities(Dwarf3Binary(coordinator, description) for description in BINARY_SENSORS)


class Dwarf3Binary(Dwarf3Entity, BinarySensorEntity):
    entity_description: Dwarf3BinaryDescription

    def __init__(self, coordinator: Dwarf3Coordinator, description: Dwarf3BinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value(self.coordinator.data)
