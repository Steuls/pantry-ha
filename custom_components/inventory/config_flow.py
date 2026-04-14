"""Config flow for Inventory integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import slugify

from .api import PantryApiClient
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_ENABLE_CACHE,
    CONF_ICON,
    CONF_POLL_SECONDS,
    CONF_REQUEST_TIMEOUT,
    DEFAULT_ENABLE_CACHE,
    DEFAULT_ICON,
    DEFAULT_POLL_SECONDS,
    DEFAULT_REQUEST_TIMEOUT,
    DOMAIN,
)
from .exceptions import (
    PantryAuthError,
    PantryConflictError,
    PantryNotFoundError,
    PantryTimeoutError,
    PantryUnavailableError,
    PantryValidationError,
)
from .runtime import get_api, get_coordinator, get_storage
from .storage import InventoryStorage


def _config_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the setup schema."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_BASE_URL,
                default=defaults.get(CONF_BASE_URL, "http://pantry-server:3000"),
            ): TextSelector(),
            vol.Required(
                CONF_API_KEY,
                default=defaults.get(CONF_API_KEY, ""),
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            vol.Required(
                CONF_POLL_SECONDS,
                default=defaults.get(CONF_POLL_SECONDS, DEFAULT_POLL_SECONDS),
            ): NumberSelector(
                NumberSelectorConfig(min=10, max=3600, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_REQUEST_TIMEOUT,
                default=defaults.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT),
            ): NumberSelector(
                NumberSelectorConfig(min=5, max=120, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_ENABLE_CACHE,
                default=defaults.get(CONF_ENABLE_CACHE, DEFAULT_ENABLE_CACHE),
            ): BooleanSelector(),
        }
    )


async def _validate_server(hass, user_input: dict[str, Any]) -> None:
    """Validate connectivity to pantry-server."""
    client = PantryApiClient(
        session=async_get_clientsession(hass),
        base_url=user_input[CONF_BASE_URL],
        api_key=user_input[CONF_API_KEY],
        request_timeout=int(user_input[CONF_REQUEST_TIMEOUT]),
    )
    await client.health()
    await client.get_state()


class InventoryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Inventory."""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            normalized_input = {
                **user_input,
                CONF_BASE_URL: str(user_input[CONF_BASE_URL]).rstrip("/"),
                CONF_POLL_SECONDS: int(user_input[CONF_POLL_SECONDS]),
                CONF_REQUEST_TIMEOUT: int(user_input[CONF_REQUEST_TIMEOUT]),
            }
            try:
                await _validate_server(self.hass, normalized_input)
            except PantryAuthError:
                errors["base"] = "auth"
            except PantryTimeoutError:
                errors["base"] = "timeout"
            except PantryValidationError:
                errors["base"] = "invalid_response"
            except PantryUnavailableError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="Inventory", data=normalized_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_config_schema(user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> InventoryOptionsFlow:
        """Get the options flow for this handler."""
        return InventoryOptionsFlow()


class InventoryOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Inventory."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self._selected_location: str | None = None

    def _snapshot_locations(self) -> dict[str, dict[str, Any]]:
        """Return current known locations."""
        coordinator = get_coordinator(self.hass)
        return InventoryStorage.get_locations(coordinator.data)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle options flow."""
        locations = self._snapshot_locations()
        if not locations:
            return await self.async_step_add_location()

        return self.async_show_menu(
            step_id="init",
            menu_options=["add_location", "select_location"],
            description_placeholders={"location_count": str(len(locations))},
        )

    async def async_step_add_location(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Create a server-backed location."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input["name"]).strip()
            if not name:
                errors["name"] = "name_required"
            else:
                location_id = slugify(name)
                try:
                    await get_api(self.hass).create_location(location_id, name)
                    await get_storage(self.hass).async_set_location_icon(location_id, DEFAULT_ICON)
                    await get_coordinator(self.hass).async_request_refresh()
                    await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                    return self.async_create_entry(title="", data={})
                except PantryConflictError:
                    errors["name"] = "name_exists"
                except PantryValidationError:
                    errors["base"] = "invalid_response"
                except PantryUnavailableError:
                    errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="add_location",
            data_schema=vol.Schema({vol.Required("name"): str}),
            errors=errors,
        )

    async def async_step_select_location(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a location to manage."""
        locations = self._snapshot_locations()
        if len(locations) == 1:
            self._selected_location = next(iter(locations))
            return await self.async_step_manage_location()

        if user_input is not None:
            self._selected_location = user_input["location"]
            return await self.async_step_manage_location()

        return self.async_show_form(
            step_id="select_location",
            data_schema=vol.Schema(
                {
                    vol.Required("location"): vol.In(
                        {loc_id: location["name"] for loc_id, location in locations.items()}
                    )
                }
            ),
        )

    async def async_step_manage_location(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage selected location."""
        location = self._snapshot_locations().get(self._selected_location or "")
        location_name = location["name"] if location else self._selected_location or ""
        return self.async_show_menu(
            step_id="manage_location",
            menu_options=["rename_location", "delete_location", "init"],
            description_placeholders={"location_name": location_name},
        )

    async def async_step_rename_location(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Rename a location and optionally update its local icon."""
        errors: dict[str, str] = {}
        storage = get_storage(self.hass)
        location = self._snapshot_locations().get(self._selected_location or "")

        if user_input is not None and self._selected_location is not None:
            name = str(user_input["name"]).strip()
            icon = str(user_input[CONF_ICON]).strip() or DEFAULT_ICON
            if not name:
                errors["name"] = "name_required"
            else:
                try:
                    await get_api(self.hass).update_location(self._selected_location, name)
                    await storage.async_set_location_icon(self._selected_location, icon)
                    await get_coordinator(self.hass).async_request_refresh()
                    await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                    return self.async_create_entry(title="", data={})
                except PantryNotFoundError:
                    errors["base"] = "location_not_found"
                except PantryConflictError:
                    errors["name"] = "name_exists"
                except PantryUnavailableError:
                    errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="rename_location",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=location["name"] if location else ""): str,
                    vol.Optional(
                        CONF_ICON,
                        default=storage.get_location_icon(self._selected_location or ""),
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_delete_location(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Delete a location."""
        errors: dict[str, str] = {}
        location = self._snapshot_locations().get(self._selected_location or "")
        location_name = location["name"] if location else self._selected_location or ""
        item_count = len(location.get("items", [])) if location else 0

        if user_input is not None and self._selected_location is not None:
            if not user_input.get("confirm", False):
                return await self.async_step_init()
            try:
                await get_api(self.hass).delete_location(self._selected_location)
                await get_storage(self.hass).async_remove_location_icon(self._selected_location)
                await get_coordinator(self.hass).async_request_refresh()
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                return self.async_create_entry(title="", data={})
            except PantryConflictError:
                errors["base"] = "location_not_empty"
            except PantryNotFoundError:
                errors["base"] = "location_not_found"
            except PantryUnavailableError:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="delete_location",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            description_placeholders={
                "location_name": location_name,
                "item_count": str(item_count),
            },
            errors=errors,
        )
