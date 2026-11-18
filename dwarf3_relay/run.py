"""Read the app options and start the relay. Home Assistant puts them in /data/options.json."""

import json
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

options = json.loads(Path("/data/options.json").read_text())
host = (options.get("scope_host") or "").strip()
if not host:
    sys.exit("Set scope_host to the scope's IP address in the app configuration.")

env = os.environ
env["DWARF3_HOST"] = host
if not options.get("auth", True):
    env["DWARF3_AUTH"] = "off"
else:
    token = (options.get("api_token") or "").strip()
    if not token:
        saved = Path("/data/api-token")
        if not saved.exists():
            saved.write_text(secrets.token_urlsafe(32))
            saved.chmod(0o600)
        token = saved.read_text().strip()
        print(f"No api_token option is set. Use this token in the integration: {token}", flush=True)
    env["DWARF3_API_TOKEN"] = token

# `prepare` needs the site. Leave these empty and `prepare` fails, with nothing guessed.
if options.get("latitude") and options.get("longitude") and options.get("timezone"):
    zone = options["timezone"]
    env["DWARF3_LAT"], env["DWARF3_LON"], env["DWARF3_TZ"] = options["latitude"], options["longitude"], zone
    offset = datetime.now(ZoneInfo(zone)).utcoffset().total_seconds() / 3600
    env["DWARF3_UTC_OFFSET"] = str(offset)

os.execvp("dwarf3", ["dwarf3", "proxy", "--log-dir", "/data"])
