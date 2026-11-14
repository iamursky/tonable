"""The table-driven property layer against plain stand-in objects."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "remote_script"))

from Tonable import props  # noqa: E402
from Tonable.server import CommandError  # noqa: E402

MODES = {"Trigger": 0, "Gate": 1, "Toggle": 2, "Repeat": 3}
TABLE = [
    props.prop("mode", "launch_mode", "enum", choices=MODES),
    props.prop("muted", "muted", "bool"),
    props.prop("gain", "gain", "float", lo=0.0, hi=1.0),
    props.prop("steps", "steps", "int", lo=0, hi=8),
    props.prop("label", "label", "str"),
    props.prop("length", "length", "float", readonly=True),
]


def thing(**over):
    base = dict(launch_mode=0, muted=False, gain=0.5, steps=2, label="a", length=4.0)
    base.update(over)
    return SimpleNamespace(**base)


def test_read_shows_enum_labels_and_skips_missing_attributes():
    obj = SimpleNamespace(launch_mode=1, muted=True)
    assert props.read(obj, TABLE) == {"mode": "Gate", "muted": True}


def test_write_reads_back_and_reports_now():
    obj = thing()
    out = props.write(obj, TABLE, {"mode": "toggle", "muted": "true", "gain": 0.25})
    assert out == [
        {"field": "mode", "now": "Toggle"},
        {"field": "muted", "now": True},
        {"field": "gain", "now": 0.25},
    ]
    assert obj.launch_mode == 2 and obj.muted is True


def test_unnamed_and_empty_fields_are_left_alone():
    obj = thing()
    assert props.write(obj, TABLE, {"mode": "", "muted": None}) == []
    assert obj.launch_mode == 0


def test_enum_takes_numbers_and_explains_bad_labels():
    obj = thing()
    assert props.write(obj, TABLE, {"mode": 3}) == [{"field": "mode", "now": "Repeat"}]
    bad = props.write(obj, TABLE, {"mode": "Loop"})[0]
    assert "Gate" in bad["error"] and obj.launch_mode == 3


def test_object_listed_choices_win_over_the_fallback():
    table = [props.prop("q", "quant", "enum", choices={"x": 0}, choices_attr="quants")]
    obj = SimpleNamespace(quant=0, quants=["None", "1 Bar", "1/4"])
    assert props.write(obj, table, {"q": "1/4"}) == [{"field": "q", "now": "1/4"}]
    assert obj.quant == 2


def test_range_and_whole_number_checks():
    obj = thing()
    assert "0 to 1" in props.write(obj, TABLE, {"gain": 3})[0]["error"]
    assert "whole" in props.write(obj, TABLE, {"steps": 1.5})[0]["error"]
    assert "number" in props.write(obj, TABLE, {"steps": "many"})[0]["error"]
    assert obj.gain == 0.5 and obj.steps == 2


def test_readonly_and_missing_attributes_are_errors():
    assert props.write(thing(), TABLE, {"length": 8})[0]["error"] == "read-only"
    bare = SimpleNamespace()
    assert "does not have" in props.write(bare, TABLE, {"muted": True})[0]["error"]


def test_a_silent_revert_is_reported_not_hidden():
    class Stubborn(SimpleNamespace):
        def __setattr__(self, name, value):
            if name == "launch_mode":
                return  # Live keeps the old value
            super().__setattr__(name, value)

    obj = Stubborn(launch_mode=0)
    line = props.write(obj, TABLE, {"mode": "Gate"})[0]
    assert "Live still shows" in line["error"] and line["now"] == "Trigger"


def test_a_value_snapped_to_a_step_is_a_note_not_an_error():
    class Stepped(SimpleNamespace):
        def __setattr__(self, name, value):
            super().__setattr__(name, round(value) if name == "gain" else value)

    line = props.write(Stepped(gain=0.0), TABLE, {"gain": 0.8})[0]
    assert line["now"] == 1.0 and "nearest" in line["note"]


def test_refused_write_becomes_an_error_line():
    class Refuses(SimpleNamespace):
        def __setattr__(self, name, value):
            if name == "muted":
                raise RuntimeError("not on the master track")
            super().__setattr__(name, value)

    line = props.write(Refuses(muted=False), TABLE, {"muted": True})[0]
    assert "not on the master track" in line["error"]


def test_get_survives_live_raising_runtime_errors():
    class Master:
        @property
        def arm(self):
            raise RuntimeError("master has no arm")

    assert props.get(Master(), "arm", "n/a") == "n/a"


def test_convert_bool_words():
    p = props.prop("on", "on", "bool")
    assert props.convert(None, p, "Off") is False
    assert props.convert(None, p, "yes") is True
    with pytest.raises(CommandError):
        props.convert(None, p, "maybe")


def test_describe_lists_options_and_ranges():
    described = {d["name"]: d for d in props.describe(thing(), TABLE)}
    assert described["mode"]["options"] == list(MODES)
    assert described["gain"]["range"] == "0 to 1"
    assert described["length"]["readonly"] is True


def test_an_enum_class_as_the_choices_list():
    """Live's mixer lists its choices as a class with a `values` map, not a list."""

    class Member:
        def __init__(self, name):
            self.name = name

    class Assignments:  # stands in for a Boost.Python enum class
        values = {0: Member("A"), 1: Member("NONE"), 2: Member("B")}

    table = [
        props.prop("x", "assign", "enum", choices={"A": 0}, choices_attr="assigns")
    ]
    obj = SimpleNamespace(assign=1, assigns=Assignments)
    assert props.read(obj, table) == {"x": "NONE"}
    assert props.write(obj, table, {"x": "b"}) == [{"field": "x", "now": "B"}]
    assert obj.assign == 2


def test_an_unreadable_choices_list_falls_back_to_the_built_in_labels():
    table = [
        props.prop("x", "assign", "enum", choices={"A": 0, "B": 1}, choices_attr="l")
    ]
    obj = SimpleNamespace(assign=0, l=object())  # not iterable, not a class
    assert props.write(obj, table, {"x": "B"}) == [{"field": "x", "now": "B"}]
