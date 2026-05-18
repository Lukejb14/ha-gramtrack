"""Config + options flow for GramTrack.

A single config entry. The user picks any entities (mixed domains allowed)
with Home Assistant's native multi-select entity picker — the same kind of
UI the HomeKit integration uses — at install time and via Configure later.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import CONF_ENTITIES, DOMAIN

_ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(multiple=True)
)


class GramTrackConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="GramTrack", data=user_input)

        schema = vol.Schema(
            {vol.Optional(CONF_ENTITIES, default=[]): _ENTITY_SELECTOR}
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return GramTrackOptionsFlow(config_entry)


class GramTrackOptionsFlow(OptionsFlow):
    """Edit the selected entities after setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        # Stored under a private name so we don't shadow the base-class
        # `config_entry` property (avoids the HA deprecation warning).
        self._entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._entry.options.get(
            CONF_ENTITIES, self._entry.data.get(CONF_ENTITIES, [])
        )
        schema = vol.Schema(
            {vol.Optional(CONF_ENTITIES, default=current): _ENTITY_SELECTOR}
        )
        return self.async_show_form(step_id="init", data_schema=schema)
