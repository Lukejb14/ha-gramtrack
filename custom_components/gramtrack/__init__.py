"""The GramTrack integration.

Lets you pick, in the Home Assistant UI, which entities appear in the
GramTrack iOS app's Home-screen sensor strip. The selection is published
as `sensor.gramtrack` (the chosen entity_ids live in its attributes), which
the app reads through Home Assistant's existing /api/states endpoint.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GramTrack from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when the entity selection changes in Options."""
    await hass.config_entries.async_reload(entry.entry_id)
