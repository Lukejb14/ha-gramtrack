"""Keeps the Home layout in step with the dashboard named in Options.

The dashboard is read in-process through Lovelace's own objects (no
websocket, no token): once at setup, whenever Home Assistant reports a save
of that dashboard (``lovelace_updated``), and every 5 minutes as a backstop.
``hass.data["lovelace"]`` is internal to Home Assistant, so the read is
defensive, and a failed read never clears the last good layout (the rules
live in ``layout.next_state``).

Each tile also carries its device's other entities (``layout.attach_devices``),
looked up in the entity and device registries on every read, with the
device's integration and its twins: the same appliance under another
integration (``layout.twins_among`` decides which). A change to either
registry triggers a read too, at most once every ``REGISTRY_COOLDOWN``
seconds, so a new entity on a device reaches the app.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator, Mapping
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.const import EVENT_LOVELACE_UPDATED
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .layout import DEVICE_ENTITY_CAP, MISSING, next_state, twins_among

_LOGGER = logging.getLogger(__name__)

REFRESH_INTERVAL = timedelta(minutes=5)
REGISTRY_COOLDOWN = 10  # seconds
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
        self._capped_logged: set[str] = set()
        self._registry_failed = False
        self._registry_refresh = Debouncer(
            hass,
            _LOGGER,
            cooldown=REGISTRY_COOLDOWN,
            immediate=False,
            function=self.async_refresh,
        )

    async def async_start(self) -> None:
        """Read once, then follow saves, registry changes and the backstop timer."""
        await self.async_refresh()
        self._unsubs.append(
            async_track_time_interval(self.hass, self._async_on_interval, REFRESH_INTERVAL)
        )
        self._unsubs.append(
            self.hass.bus.async_listen(EVENT_LOVELACE_UPDATED, self._on_lovelace_updated)
        )
        for event_type in (er.EVENT_ENTITY_REGISTRY_UPDATED, dr.EVENT_DEVICE_REGISTRY_UPDATED):
            self._unsubs.append(
                self.hass.bus.async_listen(event_type, self._on_registry_updated)
            )

    @callback
    def async_stop(self) -> None:
        """Drop the event listeners, the timer and any pending registry read."""
        while self._unsubs:
            self._unsubs.pop()()
        self._registry_refresh.async_cancel()
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
                previous,
                result,
                dt_util.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                self._device_lookup(),
                self._on_device_cap,
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

    @callback
    def _on_registry_updated(self, _event: Event) -> None:
        self.hass.async_create_task(self._registry_refresh.async_call())

    @callback
    def _device_lookup(self) -> Callable[[str], dict[str, Any] | None]:
        """``device_of`` for ``layout.attach_devices``, read from the registries.

        Each device is looked up once per read, and the registry is scanned
        for twins at most once per read (only when a tile's device has a
        model). A lookup that fails gives that tile no ``device``, and a twin
        lookup that fails gives it no ``twins`` (the first failure is
        logged), rather than stopping the read.
        """
        hass = self.hass
        entities = er.async_get(hass)
        devices = dr.async_get(hass)
        seen: dict[str, dict[str, Any] | None] = {}
        summaries: list[dict[str, Any]] | None = None

        def record_of(device: Any) -> dict[str, Any] | None:
            if device is None:
                return None
            return _device_record(
                device,
                _integration_of(hass, device),
                er.async_entries_for_device(
                    entities, device.id, include_disabled_entities=True
                ),
            )

        def registry() -> list[dict[str, Any]]:
            nonlocal summaries
            if summaries is None:
                summaries = [
                    {
                        "id": device.id,
                        "model": _model_of(device),
                        "integration": _integration_of(hass, device),
                    }
                    for device in _all_devices(devices)
                ]
            return summaries

        def twins_of(device_id: str, record: dict[str, Any]) -> list[dict[str, Any]]:
            found = twins_among({**record, "id": device_id}, registry())
            twins = (record_of(devices.async_get(twin["id"])) for twin in found)
            return [twin for twin in twins if twin is not None]

        def device_of(entity_id: str) -> dict[str, Any] | None:
            try:
                entry = entities.async_get(entity_id)
                device_id = entry.device_id if entry is not None else None
                if not device_id:
                    return None
                if device_id not in seen:
                    record = record_of(devices.async_get(device_id))
                    if record is not None and record["model"]:
                        try:
                            record["twins"] = twins_of(device_id, record)
                        except Exception:  # noqa: BLE001 - costs this tile its twins only
                            self._lookup_failed(entity_id, "twins")
                    seen[device_id] = record
                return seen[device_id]
            except Exception:  # noqa: BLE001 - a bad lookup only costs this tile its device
                self._lookup_failed(entity_id, "device")
                return None

        return device_of

    def _lookup_failed(self, entity_id: str, what: str) -> None:
        if not self._registry_failed:
            self._registry_failed = True
            _LOGGER.warning(
                "Couldn't read the %s of %s for the GramTrack Home layout; "
                "its tile goes without (later failures are logged at debug)",
                what,
                entity_id,
                exc_info=True,
            )
        else:
            _LOGGER.debug("Couldn't read the %s of %s", what, entity_id, exc_info=True)

    @callback
    def _on_device_cap(self, device_name: str, count: int) -> None:
        if device_name not in self._capped_logged:
            self._capped_logged.add(device_name)
            _LOGGER.warning(
                "Device '%s' has %d entities to show; the GramTrack app gets the first %d",
                device_name,
                count,
                DEVICE_ENTITY_CAP,
            )

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


def _device_record(
    device: Any, integration: str, entries: list[er.RegistryEntry]
) -> dict[str, Any]:
    """A device as ``layout.attach_devices`` takes it; the filtering happens there."""
    return {
        "name": device.name_by_user or device.name or "",
        "model": _model_of(device),
        "integration": integration,
        "entities": [
            {
                "entity": entry.entity_id,
                # EntityCategory is a str enum; its value is "config"/"diagnostic".
                "category": getattr(entry.entity_category, "value", entry.entity_category),
                "hidden": entry.hidden_by is not None,
                "disabled": entry.disabled_by is not None,
            }
            for entry in entries
        ],
    }


def _model_of(device: Any) -> str:
    """A device's model, or "" (child devices, 2026.9+, have none)."""
    if not isinstance(device, dr.DeviceEntry):
        return ""
    return (device.model or "").strip()


def _integration_of(hass: HomeAssistant, device: Any) -> str:
    """The domain of the device's config entry, or "" when it can't be found.

    Since 2026.10 a device belongs to one config entry (``config_entry_id``);
    before that it had a set, with ``primary_config_entry`` from 2024.7.
    """
    entry_id = getattr(device, "config_entry_id", None)
    if entry_id is None:
        entry_id = getattr(device, "primary_config_entry", None)
    if entry_id is None:
        entry_id = next(iter(sorted(getattr(device, "config_entries", None) or ())), None)
    entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
    return entry.domain if entry is not None else ""


def _all_devices(devices: dr.DeviceRegistry) -> Iterator[Any]:
    """Every device in the registry, in its order.

    Iterating ``devices.devices`` yields entries in current cores (2026.10+;
    using it as a mapping is deprecated) and device ids in older ones.
    """
    for item in devices.devices:
        device = devices.async_get(item) if isinstance(item, str) else item
        if device is not None:
            yield device
