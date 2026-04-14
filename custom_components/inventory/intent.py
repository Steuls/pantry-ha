"""Assist intent handlers for the Inventory integration."""

from __future__ import annotations

from collections.abc import Iterable

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import intent

from . import get_coordinator
from .const import DATA_INTENTS_REGISTERED, DOMAIN
from .storage import InventoryStorage

INTENT_ADD_ITEM = "InventoryAddItem"
INTENT_REMOVE_ITEM = "InventoryRemoveItem"
INTENT_GET_ITEMS = "InventoryGetItems"
INTENT_GET_EXPIRING_SOON = "InventoryGetExpiringSoon"


def async_setup_intents(hass: HomeAssistant) -> None:
    """Register Assist intent handlers."""
    if hass.data[DOMAIN].get(DATA_INTENTS_REGISTERED):
        return

    intent.async_register(hass, AddItemIntentHandler())
    intent.async_register(hass, RemoveItemIntentHandler())
    intent.async_register(hass, GetItemsIntentHandler())
    intent.async_register(hass, GetExpiringSoonIntentHandler())
    hass.data[DOMAIN][DATA_INTENTS_REGISTERED] = True


def _snapshot(hass: HomeAssistant) -> dict:
    """Return current normalized snapshot."""
    return get_coordinator(hass).data or {}


def _slot_value(slot_data: dict | None) -> str | None:
    """Extract a trimmed slot value."""
    if not slot_data:
        return None
    value = slot_data.get("value")
    if value is None:
        return None
    return str(value).strip() or None


def _resolve_location(snapshot: dict, spoken_location: str | None) -> tuple[str, dict]:
    """Resolve a spoken location to a known location id."""
    if spoken_location is None:
        raise intent.IntentHandleError("I need a storage location.")

    lookup = spoken_location.casefold()
    for location_id, location in InventoryStorage.get_locations(snapshot).items():
        if location_id.casefold() == lookup or location["name"].casefold() == lookup:
            return location_id, location

    raise intent.IntentHandleError(f"I couldn't find a location named {spoken_location}.")


def _join_names(names: Iterable[str]) -> str:
    """Join item names into natural speech."""
    values = [name for name in names if name]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


class _InventoryIntentHandler(intent.IntentHandler):
    """Base inventory handler helpers."""

    def _create_response(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Create a response object for the current request."""
        return intent_obj.create_response()


class AddItemIntentHandler(_InventoryIntentHandler):
    """Handle adding an inventory item."""

    intent_type = INTENT_ADD_ITEM

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        snapshot = _snapshot(intent_obj.hass)
        item_name = _slot_value(intent_obj.slots.get("item"))
        location_name = _slot_value(intent_obj.slots.get("location"))

        if item_name is None:
            raise intent.IntentHandleError("I didn't catch the item name.")

        location_id, location = _resolve_location(snapshot, location_name)

        try:
            await intent_obj.hass.services.async_call(
                DOMAIN,
                "add_item",
                {"location": location_id, "name": item_name},
                blocking=True,
            )
        except HomeAssistantError as err:
            raise intent.IntentHandleError(str(err)) from err

        response = self._create_response(intent_obj)
        response.async_set_speech(f"Added {item_name} to {location['name']}.")
        return response


class RemoveItemIntentHandler(_InventoryIntentHandler):
    """Handle removing an inventory item."""

    intent_type = INTENT_REMOVE_ITEM

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        snapshot = _snapshot(intent_obj.hass)
        item_name = _slot_value(intent_obj.slots.get("item"))
        location_name = _slot_value(intent_obj.slots.get("location"))

        if item_name is None:
            raise intent.IntentHandleError("I didn't catch the item name.")

        location_id, location = _resolve_location(snapshot, location_name)
        existing_item = InventoryStorage.get_item(snapshot, location_id, item_name)
        if existing_item is None:
            raise intent.IntentHandleError(f"I couldn't find {item_name} in {location['name']}.")

        try:
            await intent_obj.hass.services.async_call(
                DOMAIN,
                "remove_item",
                {"location": location_id, "name": item_name},
                blocking=True,
            )
        except HomeAssistantError as err:
            raise intent.IntentHandleError(str(err)) from err

        response = self._create_response(intent_obj)
        response.async_set_speech(f"Removed {item_name} from {location['name']}.")
        return response


class GetItemsIntentHandler(_InventoryIntentHandler):
    """Handle listing items in a location."""

    intent_type = INTENT_GET_ITEMS

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        snapshot = _snapshot(intent_obj.hass)
        location_name = _slot_value(intent_obj.slots.get("location"))
        location_id, location = _resolve_location(snapshot, location_name)
        items = InventoryStorage.get_items(snapshot, location_id)

        response = self._create_response(intent_obj)
        if not items:
            response.async_set_speech(f"{location['name']} is empty.")
            return response

        item_names = [str(item.get("name", "")).strip() for item in items]
        response.async_set_speech(
            f"{location['name']} has {len(items)} item"
            f"{'' if len(items) == 1 else 's'}: {_join_names(item_names[:5])}."
        )
        return response


class GetExpiringSoonIntentHandler(_InventoryIntentHandler):
    """Handle querying expiring items."""

    intent_type = INTENT_GET_EXPIRING_SOON

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        snapshot = _snapshot(intent_obj.hass)
        location_name = _slot_value(intent_obj.slots.get("location"))
        response = self._create_response(intent_obj)

        if location_name is None:
            matches: list[tuple[str, str]] = []
            for location_id, location in InventoryStorage.get_locations(snapshot).items():
                for item in InventoryStorage.get_expiring_soon_items(snapshot, location_id):
                    matches.append((str(item.get("name", "")).strip(), location["name"]))

            if not matches:
                response.async_set_speech("Nothing is expiring soon.")
                return response

            response.async_set_speech(
                f"Expiring soon: {_join_names([f'{item} in {location}' for item, location in matches[:5]])}."
            )
            return response

        location_id, location = _resolve_location(snapshot, location_name)
        items = InventoryStorage.get_expiring_soon_items(snapshot, location_id)
        if not items:
            response.async_set_speech(f"Nothing in {location['name']} is expiring soon.")
            return response

        item_names = [str(item.get("name", "")).strip() for item in items]
        response.async_set_speech(
            f"In {location['name']}, expiring soon: {_join_names(item_names[:5])}."
        )
        return response
