"""Base entity."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import DOMAIN


class Dwarf3Entity(CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DataUpdateCoordinator[dict[str, Any]], key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="DWARF 3",
            manufacturer="DWARFLAB",
            model="DWARF 3",
        )
