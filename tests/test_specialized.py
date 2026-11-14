"""configure_device against stand-ins for the specialized Live devices.

The stand-ins follow what Producer Pal probed in Live 12.4 (silent reverts, the
index-not-count voice setting, the int 1 that marks a missing modulation row); they
are not Live. See the module docstring of Tonable/specialized.py for what is
verified and what is from memory.
"""

import asyncio
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "remote_script"))

import fake_live  # noqa: E402
from Tonable import specialized  # noqa: E402
from Tonable.server import CommandError  # noqa: E402

# --- stand-ins ---------------------------------------------------------------------


def device(class_name, name=None, **attrs):
    dev = fake_live.Device(name or class_name, class_name, 1)
    dev.view = SimpleNamespace(is_collapsed=False)
    for key, value in attrs.items():
        setattr(dev, key, value)
    return dev


class Stubborn(fake_live.Device):
    """Keeps the old value of the attributes in `_ignore`, like Live does."""

    def __setattr__(self, name, value):
        if name in getattr(self, "_ignore", ()):
            return
        super().__setattr__(name, value)


def song_with(*devices):
    track = fake_live.Track("Track", list(devices))
    return fake_live.UndoSong(
        tracks=[track],
        return_tracks=[],
        master_track=fake_live.Track("Master", kind="return"),
    )


def run(song, target="t0/d0", **kw):
    return specialized.configure_device(song, {"target": target, **kw})


def line(out, field):
    return next(r for r in out["results"] if r["field"] == field)


def simpler(**over):
    calls = []
    sample = SimpleNamespace(
        file_path="/x/kick.wav",
        warping=False,
        warp_mode=0,
        gain=0.5,
        slicing_style=0,
        slicing_sensitivity=0.5,
        slicing_beat_division=4,
        slicing_region_count=8,
        slices=(0, 100),
        insert_slice=lambda t: calls.append(("insert_slice", t)),
        clear_slices=lambda: calls.append(("clear_slices",)),
    )
    attrs = dict(
        playback_mode=0,
        slicing_playback_mode=0,
        retrigger=False,
        pad_slicing=False,
        voices=4,
        pitch_bend_range=5,
        note_pitch_bend_range=48,
        multi_sample_mode=False,
        sample=sample,
        reverse=lambda: calls.append(("reverse",)),
        warp_as=lambda beats: calls.append(("warp_as", beats)),
        replace_sample=lambda path: calls.append(("replace_sample", path)),
    )
    attrs.update(over)
    dev = device("OriginalSimpler", "Simpler", **attrs)
    dev.calls = calls
    return dev


# --- discovery -------------------------------------------------------------------


def test_a_bare_target_lists_settings_and_actions():
    out = run(song_with(simpler()))
    names = {s["name"] for s in out["settings"]}
    assert {"playback_mode", "voices", "sample_warping", "collapsed"} <= names
    mode = next(s for s in out["settings"] if s["name"] == "playback_mode")
    assert mode["value"] == "Classic" and mode["options"] == [
        "Classic",
        "One-Shot",
        "Slicing",
    ]
    assert {"reverse", "warp_as", "replace_sample"} <= {
        a["name"] for a in out["actions"]
    }
    assert "is_active" in out["not_available"]  # the stand-in has no such member


def test_discovery_changes_nothing_and_takes_no_undo_step():
    song = song_with(simpler())
    run(song)
    assert getattr(song, "undo_steps", 0) == 0


def test_a_track_address_is_refused_with_a_hint():
    with pytest.raises(CommandError) as err:
        run(song_with(simpler()), "t0")
    assert "update_track" in str(err.value)


def test_a_device_without_specialties_offers_only_the_generic_settings():
    out = run(song_with(device("Reverb")))
    assert {s["name"] for s in out["settings"]} == {"collapsed"}
    assert [a["name"] for a in out["actions"]] == ["compare_ab"]
    assert specialized.describe(device("Reverb")) == {}


def test_tables_have_unique_names():
    for spec in specialized.SPECS:
        names = [e.row.name for e in specialized.GENERIC.entries + spec.entries]
        assert len(names) == len(set(names)), spec.label
        acts = [a.name for a in specialized.GENERIC.actions + spec.actions]
        assert len(acts) == len(set(acts)), spec.label


# --- Simpler ---------------------------------------------------------------------


def test_simpler_settings_are_converted_and_read_back():
    dev = simpler()
    out = run(
        song_with(dev),
        settings=[
            {"setting": "playback_mode", "value": "one-shot"},
            {"setting": "voices", "value": 12},
            {"setting": "sample_warping", "value": "true"},
            {"setting": "sample_warp_mode", "value": "Complex Pro"},
            {"setting": "retrigger", "value": True},
        ],
    )
    assert dev.playback_mode == 1 and dev.voices == 12 and dev.retrigger is True
    assert dev.sample.warping is True and dev.sample.warp_mode == 6
    assert line(out, "playback_mode")["now"] == "One-Shot"
    assert line(out, "voices")["now"] == 12
    assert "error" not in str(out["results"])


def test_voices_outside_the_live_set_is_refused_not_snapped():
    dev = simpler()
    out = run(song_with(dev), settings=[{"setting": "voices", "value": 9}])
    assert "use one of" in line(out, "voices")["error"] and dev.voices == 4


def test_simpler_ranges_and_read_only_settings():
    dev = simpler()
    out = run(
        song_with(dev),
        settings={"pitch_bend_range": 99, "multi_sample_mode": True, "sample_gain": 2},
    )
    assert "0 to 24" in line(out, "pitch_bend_range")["error"]
    assert line(out, "multi_sample_mode")["error"] == "read-only"
    assert "0 to 1" in line(out, "sample_gain")["error"]


def test_camel_case_and_mapping_forms_are_accepted():
    dev = simpler()
    out = run(song_with(dev), settings={"playbackMode": "Slicing"})
    assert dev.playback_mode == 2 and line(out, "playback_mode")["now"] == "Slicing"


def test_unknown_setting_suggests_names_and_does_not_stop_the_rest():
    dev = simpler()
    out = run(
        song_with(dev),
        settings=[
            {"setting": "playbak_mode", "value": 1},
            {"setting": "retrigger", "value": 1},
        ],
    )
    bad = line(out, "playbak_mode")
    assert bad["error"] == "no such setting" and "playback_mode" in bad["similar"]
    assert dev.retrigger is True


def test_settings_and_action_are_one_undo_step():
    dev = simpler()
    song = song_with(dev)
    out = run(
        song,
        settings=[{"setting": "retrigger", "value": True}],
        action="warp_as",
        args=[{"name": "beats", "value": 4}],
    )
    assert song.undo_steps == 1 and song.undo_depth == 0
    assert out["action"] == {"action": "warp_as", "ok": True}
    assert ("warp_as", 4) in dev.calls  # a whole number goes as an int


def test_actions_check_their_arguments():
    dev = simpler()
    song = song_with(dev)
    assert not run(song, action="warp_as")["action"]["ok"]
    assert not run(song, action="warp_as", args=[{"name": "beats", "value": -1}])[
        "action"
    ]["ok"]
    assert not run(song, action="warp_as", args=[{"name": "bars", "value": 4}])[
        "action"
    ]["ok"]
    unknown = run(song, action="explode")["action"]
    assert not unknown["ok"] and "reverse" in unknown["error"]
    assert dev.calls == []


def test_an_action_missing_in_this_live_is_an_error_line():
    out = run(song_with(simpler()), action="crop")
    assert out["action"]["ok"] is False and "not available" in out["action"]["error"]


def test_replace_sample_only_takes_an_existing_audio_file(tmp_path):
    dev = simpler()
    song = song_with(dev)
    note = tmp_path / "notes.txt"
    note.write_text("x")
    wav = tmp_path / "kick.wav"
    wav.write_bytes(b"RIFF")
    for bad in (note, tmp_path / "gone.wav"):
        out = run(
            song, action="replace_sample", args=[{"name": "path", "value": str(bad)}]
        )
        assert out["action"]["ok"] is False
    assert dev.calls == []
    out = run(song, action="replace_sample", args={"path": str(wav)})
    assert out["action"]["ok"] and dev.calls == [("replace_sample", str(wav.resolve()))]
    dev.multi_sample_mode = True
    out = run(song, action="replace_sample", args={"path": str(wav)})
    assert "multi-sample" in out["action"]["error"]


def test_slice_actions_go_to_the_sample():
    dev = simpler()
    run(song_with(dev), action="insert_slice", args={"time": 4410.0})
    run(song_with(dev), action="clear_slices")
    assert dev.calls == [("insert_slice", 4410), ("clear_slices",)]


# --- Wavetable -------------------------------------------------------------------


class Wavetable(fake_live.Device):
    def __init__(self):
        super().__init__("Wavetable", "InstrumentVector", 1)
        self.parameters += [
            fake_live.Param("Osc 1 Pos"),
            fake_live.Param("Osc 2 Pos"),
            fake_live.Param("Filter 1 Freq"),
        ]
        self.poly_voices = 3  # index: 5 voices
        self.unison_voice_count = 3
        self.oscillator_1_wavetable_index = 0
        self.oscillator_1_wavetable_category = 0
        self.oscillator_wavetable_categories = ["Basics", "Vocal"]
        self.oscillator_1_wavetables = ["Sine", "Saw Dual 1"]
        self.targets = ["Volume", "Transpose", "Osc 1 Pos"]
        self.cells = {}

    def get_modulation_target_parameter_name(self, i):
        return self.targets[i] if i < len(self.targets) else 1

    def get_modulation_value(self, target, source):
        if target >= len(self.targets) or source >= 13:
            return 1
        return self.cells.get((target, source), 0)

    def set_modulation_value(self, target, source, amount):
        self.cells[(target, source)] = amount

    def is_parameter_modulatable(self, parameter):
        return 1 if parameter.name != "Filter 1 Freq" else 0

    def add_parameter_to_modulation_matrix(self, parameter):
        self.targets.append(parameter.name)


def test_wavetable_voice_count_is_stored_as_an_index():
    dev = Wavetable()
    out = run(song_with(dev), settings=[{"setting": "poly_voices", "value": 8}])
    assert dev.poly_voices == 6 and line(out, "poly_voices")["now"] == 8
    read = run(song_with(dev))
    voices = next(s for s in read["settings"] if s["name"] == "poly_voices")
    assert voices["value"] == 8 and voices["options"] == [2, 3, 4, 5, 6, 7, 8, 16]
    bad = run(song_with(dev), settings={"poly_voices": 1})
    assert "use one of" in line(bad, "poly_voices")["error"] and dev.poly_voices == 6
    assert specialized.describe(dev)["poly_voices"] == 8


def test_wavetable_selection_uses_the_devices_own_lists():
    dev = Wavetable()
    out = run(
        song_with(dev),
        settings=[
            {"setting": "osc1_wavetable", "value": "saw dual 1"},
            {"setting": "osc1_category", "value": "Vocal"},
        ],
    )
    assert dev.oscillator_1_wavetable_index == 1
    assert dev.oscillator_1_wavetable_category == 1
    assert "wavetable list changed" in line(out, "osc1_category")["note"]
    over = run(song_with(dev), settings={"unison_voice_count": 9})
    assert "2 to 8" in line(over, "unison_voice_count")["error"]


def test_set_modulation_adds_the_target_and_reads_back():
    dev = Wavetable()
    song = song_with(dev)
    out = run(
        song,
        action="set_modulation",
        args=[
            {"name": "target", "value": "osc 2 pos"},
            {"name": "source", "value": "env 2"},
            {"name": "amount", "value": 0.5},
        ],
    )
    assert out["action"]["ok"], out
    assert out["action"]["result"] == {
        "target": "Osc 2 Pos",
        "source": "Env 2",
        "amount": 0.5,
    }
    assert dev.targets[-1] == "Osc 2 Pos" and dev.cells == {(3, 1): 0.5}
    listed = run(song, action="read_modulations")["action"]["result"]
    assert listed == [{"target": "Osc 2 Pos", "source": "Env 2", "amount": 0.5}]
    run(
        song,
        action="clear_modulation",
        args={"target": "Osc 2 Pos", "source": "Env 2"},
    )
    assert run(song, action="read_modulations")["action"]["result"] == []


def test_set_modulation_refuses_what_cannot_be_modulated():
    dev = Wavetable()
    song = song_with(dev)
    for target, source, amount, needle in (
        ("Filter 1 Freq", "LFO 1", 0.2, "cannot be modulated"),
        ("Nope", "LFO 1", 0.2, "no parameter"),
        ("Osc 1 Pos", "Wobble", 0.2, "source must be"),
        ("Osc 1 Pos", "LFO 1", 2, "-1 to 1"),
    ):
        out = run(
            song,
            action="set_modulation",
            args={"target": target, "source": source, "amount": amount},
        )
        assert not out["action"]["ok"] and needle in out["action"]["error"]
    assert dev.cells == {}


# --- Drift, Meld, Spectral Resonator, Roar, Shifter ------------------------------


def test_drift_labels_come_from_the_devices_lists():
    dev = device(
        "Drift",
        voice_mode_index=0,
        voice_mode_list=["Poly", "Mono", "Stereo", "Unison"],
        voice_count_index=1,
        voice_count_list=[4, 8, 16, 24, 32],  # ints, not strings
        mod_matrix_target_1_index=0,
        mod_matrix_target_1_list=["None", "Osc 1 Gain", "LP Frequency"],
        mod_matrix_source_1_index=0,
        mod_matrix_source_1_list=["Env 1", "Env 2", "LFO"],
    )
    out = run(
        song_with(dev),
        settings=[
            {"setting": "voice_mode", "value": "Unison"},
            {"setting": "voice_count", "value": 24},
            {"setting": "mod_target_1", "value": "LP Frequency"},
            {"setting": "mod_source_1", "value": "lfo"},
        ],
    )
    assert (dev.voice_mode_index, dev.voice_count_index) == (3, 3)
    assert (dev.mod_matrix_target_1_index, dev.mod_matrix_source_1_index) == (2, 2)
    assert line(out, "voice_count")["now"] == 24


def test_meld_ranges_follow_the_probe():
    dev = device(
        "InstrumentMeld", mono_poly=1, poly_voices=2, unison_voices=0, selected_engine=0
    )
    out = run(
        song_with(dev),
        settings={"poly_voices": 7, "unison_voices": 3, "mono_poly": "mono"},
    )
    assert "1 to 6" in line(out, "poly_voices")["error"]
    assert "0 to 2" in line(out, "unison_voices")["error"]
    assert dev.mono_poly == 0 and dev.poly_voices == 2


def test_spectral_resonator_polyphony_is_an_index():
    dev = device(
        "Transmute",
        mod_mode=0,
        pitch_mode=0,
        mono_poly=1,
        midi_gate=0,
        polyphony=1,
        pitch_bend_range=5,
        frequency_dial_mode=0,
    )
    run(
        song_with(dev),
        settings={"polyphony": 16, "mod_mode": "granular", "midi_gate": "On"},
    )
    assert (dev.polyphony, dev.mod_mode, dev.midi_gate) == (3, 3, 1)


def test_shifter_without_labels_takes_numbers():
    dev = device("Shifter", pitch_bend_range=2, pitch_mode_index=0)
    out = run(song_with(dev), settings={"pitch_mode": 1, "pitch_bend_range": 12})
    assert dev.pitch_mode_index == 1 and line(out, "pitch_bend_range")["now"] == 12


def test_roar_uses_its_routing_list():
    dev = device(
        "Roar",
        routing_mode_index=0,
        routing_mode_list=["Single", "Serial", "Parallel", "Multi Band", "Mid Side"],
        env_listen=False,
    )
    run(song_with(dev), settings={"routing_mode": "multi-band", "env_listen": True})
    assert dev.routing_mode_index == 3 and dev.env_listen is True


def test_a_spec_matches_on_markers_when_the_class_name_is_different():
    dev = device("SomethingNew", global_mode=0, oversample=False)
    out = run(song_with(dev), settings={"global_mode": "M/S"})
    assert dev.global_mode == 2 and line(out, "global_mode")["now"] == "M/S"


# --- silent reverts --------------------------------------------------------------


def test_a_value_live_silently_keeps_is_reported():
    dev = Stubborn("EQ Eight", "Eq8", 1)
    dev.global_mode = 0
    dev.oversample = False
    object.__setattr__(dev, "_ignore", ("global_mode",))
    out = run(song_with(dev), settings={"global_mode": "M/S", "oversample": True})
    assert "Live kept" in line(out, "global_mode")["error"]
    assert line(out, "oversample")["now"] is True


# --- Compressor sidechain --------------------------------------------------------


class Sidechain(fake_live.Device):
    SOURCES = ["No Input", "1-Bass", "2-Drums", "Master"]

    def __init__(self):
        super().__init__("Compressor", "Compressor2", 2)
        self.available_input_routing_types = [
            SimpleNamespace(display_name=n) for n in self.SOURCES
        ]
        self._type = self.available_input_routing_types[0]
        self._refresh()

    def _refresh(self):
        # The channel choices change with the source, like Live's.
        names = (
            ["Post FX", "Pre FX"]
            if self._type.display_name != "Master"
            else ["Post Mixer"]
        )
        self.available_input_routing_channels = [
            SimpleNamespace(display_name=n) for n in names
        ]
        self._channel = self.available_input_routing_channels[0]

    @property
    def input_routing_type(self):
        return self._type

    @input_routing_type.setter
    def input_routing_type(self, value):
        self._type = value
        self._refresh()

    @property
    def input_routing_channel(self):
        return self._channel

    @input_routing_channel.setter
    def input_routing_channel(self, value):
        if value in self.available_input_routing_channels:
            self._channel = value  # an unknown one is silently ignored


def test_sidechain_source_and_channel_are_resolved_by_name():
    dev = Sidechain()
    out = run(
        song_with(dev),
        settings=[
            {"setting": "sidechain_channel", "value": "Post Mixer"},
            {"setting": "sidechain_source", "value": "Master"},
        ],
    )
    assert (
        dev._type.display_name == "Master" and dev._channel.display_name == "Post Mixer"
    )
    assert line(out, "sidechain_source")["now"] == "Master"
    assert line(out, "sidechain_channel")["now"] == "Post Mixer"


def test_sidechain_accepts_the_track_name_without_its_number():
    dev = Sidechain()
    out = run(song_with(dev), settings={"sidechain_source": "bass"})
    assert line(out, "sidechain_source")["now"] == "1-Bass"
    bad = run(song_with(dev), settings={"sidechain_source": "Vox"})
    assert "options" in line(bad, "sidechain_source")["error"]
    stale = run(song_with(dev), settings={"sidechain_channel": "Post Mixer"})
    assert "options" in line(stale, "sidechain_channel")["error"]


# --- Hybrid Reverb ---------------------------------------------------------------


def test_hybrid_reverb_category_then_file_and_the_empty_sentinel():
    dev = device(
        "Hybrid",
        ir_category_index=0,
        ir_category_list=["Halls", "Plates", "User"],
        ir_file_index=0,
        ir_file_list=["Berliner Hall LR", "Town Hall Long"],
        ir_attack_time=0.0,
        ir_decay_time=1.0,
        ir_size_factor=1.0,
        ir_time_shaping_on=False,
    )
    out = run(
        song_with(dev),
        settings=[
            {"setting": "ir_file", "value": "Town Hall Long"},
            {"setting": "ir_category", "value": "Plates"},
            {"setting": "ir_decay_time", "value": 25},
        ],
    )
    assert dev.ir_category_index == 1 and dev.ir_file_index == 1
    assert "first file" in line(out, "ir_category")["note"]
    assert "0.02 to 20" in line(out, "ir_decay_time")["error"]
    dev.ir_file_list = ["<empty>"]
    out = run(song_with(dev), settings={"ir_file": "<empty>"})
    assert "no files" in line(out, "ir_file")["error"]


# --- Looper ----------------------------------------------------------------------


def test_looper_actions_only_exist_when_the_member_does():
    plays = []
    dev = device("Looper", double_speed=lambda: plays.append("2x"), loop_length=4.0)
    out = run(song_with(dev), action="double_speed")
    assert out["action"]["ok"] and plays == ["2x"]
    out = run(song_with(dev), action="half_length")
    assert not out["action"]["ok"] and "not available" in out["action"]["error"]


# --- generic device --------------------------------------------------------------


def test_collapsing_a_device_and_the_compare_slot():
    saved = []
    dev = device(
        "Reverb",
        can_compare_ab=True,
        is_using_compare_preset_b=False,
        save_preset_to_compare_ab_slot=lambda: saved.append(1),
    )
    out = run(song_with(dev), settings={"collapsed": True}, action="compare_ab")
    assert dev.view.is_collapsed is True and line(out, "collapsed")["now"] is True
    assert out["action"]["ok"] and saved == [1]
    dev.can_compare_ab = False
    assert not run(song_with(dev), action="compare_ab")["action"]["ok"]


def test_plugin_parameter_names():
    dev = device(
        "PluginDevice",
        is_editor_open=False,
        get_parameter_names=lambda: ("Cutoff", "Gain"),
    )
    out = run(song_with(dev), action="list_plugin_parameters")
    assert out["action"]["result"] == ["Cutoff", "Gain"]
    assert specialized.describe(dev) == {"editor_open": False}


# --- racks, chains and pads ------------------------------------------------------


def volume_param():
    p = fake_live.Param("Volume", 0.85, 0.0, 1.0)
    p.str_for_value = lambda v: (
        "-inf dB" if v <= 0 else f"{40 * math.log10(v / 0.85):.1f} dB"
    )
    return p


def chain_with_mixer(name, **attrs):
    chain = fake_live.chain(name)
    chain.mixer_device = SimpleNamespace(
        volume=volume_param(),
        panning=fake_live.Param("Pan", 0.0, -1, 1, show="C"),
        sends=[],
    )
    chain.color_index = 0
    chain.is_auto_colored = True
    chain.choke_group = 0
    chain.in_note = 36
    chain.out_note = 36
    for key, value in attrs.items():
        setattr(chain, key, value)
    return chain


def drum_rack(*layers):
    kick_chains = list(layers)
    kick = SimpleNamespace(
        note=36, name="Kick", chains=kick_chains, mute=False, solo=False
    )
    snare = SimpleNamespace(
        note=38,
        name="Snare",
        chains=[chain_with_mixer("Snare")],
        mute=False,
        solo=False,
    )
    rack = fake_live.DrumRack("Kit", {36: kick, 38: snare})
    rack.has_drum_pads = True
    rack.copied = []
    rack.copy_pad = lambda src, dst: rack.copied.append((src, dst))
    return rack


def test_chain_settings_use_notes_names_and_display_units():
    chain = chain_with_mixer("Layer")
    rack = fake_live.Rack("Rack", "InstrumentGroupDevice", 1, [], [chain], [False] * 16)
    out = run(
        song_with(rack),
        "t0/d0/c0",
        settings=[
            {"setting": "color_index", "value": 12},
            {"setting": "in_note", "value": "D1"},
            {"setting": "choke_group", "value": 3},
            {"setting": "volume", "value": "-6"},
            {"setting": "name", "value": "Renamed"},
        ],
    )
    assert (chain.color_index, chain.in_note, chain.choke_group) == (12, 38, 3)
    assert line(out, "in_note")["now"] == "D1"
    assert line(out, "volume")["now"] == "-6.0 dB"
    assert chain.name == "Renamed"
    bad = run(
        song_with(rack), "t0/d0/c0", settings={"color_index": 99, "out_note": "Z9"}
    )
    assert "0 to 69" in line(bad, "color_index")["error"]
    assert "error" in line(bad, "out_note")


def test_a_pad_writes_to_every_layer_but_refuses_per_layer_settings():
    top, under = chain_with_mixer("Top"), chain_with_mixer("Under")
    song = song_with(drum_rack(top, under))
    out = run(
        song,
        "t0/d0/pC1",
        settings=[
            {"setting": "choke_group", "value": 2},
            {"setting": "mute", "value": True},
            {"setting": "volume", "value": "-6"},
        ],
    )
    assert (top.choke_group, under.choke_group) == (2, 2)
    assert line(out, "choke_group")["layers"] == 2
    assert "2 layers" in line(out, "volume")["error"]
    assert top.mixer_device.volume.value == 0.85


def test_a_pad_with_one_layer_takes_the_mixer_settings():
    only = chain_with_mixer("Only")
    out = run(song_with(drum_rack(only)), "t0/d0/pC1", settings={"volume": "-6"})
    assert line(out, "volume")["now"] == "-6.0 dB"


def test_delete_all_chains_and_copy_pad_on_a_drum_rack():
    rack = drum_rack(chain_with_mixer("Only"))
    emptied = []
    rack.drum_pads[36].delete_all_chains = lambda: emptied.append(36)
    song = song_with(rack)
    assert run(song, "t0/d0/pC1", action="delete_all_chains")["action"]["ok"]
    assert emptied == [36]
    out = run(song, action="copy_pad", args={"source": "C1", "destination": 40})
    assert out["action"]["ok"] and rack.copied == [(36, 40)]
    assert out["action"]["result"] == {"copied": "C1", "to": "E1"}


def test_copy_pad_is_refused_where_it_would_crash_live():
    rack = drum_rack(chain_with_mixer("Only"))
    rack.has_drum_pads = False  # a Drum Rack nested in a pad
    song = song_with(rack)
    out = run(song, action="copy_pad", args={"source": "C1", "destination": 40})
    assert not out["action"]["ok"] and rack.copied == []
    rack.has_drum_pads = True
    for args in (
        {"source": "C1", "destination": "C1"},
        {"source": "G5", "destination": "C1"},
    ):
        assert not run(song, action="copy_pad", args=args)["action"]["ok"]
    assert rack.copied == []


def test_insert_chain_validates_the_index():
    rack = fake_live.Rack("Rack", "InstrumentGroupDevice", 1, [], [], [False] * 16)
    rack.insert_chain = lambda index: rack.chains.insert(index, fake_live.chain("New"))
    song = song_with(rack)
    assert run(song, action="insert_chain")["action"]["result"]["chains"] == 1
    assert run(song, action="insert_chain", args={"index": 0})["action"]["ok"]
    assert not run(song, action="insert_chain", args={"index": 9})["action"]["ok"]


# --- the MCP tool ----------------------------------------------------------------


def test_tool_schema_is_described_and_has_no_any_of():
    from tonable import server
    from tonable.tools import specialized as tool_module  # noqa: F401  (registers it)

    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    tool = tools["configure_device"]
    assert len(tool.description) > 40
    assert tool.annotations is not None and tool.annotations.readOnlyHint is False
    assert "anyOf" not in str(tool.inputSchema)
    for name, prop in tool.inputSchema["properties"].items():
        assert prop.get("description"), name
    assert tool.inputSchema["required"] == ["target"]
