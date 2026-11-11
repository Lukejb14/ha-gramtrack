"""Turn a dashboard config into the GramTrack Home layout.

Pure functions, no Home Assistant imports, so they're unit-tested on any
machine. The dashboard is the one the user names in the integration's
options; this module never knows its path or any entity ID.

Contract with the app (docs/HOME_DASHBOARD_LAYOUT.md in the GramTrack repo):
- The first view holds sections. A section's title, lowercased, is the
  building id the app knows (it decides which titles mean something).
- Only ``type: tile`` cards with an ``entity`` become tiles. A card with a
  ``visibility`` condition is dropped and listed under ``ignored``; so is
  any other card type, except ``heading`` cards, which carry nothing.
- ``name`` is only present when the card sets one.
- ``device`` (since 1.2.0) is only present when the tile's entity sits on a
  device that has other entities worth showing (``attach_devices``). Since
  1.3.0 it names its ``integration`` and may carry ``twins``: the same
  appliance seen through another integration (``twins_among``).

``next_state`` is the coordinator's decision step (what to publish after a
read) and ``sensor_view`` turns its result into the sensor's state and
attributes, so the never-publish-empty rule is tested here too.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

IGNORED_CAP = 20
DEVICE_ENTITY_CAP = 40
TWIN_CAP = 3
_QUIET_CARD_TYPES = {"heading"}
# Entity categories a device's list keeps. ``diagnostic`` (and anything Home
# Assistant might add later) is left out; ``config`` is kept and marked.
_SHOWN_CATEGORIES = {None, "config"}

# ``device_of(entity_id)``: the entity's device, or None. See ``attach_devices``.
DeviceOf = Callable[[str], "dict[str, Any] | None"]
# ``on_cap(device_name, count)``: a device had more than DEVICE_ENTITY_CAP to show.
OnCap = Callable[[str, int], None]


def _cards_of(section: dict[str, Any]) -> list[dict[str, Any]]:
    cards = section.get("cards")
    return [c for c in cards if isinstance(c, dict)] if isinstance(cards, list) else []


def _section_title(section: dict[str, Any], cards: list[dict[str, Any]]) -> str:
    """A section's name: its ``title`` key, or else its first heading card.

    The HA editor writes a heading card, not ``title`` (which the frontend
    treats as deprecated and turns into a heading card on load), so a
    dashboard edited by hand carries the name on the card.
    """
    title = str(section.get("title") or "").strip()
    if title:
        return title
    for card in cards:
        if card.get("type") == "heading":
            return str(card.get("heading") or "").strip()
    return ""


def build_layout(config: dict[str, Any] | None) -> dict[str, Any]:
    """Return ``{"buildings": [...], "ignored": [...]}`` for a dashboard config.

    An empty or non-sections dashboard yields no buildings; the caller
    decides whether that means "no layout" or "keep the last good one".
    """
    buildings: list[dict[str, Any]] = []
    ignored: list[dict[str, str]] = []
    if not isinstance(config, dict):
        return {"buildings": buildings, "ignored": ignored}

    views = config.get("views")
    if not isinstance(views, list) or not views:
        return {"buildings": buildings, "ignored": ignored}
    view = views[0] if isinstance(views[0], dict) else {}
    sections = view.get("sections")
    if not isinstance(sections, list):
        return {"buildings": buildings, "ignored": ignored}

    for section in sections:
        if not isinstance(section, dict):
            continue
        cards = _cards_of(section)
        title = _section_title(section, cards)
        if not title:
            continue
        building_id = title.lower()
        tiles: list[dict[str, Any]] = []
        for card in cards:
            card_type = str(card.get("type") or "")
            if card_type in _QUIET_CARD_TYPES:
                continue
            entity = card.get("entity")
            if card_type != "tile" or not isinstance(entity, str) or not entity:
                if len(ignored) < IGNORED_CAP:
                    ignored.append({"section": title, "card": card_type or "unknown"})
                continue
            if "visibility" in card:
                if len(ignored) < IGNORED_CAP:
                    ignored.append({"section": title, "card": "tile", "entity": entity,
                                    "reason": "visibility"})
                continue
            tile: dict[str, Any] = {"entity": entity}
            name = card.get("name")
            if isinstance(name, str) and name.strip():
                tile["name"] = name.strip()
            tiles.append(tile)
        buildings.append({"id": building_id, "tiles": tiles})

    return {"buildings": buildings, "ignored": ignored}


def layout_changed(old: dict[str, Any] | None, new: dict[str, Any]) -> bool:
    """True when the tiles differ (``ignored`` alone doesn't count).

    A tile's ``device`` is part of the tile, so a change in its device's
    entities counts too.
    """
    return (old or {}).get("buildings") != new.get("buildings")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def twins_among(device: dict[str, Any], devices: Iterable[Any]) -> list[dict[str, Any]]:
    """The devices that are ``device``'s appliance seen through another integration.

    ``device`` and each of ``devices`` are ``{"id": str, "model": str | None,
    "integration": str, ...}``; ``devices`` is the whole registry, in its
    order, and may include ``device`` itself (matched by ``id``).

    A twin has the same non-empty ``model`` under another integration, and
    is the only device of that model there, while ``device`` is the only
    one of its model in its own integration. A model alone doesn't make a
    twin: two door sensors of one model, or a row of identical cameras that
    a network integration also lists, can't be told apart, so they give no
    twins rather than a guess. Devices with no integration are never twins.
    Registry order is kept, uncapped (``attach_devices`` keeps the first
    TWIN_CAP that have something to show).
    """
    model = _text(device.get("model"))
    integration = _text(device.get("integration"))
    if not model or not integration:
        return []
    own_id = device.get("id")
    by_integration: dict[str, list[dict[str, Any]]] = {}
    for other in devices:
        if not isinstance(other, dict) or other is device or _text(other.get("model")) != model:
            continue
        if own_id is not None and other.get("id") == own_id:
            continue
        other_integration = _text(other.get("integration"))
        if other_integration:
            by_integration.setdefault(other_integration, []).append(other)
    if integration in by_integration:
        return []  # another unit of this model under the same integration
    return [found[0] for found in by_integration.values() if len(found) == 1]


def _entities_view(
    rows: Any, entity: str, name: str, on_cap: OnCap | None
) -> list[dict[str, str]]:
    """A device's entities as a tile carries them: filtered, in order, capped."""
    if not isinstance(rows, list):
        return []
    shown: list[dict[str, str]] = []
    seen = {entity}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sibling = row.get("entity")
        if not isinstance(sibling, str) or not sibling or sibling in seen:
            continue
        category = row.get("category")
        if row.get("hidden") or row.get("disabled") or category not in _SHOWN_CATEGORIES:
            continue
        seen.add(sibling)
        shown.append({"entity": sibling, "category": "config"} if category else {"entity": sibling})
    if len(shown) > DEVICE_ENTITY_CAP:
        if on_cap is not None:
            on_cap(name, len(shown))
        shown = shown[:DEVICE_ENTITY_CAP]
    return shown


def _described(name: str, integration: Any, entities: list[dict[str, str]]) -> dict[str, Any]:
    view: dict[str, Any] = {"name": name}
    if _text(integration):
        view["integration"] = _text(integration)
    view["entities"] = entities
    return view


def _device_view(
    entity: str, device: Any, on_cap: OnCap | None
) -> dict[str, Any] | None:
    """A tile's ``device`` value, or None when its device has nothing else to show."""
    if not isinstance(device, dict):
        return None
    name = _text(device.get("name"))
    shown = _entities_view(device.get("entities"), entity, name, on_cap)
    twins: list[dict[str, Any]] = []
    candidates = device.get("twins")
    for twin in candidates if isinstance(candidates, list) else []:
        if len(twins) == TWIN_CAP:
            break
        if not isinstance(twin, dict):
            continue
        twin_name = _text(twin.get("name"))
        rows = _entities_view(twin.get("entities"), entity, twin_name, on_cap)
        if rows:
            twins.append(_described(twin_name, twin.get("integration"), rows))
    if not shown and not twins:
        return None
    view = _described(name, device.get("integration"), shown)
    if twins:
        view["twins"] = twins
    return view


def attach_devices(
    layout: dict[str, Any], device_of: DeviceOf | None, on_cap: OnCap | None = None
) -> dict[str, Any]:
    """Give each tile the other entities of its device, as ``tile["device"]``.

    ``device_of(entity_id)`` returns the entity's device, or None when it has
    none: ``{"name": str, "integration": str, "entities": [{"entity": str,
    "category": "config" | "diagnostic" | None, "hidden": bool, "disabled":
    bool}, ...], "twins": [<the same shape, without twins>, ...]}``, the
    entities in the registry's order. ``twins`` (optional) are the devices
    ``twins_among`` found; ``integration`` is the config entry's domain.

    A tile gains ``{"name": ..., "integration": ..., "entities":
    [{"entity": ...}, ...]}`` when its device has at least one entity left
    after leaving out the tile's own entity and every hidden, disabled or
    ``diagnostic`` one. ``category`` is present (as ``"config"``) only on
    configuration entities, the way a card's ``name`` is only present when
    set; ``integration`` only when known. Order is kept; at most
    DEVICE_ENTITY_CAP entities per device, and ``on_cap(name, count)`` hears
    about any device that had more.

    ``twins`` (since 1.3.0): each twin filtered and capped the same way, as
    ``{"name", "integration", "entities"}``; a twin left with nothing is
    dropped, and at most TWIN_CAP are kept. No twins, no key. A device with
    nothing of its own to show but a twin still gives the tile a ``device``
    (with ``entities: []``). With no ``device_of`` the layout is returned
    as it came.
    """
    if device_of is None:
        return layout
    buildings = []
    for building in layout.get("buildings", []):
        tiles = []
        for tile in building.get("tiles", []):
            device = _device_view(tile["entity"], device_of(tile["entity"]), on_cap)
            tiles.append({**tile, "device": device} if device else tile)
        buildings.append({**building, "tiles": tiles})
    return {**layout, "buildings": buildings}


class _Missing:
    """Read result meaning the named dashboard doesn't exist."""

    def __repr__(self) -> str:
        return "MISSING"


MISSING = _Missing()


def clean_url_path(value: Any) -> str:
    """The dashboard url_path as typed, minus spaces and slashes ('' = off).

    Tolerates a pasted path like ``/my-dash/0`` by keeping the first part.
    """
    return str(value or "").strip().strip("/").split("/")[0].strip()


def _problem(
    result: Any, device_of: DeviceOf | None, on_cap: OnCap | None
) -> tuple[dict[str, Any] | None, str | None]:
    """The layout a read result gives, or why it can't be published."""
    if isinstance(result, BaseException):
        text = str(result)
        return None, f"{type(result).__name__}: {text}" if text else type(result).__name__
    if not isinstance(result, dict):
        return None, f"expected a dict, got {type(result).__name__}"
    layout = build_layout(result)
    if not layout["buildings"]:
        return None, "no titled sections in the first view"
    return attach_devices(layout, device_of, on_cap), None


def next_state(
    previous: dict[str, Any] | None,
    result: Any,
    now: str,
    device_of: DeviceOf | None = None,
    on_cap: OnCap | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Return the state to publish after a read, and the problem if it failed.

    ``result`` is the dashboard config, ``MISSING``, or the exception (or
    odd value) the read produced. ``device_of`` and ``on_cap`` go to
    ``attach_devices``. Rules:
    - A good read replaces the layout; ``version`` bumps and
      ``last_changed`` becomes ``now`` only when the tiles (devices
      included) changed.
    - A failed read, or one with no buildings, never publishes empty: the
      previous state is kept and marked ``stale``.
    - Only a missing dashboard drops the layout.
    """
    prev = previous or {}
    version = int(prev.get("version") or 0)
    if result is MISSING:
        return {"missing": True, "stale": False, "version": version}, None

    layout, problem = _problem(result, device_of, on_cap)
    if layout is None:
        return {**prev, "stale": True}, problem

    if layout_changed(prev, layout):
        return {**layout, "version": version + 1, "last_changed": now, "stale": False}, None
    return {**layout, "version": version, "last_changed": prev["last_changed"],
            "stale": False}, None


def sensor_view(state: dict[str, Any] | None, source: str) -> tuple[str | None, dict[str, Any]]:
    """The layout sensor's state and attributes for a ``next_state`` state.

    No layout (missing dashboard, or nothing good read yet) means state
    ``None`` (unknown) and only ``source``/``stale`` (+ ``missing``).
    """
    state = state or {}
    if "buildings" not in state:
        attrs: dict[str, Any] = {"source": source, "stale": bool(state.get("stale"))}
        if state.get("missing"):
            attrs["missing"] = True
        return None, attrs
    return state["last_changed"], {
        "source": source,
        "version": state["version"],
        "last_changed": state["last_changed"],
        "stale": state["stale"],
        "buildings": state["buildings"],
        "ignored": state["ignored"],
    }
