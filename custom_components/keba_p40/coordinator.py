"""Data coordinator for the KEBA P40 integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KebaApi, KebaApiError, KebaAuthenticationError
from .charging import MIN_CHARGING_CURRENT_A, ChargingProfile, charging_power_kw
from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


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
            wallbox, load_management = await asyncio.gather(
                self.api.async_get_wallbox(self.serial),
                self.api.async_get_load_management(),
            )
        except KebaAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except KebaApiError as err:
            raise UpdateFailed(str(err)) from err

        configs = {
            item["key"]: item.get("value")
            for item in load_management.get("configs", [])
            if isinstance(item, dict) and "key" in item
        }
        return {"wallbox": wallbox, "configs": configs}

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
