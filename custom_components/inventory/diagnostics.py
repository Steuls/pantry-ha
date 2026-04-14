"""Diagnostics support for Inventory."""

from __future__ import annotations

from urllib.parse import urlparse

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import get_coordinator, get_storage
from .const import CONF_API_KEY, CONF_BASE_URL

TO_REDACT = {CONF_API_KEY}


def _redact_base_url(base_url: str) -> str:
    """Redact path/query details from the configured base URL."""
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        return "<invalid>"
    return f"{parsed.scheme}://{parsed.netloc}"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict:
    """Return diagnostics for a config entry."""
    coordinator = get_coordinator(hass)
    storage = get_storage(hass)
    return {
        "entry": {
            **async_redact_data(dict(entry.data), TO_REDACT),
            CONF_BASE_URL: _redact_base_url(entry.data[CONF_BASE_URL]),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "failed_refresh_count": coordinator.failed_refresh_count,
            "last_successful_sync": coordinator.last_sync_success_at,
            "source": coordinator.data.get("source") if coordinator.data else None,
            "location_count": len((coordinator.data or {}).get("locations", {})),
        },
        "cache": {
            "enabled": entry.data.get("enable_cache"),
            "has_cached_snapshot": storage.get_cached_snapshot() is not None,
            "last_successful_sync": storage.get_last_successful_sync(),
        },
    }
