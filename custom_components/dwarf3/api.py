"""Client for the dwarf3 relay HTTP API. It needs nothing from the relay's own code."""

from __future__ import annotations

import base64
import json
from typing import Any

import aiohttp


class RelayError(Exception):
    """Any failure talking to the relay."""


class RelayUnreachable(RelayError):
    """The relay did not answer."""


class RelayUnauthorized(RelayError):
    """The relay wants a token and ours is missing or wrong."""


class RelayBusy(RelayError):
    """Another job or client holds the scope."""


class ScopeError(RelayError):
    """The relay answered, but the scope did not."""


class RelayClient:
    def __init__(self, session: aiohttp.ClientSession, host: str, port: int, token: str | None = None) -> None:
        self._session = session
        self._base = f"http://{host}:{port}"
        self._token = token

    async def _request(self, method: str, path: str, *, timeout: float = 20, **kwargs: Any) -> Any:
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        try:
            async with self._session.request(
                method, self._base + path, headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout), **kwargs,
            ) as response:
                text = await response.text()
                try:
                    body = json.loads(text)
                except ValueError:
                    # A relay crash answers with plain text, not the {"detail", "code"} shape.
                    body = {"detail": text.strip()[:200] or f"HTTP {response.status}"}
                if response.status == 401:
                    raise RelayUnauthorized(_detail(body))
                if response.status == 409:
                    raise RelayBusy(_detail(body))
                if response.status >= 400:
                    raise ScopeError(_detail(body)) if response.status == 502 else RelayError(_detail(body))
                return body
        except (aiohttp.ClientError, TimeoutError) as err:
            raise RelayUnreachable(str(err) or type(err).__name__) from err

    async def capabilities(self) -> dict[str, Any]:
        return await self._request("GET", "/api/capabilities")

    async def status(self) -> dict[str, Any]:
        return await self._request("GET", "/api/status", timeout=60)

    async def check_token(self) -> None:
        """Raise RelayUnauthorized if the token is wrong, without touching the scope.

        An out-of-range move is refused after the auth check and before any scope access,
        so a good token gets a 422 and a bad one a 401.
        """
        try:
            await self._request("POST", "/api/move", json={"angle": 0, "length": 0, "seconds": 0})
        except RelayUnauthorized:
            raise
        except RelayError:
            return

    async def frame(self, camera: str = "wide") -> bytes:
        # A tele frame can take over a minute, since it waits for a keyframe.
        body = await self._request("GET", "/api/frame", params={"camera": camera}, timeout=90)
        return base64.b64decode(body["data"])

    async def close_barrel(self) -> None:
        await self._request("POST", "/api/close_barrel", timeout=120)

    async def stop_capture(self) -> None:
        await self._request("POST", "/api/capture/stop")

    async def prepare(self) -> None:
        await self._request("POST", "/api/prepare", timeout=300)

    async def calibrate(self) -> None:
        await self._request("POST", "/api/calibrate", timeout=480)

    async def sessions(self) -> list[str]:
        return (await self._request("GET", "/api/sessions", timeout=60))["sessions"]

    async def start_dark(self, frames: int, exposure: str, wide: bool) -> None:
        await self._request("POST", "/api/dark", json={"frames": frames, "exposure": exposure, "wide": wide})

    async def move(self, angle: float, length: float, seconds: float) -> None:
        await self._request("POST", "/api/move", json={"angle": angle, "length": length, "seconds": seconds})

    async def point(self, pitch: float, rotation: float | None) -> None:
        await self._request("POST", "/api/point", json={"pitch": pitch, "rotation": rotation}, timeout=120)

    async def delete_session(self, session: str) -> None:
        await self._request("POST", "/api/sessions/delete", json={"session": session}, timeout=120)

    async def goto(self, name: str, ra_hours: float, dec_degrees: float) -> None:
        await self._request(
            "POST", "/api/goto", json={"name": name, "ra_hours": ra_hours, "dec_degrees": dec_degrees}, timeout=180
        )

    async def start_capture(self, frames: int, exposure: str, gain: int, filter_: str) -> dict[str, Any]:
        return await self._request(
            "POST", "/api/capture", json={"frames": frames, "exposure": exposure, "gain": gain, "filter": filter_}
        )


def _detail(body: Any) -> str:
    if isinstance(body, dict):
        return str(body.get("detail") or body.get("code") or "error")
    return "error"
