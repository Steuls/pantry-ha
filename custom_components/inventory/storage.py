"""Cache and compatibility helpers for Inventory integration."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import DEFAULT_ICON, DOMAIN

STORAGE_VERSION = 2
STORAGE_KEY = f"{DOMAIN}_data"


class InventoryStorage:
    """Manage cached state and legacy compatibility data."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize storage."""
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] = {
            "cache": None,
            "location_meta": {},
            "legacy_export": None,
            "last_successful_sync": None,
        }

    async def async_load(self) -> None:
        """Load persisted data."""
        stored = await self._store.async_load()
        if stored is None:
            return

        if "locations" in stored:
            self._data["legacy_export"] = {"locations": stored.get("locations", {})}
            self._data["location_meta"] = {
                location_id: {"icon": location.get("icon", DEFAULT_ICON)}
                for location_id, location in stored.get("locations", {}).items()
            }
            return

        self._data.update(stored)

    async def async_save(self) -> None:
        """Save storage state."""
        await self._store.async_save(self._data)

    @callback
    def get_location_icon(self, location_id: str) -> str:
        """Return a configured icon for one location."""
        return (
            self._data.get("location_meta", {})
            .get(location_id, {})
            .get("icon", DEFAULT_ICON)
        )

    async def async_set_location_icon(self, location_id: str, icon: str | None) -> None:
        """Persist an icon override for one location."""
        location_meta = self._data.setdefault("location_meta", {})
        meta = location_meta.setdefault(location_id, {})
        meta["icon"] = icon or DEFAULT_ICON
        await self.async_save()

    async def async_remove_location_icon(self, location_id: str) -> None:
        """Remove icon metadata for a deleted location."""
        location_meta = self._data.setdefault("location_meta", {})
        if location_id in location_meta:
            del location_meta[location_id]
            await self.async_save()

    @callback
    def get_cached_snapshot(self) -> dict[str, Any] | None:
        """Return the last cached normalized snapshot."""
        cache = self._data.get("cache")
        if cache is None:
            return None
        return deepcopy(cache)

    async def async_save_snapshot(self, snapshot: dict[str, Any], synced_at: str) -> None:
        """Persist a normalized snapshot."""
        self._data["cache"] = deepcopy(snapshot)
        self._data["last_successful_sync"] = synced_at
        await self.async_save()

    @callback
    def get_last_successful_sync(self) -> str | None:
        """Return the last successful sync timestamp."""
        return self._data.get("last_successful_sync")

    @callback
    def get_legacy_export_payload(self) -> dict[str, Any] | None:
        """Return legacy local data for migration export."""
        payload = self._data.get("legacy_export")
        if payload is None:
            return None
        return deepcopy(payload)

    @staticmethod
    @callback
    def normalize_state(
        raw_state: dict[str, Any],
        *,
        storage: InventoryStorage,
        source: str,
        etag: str | None,
    ) -> dict[str, Any]:
        """Normalize pantry-server state into HA-friendly location groups."""
        raw_locations = raw_state.get("locations", [])
        raw_items = raw_state.get("items", [])

        items_by_location: dict[str, list[dict[str, Any]]] = {}
        for raw_item in raw_items:
            item = InventoryStorage._normalize_item(raw_item)
            items_by_location.setdefault(item["location_id"], []).append(item)

        locations: dict[str, dict[str, Any]] = {}
        for raw_location in raw_locations:
            location_id = raw_location["id"]
            items = items_by_location.get(location_id, [])
            locations[location_id] = InventoryStorage._normalize_location(
                raw_location,
                items,
                storage.get_location_icon(location_id),
            )

        return {
            "generated_at": raw_state.get("generatedAt"),
            "source": source,
            "etag": etag,
            "summary": raw_state.get("summary", {}),
            "locations": locations,
        }

    @staticmethod
    def _normalize_item(raw_item: dict[str, Any]) -> dict[str, Any]:
        """Normalize one item record from the API."""
        expires_on = raw_item.get("expiresOn")
        added_at = raw_item.get("createdAt")
        location = raw_item.get("location") or {}
        return {
            "id": raw_item.get("id"),
            "name": raw_item.get("name"),
            "quantity": raw_item.get("quantity", 1),
            "unit": raw_item.get("unit"),
            "expiry": expires_on[:10] if isinstance(expires_on, str) else None,
            "added": added_at[:10] if isinstance(added_at, str) else None,
            "category": raw_item.get("category"),
            "notes": raw_item.get("notes"),
            "location_id": raw_item.get("locationId") or location.get("id"),
            "location_name": location.get("name"),
        }

    @staticmethod
    def _normalize_location(
        raw_location: dict[str, Any],
        items: list[dict[str, Any]],
        icon: str,
    ) -> dict[str, Any]:
        """Normalize one location."""
        expired_items = [item for item in items if InventoryStorage._is_expired(item)]
        expiring_soon_items = [
            item for item in items if InventoryStorage._is_expiring_soon(item)
        ]
        categories = sorted({item["category"] for item in items if item.get("category")})

        return {
            "id": raw_location["id"],
            "name": raw_location.get("name", raw_location["id"]),
            "icon": icon,
            "description": raw_location.get("description"),
            "sort_order": raw_location.get("sortOrder", 0),
            "items": items,
            "item_count": len(items),
            "expired_count": len(expired_items),
            "expiring_soon_count": len(expiring_soon_items),
            "categories": categories,
        }

    @staticmethod
    @callback
    def get_locations(snapshot: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        """Return locations from a normalized snapshot."""
        if snapshot is None:
            return {}
        return snapshot.get("locations", {})

    @staticmethod
    @callback
    def get_location(snapshot: dict[str, Any] | None, location_id: str) -> dict[str, Any] | None:
        """Return one location from a normalized snapshot."""
        return InventoryStorage.get_locations(snapshot).get(location_id)

    @staticmethod
    @callback
    def get_items(snapshot: dict[str, Any] | None, location_id: str) -> list[dict[str, Any]]:
        """Return items for one location."""
        location = InventoryStorage.get_location(snapshot, location_id)
        if location is None:
            return []
        return list(location.get("items", []))

    @staticmethod
    @callback
    def get_item(
        snapshot: dict[str, Any] | None,
        location_id: str,
        item_name: str,
    ) -> dict[str, Any] | None:
        """Find one item by exact case-insensitive name."""
        lookup = item_name.casefold()
        for item in InventoryStorage.get_items(snapshot, location_id):
            if str(item.get("name", "")).casefold() == lookup:
                return item
        return None

    @staticmethod
    @callback
    def get_expiring_soon_items(
        snapshot: dict[str, Any] | None,
        location_id: str,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        """Return items expiring within N days."""
        today = date.today()
        cutoff = today + timedelta(days=days)
        matches = []
        for item in InventoryStorage.get_items(snapshot, location_id):
            expiry = InventoryStorage._parse_expiry(item)
            if expiry and today <= expiry <= cutoff:
                matches.append(item)
        return matches

    @staticmethod
    def _parse_expiry(item: dict[str, Any]) -> date | None:
        """Parse item expiry."""
        expiry_str = item.get("expiry")
        if not expiry_str:
            return None
        try:
            return date.fromisoformat(expiry_str)
        except ValueError:
            return None

    @staticmethod
    def _is_expired(item: dict[str, Any]) -> bool:
        """Return whether item is expired."""
        expiry = InventoryStorage._parse_expiry(item)
        return expiry is not None and expiry < date.today()

    @staticmethod
    def _is_expiring_soon(item: dict[str, Any], days: int = 7) -> bool:
        """Return whether item expires soon."""
        expiry = InventoryStorage._parse_expiry(item)
        if expiry is None:
            return False
        today = date.today()
        return today <= expiry <= today + timedelta(days=days)
