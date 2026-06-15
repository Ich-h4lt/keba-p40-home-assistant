"""Base entity for KEBA P40."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KebaDataUpdateCoordinator


class KebaEntity(CoordinatorEntity[KebaDataUpdateCoordinator]):
    """Common KEBA entity properties."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KebaDataUpdateCoordinator,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.serial}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        wallbox = self.coordinator.data["wallbox"]
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.serial)},
            name=wallbox.get("alias") or f"KEBA P40 {self.coordinator.serial}",
            manufacturer="KEBA",
            model=wallbox.get("model") or "P40",
            serial_number=self.coordinator.serial,
            sw_version=wallbox.get("firmwareVersion"),
        )
