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
    TWIN_CAP,
    attach_devices,
    build_layout,
    layout_changed,
    twins_among,
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
        devices[f"sensor.{base}_machine_state"] = {"name": f"Washer {i}", "integration": "acme_cloud",
                                                   "entities": entities}
        cards.append({"type": "tile", "entity": f"sensor.{base}_machine_state", "name": f"Washer {i}"})
    plain = build_layout(dash([{"title": "House", "cards": cards}]))
    out = attach_devices(plain, devices.get)

    siblings = [e for t in tiles_of(out) for e in t["device"]["entities"]]
    assert len(siblings) == 20 * 21

    def size(layout):
        return len(json.dumps(layout["buildings"], separators=(",", ":")))

    added = size(out) - size(plain) - sum(len(e["entity"]) for e in siblings)
    configs = sum(1 for e in siblings if "category" in e)
    # + ~60 a tile for "device"/"name", + ~30 for "integration" (since 1.3.0)
    assert added <= 14 * len(siblings) + 20 * configs + 90 * 20
    assert size(out) < 21 * 1024


# --- Twins: the same appliance through another integration (since 1.3.0) ---


def dev(id_, model, integration, name=None, entities=()):
    """A registry device as the coordinator summarises it."""
    return {"id": id_, "name": name or id_, "model": model, "integration": integration,
            "entities": list(entities)}


RANGE_LOCAL = dev("dev-range-local", "RX-100", "acme_local", "Range")
RANGE_CLOUD = dev("dev-range-cloud", "RX-100", "acme_cloud", "My range")
REGISTRY = [
    dev("dev-lamp", "L1", "lights_co"),
    RANGE_LOCAL,
    dev("dev-plug", "", "plugs_co"),
    RANGE_CLOUD,
    dev("dev-other", "RX-200", "acme_cloud"),
]


def test_twins_found_by_model():
    assert twins_among(RANGE_LOCAL, REGISTRY) == [RANGE_CLOUD]
    assert twins_among(RANGE_CLOUD, REGISTRY) == [RANGE_LOCAL]


def test_model_is_matched_after_trimming():
    padded = dev("dev-range-padded", " RX-100 ", "acme_bridge")
    assert twins_among(RANGE_LOCAL, [*REGISTRY, padded]) == [RANGE_CLOUD, padded]


def test_no_twin_when_the_model_is_empty_or_unique():
    for model in ("", "   ", None):
        plug = dev("dev-x", model, "plugs_co")
        assert twins_among(plug, [*REGISTRY, plug, dev("dev-y", model, "other_co")]) == []
    assert twins_among(REGISTRY[0], REGISTRY) == []  # L1: the only one
    assert twins_among(REGISTRY[4], REGISTRY) == []  # RX-200: the only one


def test_own_device_is_never_its_own_twin():
    # In the registry by id, as the coordinator passes it (a different dict).
    assert RANGE_LOCAL not in twins_among(dict(RANGE_LOCAL), REGISTRY)
    assert twins_among(dict(RANGE_LOCAL), [RANGE_LOCAL]) == []
    # The very same dict, even without an id.
    no_id = {"model": "RX-100", "integration": "acme_local"}
    assert twins_among(no_id, [no_id]) == []


def test_two_units_of_one_model_under_one_integration_have_no_twins():
    """A pair of door sensors is two doors, not one door seen twice."""
    front = dev("dev-door-1", "DS-1", "radio_co")
    back = dev("dev-door-2", "DS-1", "radio_co")
    bridge = dev("dev-door-bridge", "DS-1", "bridge_co")
    registry = [front, back, bridge]
    assert twins_among(front, registry) == []
    assert twins_among(back, registry) == []
    assert twins_among(bridge, registry) == []  # two candidates there: which one?


def test_an_integration_with_several_of_the_model_is_skipped():
    """A network integration listing many identical cameras can't say which is ours."""
    cam = dev("dev-cam", "CAM-3", "cams_co")
    seen_a = dev("dev-net-a", "CAM-3", "network_co")
    seen_b = dev("dev-net-b", "CAM-3", "network_co")
    cloud = dev("dev-cam-cloud", "CAM-3", "cams_cloud")
    assert twins_among(cam, [seen_a, cam, seen_b, cloud]) == [cloud]


def test_devices_without_an_integration_are_never_twins():
    orphan = dev("dev-orphan", "RX-100", "")
    assert twins_among(RANGE_LOCAL, [*REGISTRY, orphan]) == [RANGE_CLOUD]
    assert twins_among(orphan, REGISTRY) == []


def test_twins_keep_the_registry_order():
    first = dev("dev-a", "M", "zeta_co")
    second = dev("dev-b", "M", "alpha_co")
    me = dev("dev-me", "M", "mid_co")
    assert twins_among(me, [first, me, second]) == [first, second]


# attach_devices with twins

STOVE_LOCAL = {**RANGE_LOCAL, "entities": [
    ent("sensor.range_state"),
    ent("binary_sensor.range_burner_on"),
    ent("sensor.range_cook_mode", "diagnostic"),
    ent("select.range_light", "config"),
]}
STOVE_CLOUD = {**RANGE_CLOUD, "entities": [
    ent("sensor.my_range_rssi", "diagnostic"),
    ent("sensor.my_range_mode"),
    ent("switch.my_range_lock", "config"),
    ent("switch.my_range_hidden", hidden=True),
    ent("switch.my_range_off", disabled=True),
    ent("sensor.my_range_new", "something_new"),
]}


def stove_of(*twins):
    return {"sensor.range_state": {**STOVE_LOCAL, "twins": list(twins)}}.get


def test_device_names_its_integration():
    tile = tiles_of(attach_devices(house("sensor.range_state"), stove_of()))[0]
    assert tile["device"]["integration"] == "acme_local"
    assert list(tile["device"]) == ["name", "integration", "entities"]  # no twins, no key


def test_unknown_integration_gives_no_key():
    device = {"name": "Gadget", "integration": "", "entities": [ent("sensor.g"), ent("sensor.g_x")]}
    tile = tiles_of(attach_devices(house("sensor.g"), {"sensor.g": device}.get))[0]
    assert tile["device"] == {"name": "Gadget", "entities": [{"entity": "sensor.g_x"}]}


def test_twin_is_filtered_like_the_device():
    tile = tiles_of(attach_devices(house("sensor.range_state"), stove_of(STOVE_CLOUD)))[0]
    assert tile["device"] == {
        "name": "Range",
        "integration": "acme_local",
        "entities": [{"entity": "binary_sensor.range_burner_on"},
                     {"entity": "select.range_light", "category": "config"}],
        "twins": [{
            "name": "My range",
            "integration": "acme_cloud",
            "entities": [{"entity": "sensor.my_range_mode"},
                         {"entity": "switch.my_range_lock", "category": "config"}],
        }],
    }


def test_twin_cap_and_report():
    many = {**RANGE_CLOUD, "name": "Big twin",
            "entities": [ent(f"sensor.big_{i:02d}") for i in range(DEVICE_ENTITY_CAP + 3)]}
    heard = []
    out = attach_devices(house("sensor.range_state"), stove_of(many),
                         lambda name, count: heard.append((name, count)))
    twin = tiles_of(out)[0]["device"]["twins"][0]
    assert twin["entities"] == [{"entity": f"sensor.big_{i:02d}"} for i in range(DEVICE_ENTITY_CAP)]
    assert heard == [("Big twin", DEVICE_ENTITY_CAP + 3)]


def test_at_most_three_twins_and_empty_ones_are_dropped():
    empty = {**RANGE_CLOUD, "name": "Only diagnostics", "entities": [ent("sensor.d", "diagnostic")]}
    twins = [empty, "junk"] + [
        {**RANGE_CLOUD, "name": f"Twin {i}", "integration": f"link_{i}",
         "entities": [ent(f"sensor.twin_{i}")]}
        for i in range(TWIN_CAP + 2)
    ]
    device = tiles_of(attach_devices(house("sensor.range_state"), stove_of(*twins)))[0]["device"]
    assert [t["name"] for t in device["twins"]] == [f"Twin {i}" for i in range(TWIN_CAP)]


def test_no_twins_no_key():
    for twins in ([], [{**RANGE_CLOUD, "entities": [ent("sensor.x", hidden=True)]}]):
        device = tiles_of(attach_devices(house("sensor.range_state"), stove_of(*twins)))[0]["device"]
        assert "twins" not in device
    odd = {"sensor.range_state": {**STOVE_LOCAL, "twins": "nope"}}
    assert "twins" not in tiles_of(attach_devices(house("sensor.range_state"), odd.get))[0]["device"]


def test_a_twin_alone_still_gives_the_tile_its_device():
    lonely = {**STOVE_LOCAL, "entities": [ent("sensor.range_state")], "twins": [STOVE_CLOUD]}
    device = tiles_of(attach_devices(house("sensor.range_state"), {"sensor.range_state": lonely}.get))[0]["device"]
    assert device["entities"] == []
    assert [t["name"] for t in device["twins"]] == ["My range"]


def test_layout_changed_sees_a_twin_change():
    before = attach_devices(house("sensor.range_state"), stove_of(STOVE_CLOUD))
    grown = {**STOVE_CLOUD, "entities": STOVE_CLOUD["entities"] + [ent("sensor.my_range_temp")]}
    assert layout_changed(before, attach_devices(house("sensor.range_state"), stove_of(grown)))
    assert layout_changed(before, attach_devices(house("sensor.range_state"), stove_of()))
    assert not layout_changed(before, attach_devices(house("sensor.range_state"), stove_of(STOVE_CLOUD)))


def test_size_of_a_twin():
    """A twin costs its entities as the device's do, plus a small fixed wrapper.

    Measured on a range-like tile (made-up ids): 34 siblings on the device
    and a 23-entity twin, all shown.
    """
    local = {**RANGE_LOCAL, "entities": [ent(f"sensor.range_model_x_part_{i:02d}") for i in range(35)]}
    cloud = {**RANGE_CLOUD, "entities": [ent(f"switch.my_range_part_{i:02d}") for i in range(23)]}
    tile_entity = local["entities"][0]["entity"]
    with_twin = attach_devices(house(tile_entity), {tile_entity: {**local, "twins": [cloud]}}.get)
    without = attach_devices(house(tile_entity), {tile_entity: local}.get)

    def size(layout):
        return len(json.dumps(layout["buildings"], separators=(",", ":")))

    twin = tiles_of(with_twin)[0]["device"]["twins"][0]
    assert len(twin["entities"]) == 23
    ids = sum(len(e["entity"]) for e in twin["entities"])
    wrapper = len(',"twins":[{"name":"","integration":"","entities":[]}]')
    assert size(with_twin) - size(without) == ids + 14 * 23 - 1 + wrapper + len("My range") + len("acme_cloud")
    assert size(with_twin) < 4 * 1024
