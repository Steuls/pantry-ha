"""The Inventory integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PantryApiClient
from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_ENABLE_CACHE,
    CONF_POLL_SECONDS,
    CONF_REQUEST_TIMEOUT,
    DATA_API,
    DATA_COORDINATOR,
    DATA_ENTRY_ID,
    DATA_INTENTS_REGISTERED,
    DATA_SERVICES_REGISTERED,
    DATA_STORAGE,
    DOMAIN,
)
from .coordinator import InventoryCoordinator
from .exceptions import PantryApiError
from .intent import async_setup_intents
from .panel import async_setup_panel
from .services import async_install_assist_sentences, async_setup_services
from .storage import InventoryStorage

if TYPE_CHECKING:
    from homeassistant.helpers.typing import ConfigType

PLATFORMS: list[Platform] = [Platform.SENSOR]


def _get_domain_data(hass: HomeAssistant) -> dict[str, Any]:
    """Return shared domain data."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {
            DATA_INTENTS_REGISTERED: False,
            DATA_SERVICES_REGISTERED: False,
        }
    return hass.data[DOMAIN]


def get_storage(hass: HomeAssistant) -> InventoryStorage:
    """Return integration storage."""
    return _get_domain_data(hass)[DATA_STORAGE]


def get_coordinator(hass: HomeAssistant) -> InventoryCoordinator:
    """Return integration coordinator."""
    return _get_domain_data(hass)[DATA_COORDINATOR]


def get_api(hass: HomeAssistant) -> PantryApiClient:
    """Return integration API client."""
    return _get_domain_data(hass)[DATA_API]


def get_active_entry_id(hass: HomeAssistant) -> str | None:
    """Return the active config entry id."""
    return _get_domain_data(hass).get(DATA_ENTRY_ID)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Inventory integration."""
    domain_data = _get_domain_data(hass)

    if DATA_STORAGE not in domain_data:
        storage = InventoryStorage(hass)
        await storage.async_load()
        domain_data[DATA_STORAGE] = storage

    if not domain_data[DATA_SERVICES_REGISTERED]:
        await async_setup_services(hass)
        domain_data[DATA_SERVICES_REGISTERED] = True

    try:
        await async_install_assist_sentences(hass)
    except HomeAssistantError:
        pass

    async_setup_intents(hass)
    await async_setup_panel(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Inventory from a config entry."""
    domain_data = _get_domain_data(hass)
    storage = get_storage(hass)
    session = async_get_clientsession(hass)
    api = PantryApiClient(
        session=session,
        base_url=entry.data[CONF_BASE_URL],
        api_key=entry.data[CONF_API_KEY],
        request_timeout=entry.data[CONF_REQUEST_TIMEOUT],
    )
    coordinator = InventoryCoordinator(
        hass,
        api=api,
        storage=storage,
        poll_seconds=entry.data[CONF_POLL_SECONDS],
        enable_cache=entry.data[CONF_ENABLE_CACHE],
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except PantryApiError as err:
        raise ConfigEntryNotReady(str(err)) from err
    except Exception as err:
        if coordinator.data is None:
            raise ConfigEntryNotReady(str(err)) from err

    domain_data[DATA_API] = api
    domain_data[DATA_COORDINATOR] = coordinator
    domain_data[DATA_ENTRY_ID] = entry.entry_id

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    domain_data = _get_domain_data(hass)
    domain_data.pop(DATA_API, None)
    domain_data.pop(DATA_COORDINATOR, None)
    domain_data.pop(DATA_ENTRY_ID, None)
    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_entry: Any,
) -> bool:
    """Disallow removing the shared integration device."""
    return False
