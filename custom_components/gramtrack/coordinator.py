"""Keeps the Home layout in step with the dashboard named in Options.

The dashboard is read in-process through Lovelace's own objects (no
websocket, no token): once at setup, whenever Home Assistant reports a save
of that dashboard (``lovelace_updated``), and every 5 minutes as a backstop.
``hass.data["lovelace"]`` is internal to Home Assistant, so the read is
defensive, and a failed read never clears the last good layout (the rules
live in ``layout.next_state``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.const import EVENT_LOVELACE_UPDATED
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .layout import MISSING, next_state

_LOGGER = logging.getLogger(__name__)

REFRESH_INTERVAL = timedelta(minutes=5)
_LOVELACE_DATA = "lovelace"


class HomeLayoutCoordinator:
    """Holds the latest layout state and tells the sensor when it changes."""

    def __init__(self, hass: HomeAssistant, url_path: str) -> None:
        self.hass = hass
        self.url_path = url_path
        self.state: dict[str, Any] | None = None
        self._listeners: list[CALLBACK_TYPE] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._lock = asyncio.Lock()
        self._outcome: str | None = None  # "ok" | "missing" | "failed"
        self._shape_logged = False

    async def async_start(self) -> None:
        """Read once, then follow saves and the backstop timer."""
        await self.async_refresh()
        self._unsubs.append(
            async_track_time_interval(self.hass, self._async_on_interval, REFRESH_INTERVAL)
        )
        self._unsubs.append(
            self.hass.bus.async_listen(EVENT_LOVELACE_UPDATED, self._on_lovelace_updated)
        )

    @callback
    def async_stop(self) -> None:
        """Drop the event listener and the timer."""
        while self._unsubs:
            self._unsubs.pop()()
        self._listeners.clear()

    @callback
    def async_add_listener(self, update_callback: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Call ``update_callback`` after each state change; returns the remover."""
        self._listeners.append(update_callback)

        @callback
        def remove() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return remove

    async def async_refresh(self) -> None:
        """Read the dashboard and publish the next state."""
        async with self._lock:
            result = await self._async_read()
            previous = self.state
            self.state, problem = next_state(
                previous, result, dt_util.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            )
            self._log_outcome(result, problem)
            changed = self.state != previous
        if changed:
            for update_callback in list(self._listeners):
                update_callback()

    async def _async_on_interval(self, _now: datetime) -> None:
        await self.async_refresh()

    @callback
    def _on_lovelace_updated(self, event: Event) -> None:
        if event.data.get("url_path") == self.url_path:
            self.hass.async_create_task(self.async_refresh())

    async def _async_read(self) -> Any:
        """The dashboard config, ``MISSING``, or whatever stopped the read."""
        data = self.hass.data.get(_LOVELACE_DATA)
        # A LovelaceData dataclass in current cores (2026.11 included), a
        # plain dict in older ones. Both have ``dashboards`` keyed by url_path.
        if isinstance(data, Mapping):
            dashboards = data.get("dashboards")
        else:
            dashboards = getattr(data, "dashboards", None)
        if not self._shape_logged:
            self._shape_logged = True
            _LOGGER.debug(
                "hass.data[%r] is %s; dashboards is %s (%s entries)",
                _LOVELACE_DATA,
                type(data).__name__,
                type(dashboards).__name__,
                len(dashboards) if isinstance(dashboards, Mapping) else "no",
            )

        if data is None:
            return LookupError("Lovelace isn't loaded")
        if not isinstance(dashboards, Mapping):
            return TypeError(f"no dashboards map on {type(data).__name__}")
        if self.url_path not in dashboards:
            return MISSING
        load = getattr(dashboards[self.url_path], "async_load", None)
        if load is None:
            return TypeError("dashboard has no async_load")
        try:
            return await load(False)
        except Exception as err:  # noqa: BLE001 - any failure keeps the last good layout
            return err

    def _log_outcome(self, result: Any, problem: str | None) -> None:
        """Log once per change of outcome, not on every 5-minute read."""
        outcome = "failed" if problem else "missing" if result is MISSING else "ok"
        if outcome == self._outcome:
            if problem:
                _LOGGER.debug("Dashboard '%s' still unreadable: %s", self.url_path, problem)
            return
        if outcome == "failed":
            _LOGGER.warning(
                "Couldn't read dashboard '%s' for the GramTrack Home layout (%s); "
                "keeping the last good layout, marked stale",
                self.url_path,
                problem,
            )
            if isinstance(result, BaseException):
                _LOGGER.debug("Read error for dashboard '%s'", self.url_path, exc_info=result)
        elif outcome == "missing":
            _LOGGER.warning(
                "Dashboard '%s' doesn't exist; the GramTrack Home layout is unknown "
                "until it does",
                self.url_path,
            )
        elif self._outcome is not None:
            _LOGGER.info("Dashboard '%s' is readable again", self.url_path)
        self._outcome = outcome
