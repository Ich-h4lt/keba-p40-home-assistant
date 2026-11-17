"""Data coordinator for the KEBA P40 integration."""

from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KebaApi, KebaApiError, KebaAuthenticationError
from .charging import MIN_CHARGING_CURRENT_A, ChargingProfile, charging_power_kw
from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

SESSION_LIMIT = 5
SESSION_RETRY_SECONDS = 30


class KebaDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch shared KEBA status data."""

    def __init__(
        self,
        hass,
        api: KebaApi,
        serial: str,
        scan_interval: int,
        entry_id: str,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.serial = serial
        self.phase_target: int | None = None
        self.session: dict[str, Any] | None = None
        self._session_active: bool | None = None
        self._session_checked: float | None = None
        self._session_loaded = False
        self._store = Store[dict[str, int]](
            hass,
            STORAGE_VERSION,
            STORAGE_KEY.format(entry_id=entry_id),
        )

    async def async_load_stored_state(self) -> None:
        """Load the last phase target successfully sent to the wallbox."""
        stored = await self._store.async_load()
        phases = stored.get("phase_target") if stored else None
        if phases in (1, 3):
            self.phase_target = phases

    async def async_set_phases(self, phases: int) -> None:
        """Set and persist the requested number of charging phases."""
        await self.api.async_set_phases(self.serial, phases)
        self.phase_target = phases
        await self._store.async_save({"phase_target": phases})

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            # One after another, not in parallel: the requests then share a
            # single HTTPS connection, which the wallbox keeps open between
            # polls as long as the scan interval is below its idle timeout.
            wallbox = await self.api.async_get_wallbox(self.serial)
            load_management = await self.api.async_get_load_management()
        except KebaAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except KebaApiError as err:
            raise UpdateFailed(str(err)) from err

        configs = {
            item["key"]: item.get("value")
            for item in load_management.get("configs", [])
            if isinstance(item, dict) and "key" in item
        }
        await self._async_refresh_session(wallbox)
        return {"wallbox": wallbox, "configs": configs}

    async def _async_refresh_session(self, wallbox: dict[str, Any]) -> None:
        """Read the latest session of this wallbox when it may have changed.

        The session list is only needed to tell which card a session uses. It
        is read at startup and when a session starts or ends. While the last
        read failed or an active session is not listed yet, it is read again
        at most every 30 seconds.
        """
        active = bool(wallbox.get("sessionActive"))
        changed = active != self._session_active
        self._session_active = active
        stale = not self._session_loaded or (
            active
            and (self.session is None or self.session.get("status") == "CLOSED")
        )
        now = time.monotonic()
        due = (
            self._session_checked is None
            or now - self._session_checked >= SESSION_RETRY_SECONDS
        )
        if not changed and not (stale and due):
            return

        self._session_checked = now
        try:
            sessions = await self.api.async_get_sessions(SESSION_LIMIT)
        except (KebaApiError, ValueError) as err:
            _LOGGER.debug("Reading the latest session failed: %s", err)
            return
        self._session_loaded = True
        self.session = next(
            (
                session
                for session in sessions
                if str(session.get("wallboxSerialNumber") or self.serial)
                == self.serial
            ),
            None,
        )

    async def async_start_charging(self) -> None:
        """Start charging without an RFID token."""
        try:
            await self.api.async_start_charging(self.serial)
        except KebaApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="start_charging_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.async_request_refresh()

    async def async_start_charging_with_token(self, token_id: str) -> None:
        """Start charging authorized by a specific RFID token."""
        try:
            await self.api.async_start_charging_with_token(self.serial, token_id)
        except KebaApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="start_charging_failed",
                translation_placeholders={"error": str(err)},
            ) from None
        await self.async_request_refresh()

    async def async_apply_charging_profile(
        self,
        profile: ChargingProfile,
    ) -> None:
        """Apply current and phase settings with the lower-power step first."""
        current_phases = self.phase_target
        current_ma = self.data["configs"].get("max_available_current") or 0
        current_a = float(current_ma) / 1000

        if current_phases is None:
            await self.api.async_set_max_available_current(
                MIN_CHARGING_CURRENT_A * 1000
            )
            await self.async_set_phases(profile.phases)
            if profile.current_a != MIN_CHARGING_CURRENT_A:
                await self.api.async_set_max_available_current(
                    profile.current_a * 1000
                )
            await self.async_request_refresh()
            return

        if current_phases == profile.phases:
            await self.api.async_set_max_available_current(
                profile.current_a * 1000
            )
        else:
            current_first_power = charging_power_kw(
                current_phases,
                profile.current_a,
            )
            phase_first_power = charging_power_kw(
                profile.phases,
                current_a,
            )

            if phase_first_power <= current_first_power:
                await self.async_set_phases(profile.phases)
                await self.api.async_set_max_available_current(
                    profile.current_a * 1000
                )
            else:
                await self.api.async_set_max_available_current(
                    profile.current_a * 1000
                )
                await self.async_set_phases(profile.phases)

        await self.async_request_refresh()
