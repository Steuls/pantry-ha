"""Services for Inventory integration."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from textwrap import dedent
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from . import get_api, get_coordinator, get_storage
from .const import DOMAIN
from .exceptions import (
    PantryAuthError,
    PantryConflictError,
    PantryNotFoundError,
    PantryTimeoutError,
    PantryUnavailableError,
    PantryValidationError,
)
from .storage import InventoryStorage

ASSIST_SENTENCES_EN = dedent(
    """\
    language: "en"
    intents:
      InventoryAddItem:
        data:
          - sentences:
              - "(add | put) {item} (in | into | to) [the] {location}"
              - "(add | put) {item} (in | into | to) [my] {location}"
            lists:
              item:
                wildcard: true
              location:
                wildcard: true
      InventoryRemoveItem:
        data:
          - sentences:
              - "(remove | take) {item} from [the] {location}"
              - "(remove | take) {item} from [my] {location}"
            lists:
              item:
                wildcard: true
              location:
                wildcard: true
      InventoryGetItems:
        data:
          - sentences:
              - "<what_is> in [the] {location}"
              - "<what_is> in [my] {location}"
              - "list [the] items in [the] {location}"
              - "list [the] items in [my] {location}"
            lists:
              location:
                wildcard: true
      InventoryGetExpiringSoon:
        data:
          - sentences:
              - "<what_is> expiring soon"
              - "<what_is> expiring soon in [the] {location}"
              - "<what_is> expiring soon in [my] {location}"
            lists:
              location:
                wildcard: true
    expansion_rules:
      what_is: "(what's | whats | what is)"
    """
)


def _get_assist_sentence_target_path(hass: HomeAssistant) -> Path:
    """Return the installed Assist sentence path."""
    return Path(hass.config.path("custom_sentences", "en", "inventory.yaml"))


async def async_install_assist_sentences(hass: HomeAssistant) -> str:
    """Install the packaged Assist sentence file into the HA config dir."""
    target_path = _get_assist_sentence_target_path(hass)

    def _write_file() -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(ASSIST_SENTENCES_EN, encoding="utf-8")

    await hass.async_add_executor_job(_write_file)
    return str(target_path)


def _fire_event(hass: HomeAssistant, event_type: str, data: dict[str, Any]) -> None:
    """Fire an inventory event."""
    hass.bus.async_fire(f"{DOMAIN}_{event_type}", data)


def _snapshot(hass: HomeAssistant) -> dict[str, Any]:
    """Return current normalized snapshot."""
    return get_coordinator(hass).data or {}


def _validate_location(hass: HomeAssistant, location_id: str) -> dict[str, Any]:
    """Validate location exists and return it."""
    location = InventoryStorage.get_location(_snapshot(hass), location_id)
    if location is None:
        raise ServiceValidationError(f"Location '{location_id}' not found")
    return location


def _validate_expiry_date(expiry: str | None) -> str | None:
    """Validate expiry date format."""
    if expiry is None:
        return None
    try:
        date.fromisoformat(expiry)
    except ValueError as err:
        raise ServiceValidationError(
            f"Invalid expiry date format: {expiry}. Use YYYY-MM-DD."
        ) from err
    return expiry


def _normalize_item_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize an API item payload to HA shape."""
    if result is None:
        return None
    return InventoryStorage._normalize_item(result)


def _raise_service_error(err: Exception) -> None:
    """Translate pantry API errors into HA service errors."""
    if isinstance(err, PantryNotFoundError):
        raise ServiceValidationError(str(err)) from err
    if isinstance(err, PantryValidationError):
        raise ServiceValidationError(str(err)) from err
    if isinstance(err, PantryConflictError):
        raise HomeAssistantError(str(err)) from err
    if isinstance(err, (PantryAuthError, PantryTimeoutError, PantryUnavailableError)):
        raise HomeAssistantError(str(err)) from err
    raise err


ADD_ITEM_SCHEMA = vol.Schema(
    {
        vol.Required("location"): str,
        vol.Required("name"): str,
        vol.Optional("quantity", default=1): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("unit"): str,
        vol.Optional("expiry"): str,
        vol.Optional("category"): str,
        vol.Optional("notes"): str,
    }
)
REMOVE_ITEM_SCHEMA = vol.Schema(
    {
        vol.Required("location"): str,
        vol.Required("name"): str,
        vol.Optional("quantity"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)
UPDATE_ITEM_SCHEMA = vol.Schema(
    {
        vol.Required("location"): str,
        vol.Required("name"): str,
        vol.Optional("quantity"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("unit"): str,
        vol.Optional("expiry"): str,
        vol.Optional("category"): str,
        vol.Optional("notes"): str,
    }
)
CLEAR_EXPIRED_SCHEMA = vol.Schema({vol.Optional("location"): str})
CLEAR_ALL_SCHEMA = vol.Schema({vol.Required("location"): str})
INSTALL_ASSIST_SENTENCES_SCHEMA = vol.Schema({})
EXPORT_LOCAL_DATA_SCHEMA = vol.Schema({})


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Inventory integration."""

    async def _request_refresh() -> None:
        await get_coordinator(hass).async_request_refresh()

    async def add_item(call: ServiceCall) -> None:
        location_id = call.data["location"]
        name = call.data["name"]
        quantity = call.data.get("quantity", 1)
        unit = call.data.get("unit")
        expiry = _validate_expiry_date(call.data.get("expiry"))
        category = call.data.get("category")
        notes = call.data.get("notes")

        location = _validate_location(hass, location_id)
        try:
            result = await get_api(hass).add_item(
                {
                    "location": location_id,
                    "name": name,
                    "quantity": quantity,
                    "unit": unit,
                    "expiresOn": expiry,
                    "category": category,
                    "notes": notes,
                }
            )
        except Exception as err:
            _raise_service_error(err)

        item = _normalize_item_result(result)
        _fire_event(
            hass,
            "item_added",
            {
                "location_id": location_id,
                "location_name": location["name"],
                "item": item,
            },
        )
        _fire_event(hass, "updated", {"location_id": location_id})
        await _request_refresh()

    async def remove_item(call: ServiceCall) -> None:
        location_id = call.data["location"]
        name = call.data["name"]
        quantity = call.data.get("quantity", 1)

        location = _validate_location(hass, location_id)
        existing_item = InventoryStorage.get_item(_snapshot(hass), location_id, name)
        if existing_item is None:
            return

        try:
            result = await get_api(hass).remove_item(
                {"location": location_id, "name": name, "quantity": quantity}
            )
        except Exception as err:
            _raise_service_error(err)

        removed_entirely = bool(result.get("deleted"))
        payload_item = existing_item if removed_entirely else _normalize_item_result(result.get("item"))
        reason = "depleted" if removed_entirely and existing_item.get("quantity", 1) <= quantity else "user_action"
        _fire_event(
            hass,
            "item_removed",
            {
                "location_id": location_id,
                "location_name": location["name"],
                "item_name": name,
                "item": payload_item,
                "reason": reason,
            },
        )
        _fire_event(hass, "updated", {"location_id": location_id})
        await _request_refresh()

    async def update_item(call: ServiceCall) -> None:
        location_id = call.data["location"]
        name = call.data["name"]
        quantity = call.data.get("quantity")
        unit = call.data.get("unit")
        expiry = _validate_expiry_date(call.data.get("expiry"))
        category = call.data.get("category")
        notes = call.data.get("notes")

        location = _validate_location(hass, location_id)
        try:
            result = await get_api(hass).update_item(
                {
                    "location": location_id,
                    "name": name,
                    "updates": {
                        **({"quantity": quantity} if quantity is not None else {}),
                        **({"unit": unit} if unit is not None else {}),
                        **({"expiresOn": expiry} if expiry is not None else {}),
                        **({"category": category} if category is not None else {}),
                        **({"notes": notes} if notes is not None else {}),
                    },
                }
            )
        except Exception as err:
            _raise_service_error(err)

        _fire_event(
            hass,
            "item_updated",
            {
                "location_id": location_id,
                "location_name": location["name"],
                "item": _normalize_item_result(result),
            },
        )
        _fire_event(hass, "updated", {"location_id": location_id})
        await _request_refresh()

    async def clear_expired(call: ServiceCall) -> ServiceResponse:
        location_id = call.data.get("location")
        snapshot = _snapshot(hass)

        if location_id is None:
            removed_items = [
                item
                for location in InventoryStorage.get_locations(snapshot).values()
                for item in location.get("items", [])
                if InventoryStorage._is_expired(item)
            ]
            try:
                await get_api(hass).clear_expired()
            except Exception as err:
                _raise_service_error(err)
        else:
            _validate_location(hass, location_id)
            removed_items = [
                {**item, "location_id": location_id}
                for item in InventoryStorage.get_items(snapshot, location_id)
                if InventoryStorage._is_expired(item)
            ]
            try:
                for item in removed_items:
                    await get_api(hass).delete_item(item["id"])
            except Exception as err:
                _raise_service_error(err)

        if removed_items:
            _fire_event(
                hass,
                "expired_cleared",
                {
                    "location_id": location_id,
                    "items": removed_items,
                    "count": len(removed_items),
                },
            )
            _fire_event(hass, "updated", {"location_id": location_id})
            await _request_refresh()

        return {"removed_count": len(removed_items), "items": removed_items}

    async def clear_all(call: ServiceCall) -> ServiceResponse:
        location_id = call.data["location"]
        location = _validate_location(hass, location_id)
        removed_items = list(InventoryStorage.get_items(_snapshot(hass), location_id))

        try:
            for item in removed_items:
                await get_api(hass).delete_item(item["id"])
        except Exception as err:
            _raise_service_error(err)

        _fire_event(
            hass,
            "all_cleared",
            {
                "location_id": location_id,
                "location_name": location["name"],
                "count": len(removed_items),
            },
        )
        _fire_event(hass, "updated", {"location_id": location_id})
        await _request_refresh()
        return {"removed_count": len(removed_items)}

    async def install_assist_sentences(call: ServiceCall) -> ServiceResponse:
        """Install Assist sentences."""
        return {"installed": True, "path": await async_install_assist_sentences(hass)}

    async def export_local_data(call: ServiceCall) -> ServiceResponse:
        """Return preserved legacy local data if present."""
        payload = get_storage(hass).get_legacy_export_payload()
        return {"available": payload is not None, "data": payload}

    hass.services.async_register(DOMAIN, "add_item", add_item, schema=ADD_ITEM_SCHEMA)
    hass.services.async_register(DOMAIN, "remove_item", remove_item, schema=REMOVE_ITEM_SCHEMA)
    hass.services.async_register(DOMAIN, "update_item", update_item, schema=UPDATE_ITEM_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        "clear_expired",
        clear_expired,
        schema=CLEAR_EXPIRED_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "clear_all",
        clear_all,
        schema=CLEAR_ALL_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "install_assist_sentences",
        install_assist_sentences,
        schema=INSTALL_ASSIST_SENTENCES_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "export_local_data",
        export_local_data,
        schema=EXPORT_LOCAL_DATA_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Inventory services."""
    for service in (
        "add_item",
        "remove_item",
        "update_item",
        "clear_expired",
        "clear_all",
        "install_assist_sentences",
        "export_local_data",
    ):
        hass.services.async_remove(DOMAIN, service)
