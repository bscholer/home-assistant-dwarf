"""Install, configure and start the DWARF 3 relay app through the Supervisor.

Used by the config flow, so someone choosing full control does not have to open the app store.
The app repository lives at the URL below. Adding it is disclosed to the user in the flow.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.hassio import is_hassio

_LOGGER = logging.getLogger(__name__)

APP_REPOSITORY = "https://github.com/bscholer/home-assistant-dwarf3"
# The Supervisor names a third-party app <first 8 of sha1(repository url)>_<slug>.
APP_SLUG = "bbc0cf72_dwarf3_relay"
APP_DEFAULT_OPTIONS = {
    "scope_host": "",
    "auth": False,
    "api_token": "",
    "latitude": "",
    "longitude": "",
    "timezone": "",
}

READY_TRIES = 40
READY_WAIT_S = 3.0


class AppSetupError(Exception):
    """Something stopped the relay app from being installed or started. The text is for the user."""


def has_supervisor(hass: HomeAssistant) -> bool:
    return is_hassio(hass)


def supervisor_client(hass: HomeAssistant):  # noqa: ANN201
    from homeassistant.components.hassio import get_supervisor_client

    return get_supervisor_client(hass)


async def install_relay_app(
    hass: HomeAssistant, scope_host: str, relay_ready: Callable[[], Awaitable[str | None]]
) -> None:
    """Add the repository, install the app, give it the scope's address, start it, and wait until it answers.

    relay_ready returns None when the relay answers, or an error key. Raises AppSetupError.
    """
    from aiohasupervisor import SupervisorError, SupervisorNotFoundError
    from aiohasupervisor.models import AddonsOptions, AddonState, StoreAddRepository

    client = supervisor_client(hass)
    try:
        known = [(r.source or "").rstrip("/").lower() for r in await client.store.repositories_list()]
        if APP_REPOSITORY.lower() not in known:
            _LOGGER.info("Adding the DWARF 3 app repository %s", APP_REPOSITORY)
            await client.store.add_repository(StoreAddRepository(repository=APP_REPOSITORY))
            await client.store.reload()
        try:
            info = await client.addons.addon_info(APP_SLUG)
        except SupervisorNotFoundError:
            _LOGGER.info("Installing the DWARF 3 relay app")
            await client.store.install_addon(APP_SLUG)
            info = await client.addons.addon_info(APP_SLUG)
        options = dict(info.options or {})
        if not options.get("scope_host"):
            # Never overwrite an address the user already entered.
            await client.addons.set_addon_options(
                APP_SLUG, AddonsOptions(config={**APP_DEFAULT_OPTIONS, **options, "scope_host": scope_host})
            )
            if info.state in (AddonState.STARTED, AddonState.STARTUP):
                await client.addons.restart_addon(APP_SLUG)
        if info.state not in (AddonState.STARTED, AddonState.STARTUP):
            await client.addons.start_addon(APP_SLUG)
    except SupervisorError as err:
        raise AppSetupError(str(err) or type(err).__name__) from err

    for _ in range(READY_TRIES):
        error = await relay_ready()
        if error is None:
            return
        if error == "invalid_auth":
            raise AppSetupError("The app is running but asks for an access token. Turn that off in its settings.")
        await asyncio.sleep(READY_WAIT_S)
    raise AppSetupError("The app started but is not answering. Check its Log tab.")
