"""Read the app options and start the relay. Home Assistant puts them in /data/options.json."""

import json
import os
import secrets
import sys
import urllib.request
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_DIR = Path("/data")


def home_assistant_site(environ: Mapping[str, str]) -> tuple[str, str, str] | None:
    """This Home Assistant's latitude, longitude and time zone, for the Prepare button."""
    supervisor = environ.get("SUPERVISOR_TOKEN")
    if not supervisor:
        return None
    request = urllib.request.Request(
        "http://supervisor/core/api/config", headers={"Authorization": f"Bearer {supervisor}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as reply:
            config = json.load(reply)
        return str(config["latitude"]), str(config["longitude"]), config["time_zone"]
    except (OSError, ValueError, KeyError):
        return None


def plan(
    options: Mapping[str, object],
    environ: Mapping[str, str],
    data_dir: Path = DATA_DIR,
    fetch_site: Callable[[Mapping[str, str]], tuple[str, str, str] | None] = home_assistant_site,
) -> tuple[dict[str, str], list[str]]:
    """Work out the relay's environment from the app options. Returns (environment, messages for the log).

    Exits with a message when the scope's address is missing.
    """
    host = str(options.get("scope_host") or "").strip()
    if not host:
        sys.exit(
            "Enter your scope's IP address under Configuration > Telescope IP address, then start the app again."
        )
    env: dict[str, str] = {"DWARF3_HOST": host}
    messages: list[str] = []

    if not options.get("auth", False):
        env["DWARF3_AUTH"] = "off"
    else:
        env["DWARF3_AUTH"] = "on"
        token = str(options.get("api_token") or "").strip()
        if not token:
            saved = data_dir / "api-token"
            if not saved.exists():
                saved.write_text(secrets.token_urlsafe(32))
                saved.chmod(0o600)
            token = saved.read_text().strip()
            messages.append(f"Your access token is: {token}")
        env["DWARF3_API_TOKEN"] = token

    if options.get("latitude") and options.get("longitude") and options.get("timezone"):
        site: tuple[str, str, str] | None = (
            str(options["latitude"]),
            str(options["longitude"]),
            str(options["timezone"]),
        )
    else:
        site = fetch_site(environ)
    if site:
        lat, lon, zone = site
        env["DWARF3_LAT"], env["DWARF3_LON"], env["DWARF3_TZ"] = lat, lon, zone
        env["DWARF3_UTC_OFFSET"] = str(datetime.now(ZoneInfo(zone)).utcoffset().total_seconds() / 3600)
    else:
        messages.append("No site location found, so the Prepare button will not work. Set one in Configuration.")

    messages.append(
        "The relay is starting. In Home Assistant, add the DWARF 3 integration and choose Full control. "
        "In the DWARFLAB app, enter this Home Assistant's IP address as the scope."
    )
    return env, messages


def main() -> None:
    options = json.loads((DATA_DIR / "options.json").read_text())
    env, messages = plan(options, os.environ)
    os.environ.update(env)
    for message in messages:
        print(message, flush=True)
    os.execvp("dwarf3", ["dwarf3", "proxy", "--log-dir", str(DATA_DIR)])


if __name__ == "__main__":
    main()
