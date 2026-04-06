"""Home Assistant sidebar panel for Inventory."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

PANEL_URL_PATH = "inventory"
STATIC_URL_PATH = "/inventory_static"


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Register static assets and sidebar panel."""
    static_dir = Path(__file__).parent / "frontend"

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                STATIC_URL_PATH,
                str(static_dir),
                cache_headers=False,
            )
        ]
    )

    async_register_built_in_panel(
        hass,
        component_name="custom",
        frontend_url_path=PANEL_URL_PATH,
        sidebar_title="Inventory",
        sidebar_icon="mdi:package-variant",
        require_admin=False,
        config={
            "_panel_custom": {
                "name": "inventory-panel",
                "module_url": f"{STATIC_URL_PATH}/inventory-panel.js",
                "trust_external_script": False,
            }
        },
    )
