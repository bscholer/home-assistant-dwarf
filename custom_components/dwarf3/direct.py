"""Read-only access to the scope itself, without the relay.

This never opens the control WebSocket, the scope's one control connection, so the DWARFLAB app keeps working.
It reads only what the scope gives out over plain HTTP and FTP. The deviceInfo reply also holds the home Wi-Fi
password in clear text, so nothing here keeps or logs more of it than the card figures.
"""

from __future__ import annotations

import ftplib
import re
from typing import Any

import aiohttp

from .const import ALBUM_ROOT, SCOPE_API_PORT

RAW_SESSION = re.compile(r"^DWARF_RAW_")
STACK_FILE = "stacked.jpg"
THUMBNAIL_FILE = "stacked_thumbnail.jpg"
STAMP = re.compile(r"(\d{4}-\d\d-\d\d-\d\d-\d\d-\d\d-\d+)$")


def session_order(name: str) -> tuple[str, str]:
    """Order sessions by the time in the folder name, oldest first."""
    found = STAMP.search(name)
    return (found.group(1) if found else "", name)


class ScopeUnreachable(Exception):
    """The scope did not answer on its HTTP API."""


class ScopeDirectClient:
    def __init__(self, session: aiohttp.ClientSession, host: str) -> None:
        self._session = session
        self.host = host

    async def device_info(self) -> dict[str, Any]:
        """Return the deviceInfo data. It holds secrets: callers pick fields and drop the rest."""
        try:
            async with self._session.post(
                f"http://{self.host}:{SCOPE_API_PORT}/deviceInfo",
                json={},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                body = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise ScopeUnreachable(str(err) or type(err).__name__) from err
        data = body.get("data") if isinstance(body, dict) else None
        return data if isinstance(data, dict) else {}

    async def sd_card(self) -> dict[str, Any]:
        """Return the card figures in GB. Keys are missing when the scope does not say."""
        card = (await self.device_info()).get("sdCardInfo") or {}
        out: dict[str, Any] = {"has_sd_card": bool(card.get("hasSdcard"))}
        if card.get("hasSdcard"):
            for key, field in (("sd_free_gb", "availableSize"), ("sd_total_gb", "totalSize")):
                if isinstance(card.get(field), (int, float)):
                    out[key] = float(card[field])
        return out

    def fetch_stack_blocking(self, known: tuple[str, int] | None) -> tuple[str, int, bytes | None] | None:
        """The newest session's stacked.jpg, over FTP. Returns (session, size, jpeg), with jpeg None if unchanged.

        Run it in an executor. `known` is the (session, size) already held, so a check costs two listings.
        """
        ftp = ftplib.FTP(self.host, timeout=30)
        try:
            ftp.login()
            names = [n.rsplit("/", 1)[-1] for n in ftp.nlst(ALBUM_ROOT)]
            sessions = sorted((n for n in names if RAW_SESSION.match(n)), key=session_order)
            if not sessions:
                return None
            session = sessions[-1]
            lines: list[str] = []
            ftp.dir(f"{ALBUM_ROOT}/{session}", lines.append)
            size = next(
                (int(p[4]) for p in (line.split(None, 8) for line in lines) if len(p) == 9 and p[8] == STACK_FILE),
                None,
            )
            if size is None:
                return None
            if known == (session, size):
                return session, size, None
            buffer = bytearray()
            ftp.retrbinary(f"RETR {ALBUM_ROOT}/{session}/{STACK_FILE}", buffer.extend)
            return session, size, bytes(buffer)
        finally:
            try:
                ftp.quit()
            except (ftplib.Error, OSError):
                ftp.close()

    def index_stacks_blocking(self, known: dict[str, dict[str, int | None]]) -> dict[str, dict[str, int | None]]:
        """Which sessions have a stack, and the size of the stack and its thumbnail. Run it in an executor.

        Older sessions never change, so only sessions not in `known`, and the newest, are listed.
        """
        ftp = ftplib.FTP(self.host, timeout=30)
        try:
            ftp.login()
            names = sorted(
                (n.rsplit("/", 1)[-1] for n in ftp.nlst(ALBUM_ROOT) if RAW_SESSION.match(n.rsplit("/", 1)[-1])),
                key=session_order,
            )
            result: dict[str, dict[str, int | None]] = {}
            for index, session in enumerate(names):
                if session in known and index != len(names) - 1:
                    result[session] = known[session]
                    continue
                lines: list[str] = []
                ftp.dir(f"{ALBUM_ROOT}/{session}", lines.append)
                sizes = {p[8]: int(p[4]) for p in (line.split(None, 8) for line in lines) if len(p) == 9}
                result[session] = {"stack": sizes.get(STACK_FILE), "thumb": sizes.get(THUMBNAIL_FILE)}
            return result
        finally:
            try:
                ftp.quit()
            except (ftplib.Error, OSError):
                ftp.close()

    def read_file_blocking(self, session: str, name: str) -> bytes:
        """One file from a session folder, over FTP. Run it in an executor."""
        ftp = ftplib.FTP(self.host, timeout=30)
        try:
            ftp.login()
            buffer = bytearray()
            ftp.retrbinary(f"RETR {ALBUM_ROOT}/{session}/{name}", buffer.extend)
            return bytes(buffer)
        finally:
            try:
                ftp.quit()
            except (ftplib.Error, OSError):
                ftp.close()

    def list_sessions_blocking(self) -> list[str]:
        """List capture sessions over anonymous FTP. Run it in an executor."""
        ftp = ftplib.FTP(self.host, timeout=20)
        try:
            ftp.login()
            names = [n.rsplit("/", 1)[-1] for n in ftp.nlst(ALBUM_ROOT)]
        finally:
            try:
                ftp.quit()
            except (ftplib.Error, OSError):
                ftp.close()
        return sorted((n for n in names if RAW_SESSION.match(n)), key=session_order)
