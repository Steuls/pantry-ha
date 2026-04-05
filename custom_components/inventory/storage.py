"""Storage helper for Inventory integration."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_data"


class InventoryStorage:
    """Manage inventory data persistence."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize storage."""
        _LOGGER.debug("InventoryStorage.__init__ called")
        self._hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] | None = None

    async def async_load(self) -> None:
        """Load data from storage."""
        _LOGGER.debug("InventoryStorage.async_load called")
        self._data = await self._store.async_load()
        if self._data is None:
            _LOGGER.debug("No existing data, creating empty structure")
            self._data = {"locations": {}}
        _LOGGER.debug("Data loaded: %s locations", len(self._data.get("locations", {})))

    async def async_save(self) -> None:
        """Save data to storage."""
        if self._data is not None:
            await self._store.async_save(self._data)

    # === Location CRUD ===

    @callback
    def get_locations(self) -> dict[str, dict[str, Any]]:
        """Get all locations."""
        if self._data is None:
            return {}
        return self._data.get("locations", {})

    @callback
    def get_location(self, location_id: str) -> dict[str, Any] | None:
        """Get a specific location by ID."""
        return self.get_locations().get(location_id)

    async def async_add_location(
        self, location_id: str, name: str, icon: str = "mdi:package-variant"
    ) -> dict[str, Any]:
        """Add a new storage location."""
        if self._data is None:
            await self.async_load()

        locations = self._data.setdefault("locations", {})
        locations[location_id] = {
            "name": name,
            "icon": icon,
            "items": [],
        }
        await self.async_save()
        return locations[location_id]

    async def async_update_location(
        self, location_id: str, name: str | None = None, icon: str | None = None
    ) -> dict[str, Any] | None:
        """Update a location's metadata."""
        location = self.get_location(location_id)
        if location is None:
            return None

        if name is not None:
            location["name"] = name
        if icon is not None:
            location["icon"] = icon

        await self.async_save()
        return location

    async def async_remove_location(self, location_id: str) -> bool:
        """Remove a location and all its items."""
        if self._data is None or location_id not in self._data.get("locations", {}):
            return False

        del self._data["locations"][location_id]
        await self.async_save()
        return True

    # === Item CRUD ===

    @callback
    def get_items(self, location_id: str) -> list[dict[str, Any]]:
        """Get all items in a location."""
        location = self.get_location(location_id)
        if location is None:
            return []
        return location.get("items", [])

    @callback
    def get_item(
        self, location_id: str, item_name: str
    ) -> dict[str, Any] | None:
        """Get a specific item by name (case-insensitive)."""
        items = self.get_items(location_id)
        item_name_lower = item_name.lower()
        for item in items:
            if item.get("name", "").lower() == item_name_lower:
                return item
        return None

    async def async_add_item(
        self,
        location_id: str,
        name: str,
        quantity: int = 1,
        unit: str | None = None,
        expiry: str | None = None,
        category: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any] | None:
        """Add an item to a location. Updates existing if name matches."""
        location = self.get_location(location_id)
        if location is None:
            return None

        items = location.setdefault("items", [])

        # Check for existing item (case-insensitive)
        existing = self.get_item(location_id, name)
        if existing is not None:
            # Update existing item - merge/overwrite
            existing["quantity"] = existing.get("quantity", 1) + quantity
            if unit is not None:
                existing["unit"] = unit
            if expiry is not None:
                existing["expiry"] = expiry
            if category is not None:
                existing["category"] = category
            if notes is not None:
                existing["notes"] = notes
            item = existing
        else:
            # Add new item
            today = date.today().isoformat()
            item = {
                "name": name,
                "quantity": quantity,
                "added": today,
            }
            if unit is not None:
                item["unit"] = unit
            if expiry is not None:
                item["expiry"] = expiry
            if category is not None:
                item["category"] = category
            if notes is not None:
                item["notes"] = notes
            items.append(item)

        await self.async_save()
        return item

    async def async_remove_item(
        self, location_id: str, name: str, quantity: int | None = None
    ) -> dict[str, Any] | None:
        """Remove an item from a location.

        Args:
            location_id: The location ID
            name: Item name to remove
            quantity: If specified, reduce quantity. If None or >= current, remove entirely.

        Returns:
            The removed/updated item, or None if not found.
        """
        location = self.get_location(location_id)
        if location is None:
            return None

        items = location.get("items", [])
        item_name_lower = name.lower()

        for i, item in enumerate(items):
            if item.get("name", "").lower() == item_name_lower:
                if quantity is None or quantity >= item.get("quantity", 1):
                    # Remove entirely
                    removed = items.pop(i)
                    await self.async_save()
                    return removed
                else:
                    # Reduce quantity
                    item["quantity"] = item.get("quantity", 1) - quantity
                    await self.async_save()
                    return item

        return None

    async def async_update_item(
        self,
        location_id: str,
        name: str,
        quantity: int | None = None,
        unit: str | None = None,
        expiry: str | None = None,
        category: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any] | None:
        """Update an item's fields."""
        location = self.get_location(location_id)
        if location is None:
            return None

        item = self.get_item(location_id, name)
        if item is None:
            return None

        if quantity is not None:
            item["quantity"] = quantity
        if unit is not None:
            item["unit"] = unit
        if expiry is not None:
            item["expiry"] = expiry
        if category is not None:
            item["category"] = category
        if notes is not None:
            item["notes"] = notes

        await self.async_save()
        return item

    async def async_clear_expired(
        self, location_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Clear expired items from one or all locations.

        Args:
            location_id: Specific location, or None to clear all locations.

        Returns:
            List of removed items with their location_id added.
        """
        removed_items = []
        today = date.today()

        if location_id:
            # Clear from specific location
            location = self.get_location(location_id)
            if location is None:
                return []
            items = location.get("items", [])
            expired = [
                item
                for item in items
                if self._is_expired(item, today)
            ]
            location["items"] = [
                item for item in items if not self._is_expired(item, today)
            ]
            for item in expired:
                item["location_id"] = location_id
                removed_items.append(item)
        else:
            # Clear from all locations
            for loc_id, location in self.get_locations().items():
                items = location.get("items", [])
                expired = [
                    item
                    for item in items
                    if self._is_expired(item, today)
                ]
                location["items"] = [
                    item for item in items if not self._is_expired(item, today)
                ]
                for item in expired:
                    item["location_id"] = loc_id
                    removed_items.append(item)

        if removed_items:
            await self.async_save()

        return removed_items

    async def async_clear_all(self, location_id: str) -> list[dict[str, Any]]:
        """Clear all items from a location.

        Returns:
            List of removed items.
        """
        location = self.get_location(location_id)
        if location is None:
            return []

        items = location.get("items", [])
        location["items"] = []
        await self.async_save()
        return items

    # === Helper methods ===

    @staticmethod
    def _is_expired(item: dict[str, Any], check_date: date) -> bool:
        """Check if an item is expired."""
        expiry_str = item.get("expiry")
        if not expiry_str:
            return False
        try:
            expiry_date = date.fromisoformat(expiry_str)
            return expiry_date < check_date
        except ValueError:
            return False

    @callback
    def get_expired_count(self, location_id: str) -> int:
        """Get count of expired items in a location."""
        today = date.today()
        return sum(
            1 for item in self.get_items(location_id)
            if self._is_expired(item, today)
        )

    @callback
    def get_expiring_soon_count(self, location_id: str, days: int = 7) -> int:
        """Get count of items expiring within N days."""
        today = date.today()
        threshold = date.today()
        # Calculate date N days from now
        from datetime import timedelta
        threshold = today + timedelta(days=days)

        count = 0
        for item in self.get_items(location_id):
            expiry_str = item.get("expiry")
            if not expiry_str:
                continue
            try:
                expiry_date = date.fromisoformat(expiry_str)
                if today <= expiry_date <= threshold:
                    count += 1
            except ValueError:
                pass
        return count

    @callback
    def get_categories(self, location_id: str) -> list[str]:
        """Get unique categories in a location."""
        categories = set()
        for item in self.get_items(location_id):
            category = item.get("category")
            if category:
                categories.add(category)
        return sorted(categories)
