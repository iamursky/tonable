"""The write commands against the fake Live: values, undo steps, delete, batch,
edit_notes and the library's duplicate rule. Stage 4-8 behaviour was also checked
in Live 12.4.16 on 6 November 2026 (see tests/manual_checklist.md)."""

import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "remote_script"))

import fake_live  # noqa: E402

from Tonable import clips, dispatch, edit, library, params, song  # noqa: E402
from Tonable.server import CommandError  # noqa: E402


class Curve(fake_live.Param):
    """A parameter whose display follows a function of its raw value."""

    def __init__(self, name, lo, hi, show):
        super().__init__(name, lo, lo, hi)
        self._fn = show

    def str_for_value(self, value):
        return self._fn(value)


def db(value):  # Live's fader: 0..1, 0.85 = 0 dB, 0 = -inf
    if value <= 0:
        return "-inf dB"
    return f"{40 * math.log10(value / 0.85):.1f} dB"


def ms(value):  # an exponential time knob shown in ms and s
    t = 1.0 * (10000 ** (value / 127))
    return f"{t / 1000:.2f} s" if t >= 1000 else f"{t:.0f} ms"


def pan(value):
    n = round(value * 50)
    return "C" if n == 0 else f"{abs(n)}{'L' if n < 0 else 'R'}"


# --- display text -> value -------------------------------------------------------


@pytest.mark.parametrize(
    ("param", "text", "shown"),
    [
        (Curve("Volume", 0.0, 1.0, db), "-6 dB", "-6.0 dB"),
        (Curve("Volume", 0.0, 1.0, db), "-inf dB", "-inf dB"),
        (Curve("Release", 0.0, 127.0, ms), "400 ms", "400 ms"),
        (Curve("Release", 0.0, 127.0, ms), "1.5 s", "1.50 s"),
        (Curve("Pan", -1.0, 1.0, pan), "25L", "25L"),
        (Curve("Pan", -1.0, 1.0, pan), "C", "C"),
    ],
)
def test_display_text_finds_the_value(param, text, shown):
    raw, note = params.value_for(param, text)
    assert param.str_for_value(raw) == shown
    assert note is None


def test_units_must_match():
    with pytest.raises(CommandError) as err:
        params.value_for(Curve("Release", 0.0, 127.0, ms), "50 %")
    assert "ms" in str(err.value)


def test_outside_the_range_goes_to_the_end():
    raw, note = params.value_for(Curve("Release", 0.0, 127.0, ms), "99 s")
    assert raw == 127.0 and "nearest end" in note


def test_raw_numbers_and_options():
    knob = fake_live.Param("Drive", 0.0, 0.0, 36.0)
    assert params.value_for(knob, 12) == (12.0, None)
    raw, note = params.value_for(knob, 50)
    assert raw == 36.0 and "range" in note


def test_numbers_outside_the_raw_range_are_read_as_shown():
    volume = Curve("Volume", 0.0, 1.0, db)
    assert volume.str_for_value(params.value_for(volume, -6)[0]) == "-6.0 dB"
    panning = Curve("Pan", -1.0, 1.0, pan)
    assert panning.str_for_value(params.value_for(panning, 30)[0]) == "30R"
    release = Curve("Release", 0.0, 127.0, ms)
    assert release.str_for_value(params.value_for(release, 400)[0]) == "400 ms"
    switch = fake_live.Param("Mode", 0.0, 0.0, 2.0, items=["Off", "Sine", "Saw"])
    assert params.value_for(switch, "saw") == (2.0, None)
    with pytest.raises(CommandError):
        params.value_for(switch, True)  # three options: true means nothing here
    with pytest.raises(CommandError):
        params.value_for(switch, "Square")
    toggle = fake_live.Param("Device On", 1.0, items=["Off", "On"])
    assert params.value_for(toggle, False) == (0.0, None)


# --- undo steps --------------------------------------------------------------------


def test_nested_undo_steps_are_one_step():
    s = fake_live.UndoSong()
    with song.undo_step(s), song.undo_step(s):
        pass
    assert s.undo_steps == 1 and s.undo_depth == 0


def test_batch_is_one_undo_step(monkeypatch):
    monkeypatch.setattr(clips, "Live", fake_live.FAKE_LIVE_MODULE)
    s = fake_live.writable_song()
    surface = SimpleNamespace(song=s, live_version="12.4.16")
    table = dispatch.commands(surface)
    note = {"pitch": "C3", "start": 0, "length": 1, "velocity": 100}
    out = table["batch"](
        {
            "actions": [
                {
                    "command": "write_clip",
                    "params": {"track": "t0", "slot": 0, "notes": [note]},
                },
                {"command": "write_clip", "params": {"track": "t2", "slot": 0}},
                {"command": "batch", "params": {}},
                {
                    "command": "write_clip",
                    "params": {"track": "t1", "slot": 1, "notes": [note]},
                },
            ]
        }
    )
    assert out["ran"] == 4 and out["failed"] == 2
    assert out["results"][1]["code"] == "bad_target"
    assert "unknown command" in out["results"][2]["error"]
    assert s.undo_steps == 1


def test_batch_can_stop_on_error(monkeypatch):
    s = fake_live.writable_song()
    table = dispatch.commands(SimpleNamespace(song=s, live_version=None))
    out = table["batch"](
        {"actions": [{"command": "nope"}, {"command": "status"}], "stop_on_error": True}
    )
    assert out["ran"] == 1


# --- delete and duplicate addresses ---------------------------------------------------


@pytest.fixture
def full_song():
    s = fake_live.song()
    s.delete_track = lambda i: s.tracks.pop(i)
    s.scenes = list(s.scenes)
    s.delete_scene = lambda i: s.scenes.pop(i)
    return s


def test_delete_needs_the_exact_name(full_song):
    with pytest.raises(CommandError) as err:
        edit.delete(full_song, {"target": "t0", "name": "Bas"})
    assert err.value.code == "confirm_name" and "'Bass'" in str(err.value)
    assert len(full_song.tracks) == 5
    assert edit.delete(full_song, {"target": "t0", "name": "bass"})["deleted"] == "t0"
    assert full_song.tracks[0].name == "Drums"


def test_delete_scene_and_device(full_song):
    assert edit.delete(full_song, {"target": "s1", "name": "Break"})["kind"] == "scene"
    removed = []
    full_song.tracks[3].delete_device = removed.append
    out = edit.delete(full_song, {"target": "t3/d0", "name": "Operator"})
    assert (out["kind"], removed) == ("device", [0])


def test_master_cannot_be_deleted(full_song):
    with pytest.raises(CommandError) as err:
        edit.delete(full_song, {"target": "m", "name": "Master"})
    assert err.value.code == "bad_target"


# --- edit_notes --------------------------------------------------------------------


@pytest.fixture
def clip_song(monkeypatch):
    monkeypatch.setattr(clips, "Live", fake_live.FAKE_LIVE_MODULE)
    s = fake_live.writable_song()
    notes = [
        {"pitch": "C3", "start": 0, "length": 1, "velocity": 100},
        {"pitch": "E3", "start": 1.1, "length": 1, "velocity": 90},
        {"pitch": "G8", "start": 2, "length": 1, "velocity": 80},
    ]
    clips.write_clip(s, {"track": "t0", "slot": 0, "notes": notes})
    return s


def edit_notes(s, **p):
    return clips.edit_notes(s, {"track": "t0", "slot": 0, **p})


def test_transpose_skips_notes_that_leave_midi(clip_song):
    out = edit_notes(clip_song, action="transpose", semitones=12)
    assert out["notes_matched"] == 3
    assert [x["pitch"] for x in out["skipped"]] == ["G8"]
    pitches = [n["pitch"] for n in clips.read_clip(clip_song, "t0", 0)["notes"]]
    assert pitches == ["C4", "E4", "G8"]


def test_quantize_and_range(clip_song):
    edit_notes(clip_song, action="quantize", grid_beats=0.5, from_beats=1, to_beats=2)
    starts = [n["start"] for n in clips.read_clip(clip_song, "t0", 0)["notes"]]
    assert starts == [0.0, 1.0, 2.0]


def test_delete_by_pitch(clip_song):
    out = edit_notes(clip_song, action="delete", pitches=["E3", 60])
    assert (out["notes_matched"], out["notes_total"]) == (2, 1)


def test_quantize_needs_a_grid(clip_song):
    with pytest.raises(CommandError):
        edit_notes(clip_song, action="quantize")


# --- library -----------------------------------------------------------------------


def item(name, uri):
    return SimpleNamespace(name=name, uri=uri, is_device=False)


def test_one_file_seen_in_a_category_and_a_pack_is_one_item():
    rack = item(
        "Electric Bass Soft.adg", "query:Synths#Instrument%20Rack:Bass:FileId_5275"
    )
    simpler = item("Electric Bass Soft.adg", "query:Synths#Simpler:Bass:FileId_5275")
    pack = item(
        "Electric Bass Soft.adg", "query:LivePacks#www.ableton.com/0:Racks:X.adg"
    )
    items = [
        (
            "Instruments",
            "Instruments/Instrument Rack/Bass/Electric Bass Soft.adg",
            rack,
        ),
        ("Instruments", "Instruments/Simpler/Bass/Electric Bass Soft.adg", simpler),
        (
            "Packs",
            "Packs/Core Library/Racks/Instrument Racks/Bass/Electric Bass Soft.adg",
            pack,
        ),
    ]
    assert library._unique(items, "electric bass soft", "Electric Bass Soft") is rack


def test_two_different_files_are_ambiguous():
    a = item("Pad.adg", "query:Synths#A:FileId_1")
    b = item("Pad.adg", "query:Synths#B:FileId_2")
    items = [("Sounds", "Sounds/A/Pad.adg", a), ("Sounds", "Sounds/B/Pad.adg", b)]
    with pytest.raises(CommandError) as err:
        library._unique(items, "pad", "Pad")
    assert err.value.code == "ambiguous"
    assert "Sounds/A/Pad.adg" in str(err.value)


# --- arrangement ---------------------------------------------------------------------

from Tonable import arrangement  # noqa: E402


def test_bar_beat_like_live():
    s = SimpleNamespace(signature_numerator=4, signature_denominator=4)
    assert arrangement.bar_beat(s, 0) == "1|1"
    assert arrangement.bar_beat(s, 18) == "5|3"
    s.signature_numerator, s.signature_denominator = 6, 8
    assert arrangement.bar_beat(s, 3) == "2|1"  # a 6/8 bar is 3 beats


def test_place_scene_copies_every_clip_in_the_row():
    s = fake_live.song()
    s.begin_undo_step = s.end_undo_step = lambda: None
    copies = []
    for track in s.tracks:
        track.duplicate_clip_to_arrangement = lambda clip, at, c=copies: (
            c.append((clip.name, at)) or SimpleNamespace(end_time=at + clip.length)
        )
    out = arrangement.arrangement(
        s, {"action": "place_scene", "scene": "Verse", "at_bar": 17}
    )
    assert copies == [("Bass A", 64.0), ("Beat", 64.0), ("Pad Verse", 64.0)]
    assert out["start"] == {"bar_beat": "17|1", "beats": 64.0}
    assert out["end"]["bar_beat"] == "21|1"


def test_time_needs_a_bar_from_one():
    s = SimpleNamespace(signature_numerator=4, signature_denominator=4)
    with pytest.raises(CommandError):
        arrangement._time(s, {"at_bar": 0})


def test_find_in_library_returns_everything_without_limit(monkeypatch):
    items = [
        ("Sounds", f"Sounds/Pad {i}.adg", item(f"Pad {i}.adg", f"FileId_{i}"))
        for i in range(150)
    ]
    monkeypatch.setattr(library, "index", lambda refresh=False: items)
    monkeypatch.setitem(library._cache, "items", items)
    out = library.find_in_library({"query": "pad"})
    assert (len(out["results"]), out["found"], "more" in out) == (150, 150, False)
    assert len(library.find_in_library({"query": "pad", "limit": 0})["results"]) == 150
    out = library.find_in_library({"query": "pad", "limit": 5})
    assert (len(out["results"]), out["more"]) == (5, 145)
