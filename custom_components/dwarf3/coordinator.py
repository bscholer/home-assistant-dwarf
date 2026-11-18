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
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DIRECT_DEFAULT_SCAN_INTERVAL, DOMAIN
from .direct import ScopeDirectClient, ScopeUnreachable

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


SESSIONS_EVERY = timedelta(minutes=10)


class Dwarf3DirectCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Read-only status straight from the scope: reachability, SD card, and capture sessions."""

    config_entry: Dwarf3ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: Dwarf3ConfigEntry, client: ScopeDirectClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DIRECT_DEFAULT_SCAN_INTERVAL)),
        )
        self.client = client
        self._sessions: list[str] | None = None
        self._sessions_at = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data: dict[str, Any] = {"scope_reachable": True, **await self.client.sd_card()}
        except ScopeUnreachable:
            # Off, asleep, or out of range. Not a failure of ours, so the entities go unknown, not unavailable.
            return {"scope_reachable": False}
        now = self.hass.loop.time()
        if self._sessions_at is None or now - self._sessions_at > SESSIONS_EVERY.total_seconds():
            try:
                self._sessions = await self.hass.async_add_executor_job(self.client.list_sessions_blocking)
                self._sessions_at = now
            except OSError as err:
                _LOGGER.debug("Could not list capture sessions: %s", err)
        data["sessions"] = self._sessions
        return data
