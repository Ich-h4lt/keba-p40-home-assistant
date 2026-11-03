"""Actions for the KEBA P40 integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .cards import is_valid_token_id
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    CONF_TOKEN_ID,
    DOMAIN,
    SERVICE_START_CHARGING,
    SERVICE_START_CHARGING_WITH_TOKEN,
)
from .coordinator import KebaDataUpdateCoordinator

START_CHARGING_SCHEMA = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string})
START_CHARGING_WITH_TOKEN_SCHEMA = START_CHARGING_SCHEMA.extend(
    {vol.Required(CONF_TOKEN_ID): cv.string}
)


@callback
def _async_get_coordinator(
    hass: HomeAssistant,
    call: ServiceCall,
) -> KebaDataUpdateCoordinator:
    """Return the coordinator of the config entry named in the action."""
    entry = hass.config_entries.async_get_entry(call.data[ATTR_CONFIG_ENTRY_ID])
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found",
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
        )
    return entry.runtime_data


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the KEBA P40 actions."""

    async def _async_start_charging(call: ServiceCall) -> None:
        """Start charging without an RFID token."""
        await _async_get_coordinator(hass, call).async_start_charging()

    async def _async_start_charging_with_token(call: ServiceCall) -> None:
        """Start charging authorized by the given RFID token."""
        coordinator = _async_get_coordinator(hass, call)
        token_id = call.data[CONF_TOKEN_ID].strip()
        if not is_valid_token_id(token_id):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_token_id",
            )
        await coordinator.async_start_charging_with_token(token_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_CHARGING,
        _async_start_charging,
        schema=START_CHARGING_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_START_CHARGING_WITH_TOKEN,
        _async_start_charging_with_token,
        schema=START_CHARGING_WITH_TOKEN_SCHEMA,
    )
