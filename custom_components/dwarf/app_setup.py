"""Install, configure and start the DWARF relay app through the Supervisor.

Used by the config flow, so someone choosing full control does not have to open the app store.
The app repository lives at the URL below. Adding it is disclosed to the user in the flow.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.hassio import is_hassio

_LOGGER = logging.getLogger(__name__)

APP_REPOSITORY = "https://github.com/bscholer/home-assistant-dwarf"
# The repository's name before the rename. GitHub redirects it, and installs that added it keep its app.
LEGACY_APP_REPOSITORY = "https://github.com/bscholer/home-assistant-dwarf3"


def app_slug(repository: str) -> str:
    """The Supervisor names a third-party app <first 8 of sha1(repository url)>_<slug>."""
    return f"{hashlib.sha1(repository.lower().encode()).hexdigest()[:8]}_dwarf3_relay"


APP_SLUG = app_slug(APP_REPOSITORY)
LEGACY_APP_SLUG = app_slug(LEGACY_APP_REPOSITORY)
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
        slug = APP_SLUG
        if LEGACY_APP_REPOSITORY.lower() in known:
            slug = LEGACY_APP_SLUG
        elif APP_REPOSITORY.lower() not in known:
            _LOGGER.info("Adding the DWARF app repository %s", APP_REPOSITORY)
            await client.store.add_repository(StoreAddRepository(repository=APP_REPOSITORY))
            await client.store.reload()
        try:
            info = await client.addons.addon_info(slug)
        except SupervisorNotFoundError:
            _LOGGER.info("Installing the DWARF relay app")
            await client.store.install_addon(slug)
            info = await client.addons.addon_info(slug)
        options = dict(info.options or {})
        if not options.get("scope_host"):
            # Never overwrite an address the user already entered.
            await client.addons.set_addon_options(
                slug, AddonsOptions(config={**APP_DEFAULT_OPTIONS, **options, "scope_host": scope_host})
            )
            if info.state in (AddonState.STARTED, AddonState.STARTUP):
                await client.addons.restart_addon(slug)
        if info.state not in (AddonState.STARTED, AddonState.STARTUP):
            await client.addons.start_addon(slug)
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
