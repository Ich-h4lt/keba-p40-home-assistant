"""Number entities for KEBA P40."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KebaDataUpdateCoordinator
from .entity import KebaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up KEBA number entities."""
    coordinator: KebaDataUpdateCoordinator = entry.runtime_data
    async_add_entities([KebaMaxAvailableCurrentNumber(coordinator)])


class KebaMaxAvailableCurrentNumber(KebaEntity, NumberEntity):
    """Control max_available_current."""

    _attr_translation_key = "max_available_current"
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_min_value = 6.0
    _attr_native_step = 1.0
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: KebaDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "max_available_current")
        max_current_ma = coordinator.data["wallbox"].get("maxCurrent") or 32000
        self._attr_native_max_value = float(max_current_ma) / 1000

    @property
    def native_value(self) -> float | None:
        """Return the configured maximum current in amperes."""
        current_ma = self.coordinator.data["configs"].get(
            "max_available_current"
        )
        return float(current_ma) / 1000 if current_ma is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set maximum current."""
        await self.coordinator.api.async_set_max_available_current(
            round(value * 1000)
        )
        await self.coordinator.async_request_refresh()
