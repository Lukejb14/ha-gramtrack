"""The GramTrack integration.

Lets you pick, in the Home Assistant UI, which entities appear in the
GramTrack iOS app's Home-screen sensor strip. The selection is published
as `sensor.gramtrack` (the chosen entity_ids live in its attributes), which
the app reads through Home Assistant's existing /api/states endpoint.

Optionally, it also mirrors a dashboard you name in Options as
`sensor.gramtrack_home_layout`: the tiles the app's Home shows, by building.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_LAYOUT_DASHBOARD, DOMAIN
from .coordinator import HomeLayoutCoordinator
from .layout import clean_url_path

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GramTrack from a config entry."""
    url_path = clean_url_path(
        entry.options.get(CONF_LAYOUT_DASHBOARD, entry.data.get(CONF_LAYOUT_DASHBOARD))
    )
    if url_path:
        coordinator = HomeLayoutCoordinator(hass, url_path)
        await coordinator.async_start()
        entry.async_on_unload(coordinator.async_stop)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when the entity selection changes in Options."""
    await hass.config_entries.async_reload(entry.entry_id)
