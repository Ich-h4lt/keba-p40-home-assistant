"""Select entities for KEBA P40."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
    async_get_current_platform,
)

from .charging import (
    MIN_CHARGING_CURRENT_A,
    ChargingProfile,
    build_charging_profiles,
    charging_profile_option,
    find_charging_profile,
    profile_from_power_target,
    profile_from_summed_current,
)
from .coordinator import KebaDataUpdateCoordinator
from .entity import KebaEntity

OPTIONS = ["1", "3"]
ATTR_CURRENT = "current"
ATTR_POWER = "power"
SERVICE_SET_CHARGING_CURRENT_TARGET = "set_charging_current_target"
SERVICE_SET_CHARGING_POWER_TARGET = "set_charging_power_target"
_SERVICE_REGISTERED = False


def _build_profiles(
    coordinator: KebaDataUpdateCoordinator,
) -> list[ChargingProfile]:
    """Build profiles supported by the configured wallbox."""
    max_current_ma = coordinator.data["wallbox"].get("maxCurrent") or 32000
    max_current_a = max(
        MIN_CHARGING_CURRENT_A,
        int(max_current_ma) // 1000,
    )
    return build_charging_profiles(max_current_a)


async def _async_set_charging_current_target(
    coordinator: KebaDataUpdateCoordinator,
    profiles: list[ChargingProfile],
    current: int,
) -> None:
    """Apply a profile selected by summed target current."""
    profile = profile_from_summed_current(profiles, current)
    if profile is None:
        valid_currents = [
            profile.current_a
            if profile.phases == 1
            else profile.current_a * 3
            for profile in profiles
        ]
        raise HomeAssistantError(
            f"Unsupported charging current target {current} A. "
            f"Valid values: {', '.join(map(str, valid_currents))} A"
        )
    await coordinator.async_apply_charging_profile(profile)


async def _async_set_charging_power_target(
    coordinator: KebaDataUpdateCoordinator,
    profiles: list[ChargingProfile],
    power: float,
) -> None:
    """Apply a profile selected by an exact displayed kW target."""
    profile = profile_from_power_target(profiles, power)
    if profile is None:
        valid_powers = [f"{profile.power_kw:.1f}" for profile in profiles]
        raise HomeAssistantError(
            f"Unsupported charging power target {power:g} kW. "
            f"Valid values: {', '.join(valid_powers)} kW"
        )
    await coordinator.async_apply_charging_profile(profile)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up KEBA select entities."""
    global _SERVICE_REGISTERED

    coordinator: KebaDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        [
            KebaPhasesSelect(coordinator),
            KebaTargetChargingPowerSelect(coordinator),
        ]
    )

    if not _SERVICE_REGISTERED:
        platform = async_get_current_platform()
        platform.async_register_entity_service(
            SERVICE_SET_CHARGING_CURRENT_TARGET,
            {
                vol.Required(ATTR_CURRENT): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_CHARGING_CURRENT_A),
                )
            },
            "async_set_charging_current_target",
        )
        platform.async_register_entity_service(
            SERVICE_SET_CHARGING_POWER_TARGET,
            {
                vol.Required(ATTR_POWER): vol.All(
                    vol.Coerce(float),
                    vol.Range(min=1.4),
                )
            },
            "async_set_charging_power_target",
        )
        _SERVICE_REGISTERED = True


class KebaPhasesSelect(KebaEntity, SelectEntity):
    """Select the number of active phases."""

    _attr_translation_key = "phases"
    _attr_options = OPTIONS
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: KebaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "phases")

    @property
    def current_option(self) -> str | None:
        """Return the last phase target sent to the wallbox."""
        phases = self.coordinator.phase_target
        return str(phases) if phases is not None else None

    async def async_select_option(self, option: str) -> None:
        """Switch the number of phases."""
        await self.coordinator.async_set_phases(int(option))
        await self.coordinator.async_request_refresh()

    async def async_set_charging_current_target(self, current: int) -> None:
        """Apply a charging profile selected by summed target current."""
        await _async_set_charging_current_target(
            self.coordinator,
            _build_profiles(self.coordinator),
            current,
        )

    async def async_set_charging_power_target(self, power: float) -> None:
        """Apply a charging profile selected by a kW target."""
        await _async_set_charging_power_target(
            self.coordinator,
            _build_profiles(self.coordinator),
            power,
        )


class KebaTargetChargingPowerSelect(KebaEntity, SelectEntity):
    """Select a fixed charging profile."""

    _attr_translation_key = "target_charging_power"

    def __init__(self, coordinator: KebaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "target_charging_power")
        self._profiles = _build_profiles(coordinator)
        self._profiles_by_option = {
            charging_profile_option(profile): profile
            for profile in self._profiles
        }
        self._attr_options = list(self._profiles_by_option)

    @property
    def current_option(self) -> str | None:
        """Return the active charging profile."""
        phases = self.coordinator.phase_target
        if phases is None:
            return None
        current_ma = self.coordinator.data["configs"].get(
            "max_available_current"
        )
        if current_ma is None or int(current_ma) % 1000:
            return None

        current_a = int(current_ma) // 1000
        profile = find_charging_profile(self._profiles, phases, current_a)
        return charging_profile_option(profile) if profile else None

    async def async_select_option(self, option: str) -> None:
        """Apply the selected charging profile."""
        await self.coordinator.async_apply_charging_profile(
            self._profiles_by_option[option]
        )

    async def async_set_charging_current_target(self, current: int) -> None:
        """Apply a profile selected by summed target current."""
        await _async_set_charging_current_target(
            self.coordinator,
            self._profiles,
            current,
        )

    async def async_set_charging_power_target(self, power: float) -> None:
        """Apply a charging profile selected by a kW target."""
        await _async_set_charging_power_target(
            self.coordinator,
            self._profiles,
            power,
        )
