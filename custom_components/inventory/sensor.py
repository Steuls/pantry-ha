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
from .storage import InventoryStorage


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Inventory sensors."""
    storage: InventoryStorage = hass.data[DOMAIN]["storage"]

    # Create sensors for each location
    sensors: list[InventorySensor] = []
    for location_id, location_data in storage.get_locations().items():
        sensors.append(InventorySensor(hass, location_id))

    async_add_entities(sensors)


class InventorySensor(SensorEntity):
    """Representation of an Inventory location sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "inventory"

    def __init__(self, hass: HomeAssistant, location_id: str) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._location_id = location_id
        self._storage: InventoryStorage = hass.data[DOMAIN]["storage"]

        # Set unique ID
        self._attr_unique_id = f"{DOMAIN}_{location_id}"

        # Get location data for initial name
        location = self._storage.get_location(location_id)
        self._attr_name = location.get("name", location_id) if location else location_id

        # Device info for grouping
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, DOMAIN)},
            name="Inventory",
            manufacturer="Custom",
        )

    @property
    def location_id(self) -> str:
        """Return the location ID."""
        return self._location_id

    @property
    def native_value(self) -> int:
        """Return the item count."""
        items = self._storage.get_items(self._location_id)
        return len(items)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity attributes."""
        location = self._storage.get_location(self._location_id)
        if location is None:
            return {}

        items = self._storage.get_items(self._location_id)

        return {
            "location_id": self._location_id,
            "location_name": location.get("name", self._location_id),
            "icon": location.get("icon", "mdi:package-variant"),
            "items": items,
            "item_count": len(items),
            "expired_count": self._storage.get_expired_count(self._location_id),
            "expiring_soon_count": self._storage.get_expiring_soon_count(self._location_id),
            "categories": self._storage.get_categories(self._location_id),
        }

    @property
    def icon(self) -> str:
        """Return the icon."""
        location = self._storage.get_location(self._location_id)
        if location:
            return location.get("icon", "mdi:package-variant")
        return "mdi:package-variant"

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        # Register update callback
        self.async_on_remove(
            self.hass.bus.async_listen(
                f"{DOMAIN}_updated",
                self._on_inventory_update
            )
        )

    @callback
    def _on_inventory_update(self, event) -> None:
        """Handle inventory update event."""
        # Only update if this location is affected
        affected_location = event.data.get("location_id")
        if affected_location is None or affected_location == self._location_id:
            self.async_schedule_update_ha_state(True)
