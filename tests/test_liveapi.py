"""live_api against stand-in Live objects (nothing here ran in a real Live)."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "remote_script"))

from Tonable import liveapi  # noqa: E402
from Tonable.server import CommandError  # noqa: E402

REAL_IS_LIVE_OBJECT = liveapi.is_live_object


class L:
    """Stand-in for any Live class: the tests treat these as Live objects."""


@pytest.fixture(autouse=True)
def live_objects(monkeypatch):
    monkeypatch.setattr(liveapi, "is_live_object", lambda o: isinstance(o, L))


class Vector(L):
    def __init__(self, items):
        self._items = list(items)

    def __len__(self):
        return len(self._items)

    def __getitem__(self, i):
        return self._items[i]


class Param(L):
    def __init__(self, name, value=0.5):
        self.name = name
        self._value = value

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        if 0.0 <= v <= 1.0:  # Live keeps the old value for an invalid write
            self._value = v


class Mixer(L):
    def __init__(self):
        self.volume = Param("Volume", 0.85)
        self.sends = [Param("Send A", 0.1), Param("Send B", 0.2)]


class Device(L):
    can_have_chains = False

    def __init__(self, name):
        self.name = name
        self.parameters = Vector([Param("Device On", 1.0), Param("Gain", 0.3)])
        self.canonical_parent = None

    def reset(self, depth, label):
        """Reset the device to its defaults."""
        return f"{self.name}:{depth}:{label}"

    def delete_all_chains(self):
        """Remove every chain."""
        return "gone"


class Clip(L):
    def __init__(self, name):
        self.name = name
        self.canonical_parent = None


class Slot(L):
    def __init__(self, clip=None):
        self.clip = clip
        self.canonical_parent = None

    @property
    def has_clip(self):
        return self.clip is not None


class Track(L):
    def __init__(self, name, devices=()):
        self.name = name
        self.devices = list(devices)
        self.mixer_device = Mixer()
        self.clip_slots = [Slot(Clip("Loop")), Slot()]
        self.arrangement_clips = [Clip("Arr")]
        self.mute = False
        self.volume_steps = 3
        self.canonical_parent = None
        for d in self.devices:
            d.canonical_parent = self
        for s in self.clip_slots:
            s.canonical_parent = self
            if s.clip:
                s.clip.canonical_parent = s
        self.arrangement_clips[0].canonical_parent = self

    def stop_all_clips(self):
        """Stop every clip on the track."""
        return None


class Scene(L):
    def __init__(self, name):
        self.name = name
        self.tempo = 100.0


class View(L):
    def __init__(self):
        self.draw_mode = False


class Song(L):
    def __init__(self):
        self.tracks = [Track("Bass", [Device("Operator")]), Track("Drums")]
        self.return_tracks = [Track("A-Reverb")]
        self.master_track = Track("Master")
        self.scenes = [Scene("Verse"), Scene("Chorus")]
        self.cue_points = [Scene("Intro")]
        self.view = View()
        self.text = "plain"
        self.sneaky = os
        self.big = list(range(250))
        self.undo_steps = 0
        self._tempo = 92.0
        self.deleted = []

    @property
    def tempo(self):
        return self._tempo

    @tempo.setter
    def tempo(self, v):
        self._tempo = round(v)  # snaps to whole numbers

    @property
    def is_playing(self):
        return False

    def begin_undo_step(self):
        self.undo_steps += 1

    def end_undo_step(self):
        pass

    def delete_track(self, index):
        """Delete the track at index."""
        self.deleted.append(index)

    def move(self, device, holder, index):
        """Move a device."""
        return [device.name, holder.name, index]


class App(L):
    def __init__(self):
        self.view = View()


@pytest.fixture
def song():
    return Song()


def run(song, **params):
    return liveapi.live_api(song, params, app=App())


# --- reading ---------------------------------------------------------------------


def test_get_a_property_and_a_chain_with_indexes(song):
    assert run(song, path="song", operation="get", name="tempo")["value"] == 92.0
    out = run(song, path="t0.mixer_device.sends.1", operation="get", name="value")
    assert out["value"] == 0.2
    assert run(song, path="t0/d0.parameters.1", operation="get", name="name")[
        "value"
    ] == ("Gain")


def test_tonable_addresses_are_bases(song):
    assert run(song, path="t0/s0.clip", operation="get", name="name")["value"] == "Loop"
    assert run(song, path="t0/s1", operation="get", name="has_clip")["value"] is False
    assert run(song, path="t0/a0", operation="get", name="name")["value"] == "Arr"
    assert run(song, path="s1", operation="get", name="name")["value"] == "Chorus"
    assert run(song, path="rA", operation="get", name="name")["value"] == "A-Reverb"
    assert run(song, path="m", operation="get", name="name")["value"] == "Master"


def test_app_root_and_view_step(song):
    out = run(song, path="app.view", operation="get", name="draw_mode")
    assert out["value"] is False


def test_get_without_a_name_describes_the_object(song):
    out = run(song, path="t1", operation="get")
    assert out["value"] == {"object": "Track", "name": "Drums", "address": "t1"}


def test_live_objects_come_back_as_summaries_with_addresses(song):
    out = run(song, path="t0", operation="get", name="devices")
    assert out["value"] == [
        {"object": "Device", "name": "Operator", "address": "t0/d0"}
    ]
    clip = run(song, path="t0/s0", operation="get", name="clip")["value"]
    assert clip == {"object": "Clip", "name": "Loop", "address": "t0/s0"}


def test_long_lists_are_cut(song):
    out = run(song, path="song", operation="get", name="big")["value"]
    assert len(out) == liveapi.MAX_ITEMS + 1
    assert out[-1] == "... 50 more"


def test_json_safety_helpers():
    assert liveapi.to_json(float("nan")) == "nan"
    assert liveapi.to_json("x" * 900).endswith("...")
    assert liveapi.to_json(os) == {"type": "module"}
    assert liveapi.to_json({"a": 1}) == {"type": "dict"}
    assert liveapi.to_json(b"raw") == {"type": "bytes"}
    nested = [[[[1]]]]
    assert liveapi.to_json(nested) == [[[{"length": 1}]]]


# --- the boundary ----------------------------------------------------------------


@pytest.mark.parametrize("name", ["_private", "__class__", "__dict__", "a b", "1x"])
def test_odd_and_underscore_names_are_refused(song, name):
    with pytest.raises(CommandError) as err:
        run(song, path="song", operation="get", name=name)
    assert err.value.code == "forbidden"


def test_underscore_steps_in_a_path_are_refused(song):
    for path in ("song._tempo", "song.__class__", "t0._x.name"):
        with pytest.raises(CommandError) as err:
            run(song, path=path, operation="get", name="name")
        assert err.value.code == "forbidden"


def test_non_live_objects_are_summarised_never_opened(song):
    assert run(song, path="song", operation="get", name="sneaky")["value"] == {
        "type": "module"
    }
    with pytest.raises(CommandError) as err:
        run(song, path="song.sneaky.system", operation="get", name="name")
    assert err.value.code == "forbidden"
    with pytest.raises(CommandError):
        run(song, path="song.text", operation="get", name="upper")


def test_a_method_is_not_a_path_step_or_a_property(song):
    with pytest.raises(CommandError) as err:
        run(song, path="song.delete_track", operation="get", name="x")
    assert "method" in str(err.value)
    with pytest.raises(CommandError) as err:
        run(song, path="song", operation="get", name="delete_track")
    assert "method" in str(err.value)


def test_unknown_member_suggests_similar_names(song):
    with pytest.raises(CommandError) as err:
        run(song, path="song", operation="get", name="tempp")
    assert err.value.code == "not_found" and "tempo" in str(err.value)


def test_bad_indexes_and_operations(song):
    with pytest.raises(CommandError) as err:
        run(song, path="song.tracks.9", operation="get")
    assert "out of range" in str(err.value)
    with pytest.raises(CommandError):
        run(song, path="song.view.0", operation="get")
    with pytest.raises(CommandError):
        run(song, path="song", operation="explode")
    with pytest.raises(CommandError):
        run(song, path="", operation="info")
    with pytest.raises(CommandError):
        run(song, path="song..view", operation="get")


# --- set -------------------------------------------------------------------------


def test_set_needs_write_true(song):
    with pytest.raises(CommandError) as err:
        run(song, path="song", operation="set", name="tempo", value="100")
    assert err.value.code == "needs_write" and song.tempo == 92.0
    assert song.undo_steps == 0


def test_set_coerces_to_the_current_type_in_one_undo_step(song):
    out = run(song, path="t0", operation="set", name="mute", value="true", write=True)
    assert out["value"] is True and "warning" not in out
    out = run(song, path="t0", operation="set", name="name", value="123", write=True)
    assert out["value"] == "123"
    out = run(
        song, path="t0", operation="set", name="volume_steps", value="5", write=True
    )
    assert out["value"] == 5
    assert song.undo_steps == 3


def test_set_reads_back_and_warns_about_silent_reverts(song):
    out = run(
        song,
        path="t0.mixer_device.volume",
        operation="set",
        name="value",
        value="7",
        write=True,
    )
    assert out["value"] == 0.85
    assert "silently keeps" in out["warning"]


def test_set_warns_when_live_snaps_the_value(song):
    out = run(
        song, path="song", operation="set", name="tempo", value="100.4", write=True
    )
    assert out["value"] == 100 and "warning" in out


def test_set_rejects_a_bad_number_and_empty_value(song):
    with pytest.raises(CommandError):
        run(
            song,
            path="t0",
            operation="set",
            name="volume_steps",
            value="2.5",
            write=True,
        )
    with pytest.raises(CommandError):
        run(song, path="t0", operation="set", name="volume_steps", value="", write=True)
    with pytest.raises(CommandError):
        run(
            song,
            path="song",
            operation="set",
            name="is_playing",
            value="true",
            write=True,
        )
    with pytest.raises(CommandError):
        run(song, path="song", operation="set", name="no_such", value="1", write=True)


def test_set_can_pass_a_live_object_by_reference(song):
    out = run(
        song,
        path="song.view",
        operation="set",
        name="draw_mode",
        value="true",
        write=True,
    )
    assert out["value"] is True
    song.view.selected_track = None
    out = run(
        song,
        path="song.view",
        operation="set",
        name="selected_track",
        value="ref:t1",
        write=True,
    )
    assert out["value"]["address"] == "t1"


# --- call ------------------------------------------------------------------------


def test_call_needs_write_true(song):
    with pytest.raises(CommandError) as err:
        run(song, path="t0/d0", operation="call", name="reset")
    assert err.value.code == "needs_write"


def test_call_passes_values_and_whole_floats_as_ints(song):
    out = run(
        song,
        path="t0/d0",
        operation="call",
        name="reset",
        args=[{"value": 2.0}, {"value": "go"}],
        write=True,
    )
    assert out["result"] == "Operator:2:go" and out["args"] == 2
    assert song.undo_steps == 1


def test_call_passes_references_to_live_objects(song):
    out = run(
        song,
        path="song",
        operation="call",
        name="move",
        args=[{"ref": "t0/d0"}, {"ref": "t1"}, {"value": 0}],
        write=True,
    )
    assert out["result"] == ["Operator", "Drums", 0]


def test_destructive_methods_need_confirm(song):
    for path, name, args in (
        ("song", "delete_track", [{"value": 1}]),
        ("t0/d0", "delete_all_chains", []),
        ("t0", "stop_all_clips", []),
    ):
        with pytest.raises(CommandError) as err:
            run(song, path=path, operation="call", name=name, args=args, write=True)
        assert err.value.code == "needs_confirm", name
    assert song.deleted == []
    run(
        song,
        path="song",
        operation="call",
        name="delete_track",
        args=[{"value": 1}],
        write=True,
        confirm=True,
    )
    assert song.deleted == [1]


def test_undo_step_methods_are_not_callable(song):
    with pytest.raises(CommandError) as err:
        run(song, path="song", operation="call", name="begin_undo_step", write=True)
    assert err.value.code == "forbidden"


def test_wrong_argument_count_shows_the_docstring(song):
    with pytest.raises(CommandError) as err:
        run(song, path="t0/d0", operation="call", name="reset", write=True)
    assert err.value.code == "bad_params"
    assert "Reset the device to its defaults." in str(err.value)


def test_call_on_a_property_and_bad_arguments(song):
    with pytest.raises(CommandError):
        run(song, path="song", operation="call", name="tempo", write=True)
    with pytest.raises(CommandError):
        run(
            song,
            path="t0/d0",
            operation="call",
            name="reset",
            args=[{"nope": 1}],
            write=True,
        )


def test_a_failed_call_still_closes_its_undo_step(song):
    class Closing(Song):
        def end_undo_step(self):
            self.ended = True

    s = Closing()
    with pytest.raises(CommandError):
        run(s, path="t0/d0", operation="call", name="reset", write=True)
    assert s.ended is True


# --- info and list ---------------------------------------------------------------


def test_info_lists_members_with_kinds_and_pages(song):
    out = run(song, path="song", operation="info", limit=5)
    assert out["object"] == {"object": "Song"}
    assert len(out["members"]) == 5 and out["more"] is True
    everything = run(song, path="song", operation="info", limit=500)["members"]
    by_name = {m["name"]: m for m in everything}
    assert by_name["tempo"]["kind"] == "property"
    assert by_name["tempo"]["writable"] is True
    assert by_name["is_playing"]["writable"] is False
    assert by_name["delete_track"] == {
        "name": "delete_track",
        "kind": "function",
        "doc": "Delete the track at index.",
    }
    assert by_name["tracks"]["value"] == {"length": 2}
    assert not any(name.startswith("_") for name in by_name)
    second = run(song, path="song", operation="info", limit=5, offset=5)["members"]
    assert second[0]["name"] != out["members"][0]["name"]


def test_info_filters_by_text(song):
    out = run(song, path="song", operation="info", name="TRACK", limit=500)
    names = [m["name"] for m in out["members"]]
    assert names and all("track" in n for n in names)
    assert out["total"] == len(names)


def test_info_on_a_non_live_object_is_refused(song):
    with pytest.raises(CommandError) as err:
        run(song, path="song.sneaky", operation="info")
    assert err.value.code == "forbidden"


def test_list_children_with_addresses_and_paging(song):
    out = run(song, path="song", operation="list", name="tracks", limit=1, offset=1)
    assert out["items"] == [
        {"index": 1, "object": "Track", "name": "Drums", "address": "t1"}
    ]
    assert out["total"] == 2 and out["more"] is False
    first = run(song, path="song", operation="list", name="tracks", limit=1)
    assert first["more"] is True


def test_list_of_plain_values_and_the_path_itself(song):
    out = run(song, path="song", operation="list", name="big", limit=3)
    assert out["items"] == [
        {"index": 0, "value": 0},
        {"index": 1, "value": 1},
        {"index": 2, "value": 2},
    ]
    out = run(song, path="song.tracks", operation="list")
    assert [i["name"] for i in out["items"]] == ["Bass", "Drums"]
    with pytest.raises(CommandError):
        run(song, path="song", operation="list", name="tempo")


def test_live_vectors_can_be_indexed_and_listed(song):
    assert run(song, path="t0/d0.parameters.1", operation="get", name="value")[
        "value"
    ] == (0.3)
    out = run(song, path="t0/d0", operation="list", name="parameters")
    assert out["total"] == 2 and out["items"][1]["name"] == "Gain"


def test_addresses_of_nested_objects(song):
    device = song.tracks[0].devices[0]
    assert liveapi.address_of(song, device) == "t0/d0"
    assert liveapi.address_of(song, song.tracks[0].clip_slots[0]) == "t0/s0"
    assert liveapi.address_of(song, song.tracks[0].arrangement_clips[0]) == "t0/a0"
    assert liveapi.address_of(song, song.master_track) == "m"
    assert liveapi.address_of(song, Param("loose")) is None


# --- the MCP tool ------------------------------------------------------------------


def test_tool_schema_is_clean():
    from tonable import server
    from tonable.tools import liveapi as tool_module  # noqa: F401

    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    tool = tools["live_api"]
    assert tool.description and len(tool.description) > 40
    assert tool.annotations is not None and tool.annotations.readOnlyHint is False
    assert "anyOf" not in str(tool.inputSchema)
    for name, prop in tool.inputSchema["properties"].items():
        assert prop.get("description"), name
        assert "type" in prop or "enum" in prop, name
    assert tool.inputSchema["required"] == ["path", "operation"]


def test_tool_forwards_to_the_bridge(monkeypatch):
    from tonable import server
    from tonable.tools import liveapi as tool_module

    seen = {}

    def fake_call(command, params=None, long=False):
        seen.update(command=command, params=params)
        return {"ok": True}

    monkeypatch.setattr(tool_module, "call", fake_call)
    out = tool_module.live_api(
        path="song", operation="get", name="tempo", write="", limit="5"
    )
    assert out == {"ok": True} and seen["command"] == "live_api"
    assert seen["params"]["path"] == "song" and seen["params"]["limit"] == "5"
    assert server.mcp is not None


def test_live_classes_are_found_by_identity_not_by_module_name(monkeypatch):
    """Live reports a class's module as "Song", not "Live.Song"."""
    import types as _types

    fake_live = _types.ModuleType("Live")
    song_module = _types.ModuleType("Song")

    class Song:
        pass

    Song.__module__ = "Song"
    Song.__qualname__ = "Song"
    song_module.Song = Song
    fake_live.Song = song_module
    monkeypatch.setattr(liveapi, "Live", fake_live)
    monkeypatch.setattr(liveapi, "is_live_object", REAL_IS_LIVE_OBJECT)
    assert liveapi.is_live_object(Song())

    class Lookalike:  # same module name, but not Live's class
        pass

    Lookalike.__module__ = "Song"
    Lookalike.__qualname__ = "Lookalike"
    assert not liveapi.is_live_object(Lookalike())
    assert not liveapi.is_live_object("text")
    assert not liveapi.is_live_object(3)
