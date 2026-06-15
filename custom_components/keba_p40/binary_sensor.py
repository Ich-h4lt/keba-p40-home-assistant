"""Binary sensors for KEBA P40."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KebaDataUpdateCoordinator
from .entity import KebaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up KEBA binary sensors."""
    coordinator: KebaDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        [
            KebaVehicleConnectedBinarySensor(coordinator),
            KebaSessionActiveBinarySensor(coordinator),
        ]
    )


class KebaVehicleConnectedBinarySensor(KebaEntity, BinarySensorEntity):
    """Report whether a vehicle is connected."""

    _attr_translation_key = "vehicle_connected"
    _attr_device_class = BinarySensorDeviceClass.PLUG

    def __init__(self, coordinator: KebaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "vehicle_connected")

    @property
    def is_on(self) -> bool:
        """Return whether a vehicle is connected."""
        return bool(self.coordinator.data["wallbox"].get("vehiclePlugged"))


class KebaSessionActiveBinarySensor(KebaEntity, BinarySensorEntity):
    """Report whether a charging session is active."""

    _attr_translation_key = "session_active"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: KebaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "session_active")

    @property
    def is_on(self) -> bool:
        """Return whether a session is active."""
        return bool(self.coordinator.data["wallbox"].get("sessionActive"))
