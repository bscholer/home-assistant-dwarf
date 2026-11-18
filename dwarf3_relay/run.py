"""Read the app options and start the relay. Home Assistant puts them in /data/options.json."""

import json
import os
import secrets
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

options = json.loads(Path("/data/options.json").read_text())
host = (options.get("scope_host") or "").strip()
if not host:
    sys.exit("Enter your scope's IP address under Configuration > Telescope IP address, then start the app again.")

env = os.environ
env["DWARF3_HOST"] = host

if not options.get("auth", False):
    env["DWARF3_AUTH"] = "off"
else:
    token = (options.get("api_token") or "").strip()
    if not token:
        saved = Path("/data/api-token")
        if not saved.exists():
            saved.write_text(secrets.token_urlsafe(32))
            saved.chmod(0o600)
        token = saved.read_text().strip()
        print(f"Your access token is: {token}", flush=True)
    env["DWARF3_API_TOKEN"] = token


def home_assistant_site() -> tuple[str, str, str] | None:
    """This Home Assistant's latitude, longitude and time zone, for the Prepare button."""
    supervisor = env.get("SUPERVISOR_TOKEN")
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


site = None
if options.get("latitude") and options.get("longitude") and options.get("timezone"):
    site = (options["latitude"], options["longitude"], options["timezone"])
else:
    site = home_assistant_site()
if site:
    lat, lon, zone = site
    env["DWARF3_LAT"], env["DWARF3_LON"], env["DWARF3_TZ"] = lat, lon, zone
    env["DWARF3_UTC_OFFSET"] = str(datetime.now(ZoneInfo(zone)).utcoffset().total_seconds() / 3600)
else:
    print("No site location found, so the Prepare button will not work. Set one in Configuration.", flush=True)

print(
    "The relay is starting. In Home Assistant, add the DWARF 3 integration and choose Full control. "
    "In the DWARFLAB app, enter this Home Assistant's IP address as the scope.",
    flush=True,
)
os.execvp("dwarf3", ["dwarf3", "proxy", "--log-dir", "/data"])
