"""Config flow for KEBA P40."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    KebaApi,
    KebaApiError,
    KebaAuthenticationError,
    KebaConnectionError,
)
from .const import (
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    CONF_VERIFY_SSL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
)

PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(
        type=TextSelectorType.PASSWORD,
        autocomplete="current-password",
    )
)


class KebaP40ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a KEBA P40 config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._connection_data: dict[str, Any] = {}
        self._wallboxes: list[dict[str, Any]] = []
        self._reauth_entry: config_entries.ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return KebaP40OptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Collect connection details and test the API."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                session = async_get_clientsession(
                    self.hass,
                    verify_ssl=user_input[CONF_VERIFY_SSL],
                )
                api = KebaApi(
                    session,
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                    DEFAULT_USERNAME,
                    user_input[CONF_PASSWORD],
                )
                await api.async_login()
                self._wallboxes = await api.async_get_wallboxes()
            except KebaAuthenticationError:
                errors["base"] = "invalid_auth"
            except KebaConnectionError:
                errors["base"] = "cannot_connect"
            except KebaApiError:
                errors["base"] = "unknown"
            else:
                if not self._wallboxes:
                    errors["base"] = "no_wallboxes"
                else:
                    self._connection_data = user_input
                    if len(self._wallboxes) == 1:
                        return await self._async_create_entry(self._wallboxes[0])
                    return await self.async_step_wallbox()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
                vol.Required(CONF_VERIFY_SSL, default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_wallbox(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Let the user choose a wallbox when several are configured."""
        choices = {
            str(wallbox["serialNumber"]): (
                wallbox.get("alias") or str(wallbox["serialNumber"])
            )
            for wallbox in self._wallboxes
        }
        if user_input is not None:
            serial = user_input[CONF_SERIAL]
            wallbox = next(
                item
                for item in self._wallboxes
                if str(item["serialNumber"]) == serial
            )
            return await self._async_create_entry(wallbox)

        return self.async_show_form(
            step_id="wallbox",
            data_schema=vol.Schema(
                {vol.Required(CONF_SERIAL): vol.In(choices)}
            ),
        )

    async def _async_create_entry(
        self,
        wallbox: dict[str, Any],
    ) -> config_entries.ConfigFlowResult:
        serial = str(wallbox["serialNumber"])
        await self.async_set_unique_id(serial)
        self._abort_if_unique_id_configured()

        title = wallbox.get("alias") or f"KEBA P40 {serial}"
        return self.async_create_entry(
            title=title,
            data={**self._connection_data, CONF_SERIAL: serial},
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> config_entries.ConfigFlowResult:
        """Start reauthentication."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Confirm updated credentials."""
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None
        current = {**self._reauth_entry.data, **self._reauth_entry.options}

        if user_input is not None:
            try:
                api = KebaApi(
                    async_get_clientsession(
                        self.hass,
                        verify_ssl=current[CONF_VERIFY_SSL],
                    ),
                    current[CONF_HOST],
                    current[CONF_PORT],
                    DEFAULT_USERNAME,
                    user_input[CONF_PASSWORD],
                )
                await api.async_login()
            except KebaAuthenticationError:
                errors["base"] = "invalid_auth"
            except KebaConnectionError:
                errors["base"] = "cannot_connect"
            except KebaApiError:
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        **self._reauth_entry.data,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                    options={
                        **self._reauth_entry.options,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR}
            ),
            errors=errors,
        )


class KebaP40OptionsFlow(config_entries.OptionsFlow):
    """Handle KEBA P40 options."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Edit connection and polling options."""
        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            try:
                api = KebaApi(
                    async_get_clientsession(
                        self.hass,
                        verify_ssl=user_input[CONF_VERIFY_SSL],
                    ),
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                    DEFAULT_USERNAME,
                    user_input[CONF_PASSWORD],
                )
                await api.async_login()
                wallboxes = await api.async_get_wallboxes()
                serials = {
                    str(wallbox.get("serialNumber"))
                    for wallbox in wallboxes
                }
                if self.config_entry.data[CONF_SERIAL] not in serials:
                    errors["base"] = "wallbox_not_found"
            except KebaAuthenticationError:
                errors["base"] = "invalid_auth"
            except KebaConnectionError:
                errors["base"] = "cannot_connect"
            except KebaApiError:
                errors["base"] = "unknown"
            else:
                if not errors:
                    return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=current[CONF_HOST],
                ): str,
                vol.Required(
                    CONF_PORT,
                    default=current[CONF_PORT],
                ): int,
                vol.Required(
                    CONF_PASSWORD,
                    default=current[CONF_PASSWORD],
                ): PASSWORD_SELECTOR,
                vol.Required(
                    CONF_VERIFY_SSL,
                    default=current[CONF_VERIFY_SSL],
                ): bool,
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=current.get(
                        CONF_SCAN_INTERVAL,
                        DEFAULT_SCAN_INTERVAL,
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
