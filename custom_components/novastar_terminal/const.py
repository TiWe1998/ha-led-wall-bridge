"""Constants for the NovaStar Terminal integration."""

DOMAIN = "novastar_terminal"

# Config entry types
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_DEVICE = "device"
ENTRY_TYPE_CLOUD = "cloud"

# Device entry
CONF_SN = "sn"
CONF_PERSIST = "persist"  # legacy option, now a switch entity
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SCREENSHOT_INTERVAL = "screenshot_interval"

# Cloud entry
CONF_CLOUD_DOMAIN = "cloud_domain"
CONF_APP_KEY = "app_key"
CONF_APP_SECRET = "app_secret"

DEFAULT_PORT = 16674
DEFAULT_USERNAME = "admin"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_SCREENSHOT_INTERVAL = 60
DEFAULT_CLOUD_DOMAIN = "open-us.vnnox.com"
CLOUD_SCAN_INTERVAL = 300

PORTAL_URL_EU = "https://open-eu.vnnox.com"
PORTAL_URL_US = "https://open-us.vnnox.com"
DOCS_URL = "https://github.com/GITHUB_USER/ha-led-wall-bridge"

# Feature key -> GET path used for automatic feature detection
FEATURE_PATHS: dict[str, str] = {
    "brightness": "/core/v1/brightness",
    "volume": "/core/v1/device/volume",
    "screen": "/core/v1/screen/status",
    "brightness_policy": "/core/v1/brightness/timing-policy",
    "power_policy": "/core/v1/screen/power-policy",
    "time": "/core/v1/device/time",
    "relay": "/core/v1/relay/status",
}
