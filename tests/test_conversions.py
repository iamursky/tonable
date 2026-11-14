"""convert_audio against a stand-in for Live.Conversions."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "remote_script"))

import fake_live  # noqa: E402
from Tonable import conversions  # noqa: E402
from Tonable.server import CommandError  # noqa: E402


def audio_clip(**over):
    base = dict(name="Vox", is_midi_clip=False, is_audio_clip=True, is_recording=False)
    base.update(over)
    return SimpleNamespace(**base)


def make_song(clip=None):
    song = fake_live.UndoSong(
        signature_numerator=4,
        signature_denominator=4,
        tracks=[],
        return_tracks=[],
        master_track=fake_live.Track("Master", kind="return"),
    )
    track = fake_live.Track("Vox", kind="audio")
    track.clip_slots = [fake_live.slot(clip or audio_clip())]
    track.arrangement_clips = [audio_clip(name="Arr")]
    midi = fake_live.Track("Keys")
    midi.clip_slots = [fake_live.slot(fake_live.clip("Notes"))]
    song.tracks = [track, midi]
    return song


def make_live(song, convertible=True, instant=False):
    calls = []

    def record(name, makes_track=False):
        def fn(*args):
            calls.append((name, args[1:]))
            if instant:
                song.tracks.append(fake_live.Track("New", kind="midi"))

        return fn

    enum = SimpleNamespace(harmony_to_midi="H", melody_to_midi="M", drums_to_midi="D")
    conv = SimpleNamespace(
        AudioToMidiType=enum,
        is_convertible_to_midi=lambda s, c: convertible,
        audio_to_midi_clip=record("audio_to_midi_clip"),
        create_midi_track_with_simpler=record("create_midi_track_with_simpler"),
        create_drum_rack_from_audio_clip=record("create_drum_rack_from_audio_clip"),
        sliced_simpler_to_drum_rack=record("sliced_simpler_to_drum_rack"),
        create_midi_track_from_drum_pad=record("create_midi_track_from_drum_pad"),
        move_devices_on_track_to_new_drum_rack_pad=record("move_devices"),
    )
    return SimpleNamespace(Conversions=conv), calls


@pytest.fixture
def live(monkeypatch):
    song = make_song()
    fake, calls = make_live(song)
    monkeypatch.setattr(conversions, "Live", fake)
    return song, calls


def run(song, **p):
    return conversions.convert_audio(song, p)


def test_audio_to_midi_uses_the_enum_member(live):
    song, calls = live
    out = run(song, action="audio_to_midi", clip="t0/s0", type="Drums")
    assert calls == [("audio_to_midi_clip", (song.tracks[0].clip_slots[0].clip, "D"))]
    assert out["done"] == "audio_to_midi" and out["clip"] == "t0/s0"
    assert "next tick" in out["note"]
    assert song.undo_steps == 1 and song.undo_depth == 0


def test_enum_falls_back_to_the_documented_numbers(monkeypatch):
    song = make_song()
    fake, calls = make_live(song)
    fake.Conversions.AudioToMidiType = SimpleNamespace()
    monkeypatch.setattr(conversions, "Live", fake)
    run(song, action="audio_to_midi", clip="t0/s0", type="melody")
    assert calls[0][1][1] == 1


def test_arrangement_clips_convert_too(live):
    song, calls = live
    run(song, action="to_simpler", clip="t0/a0")
    assert calls[0][0] == "create_midi_track_with_simpler"


def test_new_tracks_are_reported_when_already_visible(monkeypatch):
    song = make_song()
    fake, _ = make_live(song, instant=True)
    monkeypatch.setattr(conversions, "Live", fake)
    out = run(song, action="to_drum_rack", clip="t0/s0")
    assert out["new_tracks"] == [{"path": "t2", "name": "New"}]
    assert "note" not in out


def test_midi_and_recording_clips_are_refused(live):
    song, calls = live
    with pytest.raises(CommandError) as err:
        run(song, action="audio_to_midi", clip="t1/s0", type="drums")
    assert "MIDI clip" in str(err.value)
    song.tracks[0].clip_slots[0].clip.is_recording = True
    with pytest.raises(CommandError) as err:
        run(song, action="to_simpler", clip="t0/s0")
    assert err.value.code == "busy" and calls == []


def test_not_convertible_and_bad_type(monkeypatch):
    song = make_song()
    fake, calls = make_live(song, convertible=False)
    monkeypatch.setattr(conversions, "Live", fake)
    with pytest.raises(CommandError):
        run(song, action="audio_to_midi", clip="t0/s0", type="drums")
    with pytest.raises(CommandError):
        run(song, action="audio_to_midi", clip="t0/s0", type="bass")
    assert calls == []


def test_clip_is_required_and_must_exist(live):
    song, _ = live
    with pytest.raises(CommandError):
        run(song, action="to_simpler")
    with pytest.raises(CommandError):
        run(song, action="to_simpler", clip="t0/s5")


def test_slices_and_pads(live):
    song, calls = live
    simpler = fake_live.Device("Simpler", "OriginalSimpler", 1)
    drums = fake_live.DrumRack("Kit", {36: fake_live.pad(36, "Kick", simpler)})
    song.tracks[1].devices = [simpler, drums]
    run(song, action="slices_to_drum_rack", target="t1/d0")
    assert calls[-1] == ("sliced_simpler_to_drum_rack", (simpler,))
    run(song, action="pad_to_track", target="t1/d1/pC1")
    assert calls[-1][0] == "create_midi_track_from_drum_pad"
    with pytest.raises(CommandError):
        run(song, action="slices_to_drum_rack", target="t1/d1")
    with pytest.raises(CommandError):
        run(song, action="pad_to_track", target="t1/d0")


def test_move_devices_passes_the_track_index(live):
    song, calls = live
    run(song, action="move_devices_to_drum_rack", track="t1")
    assert calls[-1] == ("move_devices", (1,))
    with pytest.raises(CommandError):
        run(song, action="move_devices_to_drum_rack", track="m")


def test_a_live_without_conversions_says_so(monkeypatch):
    monkeypatch.setattr(conversions, "Live", SimpleNamespace())
    with pytest.raises(CommandError) as err:
        run(make_song(), action="to_simpler", clip="t0/s0")
    assert err.value.code == "not_supported"
    monkeypatch.setattr(conversions, "Live", None)
    with pytest.raises(CommandError):
        run(make_song(), action="to_simpler", clip="t0/s0")


def test_live_refusing_is_a_readable_error(live):
    song, _ = live
    live_conv = conversions.Live.Conversions

    def boom(*a):
        raise RuntimeError("Cannot convert MIDI clip.")

    live_conv.create_midi_track_with_simpler = boom
    with pytest.raises(CommandError) as err:
        run(song, action="to_simpler", clip="t0/s0")
    assert "Cannot convert" in str(err.value)


def test_unknown_action(live):
    with pytest.raises(CommandError):
        run(live[0], action="to_wav")


def test_tool_schema():
    from tonable import server
    from tonable.tools import conversions as tool  # noqa: F401

    t = {t.name: t for t in asyncio.run(server.mcp.list_tools())}["convert_audio"]
    assert len(t.description) > 40 and t.annotations is not None
    assert "anyOf" not in str(t.inputSchema)
    for name, prop in t.inputSchema["properties"].items():
        assert prop.get("description"), name
