"""The wider Live surface: Set recording state, transport, scenes, track mixer
extras, clip settings and actions, extra note fields, timeline clips and audio files.
All against stand-in objects; nothing here has run in Live."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "remote_script"))

import fake_live  # noqa: E402
from Tonable import (  # noqa: E402
    arrangement,
    clipprops,
    clipref,
    clips,
    dispatch,
    edit,
    reading,
    song,
)
from Tonable.server import CommandError  # noqa: E402


def table(s):
    return dispatch.commands(SimpleNamespace(song=s, live_version="12.4.16"))


# --- every module of the Remote Script is reloaded ---------------------------------


def test_modules_list_covers_every_remote_script_module():
    folder = Path(dispatch.__file__).parent
    on_disk = {p.stem for p in folder.glob("*.py")}
    # server is never reloaded (it owns the socket); __init__ is the package.
    expected = on_disk - {"__init__", "server", "dispatch"}
    assert expected <= set(dispatch.MODULES), expected - set(dispatch.MODULES)


def test_new_commands_are_in_the_table():
    commands = table(fake_live.song())
    for name in (
        "update_clip",
        "create_audio_clip",
        "app",
        "groove",
        "convert_audio",
        "live_api",
    ):
        assert name in commands


def test_undo_step_flushes_parameter_writes_before_it_closes():
    """Live 12.4 applies parameter and Set-property writes a moment late; unless they
    are flushed first they land after the step closes and need a second undo."""
    order = []
    fake = SimpleNamespace(
        begin_undo_step=lambda: order.append("begin"),
        sync_parameter_changes=lambda: order.append("sync"),
        end_undo_step=lambda: order.append("end"),
    )
    with song.undo_step(fake), song.undo_step(fake):
        order.append("work")
    assert order == ["begin", "work", "sync", "end"]


def test_undo_step_works_on_a_live_without_sync():
    order = []
    fake = SimpleNamespace(
        begin_undo_step=lambda: order.append("begin"),
        end_undo_step=lambda: order.append("end"),
    )
    with song.undo_step(fake):
        pass
    assert order == ["begin", "end"]


# --- the Set ---------------------------------------------------------------------


class RecordingSong(fake_live.UndoSong):
    pass


def settable_song(**over):
    base = dict(
        tempo=120.0,
        signature_numerator=4,
        signature_denominator=4,
        is_playing=False,
        loop=False,
        loop_start=0.0,
        loop_length=16.0,
        metronome=False,
        record_mode=False,
        arrangement_overdub=False,
        punch_in=False,
        groove_amount=0.0,
        clip_trigger_quantization=4,
        count_in_duration=0,
        midi_recording_quantization=0,
        can_capture_midi=True,
        can_undo=True,
        can_redo=False,
        current_song_time=0.0,
        song_length=64.0,
    )
    base.update(over)
    return RecordingSong(**base)


def test_update_set_writes_recording_state_and_reads_it_back():
    s = settable_song()
    out = song.update_set(
        s,
        {
            "record": "true",
            "overdub": True,
            "clip_trigger_quantization": "1/4",
            "midi_recording_quantization": "1/16",
            "groove_amount": 0.5,
        },
    )
    assert s.record_mode is True and s.arrangement_overdub is True
    assert s.clip_trigger_quantization == 7 and s.midi_recording_quantization == 5
    assert set(out["changed"]) == {
        "record",
        "overdub",
        "clip_trigger_quantization",
        "midi_recording_quantization",
        "groove_amount",
    }
    assert out["settings"]["midi_recording_quantization"] == "1/16"
    assert s.undo_steps == 1


def test_update_set_reports_a_missing_setting_without_failing_the_rest():
    s = settable_song()
    out = song.update_set(s, {"tempo": 100, "link": "true"})
    assert out["changed"] == ["tempo"]
    assert "does not have" in out["results"][0]["error"]


def test_update_set_with_nothing_is_still_an_error():
    with pytest.raises(CommandError):
        song.update_set(settable_song(), {})


def test_read_set_shows_settings_and_facts():
    out = reading.read_set(fake_live.song())
    assert "settings" not in out  # the plain fake has none
    s = fake_live.song()
    s.record_mode = True
    s.song_length = 128.0
    out = reading.read_set(s)
    assert out["settings"]["record"] is True
    assert out["facts"]["song_length_beats"] == 128.0


class Calls:
    def __init__(self):
        self.log = []

    def __getattr__(self, name):
        def call(*args):
            self.log.append((name, args))

        return call


def test_transport_new_actions_call_live():
    calls = Calls()
    s = settable_song()
    for name in (
        "jump_by",
        "jump_to_next_cue",
        "jump_to_prev_cue",
        "play_selection",
        "tap_tempo",
        "capture_midi",
        "trigger_session_record",
    ):
        setattr(s, name, getattr(calls, name))
    s.tracks = []
    for action, extra in (
        ("jump_by", {"time_beats": -4}),
        ("next_locator", {}),
        ("previous_locator", {}),
        ("play_selection", {}),
        ("tap_tempo", {}),
        ("capture_midi", {}),
        ("trigger_session_record", {}),
    ):
        song.transport(s, {"action": action, **extra})
    assert [n for n, _ in calls.log] == [
        "jump_by",
        "jump_to_next_cue",
        "jump_to_prev_cue",
        "play_selection",
        "tap_tempo",
        "capture_midi",
        "trigger_session_record",
    ]
    assert calls.log[0][1] == (-4.0,)


def test_transport_action_this_live_lacks_is_not_supported():
    with pytest.raises(CommandError) as err:
        song.transport(settable_song(), {"action": "tap_tempo"})
    assert err.value.code == "not_supported"


def test_capture_midi_refuses_when_nothing_was_played():
    s = settable_song(can_capture_midi=False, capture_midi=lambda: None)
    with pytest.raises(CommandError) as err:
        song.transport(s, {"action": "capture_midi"})
    assert err.value.code == "nothing_to_capture"


def test_back_to_arranger_sets_the_property():
    s = settable_song(back_to_arranger=True)
    song.transport(s, {"action": "back_to_arranger"})
    assert s.back_to_arranger is False


def test_stop_clip_and_jump_in_clip():
    s = fake_live.song()
    stopped = []
    s.tracks[0].clip_slots[0].stop = lambda: stopped.append(0)
    s.tracks[0].jump_in_running_session_clip = lambda beats: stopped.append(beats)
    s.current_song_time = 0.0
    s.start_playing = lambda: None
    out = song.transport(s, {"action": "stop_clip", "track": "t0", "slot": 0})
    assert out["clip"] == "Bass A"
    song.transport(s, {"action": "jump_in_clip", "track": "t0", "time_beats": 2})
    assert stopped == [0, 2.0]


def test_scene_time_signature():
    s = fake_live.song()
    s.scenes[0].time_signature_enabled = False
    out = song.scene(s, {"action": "update", "scene": 0, "time_signature": "3/4"})
    assert out["time_signature"] == "3/4"
    assert s.scenes[0].time_signature_numerator == 3
    song.scene(s, {"action": "update", "scene": 0, "time_signature": "off"})
    assert s.scenes[0].time_signature_enabled is False


# --- tracks ---------------------------------------------------------------------


def test_update_track_monitoring_crossfade_and_fold():
    s = fake_live.song()
    s.begin_undo_step = lambda: None
    s.end_undo_step = lambda: None
    track = s.tracks[2]
    track.current_monitoring_state = 1
    track.fold_state = False
    track.mixer_device.crossfade_assign = 1
    track.mixer_device.crossfade_assignments = ["A", "NONE", "B"]
    out = edit.update_track(
        s,
        {"track": "t2", "monitoring": "In", "crossfade": "b", "folded": "true"},
    )
    assert track.current_monitoring_state == 0
    assert track.mixer_device.crossfade_assign == 2
    assert track.fold_state is True
    assert {r["field"] for r in out["results"]} == {"monitoring", "crossfade", "folded"}


def test_update_track_channel_routing_and_master_cue_volume():
    s = fake_live.song()
    s.begin_undo_step = lambda: None
    s.end_undo_step = lambda: None
    track = s.tracks[0]
    track.available_input_routing_channels = [
        SimpleNamespace(display_name="1/2"),
        SimpleNamespace(display_name="3/4"),
    ]
    track.input_routing_channel = track.available_input_routing_channels[0]
    out = edit.update_track(s, {"track": "t0", "input_channel": "3/4"})
    assert out["results"][0] == {"field": "input_channel", "now": "3/4"}
    out = edit.update_track(s, {"track": "t0", "pan_left": "25L"})
    assert "does not have" in out["results"][0]["error"]
    s.master_track.mixer_device.cue_volume = fake_live.Param("Cue", 0.5, show="0 dB")
    out = edit.update_track(s, {"track": "m", "cue_volume_db": "-6"})
    assert out["results"][0]["field"] == "cue_volume"


def test_read_track_shows_monitoring_and_freeze_state():
    s = fake_live.song()
    s.tracks[0].current_monitoring_state = 2
    s.tracks[0].is_frozen = False
    out = reading.read_track(s, "t0")
    assert out["settings"]["monitoring"] == "Off"
    assert out["settings"]["is_frozen"] is False


# --- notes ---------------------------------------------------------------------


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(clips, "Live", fake_live.FAKE_LIVE_MODULE)
    s = fake_live.writable_song()
    return s


def test_notes_carry_probability_and_other_new_fields(live):
    out = clips.write_clip(
        live,
        {
            "track": "t0",
            "slot": 0,
            "notes": [
                {
                    "pitch": "C3",
                    "start": 0,
                    "length": 1,
                    "velocity": 100,
                    "probability": 0.5,
                    "velocity_deviation": 12,
                    "release_velocity": 30,
                },
                {"pitch": "D3", "start": 1, "length": 1, "velocity": 90},
            ],
        },
    )
    assert out["notes_added"] == 2 and out["clip"] == "t0/s0"
    read = clips.read_clip(live, "t0", 0)
    first, second = read["notes"]
    assert first["probability"] == 0.5
    assert first["velocity_deviation"] == 12 and first["release_velocity"] == 30
    assert "probability" not in second  # defaults stay out of the answer


def test_note_field_ranges_are_checked():
    out = clips.parse_notes(
        [{"pitch": 60, "start": 0, "length": 1, "velocity": 80, "probability": 2}]
    )
    assert out[0] == [] and "probability" in out[1][0]["error"]


def test_edit_notes_sets_probability_and_mutes(live):
    clips.write_clip(
        live,
        {
            "track": "t0",
            "slot": 0,
            "notes": [
                {"pitch": 60, "start": 0, "length": 1, "velocity": 80},
                {"pitch": 62, "start": 1, "length": 1, "velocity": 80},
            ],
        },
    )
    clips.edit_notes(
        live, {"track": "t0", "slot": 0, "action": "probability", "value": 0.25}
    )
    clips.edit_notes(
        live,
        {"track": "t0", "slot": 0, "action": "mute", "from_beats": 1},
    )
    notes = clips.read_clip(live, "t0", 0)["notes"]
    assert [n.get("probability") for n in notes] == [0.25, 0.25]
    assert [n.get("mute") for n in notes] == [None, True]
    with pytest.raises(CommandError):
        clips.edit_notes(live, {"track": "t0", "slot": 0, "action": "probability"})


# --- clip addresses ----------------------------------------------------------------


def test_clip_address_parsing():
    assert clipref.parse("t0/s2") == ("t0", "s", 2)
    assert clipref.parse("rA/S1")[1] == "s"
    assert clipref.parse(" t3/a10 ") == ("t3", "a", 10)
    with pytest.raises(CommandError):
        clipref.parse("t0")


def timeline_song():
    s = fake_live.writable_song()
    a = fake_live.MidiClip(4.0)
    a.name = "Intro"
    a.start_time, a.end_time = 0.0, 4.0
    b = fake_live.MidiClip(4.0)
    b.name = "Drop"
    b.start_time, b.end_time = 8.0, 12.0
    s.tracks[0].arrangement_clips = [a, b]
    return s


def test_locate_arrangement_clip_and_errors():
    s = timeline_song()
    ref = clipref.locate(s, "t0/a1")
    assert ref.kind == "arrangement" and ref.clip.name == "Drop"
    assert clipref.path_of(s, s.tracks[0], ref.clip) == "t0/a1"
    with pytest.raises(CommandError) as err:
        clipref.locate(s, "t0/a5")
    assert "a0-a1" in str(err.value)
    with pytest.raises(CommandError) as err:
        clipref.locate(s, "t0/s0")
    assert "empty" in str(err.value)
    empty = clipref.locate(s, "t0/s0", need_clip=False)
    assert empty.clip is None and empty.slot is not None


def test_read_and_write_an_arrangement_clip_by_address(live, monkeypatch):
    s = timeline_song()
    out = clips.write_clip(
        s,
        {
            "clip": "t0/a1",
            "notes": [{"pitch": "E3", "start": 0, "length": 1, "velocity": 70}],
        },
    )
    assert out["created"] is False and out["clip"] == "t0/a1"
    assert clips.read_clip(s, None, None, "t0/a1")["notes"][0]["pitch"] == "E3"


# --- update_clip ---------------------------------------------------------------------


class Warp:
    def __init__(self, beat, sample):
        self.beat_time, self.sample_time = beat, sample


class FullClip(fake_live.MidiClip):
    """A MIDI clip with the settings Live gives every clip."""

    def __init__(self, length=4.0):
        super().__init__(length)
        self.muted = False
        self.color_index = 3
        self.launch_mode = 0
        self.launch_quantization = 0
        self.legato = False
        self.velocity_amount = 0.0
        self.scale_mode = False
        self.root_note = 0
        self.scale_name = "Major"
        self.signature_numerator = 4
        self.signature_denominator = 4
        self.calls = []

    def crop(self):
        self.calls.append("crop")

    def quantize(self, grid, amount):
        self.calls.append(("quantize", grid, amount))

    def clear_all_envelopes(self):
        self.calls.append("clear")

    def fire(self):
        self.calls.append("fire")


class AudioClip(FullClip):
    def __init__(self):
        super().__init__(8.0)
        self.is_midi_clip = False
        self.is_audio_clip = True
        self.warping = True
        self.warp_mode = 0
        self.available_warp_modes = [0, 1, 4]
        self.gain = 0.5
        self.pitch_coarse = 0
        self.file_path = "/music/loop.wav"
        self.sample_rate = 44100
        self.warp_markers = [Warp(0.0, 0.0), Warp(8.0, 4.0)]

    def add_warp_marker(self, marker):
        self.warp_markers.append(Warp(marker.beat_time, marker.sample_time))

    def remove_warp_marker(self, beat):
        self.warp_markers = [m for m in self.warp_markers if m.beat_time != beat]


def song_with(clip):
    s = fake_live.writable_song()
    s.tracks[0].clip_slots[0].clip = clip
    return s


def test_update_clip_settings_with_read_back():
    clip = FullClip()
    s = song_with(clip)
    out = clipprops.update_clip(
        s,
        {
            "clip": "t0/s0",
            "name": "Hook",
            "muted": "true",
            "launch_mode": "gate",
            "launch_quantization": "1 Bar",
            "legato": True,
            "scale_name": "Minor",
            "root_note": 9,
            "time_signature": "3/4",
        },
    )
    assert clip.name == "Hook" and clip.muted is True
    assert clip.launch_mode == 1 and clip.launch_quantization == 5
    assert (
        clip.scale_name == "Minor"
        and clip.root_note == 9
        and clip.signature_numerator == 3
    )
    shown = out["settings"]
    assert shown["launch_mode"] == "Gate" and shown["time_signature"] == "3/4"
    assert s.undo_steps == 1


def test_update_clip_reports_bad_values_per_field():
    s = song_with(FullClip())
    out = clipprops.update_clip(
        s, {"track": "t0", "slot": 0, "launch_mode": "Spin", "color_index": 99}
    )
    errors = {r["field"]: r["error"] for r in out["results"] if "error" in r}
    assert "Gate" in errors["launch_mode"] and "0 to 69" in errors["color_index"]


def test_loop_markers_are_retried_when_the_order_matters():
    clip = FullClip(8.0)

    class Strict(FullClip):
        def __setattr__(self, name, value):
            if (
                name == "loop_start"
                and "loop_end" in self.__dict__
                and value >= self.loop_end
            ):
                raise RuntimeError("start must be before the end")
            super().__setattr__(name, value)

    clip = Strict(8.0)
    s = song_with(clip)
    # loop_start 10 only works once loop_end has moved beyond it
    out = clipprops.update_clip(s, {"clip": "t0/s0", "loop_start": 10, "loop_end": 20})
    assert all("error" not in r for r in out["results"]), out
    assert clip.loop_start == 10 and clip.loop_end == 20


def test_update_clip_actions():
    clip = FullClip()
    s = song_with(clip)
    clipprops.update_clip(s, {"clip": "t0/s0", "action": "crop"})
    clipprops.update_clip(
        s, {"clip": "t0/s0", "action": "quantize", "grid": "1/16", "amount": "0.5"}
    )
    clipprops.update_clip(s, {"clip": "t0/s0", "action": "clear_envelopes"})
    assert clip.calls == ["crop", ("quantize", 5, 0.5), "clear"]
    out = clipprops.update_clip(s, {"clip": "t0/s0", "action": "quantize"})
    assert "error" in out["results"][0]
    with pytest.raises(CommandError):
        clipprops.update_clip(s, {"clip": "t0/s0", "action": "explode"})


def test_update_clip_needs_something_to_do_and_a_clip():
    s = song_with(FullClip())
    with pytest.raises(CommandError):
        clipprops.update_clip(s, {"clip": "t0/s0"})
    with pytest.raises(CommandError) as err:
        clipprops.update_clip(s, {"clip": "t0/s1", "name": "x"})
    assert "empty" in str(err.value)


def test_stop_button_works_on_an_empty_slot():
    s = fake_live.writable_song()
    s.tracks[0].clip_slots[1].has_stop_button = True
    out = clipprops.update_clip(s, {"clip": "t0/s1", "stop_button": "false"})
    assert out["results"] == [{"field": "stop_button", "now": False}]


def test_audio_clip_warp_settings_and_markers(monkeypatch):
    class Marker:  # Live's Clip.WarpMarker takes names, not an order
        def __init__(self, sample_time, beat_time):
            self.sample_time, self.beat_time = sample_time, beat_time

    monkeypatch.setattr(
        clipprops, "Live", SimpleNamespace(Clip=SimpleNamespace(WarpMarker=Marker))
    )
    clip = AudioClip()
    s = song_with(clip)
    out = clipprops.update_clip(
        s, {"clip": "t0/s0", "warp_mode": "Complex", "gain": 0.7, "pitch_coarse": -2}
    )
    assert clip.warp_mode == 4 and clip.gain == 0.7 and clip.pitch_coarse == -2
    bad = clipprops.update_clip(s, {"clip": "t0/s0", "warp_mode": "Texture"})
    assert "available" in bad["results"][0]["error"] and clip.warp_mode == 4
    added = clipprops.update_clip(
        s, {"clip": "t0/s0", "action": "add_warp_marker", "time_beats": 4}
    )
    markers = added["results"][0]["audio"]["warp_markers"]
    assert [m["beat_time"] for m in markers] == [0.0, 8.0, 4.0]
    # no sample_time given: placed between its neighbours (beat 4 of 0..8 -> 2 s)
    assert markers[-1]["sample_time"] == 2.0
    assert out["settings"]["warp_mode"] == "Complex"


def test_warp_markers_need_an_audio_clip():
    s = song_with(FullClip())
    out = clipprops.update_clip(
        s, {"clip": "t0/s0", "action": "add_warp_marker", "time_beats": 1}
    )
    assert "audio clips" in out["results"][0]["error"]


def test_read_clip_shows_audio_details_and_settings():
    s = song_with(AudioClip())
    out = clips.read_clip(s, "t0", 0)
    assert out["audio"]["file"] == "/music/loop.wav"
    assert out["audio"]["warp_markers"][1]["sample_time"] == 4.0
    assert out["settings"]["warp_mode"] == "Beats"
    assert out["clip"] == "t0/s0" and out["type"] == "audio"


def test_groove_can_be_assigned_by_name(monkeypatch):
    clip = FullClip()
    clip.groove = SimpleNamespace(name="none")
    s = song_with(clip)
    swing = SimpleNamespace(name="MPC 16 Swing")
    from Tonable import grooves

    monkeypatch.setattr(grooves, "find_groove", lambda song_, ref: swing)
    out = clipprops.update_clip(s, {"clip": "t0/s0", "groove": "MPC 16 Swing"})
    assert clip.groove is swing
    assert out["results"] == [{"field": "groove", "now": "MPC 16 Swing"}]


# --- audio files ---------------------------------------------------------------------


class AudioSlot(fake_live.ClipSlot):
    def create_audio_clip(self, path):
        self.clip = AudioClip()
        self.clip.file_path = path


def audio_song():
    s = fake_live.writable_song()
    s.tracks[2].clip_slots = [AudioSlot() for _ in range(4)]
    return s


def test_create_audio_clip_in_a_session_slot(tmp_path):
    wav = tmp_path / "kick.wav"
    wav.write_bytes(b"RIFF")
    s = audio_song()
    out = clipprops.create_audio_clip(
        s, {"path": str(wav), "track": "t2", "slot": 1, "name": "Kick"}
    )
    assert out["created"] == "t2/s1" and out["name"] == "Kick"
    assert out["audio"]["file"] == str(wav)


def test_create_audio_clip_on_the_timeline(tmp_path):
    wav = tmp_path / "loop.wav"
    wav.write_bytes(b"RIFF")
    s = audio_song()
    placed = []

    def create(path, position):
        clip = AudioClip()
        clip.start_time, clip.end_time = position, position + 8
        s.tracks[2].arrangement_clips = [clip]
        placed.append((path, position))
        return clip

    s.tracks[2].create_audio_clip = create
    out = clipprops.create_audio_clip(s, {"path": str(wav), "track": "t2", "at_bar": 3})
    assert placed == [(str(wav), 8.0)] and out["created"] == "t2/a0"


@pytest.mark.parametrize(
    ("path", "track", "slot", "code", "text"),
    [
        ("missing.wav", "t2", 0, "not_found", "no file"),
        ("notes.txt", "t2", 0, "bad_target", "only audio files"),
        ("kick.wav", "t0", 0, "bad_target", "not an audio track"),
        ("", "t2", 0, "bad_params", "path is required"),
    ],
)
def test_create_audio_clip_refusals(tmp_path, path, track, slot, code, text):
    (tmp_path / "kick.wav").write_bytes(b"RIFF")
    (tmp_path / "notes.txt").write_text("hi")
    full = str(tmp_path / path) if path else ""
    with pytest.raises(CommandError) as err:
        clipprops.create_audio_clip(
            audio_song(), {"path": full, "track": track, "slot": slot}
        )
    assert err.value.code == code and text in str(err.value)


def test_create_audio_clip_refuses_a_taken_slot(tmp_path):
    wav = tmp_path / "kick.wav"
    wav.write_bytes(b"RIFF")
    s = audio_song()
    s.tracks[2].clip_slots[0].clip = AudioClip()
    with pytest.raises(CommandError) as err:
        clipprops.create_audio_clip(s, {"path": str(wav), "track": "t2", "slot": 0})
    assert err.value.code == "slot_taken"


# --- the timeline ---------------------------------------------------------------------


def timeline_with_tools():
    s = timeline_song()
    track = s.tracks[0]
    track.take_lanes = [SimpleNamespace(name="Take 1", arrangement_clips=[1, 2])]
    track.deleted = []

    def duplicate(clip, at):
        copy = fake_live.MidiClip(clip.end_time - clip.start_time)
        copy.name = clip.name
        copy.start_time, copy.end_time = at, at + (clip.end_time - clip.start_time)
        track.arrangement_clips.append(copy)
        return copy

    track.duplicate_clip_to_arrangement = duplicate
    track.delete_clip = lambda clip: (
        track.arrangement_clips.remove(clip),
        track.deleted.append(clip.name),
    )
    return s


def test_arrangement_list_gives_addresses_and_take_lanes():
    s = timeline_with_tools()
    s.cue_points = []
    s.loop, s.loop_start, s.loop_length = False, 0.0, 16.0
    out = arrangement.arrangement(s, {"action": "list"})
    track = out["tracks"][0]
    assert [c["address"] for c in track["clips"]] == ["t0/a0", "t0/a1"]
    assert track["clips"][0]["type"] == "midi"
    assert track["take_lanes"] == [{"index": 0, "name": "Take 1", "clips": 2}]


def test_move_clip_copies_then_deletes_the_original():
    s = timeline_with_tools()
    out = arrangement.arrangement(
        s, {"action": "move_clip", "clip": "t0/a1", "at_bar": 10}
    )
    track = s.tracks[0]
    assert track.deleted == ["Drop"]
    assert out["moved"]["clip"] == "Drop"
    assert out["clip"]["start_beats"] == 36.0


def test_move_clip_refuses_its_own_span_and_session_clips():
    s = timeline_with_tools()
    with pytest.raises(CommandError) as err:
        arrangement.arrangement(
            s, {"action": "move_clip", "clip": "t0/a1", "at_beats": 10}
        )
    assert err.value.code == "overlap"
    with pytest.raises(CommandError):
        arrangement.arrangement(
            s, {"action": "move_clip", "clip": "t0/s0", "at_beats": 40}
        )
    unchanged = arrangement.arrangement(
        s, {"action": "move_clip", "clip": "t0/a1", "at_beats": 8}
    )
    assert unchanged["unchanged"] is True


def test_copy_clip_takes_a_timeline_clip_address():
    s = timeline_with_tools()
    out = arrangement.arrangement(
        s, {"action": "copy_clip", "clip": "t0/a0", "at_beats": 32}
    )
    assert out["copied"] == "t0/a0" and out["clip"]["start_beats"] == 32.0


def test_add_take_lane_needs_a_live_that_has_it():
    s = timeline_with_tools()
    with pytest.raises(CommandError) as err:
        arrangement.arrangement(s, {"action": "add_take_lane", "track": "t0"})
    assert err.value.code == "not_supported"
    s.tracks[0].create_take_lane = lambda: s.tracks[0].take_lanes.append(
        SimpleNamespace(name="Take 2", arrangement_clips=[])
    )
    out = arrangement.arrangement(s, {"action": "add_take_lane", "track": "t0"})
    assert len(out["take_lanes"]) == 2
