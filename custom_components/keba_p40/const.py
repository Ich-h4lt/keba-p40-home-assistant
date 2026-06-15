"""Constants for the KEBA P40 integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "keba_p40"

CONF_PORT: Final = "port"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_SERIAL: Final = "serial"
CONF_VERIFY_SSL: Final = "verify_ssl"

DEFAULT_USERNAME: Final = "admin"
DEFAULT_PORT: Final = 8443
DEFAULT_SCAN_INTERVAL: Final = 10

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.{{entry_id}}"

PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]
