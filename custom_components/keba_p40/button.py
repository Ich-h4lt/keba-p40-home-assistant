"""Button entities for KEBA P40."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .charging import (
    MIN_CHARGING_CURRENT_A,
    ChargingProfile,
    build_charging_profiles,
    find_charging_profile,
)
from .coordinator import KebaDataUpdateCoordinator
from .entity import KebaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up KEBA buttons."""
    coordinator: KebaDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        [
            KebaChargingProfileButton(coordinator, 1),
            KebaChargingProfileButton(coordinator, -1),
            KebaChargingControlButton(coordinator, "start_charging"),
            KebaChargingControlButton(coordinator, "stop_charging"),
        ]
    )


class KebaChargingProfileButton(KebaEntity, ButtonEntity):
    """Switch to the adjacent charging profile."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        direction: int,
    ) -> None:
        key = "increase_charging_power" if direction > 0 else "decrease_charging_power"
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._direction = direction

        max_current_ma = coordinator.data["wallbox"].get("maxCurrent") or 32000
        max_current_a = max(
            MIN_CHARGING_CURRENT_A,
            int(max_current_ma) // 1000,
        )
        self._profiles = build_charging_profiles(max_current_a)

    def _current_profile_index(self) -> int | None:
        """Return the current profile index."""
        phases = self.coordinator.phase_target
        if phases is None:
            return None
        current_ma = self.coordinator.data["configs"].get(
            "max_available_current"
        )
        if current_ma is None or int(current_ma) % 1000:
            return None

        profile = find_charging_profile(
            self._profiles,
            phases,
            int(current_ma) // 1000,
        )
        return self._profiles.index(profile) if profile else None

    def _target_profile(self) -> ChargingProfile | None:
        """Return the adjacent target profile."""
        current_index = self._current_profile_index()
        if current_index is None:
            return None
        target_index = current_index + self._direction
        if not 0 <= target_index < len(self._profiles):
            return None
        return self._profiles[target_index]

    @property
    def available(self) -> bool:
        """Return whether an adjacent profile exists."""
        return super().available and self._target_profile() is not None

    async def async_press(self) -> None:
        """Switch to the adjacent profile."""
        profile = self._target_profile()
        if profile is None:
            return
        await self.coordinator.async_apply_charging_profile(profile)


class KebaChargingControlButton(KebaEntity, ButtonEntity):
    """Start or stop charging."""

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        action: str,
    ) -> None:
        super().__init__(coordinator, action)
        self._attr_translation_key = action
        self._action = action

    async def async_press(self) -> None:
        """Send the charging control command."""
        if self._action == "start_charging":
            await self.coordinator.api.async_start_charging(
                self.coordinator.serial
            )
        else:
            await self.coordinator.api.async_stop_charging(
                self.coordinator.serial
            )
        await self.coordinator.async_request_refresh()
