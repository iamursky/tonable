"""write_clip and read_clip against the fake Live."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "remote_script"))

import fake_live  # noqa: E402
from Tonable import clips  # noqa: E402
from Tonable.server import CommandError  # noqa: E402


@pytest.fixture
def song(monkeypatch):
    monkeypatch.setattr(clips, "Live", fake_live.FAKE_LIVE_MODULE)
    return fake_live.writable_song()


def write(song, **params):
    return clips.write_clip(song, {"track": "t0", "slot": 0, **params})


CHORD = [
    {"pitch": "C3", "start": 0, "length": 1, "velocity": 100},
    {"pitch": "E3", "start": 1, "length": 1, "velocity": 90},
    {"pitch": 67, "start": "2", "length": "1.5", "velocity": "80"},
]


def test_new_clip_fits_whole_bars(song):
    out = write(song, notes=CHORD, name="Riff")
    assert out["created"] is True
    assert out["length_beats"] == 4.0  # notes end at 3.5 -> one 4/4 bar
    assert (out["notes_added"], out["notes_total"]) == (3, 3)
    assert out["name"] == "Riff"
    assert song.undo_steps == 1 and song.undo_depth == 0


def test_explicit_length_and_bars_in_3_4(song):
    assert write(song, notes=CHORD, length_beats=16)["length_beats"] == 16.0
    song.signature_numerator = 3
    out = clips.write_clip(song, {"track": "t1", "slot": 0, "notes": CHORD})
    assert out["length_beats"] == 6.0  # 3.5 beats -> two 3/4 bars


def test_empty_clip_is_one_bar(song):
    assert write(song)["length_beats"] == 4.0


def test_read_back(song):
    write(song, notes=CHORD)
    out = clips.read_clip(song, "t0", 0)
    assert out["notes"][0] == {
        "pitch": "C3",
        "midi": 60,
        "start": 0.0,
        "length": 1.0,
        "velocity": 100.0,
    }
    assert [n["pitch"] for n in out["notes"]] == ["C3", "E3", "G3"]


def test_replace_and_add(song):
    write(song, notes=CHORD)
    out = write(song, notes=CHORD[:1], mode="add")
    assert (out["created"], out["notes_removed"], out["notes_total"]) == (False, 0, 4)
    out = write(song, notes=CHORD[1:2])
    assert (out["notes_removed"], out["notes_total"]) == (4, 1)


def test_resize_existing_clip(song):
    write(song, notes=CHORD)
    assert write(song, mode="add", length_beats=8)["length_beats"] == 8.0
    assert write(song, mode="add", length_beats=2)["length_beats"] == 2.0


def test_bad_notes_are_rejected_one_by_one(song):
    notes = [
        *CHORD,
        {"pitch": "H2", "start": 0, "length": 1, "velocity": 100},
        {"pitch": "C3", "start": 0, "length": 0, "velocity": 100},
        {"pitch": "C3", "start": 0, "length": 1},
        "C3",
    ]
    out = write(song, notes=notes)
    assert out["notes_added"] == 3
    reasons = [r["error"] for r in out["rejected"]]
    assert [r["index"] for r in out["rejected"]] == [3, 4, 5, 6]
    assert "note name" in reasons[0]
    assert "more than 0" in reasons[1]
    assert "velocity is required" in reasons[2]


def test_note_field_aliases(song):
    out = write(song, notes=[{"note": "A2", "time": 0, "duration": 2, "vel": 64}])
    assert out["notes_added"] == 1


def test_note_after_clip_end_warns(song):
    out = write(
        song,
        notes=[{"pitch": 60, "start": 8, "length": 1, "velocity": 100}],
        length_beats=4,
    )
    assert "after the clip end" in out["warning"]


@pytest.mark.parametrize(
    ("params", "code", "words"),
    [
        ({"track": "t2"}, "bad_target", "not a MIDI track"),
        ({"track": "rA"}, "not_found", "no return tracks"),
        ({"track": "m"}, "bad_target", "no clip slots"),
        ({"slot": 9}, "not_found", "4 scenes"),
        ({"mode": "merge"}, "bad_params", "replace or add"),
    ],
)
def test_errors(song, params, code, words):
    with pytest.raises(CommandError) as err:
        write(song, **params)
    assert err.value.code == code
    assert words in str(err.value)


def test_read_empty_slot(song):
    with pytest.raises(CommandError) as err:
        clips.read_clip(song, "t0", 0)
    assert "is empty" in str(err.value)
