"""Coordinator for pantry-server state."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PantryApiClient
from .exceptions import PantryAuthError, PantryTimeoutError, PantryUnavailableError
from .storage import InventoryStorage

_LOGGER = logging.getLogger(__name__)


class InventoryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate state updates from pantry-server."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        api: PantryApiClient,
        storage: InventoryStorage,
        poll_seconds: int,
        enable_cache: bool,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Inventory",
            update_interval=None if poll_seconds <= 0 else timedelta(seconds=poll_seconds),
        )
        self.api = api
        self.storage = storage
        self.enable_cache = enable_cache
        self.failed_refresh_count = 0
        self.last_sync_success_at: str | None = storage.get_last_successful_sync()

    @property
    def has_usable_data(self) -> bool:
        """Return whether the coordinator can serve state."""
        return self.data is not None

    async def async_config_entry_first_refresh(self) -> None:
        """Prefer cached state before the first network refresh if available."""
        if self.enable_cache:
            cached = self.storage.get_cached_snapshot()
            if cached is not None:
                self.async_set_updated_data(cached)
        await super().async_config_entry_first_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and normalize the latest pantry state."""
        current_etag = self.data.get("etag") if self.data else None

        try:
            status, etag, payload = await self.api.get_state(etag=current_etag)
        except PantryAuthError as err:
            raise UpdateFailed(str(err)) from err
        except (PantryTimeoutError, PantryUnavailableError) as err:
            self.failed_refresh_count += 1
            cached = self.storage.get_cached_snapshot() if self.enable_cache else None
            if cached is not None:
                return cached
            raise UpdateFailed(str(err)) from err

        self.failed_refresh_count = 0

        if status == 304 and self.data is not None:
            refreshed = dict(self.data)
            refreshed["source"] = "server"
            return refreshed

        normalized = InventoryStorage.normalize_state(
            payload or {},
            storage=self.storage,
            source="server",
            etag=etag,
        )
        synced_at = datetime.now(timezone.utc).isoformat()
        self.last_sync_success_at = synced_at
        if self.enable_cache:
            await self.storage.async_save_snapshot(normalized, synced_at)
        return normalized
