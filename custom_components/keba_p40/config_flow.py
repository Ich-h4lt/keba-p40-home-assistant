"""Config flow for KEBA P40."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util

from .api import (
    KebaApi,
    KebaApiError,
    KebaAuthenticationError,
    KebaConnectionError,
)
from .cards import (
    KnownCard,
    async_get_known_cards,
    configured_token_ids,
    is_valid_token_id,
    mask_token_id,
)
from .const import (
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    CONF_TOKEN_ID,
    CONF_VERIFY_SSL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
    SUBENTRY_TYPE_CARD,
)

PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(
        type=TextSelectorType.PASSWORD,
        autocomplete="current-password",
    )
)

CONF_CARD = "card"
CARD_NAME_MAX_LENGTH = 40


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

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls,
        config_entry: config_entries.ConfigEntry,
    ) -> dict[str, type[config_entries.ConfigSubentryFlow]]:
        """Return the subentry types: charging cards."""
        return {SUBENTRY_TYPE_CARD: KebaCardSubentryFlow}

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


def _validate_card_name(name: str) -> str | None:
    """Return the stripped comment, or None if it is empty or too long."""
    name = name.strip()
    return name if 0 < len(name) <= CARD_NAME_MAX_LENGTH else None


class KebaCardSubentryFlow(config_entries.ConfigSubentryFlow):
    """Add or edit a charging card.

    The token id is stored only in the subentry data. It is never put into a
    title, a unique id or a form option value, and shown only shortened.
    """

    def __init__(self) -> None:
        self._known_cards: list[KnownCard] = []

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.SubentryFlowResult:
        """Offer the cards known to the wallbox or manual entry."""
        entry = self._get_entry()
        configured = configured_token_ids(entry)
        known: list[KnownCard] = []
        if entry.state is config_entries.ConfigEntryState.LOADED:
            try:
                known = await async_get_known_cards(entry.runtime_data.api)
            except (KebaApiError, ValueError):
                known = []
        self._known_cards = [
            card for card in known if card.token_id not in configured
        ]
        if not self._known_cards:
            return await self.async_step_manual()
        return self.async_show_menu(
            step_id="user",
            menu_options=["pick", "manual"],
        )

    async def async_step_pick(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.SubentryFlowResult:
        """Choose one of the cards known to the wallbox."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = _validate_card_name(user_input[CONF_NAME])
            index = int(user_input[CONF_CARD])
            if name is None:
                errors[CONF_NAME] = "invalid_name"
            elif not 0 <= index < len(self._known_cards):
                errors[CONF_CARD] = "invalid_card"
            else:
                return self._async_create_card(
                    self._known_cards[index].token_id, name
                )

        options = [
            SelectOptionDict(
                value=str(index),
                label=(
                    f"{mask_token_id(card.token_id)} · "
                    f"{dt_util.as_local(card.last_used).date().isoformat()}"
                    if card.last_used
                    else mask_token_id(card.token_id)
                ),
            )
            for index, card in enumerate(self._known_cards)
        ]
        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CARD, default="0"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(CONF_NAME): str,
                }
            ),
            errors=errors,
        )

    async def async_step_manual(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.SubentryFlowResult:
        """Enter the id of a card."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token_id = user_input[CONF_TOKEN_ID].strip()
            name = _validate_card_name(user_input[CONF_NAME])
            if not is_valid_token_id(token_id):
                errors[CONF_TOKEN_ID] = "invalid_token_id"
            elif token_id in configured_token_ids(self._get_entry()):
                errors[CONF_TOKEN_ID] = "already_configured"
            elif name is None:
                errors[CONF_NAME] = "invalid_name"
            else:
                return self._async_create_card(token_id, name)

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN_ID): str,
                    vol.Required(CONF_NAME): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.SubentryFlowResult:
        """Change the comment of a card."""
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            name = _validate_card_name(user_input[CONF_NAME])
            if name is None:
                errors[CONF_NAME] = "invalid_name"
            else:
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=name,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_NAME, default=subentry.title): str}
            ),
            description_placeholders={
                "card": mask_token_id(subentry.data[CONF_TOKEN_ID])
            },
            errors=errors,
        )

    @callback
    def _async_create_card(
        self,
        token_id: str,
        name: str,
    ) -> config_entries.SubentryFlowResult:
        """Store the card, unless another subentry already has its id."""
        if token_id in configured_token_ids(self._get_entry()):
            return self.async_abort(reason="already_configured")
        return self.async_create_entry(title=name, data={CONF_TOKEN_ID: token_id})
