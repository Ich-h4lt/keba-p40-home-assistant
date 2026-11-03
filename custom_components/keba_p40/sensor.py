"""Sensors for KEBA P40."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .cards import configured_token_ids, mask_token_id
from .const import SESSION_CARD_NONE, SESSION_CARD_UNKNOWN
from .coordinator import KebaDataUpdateCoordinator
from .entity import KebaEntity


@dataclass(frozen=True, kw_only=True)
class KebaSensorDescription(SensorEntityDescription):
    """Describe a KEBA sensor."""

    value_fn: Callable[[dict[str, Any]], Any]


def _meter_value(data: dict[str, Any], key: str) -> Any:
    """Return a raw meter value."""
    return (data["wallbox"].get("meter") or {}).get(key)


def _scaled_meter_value(
    data: dict[str, Any],
    key: str,
    divisor: float,
) -> float | None:
    """Return a scaled meter value."""
    value = _meter_value(data, key)
    return float(value) / divisor if value is not None else None


def _line_value(
    data: dict[str, Any],
    phase: str,
    key: str,
    divisor: float = 1,
) -> float | None:
    """Return a value for one meter phase."""
    lines = (data["wallbox"].get("meter") or {}).get("lines") or []
    line = next(
        (
            item
            for item in lines
            if isinstance(item, dict) and item.get("socketPhase") == phase
        ),
        None,
    )
    if line is None or line.get(key) is None:
        return None
    return float(line[key]) / divisor


def _error_code(data: dict[str, Any]) -> str:
    """Return a normalized wallbox error code."""
    value = data["wallbox"].get("errorCode")
    return "none" if value in (None, "") else str(value)


def _measured_active_phases(data: dict[str, Any]) -> int | None:
    """Count phases carrying charging current."""
    lines = (data["wallbox"].get("meter") or {}).get("lines") or []
    active_phases = sum(
        1
        for line in lines
        if isinstance(line, dict)
        and isinstance(line.get("current"), (int, float))
        and line["current"] > 500
    )
    return active_phases or None


SENSORS = (
    KebaSensorDescription(
        key="state",
        translation_key="state",
        value_fn=lambda data: data["wallbox"].get("state"),
    ),
    KebaSensorDescription(
        key="phase_used",
        translation_key="phase_used",
        value_fn=lambda data: data["wallbox"].get("phaseUsed"),
    ),
    KebaSensorDescription(
        key="measured_active_phases",
        translation_key="measured_active_phases",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_measured_active_phases,
    ),
    KebaSensorDescription(
        key="current_offered",
        translation_key="current_offered",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: _scaled_meter_value(
            data, "currentOffered", 1000
        ),
    ),
    KebaSensorDescription(
        key="total_active_power",
        translation_key="total_active_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: _scaled_meter_value(
            data, "totalActivePower", 1000
        ),
    ),
    KebaSensorDescription(
        key="total_energy",
        translation_key="total_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        value_fn=lambda data: _scaled_meter_value(data, "meterValue", 1_000_000),
    ),
    KebaSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: _scaled_meter_value(data, "temperature", 100),
    ),
    *tuple(
        KebaSensorDescription(
            key=f"current_{phase.lower()}",
            translation_key=f"current_{phase.lower()}",
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=2,
            value_fn=lambda data, phase=phase: _line_value(
                data, phase, "current", 1000
            ),
        )
        for phase in ("L1", "L2", "L3")
    ),
    *tuple(
        KebaSensorDescription(
            key=f"voltage_{phase.lower()}",
            translation_key=f"voltage_{phase.lower()}",
            device_class=SensorDeviceClass.VOLTAGE,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            value_fn=lambda data, phase=phase: _line_value(
                data, phase, "voltage"
            ),
        )
        for phase in ("L1", "L2", "L3")
    ),
    KebaSensorDescription(
        key="hardware_max_current",
        translation_key="hardware_max_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda data: (
            float(data["wallbox"]["maxCurrent"]) / 1000
            if data["wallbox"].get("maxCurrent") is not None
            else None
        ),
    ),
    KebaSensorDescription(
        key="error_code",
        translation_key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_error_code,
    ),
    KebaSensorDescription(
        key="max_asymmetrical_phase_current",
        translation_key="max_asymmetrical_phase_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: (
            float(data["configs"]["max_asymmetrical_phase_current"]) / 1000
            if data["configs"].get("max_asymmetrical_phase_current")
            is not None
            else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up KEBA sensors."""
    coordinator: KebaDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        [
            *(KebaSensor(coordinator, description) for description in SENSORS),
            KebaSessionCardSensor(coordinator, configured_token_ids(entry)),
        ]
    )


class KebaSensor(KebaEntity, SensorEntity):
    """Representation of a KEBA sensor."""

    entity_description: KebaSensorDescription

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        description: KebaSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)


class KebaSessionCardSensor(KebaEntity, SensorEntity):
    """Show which charging card the current or last session uses."""

    _attr_translation_key = "session_card"
    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        cards: dict[str, str],
    ) -> None:
        super().__init__(coordinator, "session_card")
        self._cards = cards
        self._attr_options = list(
            dict.fromkeys(
                [*cards.values(), SESSION_CARD_NONE, SESSION_CARD_UNKNOWN]
            )
        )

    @property
    def native_value(self) -> str | None:
        """Return the card comment, or that no or an unknown card was used."""
        session = self.coordinator.session
        if session is None:
            return None
        token_id = session.get("tokenId")
        if not token_id:
            return SESSION_CARD_NONE
        return self._cards.get(str(token_id), SESSION_CARD_UNKNOWN)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the session status and start, and a hint for unknown cards."""
        session = self.coordinator.session
        if session is None:
            return None
        start = session.get("startDate")
        attributes: dict[str, Any] = {
            "session_status": session.get("status"),
            "session_start": (
                dt_util.utc_from_timestamp(start / 1000)
                if isinstance(start, (int, float)) and start > 0
                else None
            ),
        }
        token_id = session.get("tokenId")
        if token_id and str(token_id) not in self._cards:
            attributes["card_hint"] = mask_token_id(str(token_id))
        return attributes
