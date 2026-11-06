"""Tests for the pure dashboard → layout conversion (no Home Assistant needed).

Run: python3 -m pytest tests -q
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "gramtrack"))

from layout import IGNORED_CAP, build_layout, layout_changed  # noqa: E402


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
