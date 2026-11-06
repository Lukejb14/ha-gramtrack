"""Config + options flow for GramTrack.

A single config entry. The user picks any entities (mixed domains allowed)
with Home Assistant's native multi-select entity picker — the same kind of
UI the HomeKit integration uses — at install time and via Configure later.
Optionally they also name a dashboard (its url path) whose tile cards lay
out the app's Home.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_ENTITIES, CONF_LAYOUT_DASHBOARD, DOMAIN
from .layout import clean_url_path

_ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(multiple=True)
)
_DASHBOARD_SELECTOR = selector.TextSelector(selector.TextSelectorConfig())


def _with_clean_dashboard(user_input: dict[str, Any]) -> dict[str, Any]:
    """Always store the dashboard key, trimmed ('' when left empty)."""
    return {
        **user_input,
        CONF_LAYOUT_DASHBOARD: clean_url_path(user_input.get(CONF_LAYOUT_DASHBOARD)),
    }


class GramTrackConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="GramTrack", data=_with_clean_dashboard(user_input)
            )

        schema = vol.Schema(
            {
                vol.Optional(CONF_ENTITIES, default=[]): _ENTITY_SELECTOR,
                vol.Optional(CONF_LAYOUT_DASHBOARD, default=""): _DASHBOARD_SELECTOR,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return GramTrackOptionsFlow(config_entry)


class GramTrackOptionsFlow(OptionsFlow):
    """Edit the selected entities and the layout dashboard after setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        # Stored under a private name so we don't shadow the base-class
        # `config_entry` property (avoids the HA deprecation warning).
        self._entry = config_entry

    async def async_step_init(self, user_input: dict | None = None):
        if user_input is not None:
            return self.async_create_entry(
                title="", data=_with_clean_dashboard(user_input)
            )

        current = self._entry.options.get(
            CONF_ENTITIES, self._entry.data.get(CONF_ENTITIES, [])
        )
        current_dashboard = self._entry.options.get(
            CONF_LAYOUT_DASHBOARD, self._entry.data.get(CONF_LAYOUT_DASHBOARD, "")
        )
        schema = vol.Schema(
            {
                vol.Optional(CONF_ENTITIES, default=current): _ENTITY_SELECTOR,
                # A suggested value, not a default: the frontend drops an
                # emptied optional field, and a default would put the old
                # path back, so the feature could never be turned off.
                vol.Optional(
                    CONF_LAYOUT_DASHBOARD,
                    description={"suggested_value": current_dashboard},
                ): _DASHBOARD_SELECTOR,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
