"""Typed exceptions for pantry server operations."""

from __future__ import annotations


class PantryApiError(Exception):
    """Base pantry API error."""


class PantryAuthError(PantryApiError):
    """Authentication or authorization failed."""


class PantryTimeoutError(PantryApiError):
    """Request timed out."""


class PantryNotFoundError(PantryApiError):
    """Requested resource was not found."""


class PantryValidationError(PantryApiError):
    """Request validation failed."""


class PantryConflictError(PantryApiError):
    """Request conflicted with current server state."""


class PantryUnavailableError(PantryApiError):
    """Pantry server is unavailable."""
