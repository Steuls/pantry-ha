"""Sensor platform for Inventory integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import InventoryCoordinator
from .runtime import get_coordinator
from .storage import InventoryStorage


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Inventory sensors."""
    coordinator = get_coordinator(hass)
    known_locations: set[str] = set()

    @callback
    def _sync_entities() -> None:
        new_entities: list[InventorySensor] = []
        for location_id in InventoryStorage.get_locations(coordinator.data):
            if location_id in known_locations:
                continue
            known_locations.add(location_id)
            new_entities.append(InventorySensor(coordinator, location_id))
        if new_entities:
            async_add_entities(new_entities)

    _sync_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_entities))


class InventorySensor(CoordinatorEntity[InventoryCoordinator], SensorEntity):
    """Representation of one inventory location sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "inventory"

    def __init__(self, coordinator: InventoryCoordinator, location_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._location_id = location_id
        self._attr_unique_id = f"{DOMAIN}_{location_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, DOMAIN)},
            name="Inventory",
            manufacturer="Pantry",
        )

    @property
    def _location(self) -> dict[str, Any] | None:
        """Return current location snapshot."""
        return InventoryStorage.get_location(self.coordinator.data, self._location_id)

    @property
    def available(self) -> bool:
        """Return whether the entity is available."""
        return self._location is not None and self.coordinator.has_usable_data

    @property
    def name(self) -> str | None:
        """Return the display name."""
        location = self._location
        return location["name"] if location else self._location_id

    @property
    def native_value(self) -> int:
        """Return the item count."""
        location = self._location
        return location.get("item_count", 0) if location else 0

    @property
    def icon(self) -> str:
        """Return the icon."""
        location = self._location
        return location.get("icon") if location else "mdi:package-variant"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity attributes."""
        location = self._location
        if location is None:
            return {}

        return {
            "location_id": self._location_id,
            "location_name": location["name"],
            "icon": location.get("icon", "mdi:package-variant"),
            "items": location.get("items", []),
            "item_count": location.get("item_count", 0),
            "expired_count": location.get("expired_count", 0),
            "expiring_soon_count": location.get("expiring_soon_count", 0),
            "categories": location.get("categories", []),
        }
