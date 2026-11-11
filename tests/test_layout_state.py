"""Tests for the coordinator's decision step and the sensor view (no Home Assistant needed).

Run: python3 -m pytest tests -q
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "gramtrack"))

from layout import MISSING, clean_url_path, next_state, sensor_view  # noqa: E402

T1, T2, T3 = "2026-11-06T19:00:00Z", "2026-11-06T19:05:00Z", "2026-11-06T19:10:00Z"


def dash(*sections):
    return {"views": [{"type": "sections", "sections": list(sections)}]}


HOUSE = {"title": "House", "cards": [{"type": "tile", "entity": "light.a"}]}
BARN = {"title": "Barn", "cards": [{"type": "tile", "entity": "camera.b", "name": "Barn"}]}


def good():
    state, problem = next_state(None, dash(HOUSE), T1)
    assert problem is None
    return state


def test_first_good_read_publishes_version_1():
    state = good()
    assert state == {
        "buildings": [{"id": "house", "tiles": [{"entity": "light.a"}]}],
        "ignored": [],
        "version": 1,
        "last_changed": T1,
        "stale": False,
    }


def test_success_replaces_and_bumps_version():
    state, problem = next_state(good(), dash(HOUSE, BARN), T2)
    assert problem is None
    assert [b["id"] for b in state["buildings"]] == ["house", "barn"]
    assert state["version"] == 2
    assert state["last_changed"] == T2
    assert state["stale"] is False


def test_version_only_bumps_on_change():
    first = good()
    md = {"title": "House", "cards": [{"type": "tile", "entity": "light.a"}, {"type": "markdown"}]}
    state, _ = next_state(first, dash(md), T2)
    assert state["version"] == 1
    assert state["last_changed"] == T1
    assert state["ignored"] == [{"section": "House", "card": "markdown"}]  # ignored still refreshes


def test_exception_keeps_last_good_and_marks_stale():
    first = good()
    state, problem = next_state(first, RuntimeError("boom"), T2)
    assert problem == "RuntimeError: boom"
    assert state == {**first, "stale": True}


def test_non_dict_result_keeps_last_good():
    first = good()
    state, problem = next_state(first, ["not", "a", "dict"], T2)
    assert problem == "expected a dict, got list"
    assert state["buildings"] == first["buildings"]
    assert state["stale"] is True


def test_exception_without_message_names_its_type():
    class ConfigNotFound(Exception):
        pass

    _, problem = next_state(good(), ConfigNotFound(), T2)
    assert problem == "ConfigNotFound"


def test_read_with_no_buildings_never_publishes_empty():
    first = good()
    state, problem = next_state(first, {"views": [{"cards": []}]}, T2)
    assert problem == "no titled sections in the first view"
    assert state == {**first, "stale": True}


def test_recovery_clears_stale_without_bumping():
    stale, _ = next_state(good(), RuntimeError("boom"), T2)
    state, problem = next_state(stale, dash(HOUSE), T3)
    assert problem is None
    assert state["stale"] is False
    assert state["version"] == 1
    assert state["last_changed"] == T1


def test_failure_before_any_good_read_has_no_layout():
    state, problem = next_state(None, RuntimeError("boom"), T1)
    assert problem
    assert sensor_view(state, "my-dash") == (None, {"source": "my-dash", "stale": True})


def test_missing_dashboard_drops_the_layout():
    state, problem = next_state(good(), MISSING, T2)
    assert problem is None
    assert sensor_view(state, "my-dash") == (
        None, {"source": "my-dash", "stale": False, "missing": True},
    )


def test_dashboard_back_after_missing_bumps_version():
    missing, _ = next_state(good(), MISSING, T2)
    state, _ = next_state(missing, dash(HOUSE), T3)
    assert state["version"] == 2
    assert state["last_changed"] == T3
    assert state["stale"] is False


def test_failure_while_missing_stays_missing_and_stale():
    missing, _ = next_state(good(), MISSING, T2)
    state, _ = next_state(missing, RuntimeError("boom"), T3)
    assert sensor_view(state, "d") == (None, {"source": "d", "stale": True, "missing": True})


def test_sensor_view_of_a_good_state():
    value, attrs = sensor_view(good(), "my-dash")
    assert value == T1
    assert attrs == {
        "source": "my-dash",
        "version": 1,
        "last_changed": T1,
        "stale": False,
        "buildings": [{"id": "house", "tiles": [{"entity": "light.a"}]}],
        "ignored": [],
    }


def test_sensor_view_of_a_stale_state_keeps_the_layout():
    stale, _ = next_state(good(), RuntimeError("boom"), T2)
    value, attrs = sensor_view(stale, "my-dash")
    assert value == T1
    assert attrs["stale"] is True
    assert attrs["buildings"] == [{"id": "house", "tiles": [{"entity": "light.a"}]}]


def test_clean_url_path():
    assert clean_url_path(None) == ""
    assert clean_url_path("  ") == ""
    assert clean_url_path(" my-dash ") == "my-dash"
    assert clean_url_path("/my-dash/0") == "my-dash"
    assert clean_url_path("my-dash/") == "my-dash"


# --- Devices through the decision step (since 1.2.0) ----------------------


WASHER_TILE = {"title": "House", "cards": [{"type": "tile", "entity": "sensor.washer_state"}]}


def washer(*extra):
    rows = ["sensor.washer_state", "button.washer_start", *extra]
    device = {"name": "Washer", "entities": [
        {"entity": e, "category": None, "hidden": False, "disabled": False} for e in rows
    ]}
    return {"sensor.washer_state": device}.get


def test_good_read_carries_the_device():
    state, problem = next_state(None, dash(WASHER_TILE), T1, washer())
    assert problem is None
    assert state["buildings"] == [{"id": "house", "tiles": [{
        "entity": "sensor.washer_state",
        "device": {"name": "Washer", "entities": [{"entity": "button.washer_start"}]},
    }]}]
    assert sensor_view(state, "d")[1]["buildings"] == state["buildings"]


def test_new_sibling_bumps_the_version():
    first, _ = next_state(None, dash(WASHER_TILE), T1, washer())
    same, _ = next_state(first, dash(WASHER_TILE), T2, washer())
    assert (same["version"], same["last_changed"]) == (1, T1)
    grown, _ = next_state(same, dash(WASHER_TILE), T3, washer("sensor.washer_water"))
    assert (grown["version"], grown["last_changed"]) == (2, T3)
    assert [e["entity"] for e in grown["buildings"][0]["tiles"][0]["device"]["entities"]] == [
        "button.washer_start", "sensor.washer_water"]


def test_failed_read_keeps_the_last_devices():
    first, _ = next_state(None, dash(WASHER_TILE), T1, washer())
    state, problem = next_state(first, RuntimeError("boom"), T2, washer("sensor.washer_water"))
    assert problem == "RuntimeError: boom"
    assert state == {**first, "stale": True}


def test_cap_is_heard_through_the_decision_step():
    many = [f"sensor.washer_{i:02d}" for i in range(45)]
    heard = []
    next_state(None, dash(WASHER_TILE), T1, washer(*many), lambda n, c: heard.append((n, c)))
    assert heard == [("Washer", 46)]  # the start button plus the 45
