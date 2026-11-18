"""Constants for the DWARF 3 integration."""

DOMAIN = "dwarf3"

CONF_TOKEN = "token"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORT = 9902
DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 10

# The relay publishes this in /api/capabilities. A different major version is refused.
SUPPORTED_SPEC_MAJOR = 0

EXPOSURES = ["15", "30", "60"]
FILTERS = ["vis", "astro", "duo"]
