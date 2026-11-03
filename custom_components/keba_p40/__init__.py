"""KEBA P40 integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import KebaApi
from .const import (
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import KebaDataUpdateCoordinator
from .services import async_setup_services

type KebaConfigEntry = ConfigEntry[KebaDataUpdateCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the KEBA P40 actions."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: KebaConfigEntry) -> bool:
    """Set up KEBA P40 from a config entry."""
    config = {**entry.data, **entry.options}
    session = async_get_clientsession(
        hass,
        verify_ssl=config[CONF_VERIFY_SSL],
    )
    api = KebaApi(
        session,
        config[CONF_HOST],
        config[CONF_PORT],
        DEFAULT_USERNAME,
        config[CONF_PASSWORD],
    )
    coordinator = KebaDataUpdateCoordinator(
        hass,
        api,
        entry.data[CONF_SERIAL],
        config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        entry.entry_id,
    )
    await coordinator.async_load_stored_state()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KebaConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(
    hass: HomeAssistant,
    entry: KebaConfigEntry,
) -> None:
    """Reload after configuration changes."""
    await hass.config_entries.async_reload(entry.entry_id)
