"""Constants for the KEBA P40 integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "keba_p40"

CONF_PORT: Final = "port"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_SERIAL: Final = "serial"
CONF_TOKEN_ID: Final = "token_id"
CONF_VERIFY_SSL: Final = "verify_ssl"

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"

SUBENTRY_TYPE_CARD: Final = "card"

SERVICE_START_CHARGING: Final = "start_charging"
SERVICE_START_CHARGING_WITH_TOKEN: Final = "start_charging_with_token"

SESSION_CARD_NONE: Final = "no_card"
SESSION_CARD_UNKNOWN: Final = "unknown_card"

DEFAULT_USERNAME: Final = "admin"
DEFAULT_PORT: Final = 8443
DEFAULT_SCAN_INTERVAL: Final = 5

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.{{entry_id}}"

PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]
