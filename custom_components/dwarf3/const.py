"""Constants for the DWARF 3 integration."""

DOMAIN = "dwarf3"

CONF_TOKEN = "token"
CONF_MAC = "mac"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORT = 9902
DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 10

# The relay publishes this in /api/capabilities. A different major version is refused.
SUPPORTED_SPEC_MAJOR = 0

# What a relay from before spec 0.2 accepts, and what a DWARF 3 offers. Newer relays list the connected model's
# own choices in capabilities["capture"].
EXPOSURES = ["15", "30", "60"]
FILTERS = ["vis", "astro", "duo"]  # every filter name any model uses; the relay refuses one its model lacks
LEGACY_CAPTURE = {"filters": FILTERS, "exposures": EXPOSURES, "wide_darks": True}

# Models. Only the DWARF 3 is tested; the others follow dwarf_python_api and the relay.
DEFAULT_MODEL = "DWARF 3"
MODEL_BY_DEVICE_ID = {1: "DWARF II", 2: "DWARF 3", 4: "DWARF mini"}  # deviceId in the scope's /deviceInfo
MODEL_BY_NAME_PREFIX = (("DWARF3_", "DWARF 3"), ("DWARF_mini_", "DWARF mini"), ("DWARF_", "DWARF II"))
# Motor pitch for straight up. Unknown for the other models, so Point up refuses there rather than guess.
POINT_UP_PITCH = {"DWARF 3": 172.5}
# FTP folders that may hold the astro sessions, tried in order.
ALBUM_ROOTS = {
    "DWARF 3": ("/Astronomy",),
    "DWARF mini": ("/Astronomy", "/DWARF_mini/Astronomy"),
    "DWARF II": ("/DWARF_II/Astronomy", "/Astronomy"),
}


def model_from_device_info(info: dict) -> str | None:
    """The model named by a /deviceInfo reply: its deviceId, else its device name. None when neither says."""
    if info.get("deviceId") in MODEL_BY_DEVICE_ID:
        return MODEL_BY_DEVICE_ID[info["deviceId"]]
    name = str(info.get("deviceName") or "")
    return next((model for prefix, model in MODEL_BY_NAME_PREFIX if name.startswith(prefix)), None)


CONF_MODE = "mode"
MODE_RELAY = "relay"
MODE_DIRECT = "direct"
DIRECT_DEFAULT_SCAN_INTERVAL = 60
SCOPE_API_PORT = 8082
ALBUM_ROOT = "/Astronomy"  # the DWARF 3; see ALBUM_ROOTS

RTSP_PORT = 554
# Where each camera's live video is on the scope.
RTSP_PATHS = {"wide": "ch1/stream0", "tele": "ch0/stream0"}
