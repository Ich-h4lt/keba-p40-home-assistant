"""Charging card helpers for KEBA P40."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.util import dt as dt_util

from .api import KebaApi
from .const import CONF_TOKEN_ID, SUBENTRY_TYPE_CARD

KNOWN_CARD_SESSIONS = 50
TOKEN_ID_PATTERN = re.compile(r"\S{1,36}")


@dataclass(frozen=True)
class KnownCard:
    """A card the wallbox has seen."""

    token_id: str
    last_used: datetime | None


def mask_token_id(token_id: str) -> str:
    """Return a shortened token id that is safe to display."""
    if len(token_id) <= 4:
        return "…"
    return f"{token_id[:2]}…{token_id[-2:]}"


def is_valid_token_id(token_id: str) -> bool:
    """Return whether a token id has 1 to 36 characters and no whitespace."""
    return TOKEN_ID_PATTERN.fullmatch(token_id) is not None


def card_subentries(entry: ConfigEntry) -> list[ConfigSubentry]:
    """Return the charging cards configured for a config entry."""
    return [
        subentry
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_CARD
    ]


def configured_token_ids(entry: ConfigEntry) -> dict[str, str]:
    """Map the token id of each configured card to its comment."""
    return {
        card.data[CONF_TOKEN_ID]: card.title for card in card_subentries(entry)
    }


def _timestamp_ms(value: Any) -> int:
    """Return a millisecond timestamp, or 0 if the value is not one."""
    return int(value) if isinstance(value, (int, float)) and value > 0 else 0


async def async_get_known_cards(api: KebaApi) -> list[KnownCard]:
    """Return the cards from the token list and recent sessions, newest first."""
    last_used: dict[str, int] = {}

    def _remember(token_id: Any, used_ms: int) -> None:
        if token_id:
            key = str(token_id)
            last_used[key] = max(last_used.get(key, 0), used_ms)

    for token in await api.async_get_rfid_tokens():
        _remember(
            token.get("id"),
            max(
                _timestamp_ms(token.get("usedDate")),
                _timestamp_ms(token.get("changedDate")),
            ),
        )
    for session in await api.async_get_sessions(KNOWN_CARD_SESSIONS):
        _remember(session.get("tokenId"), _timestamp_ms(session.get("startDate")))

    return [
        KnownCard(
            token_id,
            dt_util.utc_from_timestamp(used_ms / 1000) if used_ms else None,
        )
        for token_id, used_ms in sorted(
            last_used.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    ]
