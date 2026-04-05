"""Config flow for Inventory integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.util import slugify

from .const import DOMAIN
from .storage import InventoryStorage

DEFAULT_ICON = "mdi:package-variant"


def _get_storage(hass: HomeAssistant) -> InventoryStorage | None:
    """Get the storage instance."""
    if DOMAIN not in hass.data:
        return None
    return hass.data[DOMAIN].get("storage")


async def _ensure_storage(hass: HomeAssistant) -> InventoryStorage:
    """Ensure storage is initialized and return it."""
    if DOMAIN not in hass.data:
        from .storage import InventoryStorage
        storage = InventoryStorage(hass)
        await storage.async_load()
        hass.data[DOMAIN] = {"storage": storage}
    return hass.data[DOMAIN]["storage"]


class InventoryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Inventory."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="Inventory", data={})

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> InventoryOptionsFlow:
        """Get the options flow for this handler."""
        return InventoryOptionsFlow(config_entry)


class InventoryOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Inventory."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._selected_location: str | None = None

    def _get_storage(self) -> InventoryStorage:
        """Get storage instance."""
        storage = _get_storage(self.hass)
        if storage is None:
            raise RuntimeError("Storage not initialized")
        return storage

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow - show menu."""
        # Ensure storage is initialized
        await _ensure_storage(self.hass)

        if user_input is not None:
            action = user_input.get("action")
            if action == "add":
                return await self.async_step_add_location()
            elif action == "manage":
                return await self.async_step_select_location()

        # Build options menu
        locations = self._get_storage().get_locations()
        location_count = len(locations)

        options_schema = vol.Schema({
            vol.Required("action"): vol.In(["add", "manage"] if location_count > 0 else ["add"])
        })

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            description_placeholders={
                "location_count": str(location_count)
            },
        )

    async def async_step_add_location(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a new location."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input.get("name", "").strip()
            icon = user_input.get("icon", DEFAULT_ICON)

            if not name:
                errors["name"] = "name_required"
            else:
                storage = self._get_storage()
                # Check for duplicate name
                for loc in storage.get_locations().values():
                    if loc.get("name", "").lower() == name.lower():
                        errors["name"] = "name_exists"
                        break

                if not errors:
                    location_id = slugify(name)
                    base_id = location_id
                    counter = 1
                    while storage.get_location(location_id) is not None:
                        location_id = f"{base_id}_{counter}"
                        counter += 1
                    await storage.async_add_location(location_id, name, icon)
                    return await self.async_step_init()

        schema = vol.Schema({
            vol.Required("name"): str,
            vol.Optional("icon", default=DEFAULT_ICON): str,
        })

        return self.async_show_form(
            step_id="add_location",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_select_location(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a location to manage."""
        if user_input is not None:
            self._selected_location = user_input.get("location")
            return await self.async_step_manage_location()

        storage = self._get_storage()
        locations = storage.get_locations()

        location_options = {
            loc_id: loc_data.get("name", loc_id)
            for loc_id, loc_data in locations.items()
        }

        schema = vol.Schema({
            vol.Required("location"): vol.In(location_options)
        })

        return self.async_show_form(
            step_id="select_location",
            data_schema=schema,
        )

    async def async_step_manage_location(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage selected location - rename, delete, or back."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "rename":
                return await self.async_step_rename_location()
            elif action == "delete":
                return await self.async_step_delete_location()
            elif action == "back":
                return await self.async_step_init()

        storage = self._get_storage()
        location = storage.get_location(self._selected_location)
        location_name = location.get("name", self._selected_location) if location else self._selected_location

        schema = vol.Schema({
            vol.Required("action"): vol.In(["rename", "delete", "back"])
        })

        return self.async_show_form(
            step_id="manage_location",
            data_schema=schema,
            description_placeholders={
                "location_name": location_name
            },
        )

    async def async_step_rename_location(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Rename a location."""
        errors: dict[str, str] = {}

        storage = self._get_storage()
        location = storage.get_location(self._selected_location)

        if user_input is not None:
            new_name = user_input.get("name", "").strip()
            new_icon = user_input.get("icon")

            if not new_name:
                errors["name"] = "name_required"
            else:
                # Check for duplicate name (excluding current)
                for loc_id, loc_data in storage.get_locations().items():
                    if loc_id != self._selected_location:
                        if loc_data.get("name", "").lower() == new_name.lower():
                            errors["name"] = "name_exists"
                            break

                if not errors:
                    await storage.async_update_location(
                        self._selected_location,
                        name=new_name,
                        icon=new_icon
                    )
                    return await self.async_step_init()

        current_name = location.get("name", "") if location else ""
        current_icon = location.get("icon", DEFAULT_ICON) if location else DEFAULT_ICON

        schema = vol.Schema({
            vol.Required("name", default=current_name): str,
            vol.Optional("icon", default=current_icon): str,
        })

        return self.async_show_form(
            step_id="rename_location",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_delete_location(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Delete a location with confirmation."""
        if user_input is not None:
            confirm = user_input.get("confirm", False)
            if confirm:
                storage = self._get_storage()
                await storage.async_remove_location(self._selected_location)
            return await self.async_step_init()

        storage = self._get_storage()
        location = storage.get_location(self._selected_location)
        location_name = location.get("name", self._selected_location) if location else self._selected_location
        item_count = len(location.get("items", [])) if location else 0

        schema = vol.Schema({
            vol.Required("confirm", default=False): bool
        })

        return self.async_show_form(
            step_id="delete_location",
            data_schema=schema,
            description_placeholders={
                "location_name": location_name,
                "item_count": str(item_count)
            },
        )
