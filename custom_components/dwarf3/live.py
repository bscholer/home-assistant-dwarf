"""Follow the relay's live status stream, so Home Assistant is never more than a moment behind it.

The relay pushes a status the moment anything changes. This listens quietly: one warning when the link is
lost, one line when it is back, and nothing for the retries in between. Without the stream (an older relay)
the integration simply keeps polling.
"""

from __future__ import annotations

import asyncio
import logging

from .api import EventsUnsupported, RelayError, RelayUnreachable
from .coordinator import Dwarf3Coordinator

_LOGGER = logging.getLogger(__name__)

FIRST_RETRY_S = 1.0
LONGEST_RETRY_S = 15.0


async def follow_relay(coordinator: Dwarf3Coordinator) -> None:
    """Run until cancelled."""
    delay = FIRST_RETRY_S
    warned = False
    connected_once = False
    while True:
        try:
            async for pushed in coordinator.client.events():
                if not coordinator.live_connected:
                    coordinator.live_connected = True
                    if warned:
                        _LOGGER.info("Live updates from the relay are back")
                        warned = False
                    if connected_once:
                        # Anything could have changed while we were away.
                        coordinator.hass.async_create_task(coordinator.async_request_refresh())
                    connected_once = True
                    delay = FIRST_RETRY_S
                coordinator.apply_live(pushed)
            error: Exception | None = None  # the relay closed the stream, such as when it restarts
        except EventsUnsupported:
            _LOGGER.debug("The relay has no live event stream, so status is polled")
            return
        except asyncio.CancelledError:
            coordinator.live_connected = False
            raise
        except RelayError as err:
            error = err
        coordinator.live_connected = False
        if connected_once and not warned:
            _LOGGER.warning("Lost the live connection to the relay (%s). Trying again", error or "it closed")
            warned = True
        else:
            _LOGGER.debug("Live connection to the relay failed: %s", error or "closed")
        if isinstance(error, RelayUnreachable) or error is None:
            await asyncio.sleep(delay)
            delay = min(delay * 2, LONGEST_RETRY_S)
        else:
            await asyncio.sleep(LONGEST_RETRY_S)
