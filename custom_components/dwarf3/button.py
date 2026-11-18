"""Scope actions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import RelayClient, RelayError
from .coordinator import Dwarf3ConfigEntry, Dwarf3Coordinator
from .entity import Dwarf3Entity


@dataclass(frozen=True, kw_only=True)
class Dwarf3ButtonDescription(ButtonEntityDescription):
    press: Callable[[RelayClient], Awaitable[None]]


BUTTONS: tuple[Dwarf3ButtonDescription, ...] = (
    Dwarf3ButtonDescription(key="close_barrel", translation_key="close_barrel", press=lambda c: c.close_barrel()),
    Dwarf3ButtonDescription(key="stop_capture", translation_key="stop_capture", press=lambda c: c.stop_capture()),
    Dwarf3ButtonDescription(key="prepare", translation_key="prepare", press=lambda c: c.prepare()),
    Dwarf3ButtonDescription(key="calibrate", translation_key="calibrate", press=lambda c: c.calibrate()),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: Dwarf3ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(Dwarf3Button(coordinator, description) for description in BUTTONS)


class Dwarf3Button(Dwarf3Entity, ButtonEntity):
    entity_description: Dwarf3ButtonDescription

    def __init__(self, coordinator: Dwarf3Coordinator, description: Dwarf3ButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        try:
            await self.entity_description.press(self.coordinator.client)
        except RelayError as err:
            raise HomeAssistantError(f"{self.entity_description.key} failed: {err}") from err
        await self.coordinator.async_request_refresh()
