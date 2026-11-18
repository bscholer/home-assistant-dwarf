"""Poll the relay for scope status."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RelayClient, RelayError, RelayUnauthorized, RelayUnreachable, ScopeError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type Dwarf3ConfigEntry = ConfigEntry[Dwarf3Coordinator]


class Dwarf3Coordinator(DataUpdateCoordinator[dict[str, Any]]):
    config_entry: Dwarf3ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: Dwarf3ConfigEntry, client: RelayClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        self.client = client
        self.relay_version: str | None = None
        self.sessions = Dwarf3SessionsCoordinator(hass, entry, client)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.status()
        except RelayUnauthorized as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ScopeError:
            # The relay is up and the scope is not (asleep, or off the network). Keep the relay entities.
            return {"scope_reachable": False}
        except RelayUnreachable as err:
            raise UpdateFailed(f"Relay did not answer: {err}") from err


class Dwarf3SessionsCoordinator(DataUpdateCoordinator[list[str]]):
    """The capture sessions on the scope's SD card. Slow, because it reads the scope's album."""

    def __init__(self, hass: HomeAssistant, entry: Dwarf3ConfigEntry, client: RelayClient) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=f"{DOMAIN} sessions", update_interval=timedelta(minutes=10)
        )
        self.client = client

    async def _async_update_data(self) -> list[str]:
        try:
            return await self.client.sessions()
        except RelayUnauthorized as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except RelayError as err:
            raise UpdateFailed(str(err)) from err
