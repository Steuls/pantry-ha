"""Shared runtime accessors for Inventory."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    DATA_API,
    DATA_COORDINATOR,
    DATA_ENTRY_ID,
    DATA_INTENTS_REGISTERED,
    DATA_SERVICES_REGISTERED,
    DATA_STORAGE,
    DOMAIN,
)


def get_domain_data(hass: HomeAssistant) -> dict[str, Any]:
    """Return shared domain data."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {
            DATA_INTENTS_REGISTERED: False,
            DATA_SERVICES_REGISTERED: False,
        }
    return hass.data[DOMAIN]


def get_storage(hass: HomeAssistant):
    """Return integration storage."""
    return get_domain_data(hass)[DATA_STORAGE]


def get_coordinator(hass: HomeAssistant):
    """Return integration coordinator."""
    return get_domain_data(hass)[DATA_COORDINATOR]


def get_api(hass: HomeAssistant):
    """Return integration API client."""
    return get_domain_data(hass)[DATA_API]


def get_active_entry_id(hass: HomeAssistant) -> str | None:
    """Return the active config entry id."""
    return get_domain_data(hass).get(DATA_ENTRY_ID)
