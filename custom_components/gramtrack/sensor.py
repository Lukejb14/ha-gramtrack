"""GramTrack publishes the selected entity list as a single sensor.

`sensor.gramtrack`:
  - state: number of selected entities
  - attributes.entities  : list of chosen entity_ids (canonical)
  - attributes.entity_id : same list, mirrored so the iOS app's existing
                            group-member decode works with zero changes
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENTITIES, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([GramTrackSensor(entry)])


class GramTrackSensor(SensorEntity):
    """Surfaces the user's entity selection for the GramTrack app."""

    _attr_should_poll = False
    _attr_icon = "mdi:cellphone-link"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_name = "GramTrack"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="GramTrack",
            manufacturer="GramTrack",
        )

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
