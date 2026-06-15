"""Charging profile calculations for KEBA P40."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

MIN_CHARGING_CURRENT_A = 6
MAX_SINGLE_PHASE_CURRENT_A = 16
PHASE_VOLTAGE_V = 230
LINE_VOLTAGE_V = 400


@dataclass(frozen=True)
class ChargingProfile:
    """A valid combination of phases, current and resulting power."""

    phases: int
    current_a: int
    power_kw: float


def charging_power_kw(phases: int, current_a: float) -> float:
    """Calculate approximate charging power."""
    if phases == 1:
        return PHASE_VOLTAGE_V * current_a / 1000
    if phases == 3:
        return sqrt(3) * LINE_VOLTAGE_V * current_a / 1000
    raise ValueError("phases must be 1 or 3")


def build_charging_profiles(max_current_a: int) -> list[ChargingProfile]:
    """Build profiles in one-ampere increments."""
    three_phase_max = max(max_current_a, MIN_CHARGING_CURRENT_A)
    single_phase_max = min(
        three_phase_max,
        MAX_SINGLE_PHASE_CURRENT_A,
    )
    profiles = [
        ChargingProfile(1, current, charging_power_kw(1, current))
        for current in range(
            MIN_CHARGING_CURRENT_A,
            single_phase_max + 1,
        )
    ]
    profiles.extend(
        ChargingProfile(3, current, charging_power_kw(3, current))
        for current in range(MIN_CHARGING_CURRENT_A, three_phase_max + 1)
    )
    return profiles


def charging_profile_option(profile: ChargingProfile) -> str:
    """Return the Home Assistant option label for a profile."""
    return (
        f"{profile.power_kw:.1f} kW "
        f"({profile.phases}-phase, {profile.current_a} A)"
    )


def find_charging_profile(
    profiles: list[ChargingProfile],
    phases: int,
    current_a: int,
) -> ChargingProfile | None:
    """Find a profile matching the active phase and current settings."""
    return next(
        (
            profile
            for profile in profiles
            if profile.phases == phases and profile.current_a == current_a
        ),
        None,
    )


def profile_from_summed_current(
    profiles: list[ChargingProfile],
    target_current_a: int,
) -> ChargingProfile | None:
    """Map a summed target current to a one- or three-phase profile."""
    if MIN_CHARGING_CURRENT_A <= target_current_a <= MAX_SINGLE_PHASE_CURRENT_A:
        return find_charging_profile(profiles, 1, target_current_a)
    if target_current_a >= 3 * MIN_CHARGING_CURRENT_A and target_current_a % 3 == 0:
        return find_charging_profile(profiles, 3, target_current_a // 3)
    return None


def profile_from_power_target(
    profiles: list[ChargingProfile],
    target_power_kw: float,
) -> ChargingProfile | None:
    """Map an exact displayed kW target to a charging profile."""
    if abs(target_power_kw - round(target_power_kw, 1)) > 1e-6:
        return None
    return next(
        (
            profile
            for profile in profiles
            if abs(round(profile.power_kw, 1) - target_power_kw) < 1e-6
        ),
        None,
    )
