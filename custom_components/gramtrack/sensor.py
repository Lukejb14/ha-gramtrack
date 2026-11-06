"""GramTrack's sensors.

`sensor.gramtrack` publishes the selected entity list:
  - state: number of selected entities
  - attributes.entities  : list of chosen entity_ids (canonical)
  - attributes.entity_id : same list, mirrored so the iOS app's existing
                            group-member decode works with zero changes

`sensor.gramtrack_home_layout` (only when a layout dashboard is set in
Options) publishes that dashboard as the app's Home layout:
  - state: when the tiles last changed (ISO, UTC); unknown when the
           dashboard is missing
  - attributes: source, version, last_changed, stale, buildings, ignored
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENTITIES, DOMAIN
from .coordinator import HomeLayoutCoordinator
from .layout import sensor_view


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities: list[SensorEntity] = [GramTrackSensor(entry)]
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None:
        entities.append(GramTrackHomeLayoutSensor(entry, coordinator))
    async_add_entities(entities)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="GramTrack",
        manufacturer="GramTrack",
    )


class GramTrackSensor(SensorEntity):
    """Surfaces the user's entity selection for the GramTrack app."""

    _attr_should_poll = False
    _attr_icon = "mdi:cellphone-link"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_name = "GramTrack"
        self._attr_device_info = _device_info(entry)

    @property
    def _entities(self) -> list[str]:
        return list(
            self._entry.options.get(
                CONF_ENTITIES, self._entry.data.get(CONF_ENTITIES, [])
            )
        )

    @property
    def native_value(self) -> int:
        return len(self._entities)

    @property
    def extra_state_attributes(self) -> dict[str, list[str]]:
        ents = self._entities
        return {"entities": ents, "entity_id": ents}


class GramTrackHomeLayoutSensor(SensorEntity):
    """Mirrors the dashboard named in Options as the app's Home layout."""

    _attr_should_poll = False
    _attr_icon = "mdi:view-dashboard-edit"
    # The layout can run to a few KB; keeping its history is of no use.
    _unrecorded_attributes = frozenset({"buildings", "ignored"})

    def __init__(self, entry: ConfigEntry, coordinator: HomeLayoutCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_home_layout"
        self._attr_name = "GramTrack Home Layout"
        self._attr_device_info = _device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )

    @property
    def native_value(self) -> str | None:
        return sensor_view(self._coordinator.state, self._coordinator.url_path)[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return sensor_view(self._coordinator.state, self._coordinator.url_path)[1]
