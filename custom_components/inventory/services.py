"""Services for Inventory integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .storage import InventoryStorage


def _get_storage(hass: HomeAssistant) -> InventoryStorage:
    """Get storage instance."""
    return hass.data[DOMAIN]["storage"]


def _fire_event(hass: HomeAssistant, event_type: str, data: dict) -> None:
    """Fire an inventory event."""
    hass.bus.async_fire(f"{DOMAIN}_{event_type}", data)


# Service schemas
ADD_ITEM_SCHEMA = vol.Schema({
    vol.Required("location"): str,
    vol.Required("name"): str,
    vol.Optional("quantity", default=1): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional("unit"): str,
    vol.Optional("expiry"): str,
    vol.Optional("category"): str,
    vol.Optional("notes"): str,
})

REMOVE_ITEM_SCHEMA = vol.Schema({
    vol.Required("location"): str,
    vol.Required("name"): str,
    vol.Optional("quantity"): vol.All(vol.Coerce(int), vol.Range(min=1)),
})

UPDATE_ITEM_SCHEMA = vol.Schema({
    vol.Required("location"): str,
    vol.Required("name"): str,
    vol.Optional("quantity"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional("unit"): str,
    vol.Optional("expiry"): str,
    vol.Optional("category"): str,
    vol.Optional("notes"): str,
})

CLEAR_EXPIRED_SCHEMA = vol.Schema({
    vol.Optional("location"): str,
})

CLEAR_ALL_SCHEMA = vol.Schema({
    vol.Required("location"): str,
})


def _validate_location(hass: HomeAssistant, location_id: str) -> dict:
    """Validate location exists and return it."""
    storage = _get_storage(hass)
    location = storage.get_location(location_id)
    if location is None:
        raise ServiceValidationError(
            f"Location '{location_id}' not found",
            translation_domain=DOMAIN,
            translation_key="location_not_found",
            translation_placeholders={"location": location_id},
        )
    return location


def _validate_expiry_date(expiry: str) -> str:
    """Validate expiry date format."""
    if expiry is None:
        return None
    try:
        from datetime import date
        date.fromisoformat(expiry)
        return expiry
    except ValueError:
        raise ServiceValidationError(
            f"Invalid expiry date format: {expiry}. Use YYYY-MM-DD.",
            translation_domain=DOMAIN,
            translation_key="invalid_expiry",
            translation_placeholders={"expiry": expiry},
        )


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Inventory integration."""

    async def add_item(call: ServiceCall) -> None:
        """Add an item to a location."""
        storage = _get_storage(hass)
        location_id = call.data["location"]
        name = call.data["name"]
        quantity = call.data.get("quantity", 1)
        unit = call.data.get("unit")
        expiry = call.data.get("expiry")
        category = call.data.get("category")
        notes = call.data.get("notes")

        # Validate
        _validate_location(hass, location_id)
        if expiry:
            expiry = _validate_expiry_date(expiry)

        # Add item
        item = await storage.async_add_item(
            location_id, name, quantity, unit, expiry, category, notes
        )

        # Fire event
        location = storage.get_location(location_id)
        _fire_event(hass, "item_added", {
            "location_id": location_id,
            "location_name": location.get("name", location_id) if location else location_id,
            "item": item,
        })
        _fire_event(hass, "updated", {"location_id": location_id})

    async def remove_item(call: ServiceCall) -> None:
        """Remove an item from a location."""
        storage = _get_storage(hass)
        location_id = call.data["location"]
        name = call.data["name"]
        quantity = call.data.get("quantity")

        # Validate
        _validate_location(hass, location_id)

        # Remove item
        result = await storage.async_remove_item(location_id, name, quantity)

        if result is None:
            # Item not found - just log warning, don't error
            return

        # Determine reason for removal
        reason = "user_action"
        if quantity is not None and result.get("quantity", 0) == 0:
            reason = "depleted"

        # Fire event
        location = storage.get_location(location_id)
        _fire_event(hass, "item_removed", {
            "location_id": location_id,
            "location_name": location.get("name", location_id) if location else location_id,
            "item_name": name,
            "item": result,
            "reason": reason,
        })
        _fire_event(hass, "updated", {"location_id": location_id})

    async def update_item(call: ServiceCall) -> None:
        """Update an item in a location."""
        storage = _get_storage(hass)
        location_id = call.data["location"]
        name = call.data["name"]
        quantity = call.data.get("quantity")
        unit = call.data.get("unit")
        expiry = call.data.get("expiry")
        category = call.data.get("category")
        notes = call.data.get("notes")

        # Validate
        _validate_location(hass, location_id)
        if expiry:
            expiry = _validate_expiry_date(expiry)

        # Update item
        item = await storage.async_update_item(
            location_id, name, quantity, unit, expiry, category, notes
        )

        if item is None:
            raise ServiceValidationError(
                f"Item '{name}' not found in location '{location_id}'",
                translation_domain=DOMAIN,
                translation_key="item_not_found",
                translation_placeholders={"name": name, "location": location_id},
            )

        # Fire event
        location = storage.get_location(location_id)
        _fire_event(hass, "item_updated", {
            "location_id": location_id,
            "location_name": location.get("name", location_id) if location else location_id,
            "item": item,
        })
        _fire_event(hass, "updated", {"location_id": location_id})

    async def clear_expired(call: ServiceCall) -> ServiceResponse:
        """Clear expired items from one or all locations."""
        storage = _get_storage(hass)
        location_id = call.data.get("location")

        # Validate location if specified
        if location_id:
            _validate_location(hass, location_id)

        # Clear expired items
        removed_items = await storage.async_clear_expired(location_id)

        if removed_items:
            # Fire event
            _fire_event(hass, "expired_cleared", {
                "location_id": location_id,
                "items": removed_items,
                "count": len(removed_items),
            })
            _fire_event(hass, "updated", {"location_id": location_id})

        return {
            "removed_count": len(removed_items),
            "items": removed_items,
        }

    async def clear_all(call: ServiceCall) -> ServiceResponse:
        """Clear all items from a location."""
        storage = _get_storage(hass)
        location_id = call.data["location"]

        # Validate
        _validate_location(hass, location_id)

        # Clear all items
        removed_items = await storage.async_clear_all(location_id)

        # Fire event
        location = storage.get_location(location_id)
        _fire_event(hass, "all_cleared", {
            "location_id": location_id,
            "location_name": location.get("name", location_id) if location else location_id,
            "count": len(removed_items),
        })
        _fire_event(hass, "updated", {"location_id": location_id})

        return {
            "removed_count": len(removed_items),
        }

    hass.services.async_register(
        DOMAIN, "add_item", add_item, schema=ADD_ITEM_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "remove_item", remove_item, schema=REMOVE_ITEM_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "update_item", update_item, schema=UPDATE_ITEM_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "clear_expired", clear_expired,
        schema=CLEAR_EXPIRED_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, "clear_all", clear_all,
        schema=CLEAR_ALL_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Inventory services."""
    hass.services.async_remove(DOMAIN, "add_item")
    hass.services.async_remove(DOMAIN, "remove_item")
    hass.services.async_remove(DOMAIN, "update_item")
    hass.services.async_remove(DOMAIN, "clear_expired")
    hass.services.async_remove(DOMAIN, "clear_all")
