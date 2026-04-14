"""Async client for pantry-server."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from .exceptions import (
    PantryAuthError,
    PantryConflictError,
    PantryNotFoundError,
    PantryTimeoutError,
    PantryUnavailableError,
    PantryValidationError,
)


class PantryApiClient:
    """Client for pantry-server endpoints."""

    def __init__(
        self,
        session: ClientSession,
        base_url: str,
        api_key: str,
        request_timeout: int,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._request_timeout = request_timeout

    @property
    def base_url(self) -> str:
        """Return the configured base URL."""
        return self._base_url

    async def health(self) -> dict[str, Any]:
        """Fetch health status."""
        return await self._request("get", "/health")

    async def get_state(self, etag: str | None = None) -> tuple[int, str | None, dict[str, Any] | None]:
        """Fetch pantry state."""
        headers = {}
        if etag:
            headers["If-None-Match"] = etag

        return await self._request("get", "/state", headers=headers, allow_not_modified=True)

    async def list_locations(self) -> list[dict[str, Any]]:
        """List locations."""
        response = await self._request("get", "/locations")
        return list(response)

    async def create_location(self, location_id: str, name: str) -> dict[str, Any]:
        """Create a location."""
        return await self._request(
            "post",
            "/locations",
            json={"id": location_id, "name": name},
        )

    async def update_location(self, location_id: str, name: str) -> dict[str, Any]:
        """Rename a location."""
        return await self._request(
            "patch",
            f"/locations/{location_id}",
            json={"name": name},
        )

    async def delete_location(self, location_id: str) -> None:
        """Delete an empty location."""
        await self._request("delete", f"/locations/{location_id}", expect_json=False)

    async def add_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Add an item."""
        return await self._request("post", "/actions/add_item", json=payload)

    async def remove_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Remove an item."""
        return await self._request("post", "/actions/remove_item", json=payload)

    async def update_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Update an item."""
        return await self._request("post", "/actions/update_item", json=payload)

    async def clear_expired(self) -> dict[str, Any]:
        """Clear expired items globally."""
        return await self._request("post", "/actions/clear_expired")

    async def clear_all(self) -> dict[str, Any]:
        """Clear all items globally."""
        return await self._request("post", "/actions/clear_all")

    async def delete_item(self, item_id: str) -> None:
        """Delete one item."""
        await self._request("delete", f"/items/{item_id}", expect_json=False)

    async def update_item_record(self, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Patch one item record."""
        return await self._request("patch", f"/items/{item_id}", json=payload)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        allow_not_modified: bool = False,
        expect_json: bool = True,
    ) -> Any:
        """Perform one API request."""
        request_headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }
        if headers:
            request_headers.update(headers)

        url = f"{self._base_url}/api/v1{path}"

        try:
            async with self._session.request(
                method,
                url,
                headers=request_headers,
                json=json,
                timeout=self._request_timeout,
            ) as response:
                if allow_not_modified and response.status == 304:
                    return 304, response.headers.get("etag"), None

                if response.status in (401, 403):
                    raise PantryAuthError("Authentication with pantry server failed.")
                if response.status == 404:
                    raise PantryNotFoundError("Requested pantry resource was not found.")
                if response.status == 409:
                    raise PantryConflictError("Pantry server rejected the request due to a conflict.")
                if response.status == 400:
                    raise PantryValidationError("Pantry server rejected the request.")
                if response.status >= 500:
                    raise PantryUnavailableError("Pantry server is unavailable.")

                response.raise_for_status()

                if not expect_json or response.status == 204:
                    return None

                payload = await response.json()
                if allow_not_modified:
                    return response.status, response.headers.get("etag"), payload
                return payload

        except PantryAuthError:
            raise
        except PantryNotFoundError:
            raise
        except PantryConflictError:
            raise
        except PantryValidationError:
            raise
        except PantryUnavailableError:
            raise
        except TimeoutError as err:
            raise PantryTimeoutError("Request to pantry server timed out.") from err
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise PantryAuthError("Authentication with pantry server failed.") from err
            if err.status == 404:
                raise PantryNotFoundError("Requested pantry resource was not found.") from err
            if err.status == 409:
                raise PantryConflictError("Pantry server rejected the request due to a conflict.") from err
            if err.status == 400:
                raise PantryValidationError("Pantry server rejected the request.") from err
            raise PantryUnavailableError("Pantry server request failed.") from err
        except ClientError as err:
            raise PantryUnavailableError("Unable to reach pantry server.") from err
