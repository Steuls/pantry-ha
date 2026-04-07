"""The Inventory integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .intent import async_setup_intents
from .panel import async_setup_panel
from .services import (
    async_install_assist_sentences,
    async_setup_services,
    async_unload_services,
)
from .storage import InventoryStorage

if TYPE_CHECKING:
    from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Inventory integration."""
    _LOGGER.debug("async_setup called")
    # Initialize storage
    if DOMAIN not in hass.data:
        _LOGGER.debug("Creating storage instance")
        storage = InventoryStorage(hass)
        await storage.async_load()
        hass.data[DOMAIN] = {"storage": storage}
        _LOGGER.debug("Storage initialized")
    else:
        _LOGGER.debug("Storage already exists")

    # Register services
    _LOGGER.debug("Setting up services")
    await async_setup_services(hass)

    # Keep Assist sentence pack in sync with the installed integration version
    try:
        await async_install_assist_sentences(hass)
    except HomeAssistantError:
        _LOGGER.exception("Failed to install Assist sentences")

    # Register Assist intent handlers
    _LOGGER.debug("Setting up intents")
    async_setup_intents(hass)

    # Register sidebar panel
    _LOGGER.debug("Setting up panel")
    await async_setup_panel(hass)

    _LOGGER.debug("async_setup complete")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Inventory from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
