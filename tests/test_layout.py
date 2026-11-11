"""Tests for the pure dashboard → layout conversion (no Home Assistant needed).

Run: python3 -m pytest tests -q
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "gramtrack"))

import json  # noqa: E402

from layout import (  # noqa: E402
    DEVICE_ENTITY_CAP,
    IGNORED_CAP,
    attach_devices,
    build_layout,
    layout_changed,
)


def dash(sections):
    return {"views": [{"type": "sections", "sections": sections}]}


def test_tiles_in_order_with_optional_name():
    cfg = dash([{"title": "House", "cards": [
        {"type": "tile", "entity": "climate.t", "name": "Thermostat"},
        {"type": "tile", "entity": "light.porch"},
    ]}])
    out = build_layout(cfg)
    assert out["buildings"] == [{"id": "house", "tiles": [
        {"entity": "climate.t", "name": "Thermostat"},
        {"entity": "light.porch"},
    ]}]
    assert out["ignored"] == []


def test_section_title_becomes_lowercase_id():
    out = build_layout(dash([{"title": "Gazebo", "cards": []}, {"title": "Scenes", "cards": []}]))
    assert [b["id"] for b in out["buildings"]] == ["gazebo", "scenes"]


def test_heading_card_names_the_section_when_title_is_absent():
    """The HA editor writes a heading card instead of a section title."""
    cfg = dash([{"type": "grid", "cards": [
        {"type": "heading", "heading": "Barn", "heading_style": "title"},
        {"type": "tile", "entity": "camera.barn"},
    ]}])
    out = build_layout(cfg)
    assert out["buildings"] == [{"id": "barn", "tiles": [{"entity": "camera.barn"}]}]
    assert out["ignored"] == []


def test_section_title_wins_over_heading_card():
    cfg = dash([{"title": "House", "cards": [{"type": "heading", "heading": "Other"}]}])
    assert build_layout(cfg)["buildings"][0]["id"] == "house"


def test_visibility_cards_are_dropped_and_listed():
    cfg = dash([{"title": "House", "cards": [
        {"type": "tile", "entity": "light.a", "visibility": [{"condition": "state", "entity": "x", "state": "on"}]},
        {"type": "tile", "entity": "light.b"},
    ]}])
    out = build_layout(cfg)
    assert out["buildings"][0]["tiles"] == [{"entity": "light.b"}]
    assert out["ignored"] == [{"section": "House", "card": "tile", "entity": "light.a", "reason": "visibility"}]


def test_other_card_types_are_ignored_except_headings():
    cfg = dash([{"title": "Barn", "cards": [
        {"type": "heading", "heading": "Barn"},
        {"type": "markdown", "content": "hi"},
        {"type": "tile"},
        {"type": "tile", "entity": "camera.barn"},
    ]}])
    out = build_layout(cfg)
    assert out["buildings"][0]["tiles"] == [{"entity": "camera.barn"}]
    assert out["ignored"] == [{"section": "Barn", "card": "markdown"}, {"section": "Barn", "card": "tile"}]


def test_ignored_is_capped():
    cards = [{"type": "markdown"} for _ in range(IGNORED_CAP + 5)]
    out = build_layout(dash([{"title": "House", "cards": cards}]))
    assert len(out["ignored"]) == IGNORED_CAP


def test_untitled_sections_and_junk_are_skipped():
    cfg = dash([{"cards": [{"type": "tile", "entity": "light.a"}]}, "junk", {"title": "House", "cards": "nope"}])
    out = build_layout(cfg)
    assert out["buildings"] == [{"id": "house", "tiles": []}]


def test_empty_or_wrong_shapes_give_no_buildings():
    assert build_layout(None)["buildings"] == []
    assert build_layout({})["buildings"] == []
    assert build_layout({"views": []})["buildings"] == []
    assert build_layout({"views": [{"cards": []}]})["buildings"] == []


def test_layout_changed_ignores_the_ignored_list():
    a = {"buildings": [{"id": "house", "tiles": []}], "ignored": []}
    b = {"buildings": [{"id": "house", "tiles": []}], "ignored": [{"section": "House", "card": "markdown"}]}
    c = {"buildings": [{"id": "barn", "tiles": []}], "ignored": []}
    assert not layout_changed(a, b)
    assert layout_changed(a, c)
    assert layout_changed(None, a)


# --- Each tile's device (attach_devices, since 1.2.0) ---------------------


def ent(entity, category=None, hidden=False, disabled=False):
    """A device entity as the coordinator hands it over (registry order)."""
    return {"entity": entity, "category": category, "hidden": hidden, "disabled": disabled}


WASHER = {"name": "Washer", "entities": [
    ent("sensor.washer_state"),
    ent("select.washer_cycle"),
    ent("sensor.washer_signal", "diagnostic"),
    ent("button.washer_start"),
    ent("sensor.washer_total", hidden=True),
    ent("button.washer_drain", disabled=True),
    ent("switch.washer_extra_rinse", "config"),
]}
DOOR = {"name": "Door sensor", "entities": [
    ent("binary_sensor.door_open"),
    ent("sensor.door_battery", "diagnostic"),
]}
DEVICES = {
    "sensor.washer_state": WASHER,
    "select.washer_cycle": WASHER,
    "binary_sensor.door_open": DOOR,
}


def house(*entities):
    return build_layout(dash([{"title": "House", "cards": [
        {"type": "tile", "entity": e} for e in entities
    ]}]))


def tiles_of(layout):
    return layout["buildings"][0]["tiles"]


WASHER_SHOWN = [
    {"entity": "select.washer_cycle"},
    {"entity": "button.washer_start"},
    {"entity": "switch.washer_extra_rinse", "category": "config"},
]


def test_device_only_where_it_has_other_entities():
    out = attach_devices(house("sensor.washer_state", "binary_sensor.door_open", "light.lamp"),
                         DEVICES.get)
    washer, door, lamp = tiles_of(out)
    assert washer == {"entity": "sensor.washer_state",
                      "device": {"name": "Washer", "entities": WASHER_SHOWN}}
    assert door == {"entity": "binary_sensor.door_open"}  # only a diagnostic sibling
    assert lamp == {"entity": "light.lamp"}  # no device


def test_device_leaves_out_self_hidden_disabled_and_diagnostic():
    device = tiles_of(attach_devices(house("sensor.washer_state"), DEVICES.get))[0]["device"]
    shown = [e["entity"] for e in device["entities"]]
    assert "sensor.washer_state" not in shown  # the tile's own entity
    assert "sensor.washer_total" not in shown  # hidden
    assert "button.washer_drain" not in shown  # disabled
    assert "sensor.washer_signal" not in shown  # diagnostic
    assert device["entities"] == WASHER_SHOWN


def test_device_leaves_out_an_unknown_category():
    device = {"name": "Gadget", "entities": [ent("sensor.gadget"), ent("sensor.gadget_x", "something_new")]}
    out = attach_devices(house("sensor.gadget"), {"sensor.gadget": device}.get)
    assert tiles_of(out) == [{"entity": "sensor.gadget"}]


def test_two_tiles_on_one_device_each_leave_out_their_own():
    a, b = tiles_of(attach_devices(house("sensor.washer_state", "select.washer_cycle"), DEVICES.get))
    assert [e["entity"] for e in a["device"]["entities"]] == [
        "select.washer_cycle", "button.washer_start", "switch.washer_extra_rinse"]
    assert [e["entity"] for e in b["device"]["entities"]] == [
        "sensor.washer_state", "button.washer_start", "switch.washer_extra_rinse"]


def test_device_keeps_the_registry_order():
    names = ["switch.z", "sensor.a", "button.m", "select.b", "number.y"]
    device = {"name": "Thing", "entities": [ent("sensor.thing")] + [ent(n) for n in names]}
    out = attach_devices(house("sensor.thing"), {"sensor.thing": device}.get)
    assert [e["entity"] for e in tiles_of(out)[0]["device"]["entities"]] == names


def test_device_cap_keeps_the_first_and_reports_the_rest():
    many = [ent(f"sensor.big_{i:02d}") for i in range(DEVICE_ENTITY_CAP + 5)]
    device = {"name": "Big", "entities": [ent("sensor.big")] + many}
    heard = []
    out = attach_devices(house("sensor.big"), {"sensor.big": device}.get,
                         lambda name, count: heard.append((name, count)))
    shown = tiles_of(out)[0]["device"]["entities"]
    assert len(shown) == DEVICE_ENTITY_CAP
    assert shown == [{"entity": e["entity"]} for e in many[:DEVICE_ENTITY_CAP]]
    assert heard == [("Big", DEVICE_ENTITY_CAP + 5)]


def test_device_at_the_cap_is_not_reported():
    device = {"name": "Full", "entities": [ent("sensor.full")]
              + [ent(f"sensor.full_{i:02d}") for i in range(DEVICE_ENTITY_CAP)]}
    heard = []
    out = attach_devices(house("sensor.full"), {"sensor.full": device}.get,
                         lambda name, count: heard.append((name, count)))
    assert len(tiles_of(out)[0]["device"]["entities"]) == DEVICE_ENTITY_CAP
    assert heard == []


def test_no_device_of_leaves_an_old_layout_unchanged():
    layout = build_layout(dash([{"title": "House", "cards": [
        {"type": "tile", "entity": "sensor.washer_state", "name": "Washer"},
        {"type": "markdown"},
    ]}]))
    before = json.dumps(layout, sort_keys=True)
    assert attach_devices(layout, None) is layout
    assert json.dumps(layout, sort_keys=True) == before
    assert "device" not in tiles_of(layout)[0]


def test_device_keeps_the_card_name_and_the_other_keys():
    layout = build_layout(dash([
        {"title": "House", "cards": [{"type": "tile", "entity": "sensor.washer_state", "name": "Laundry"}]},
        {"title": "Barn", "cards": [{"type": "markdown"}]},
    ]))
    out = attach_devices(layout, DEVICES.get)
    assert tiles_of(out)[0]["name"] == "Laundry"
    assert tiles_of(out)[0]["device"]["name"] == "Washer"
    assert out["buildings"][1] == {"id": "barn", "tiles": []}
    assert out["ignored"] == [{"section": "Barn", "card": "markdown"}]
    assert "device" not in tiles_of(layout)[0]  # the input isn't changed


def test_odd_device_shapes_give_no_key():
    odd = {
        "sensor.a": {"name": "A"},  # no entities
        "sensor.b": {"name": "B", "entities": "nope"},
        "sensor.c": {"name": "C", "entities": ["junk", {"category": None}, {"entity": ""}]},
        "sensor.d": "not a device",
    }
    out = attach_devices(house(*odd), odd.get)
    assert all("device" not in t for t in tiles_of(out))


def test_device_without_a_name_gets_an_empty_one():
    device = {"name": None, "entities": [ent("sensor.x"), ent("sensor.y")]}
    out = attach_devices(house("sensor.x"), {"sensor.x": device}.get)
    assert tiles_of(out)[0]["device"] == {"name": "", "entities": [{"entity": "sensor.y"}]}


def test_layout_changed_sees_a_new_sibling():
    before = attach_devices(house("sensor.washer_state"), DEVICES.get)
    grown = {**WASHER, "entities": WASHER["entities"] + [ent("sensor.washer_water")]}
    after = attach_devices(house("sensor.washer_state"), {"sensor.washer_state": grown}.get)
    assert layout_changed(before, after)
    assert not layout_changed(before, attach_devices(house("sensor.washer_state"), DEVICES.get))


# A 22-entity appliance (made-up ids): 2 selects, 5 buttons, 9 sensors,
# 3 binary sensors and 3 config switches.
_APPLIANCE = [
    ("select", ""), ("select", "_cycle"),
    ("button", "_start"), ("button", "_pause"), ("button", "_resume"),
    ("button", "_cancel"), ("button", "_cancel_and_drain"),
    ("sensor", "_machine_state"), ("sensor", "_job_state"), ("sensor", "_completion_time"),
    ("sensor", "_energy"), ("sensor", "_energy_difference"), ("sensor", "_energy_saved"),
    ("sensor", "_power"), ("sensor", "_power_energy"), ("sensor", "_water_consumption"),
    ("binary_sensor", "_child_lock"), ("binary_sensor", "_remote_control"),
    ("binary_sensor", "_power"),
    ("switch", "_sanitize"), ("switch", "_storm_wash"), ("switch", "_heated_dry"),
]


def test_size_of_twenty_tiles_each_on_a_22_entity_device():
    """The worst case the brief names, measured as Home Assistant sends it (compact JSON).

    About 20 KB with these ~27-character ids, of which the 420 sibling ids
    alone are about 11 KB, so no list of full entity ids gets this case
    "well under 16 KB". ``buildings`` is an unrecorded attribute, so the
    recorder's 16 KB limit never sees it. What this guards is the shape:
    each sibling costs its id plus ~14 bytes (``{"entity":"…"},``), and a
    configuration one 20 more. A state or a name per entity would fail it.
    """
    devices, cards = {}, []
    for i in range(20):
        base = f"washer_{i:02d}"
        entities = [ent(f"{domain}.{base}{suffix}", "config" if domain == "switch" else None)
                    for domain, suffix in _APPLIANCE]
        assert len(entities) == 22
        devices[f"sensor.{base}_machine_state"] = {"name": f"Washer {i}", "entities": entities}
        cards.append({"type": "tile", "entity": f"sensor.{base}_machine_state", "name": f"Washer {i}"})
    plain = build_layout(dash([{"title": "House", "cards": cards}]))
    out = attach_devices(plain, devices.get)

    siblings = [e for t in tiles_of(out) for e in t["device"]["entities"]]
    assert len(siblings) == 20 * 21

    def size(layout):
        return len(json.dumps(layout["buildings"], separators=(",", ":")))

    added = size(out) - size(plain) - sum(len(e["entity"]) for e in siblings)
    configs = sum(1 for e in siblings if "category" in e)
    assert added <= 14 * len(siblings) + 20 * configs + 60 * 20  # + ~60 a tile for "device"/"name"
    assert size(out) < 21 * 1024
