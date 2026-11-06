"""read_set, read_track and read_device against the fake Live, plus addresses."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "remote_script"))

import fake_live  # noqa: E402
from Tonable import objects, reading  # noqa: E402
from Tonable.server import CommandError  # noqa: E402


@pytest.fixture
def song():
    return fake_live.song()


# --- addresses ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "number"),
    [("C3", 60), ("C1", 36), ("C-2", 0), ("G8", 127), ("F#2", 54), ("Bb1", 46)],
)
def test_note_names(name, number):
    assert objects.note_number(name) == number


def test_note_name_round_trip():
    assert all(objects.note_number(objects.note_name(n)) == n for n in range(128))


@pytest.mark.parametrize("bad", ["H1", "C", "C9", "C-3"])
def test_bad_note_names(bad):
    with pytest.raises(CommandError):
        objects.note_number(bad)


def test_resolve_paths(song):
    assert objects.resolve(song, "t0")[2] == "t0"
    kind, obj, path = objects.resolve(song, "t0/d0/c0/d1")
    assert (kind, obj.name, path) == ("device", "Saturator", "t0/d0/c0/d1")
    kind, obj, path = objects.resolve(song, "t1/d0/pc1")
    assert (kind, obj.name, path) == ("pad", "Kick", "t1/d0/pC1")
    assert objects.resolve(song, "rb/d0")[2] == "rB/d0"
    assert objects.resolve(song, "m")[0] == "track"


@pytest.mark.parametrize(
    ("path", "code", "words"),
    [
        ("t9", "not_found", "t0-t4"),
        ("rC", "not_found", "returns A, B"),
        ("t0/d3", "not_found", "only d0"),
        ("t3/d0/c0", "not_found", "not a rack"),
        ("t0/d0/pC1", "not_found", "not a Drum Rack"),
        ("x1", "bad_address", "t0, rA or m"),
        ("t0/c0", "bad_address", "hold devices"),
    ],
)
def test_resolve_errors_say_what_exists(song, path, code, words):
    with pytest.raises(CommandError) as err:
        objects.resolve(song, path)
    assert err.value.code == code
    assert words in str(err.value)


# --- read_set ----------------------------------------------------------------


def test_read_set(song):
    out = reading.read_set(song)
    assert out["tempo"] == 92.0
    assert out["time_signature"] == "4/4"
    assert [t["path"] for t in out["tracks"]] == ["t0", "t1", "t2", "t3", "t4"]
    assert out["tracks"][3] == {
        "path": "t3",
        "name": "Pad",
        "kind": "midi",
        "group": "t2",
        "device_names": ["Operator"],
    }
    assert out["tracks"][4]["mute"] is True
    assert out["tracks"][4]["kind"] == "audio"
    assert out["returns"] == [
        {"path": "rA", "name": "A-Reverb"},
        {"path": "rB", "name": "B-Delay"},
    ]
    assert out["scenes"][0] == {
        "index": 0,
        "name": "Verse",
        "clips": {"t0": "Bass A", "t1": "Beat", "t3": "Pad Verse"},
    }
    assert out["scenes"][1]["clips"] == {"t0": "Bass B", "t1": "Beat"}
    assert out["scenes"][2]["tempo"] == 96.0
    assert out["locators"] == [{"name": "Intro", "time_beats": 0.0}]


# --- read_track --------------------------------------------------------------


def test_read_track_bass(song):
    out = reading.read_track(song, "t0")
    assert out["mixer"] == {
        "volume": "0.0 dB",
        "pan": "C",
        "sends": [
            {"return": "A", "level": "-inf dB"},
            {"return": "B", "level": "-12 dB"},
        ],
    }
    assert out["routing"] == {"input": "All Ins", "output": "Master"}
    rack = out["devices"][0]
    assert rack["path"] == "t0/d0"
    assert rack["rack"] == "rack"
    assert rack["kind"] == "instrument"
    inner = rack["chains"][0]["devices"]
    assert [(d["path"], d["name"]) for d in inner] == [
        ("t0/d0/c0/d0", "Simpler"),
        ("t0/d0/c0/d1", "Saturator"),
    ]
    assert out["session_clips"][0] == {
        "slot": 0,
        "name": "Bass A",
        "length_beats": 16.0,
        "type": "midi",
        "looping": True,
        "playing": True,
    }


def test_read_track_drum_pads(song):
    pads = reading.read_track(song, "t1")["devices"][0]["chains"]
    assert [(p["path"], p["name"], p["note"]) for p in pads] == [
        ("t1/d0/pC1", "Kick", "C1"),
        ("t1/d0/pD1", "Snare", "D1"),
    ]
    assert pads[0]["devices"][0]["path"] == "t1/d0/pC1/c0/d0"


def test_read_return_and_master(song):
    ret = reading.read_track(song, "rB")
    assert ret["path"] == "rB"
    assert ret["devices"][0]["on"] is False
    assert "session_clips" not in ret
    assert reading.read_track(song, "m")["path"] == "m"


# --- read_device -------------------------------------------------------------


def test_rack_shows_mapped_macros_only(song):
    out = reading.read_device(song, "t0/d0")
    assert out["on"] is True
    assert [m["name"] for m in out["macros"]] == [
        "Filter Cutoff",
        "Filter Reso",
        "LFO Rate",
        "Volume LFO",
        "Decay",
        "Release",
        "Chorus",
        "Saturate",
    ]
    assert out["macros"][5]["index"] == 6
    assert "parameters" not in out
    assert out["chains"][0]["devices"][1]["name"] == "Saturator"


def test_rack_all_params(song):
    out = reading.read_device(song, "t0/d0", all_params=True)
    assert len(out["parameters"]) == 16  # Device On is "on", not a parameter


def test_plain_device_shows_parameters(song):
    out = reading.read_device(song, "rA/d0")
    assert out["parameters"] == [
        {
            "index": 1,
            "name": "Decay Time",
            "display": "2.00 s",
            "value": 0.5,
            "min": 0.0,
            "max": 1.0,
        }
    ]


def test_pick_parameters_with_typo(song):
    out = reading.read_device(song, "t0/d0", wanted=["release", "Decy"])
    assert out["parameters"][0]["name"] == "Release"
    assert out["parameters"][1]["error"] == "no such parameter"
    assert "Decay" in out["parameters"][1]["similar"]


def test_quantized_parameter_lists_options(song):
    out = reading.read_device(song, "t0/d0/c0/d0", wanted=["Device On"])
    assert out["parameters"][0]["options"] == ["Off", "On"]
    assert "min" not in out["parameters"][0]


def test_chain_and_pad(song):
    chain = reading.read_device(song, "t0/d0/c0")
    assert chain["kind"] == "chain"
    assert [d["name"] for d in chain["devices"]] == ["Simpler", "Saturator"]
    pad = reading.read_device(song, "t1/d0/pC1")
    assert (pad["kind"], pad["name"], pad["note"]) == ("pad", "Kick", "C1")


def test_empty_pad_is_addressable(song):
    """Live lists all 128 pads; an empty one is a valid target."""
    pad = reading.read_device(song, "t1/d0/pD5")
    assert (pad["note"], pad["chains"]) == ("D5", [])


def test_track_address_points_to_read_track(song):
    with pytest.raises(CommandError) as err:
        reading.read_device(song, "t0")
    assert "read_track" in str(err.value)
