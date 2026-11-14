"""configure_device: the state and actions of a device that are not DeviceParameters.

Racks, Simpler, Wavetable, Compressor's sidechain, EQ Eight's mode, Hybrid Reverb's
impulse responses, a chain's choke group: Live keeps these as class-level properties
and functions. They are listed here as tables, one `Spec` per device family, and one
small engine reads, writes (with read-back) and runs the actions. Main thread only.

A spec applies to a device when its `class_name` is listed OR when the device has the
spec's marker members, so a wrong class name from memory does not hide a feature. A
member that a Live version lacks is reported as "not available", never a crash.

Where the names come from
-------------------------
Probed against Live 12.4 and written down in Producer Pal's notes
(local/producer-pal/dev/live-api/specialized-devices/): Simpler (README.md,
instruments/simpler.md), Wavetable (instruments/wavetable.md, including the
poly_voices *index* trap and the 3-argument set_modulation_value), Drift
(instruments/drift.md), Meld (instruments/meld.md), Compressor sidechain routing,
EQ Eight, Hybrid Reverb, Roar, Shifter, Spectral Resonator (audio-effects.md),
Drum Rack chains and the copy_pad crash on a rack without pads (drum-racks.md),
the Python-only members (python-remote-script-api/python-only-candidates.md:
pitch_bend_range on Simpler, the Shifter and Spectral Resonator *_list members,
PluginDevice.get_parameter_names / is_editor_open, MixerDevice routing lists).

From memory of the Live Object Model, NOT verified against a running Live:
the class names Compressor2 / Hybrid / Looper, the Looper members, the Sample child
(warping, warp_mode, gain, slicing_*, slice functions), Eq8 selected_band, Device
is_using_compare_preset_b as writable, RackDevice.insert_chain / is_showing_chains /
drum_pads_scroll_position, DrumChain color_index / is_auto_colored / choke_group /
in_note / out_note ranges, and the Meld selected_engine labels. Live silently keeps
the old value for many invalid writes, so every write is read back and a value Live
did not accept comes back as an error line.
"""

import difflib
import os
import re
from collections import namedtuple

from . import objects, params, props
from .server import CommandError
from .song import undo_step

AUDIO_EXTENSIONS = (".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg", ".m4a")
_NA = object()

# --- row types -----------------------------------------------------------------
# props.Prop is the usual row. These cover what it cannot:
#   Counted  a number from a fixed set; `indexed` rows store the position in the set
#            (Wavetable poly_voices 8 is stored as 6), not the number itself
#   Note     a MIDI note given as 0-127 or a name like C1
#   Routing  a routing object chosen by the name Live shows (sidechain source)
#   Mix      a mixer parameter of a chain, written in display units (-6 dB, 25L)
Counted = namedtuple(
    "Counted",
    "name attr values indexed list_attr readonly",
    defaults=(False, None, False),
)
Note = namedtuple("Note", "name attr")
Routing = namedtuple("Routing", "name attr options_attr")
Mix = namedtuple("Mix", "name attr index")
# child: the attribute of the device that holds the property (view, sample...).
Entry = namedtuple("Entry", "row child")
Arg = namedtuple("Arg", "name kind doc lo hi optional", defaults=(None, None, False))
# An action calls `method` on the device (or its `child`), or runs `handler`.
Act = namedtuple(
    "Act", "name args doc method handler child", defaults=(None, None, None)
)
Spec = namedtuple("Spec", "label match entries actions")


def P(name, attr, kind, child=None, **kw):
    return Entry(props.prop(name, attr, kind, **kw), child)


def C(name, attr, values, child=None, **kw):
    return Entry(Counted(name, attr, tuple(values), **kw), child)


def _by(classes=(), markers=(), truthy=()):
    """A device test: a listed class name, a marker member, or a true flag."""
    names = {c.casefold() for c in classes}

    def match(device):
        if str(props.get(device, "class_name", "")).casefold() in names:
            return True
        if any(props.get(device, m, _NA) is not _NA for m in markers):
            return True
        return any(props.get(device, t, False) for t in truthy)

    return match


# --- device tables -------------------------------------------------------------

GENERIC = Spec(
    "Device",
    lambda device: True,
    [
        P("is_active", "is_active", "bool", readonly=True),
        P("collapsed", "is_collapsed", "bool", child="view"),
        P("latency_ms", "latency_in_ms", "float", readonly=True),
        P("latency_samples", "latency_in_samples", "int", readonly=True),
        P("can_compare_ab", "can_compare_ab", "bool", readonly=True),
        P("using_preset_b", "is_using_compare_preset_b", "bool"),
    ],
    [],  # compare_ab is added below, once its handler exists
)

WARP_MODES = {
    "Beats": 0,
    "Tones": 1,
    "Texture": 2,
    "Re-Pitch": 3,
    "Complex": 4,
    "Complex Pro": 6,
}
SAMPLE = "sample"
SIMPLER = Spec(
    "Simpler",
    _by(["OriginalSimpler"], ["pad_slicing", "slicing_playback_mode"]),
    [
        P(
            "playback_mode",
            "playback_mode",
            "enum",
            choices={"Classic": 0, "One-Shot": 1, "Slicing": 2},
        ),
        P(
            "slicing_playback_mode",
            "slicing_playback_mode",
            "enum",
            choices={"Mono": 0, "Poly": 1, "Thru": 2},
        ),
        P("retrigger", "retrigger", "bool"),
        P("pad_slicing", "pad_slicing", "bool"),
        # Producer Pal: the exact UI set; in-between values silently revert.
        C("voices", "voices", (1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 20, 24, 32)),
        P("pitch_bend_range", "pitch_bend_range", "int", lo=0, hi=24),
        P("note_pitch_bend_range", "note_pitch_bend_range", "int", lo=0, hi=48),
        P("multi_sample_mode", "multi_sample_mode", "bool", readonly=True),
        P("can_warp_as", "can_warp_as", "bool", readonly=True),
        P("can_warp_double", "can_warp_double", "bool", readonly=True),
        P("can_warp_half", "can_warp_half", "bool", readonly=True),
        P("sample_file", "file_path", "str", child=SAMPLE, readonly=True),
        P("sample_warping", "warping", "bool", child=SAMPLE),
        P("sample_warp_mode", "warp_mode", "enum", child=SAMPLE, choices=WARP_MODES),
        P("sample_gain", "gain", "float", child=SAMPLE, lo=0.0, hi=1.0),
        P(
            "sample_slicing_style",
            "slicing_style",
            "enum",
            child=SAMPLE,
            choices={"Transient": 0, "Beat": 1, "Region": 2, "Manual": 3},
        ),
        P(
            "sample_slicing_sensitivity",
            "slicing_sensitivity",
            "float",
            child=SAMPLE,
            lo=0.0,
            hi=1.0,
        ),
        P("sample_slicing_beat_division", "slicing_beat_division", "int", child=SAMPLE),
        P("sample_slicing_region_count", "slicing_region_count", "int", child=SAMPLE),
        P("sample_slices", "slices", "str", child=SAMPLE, readonly=True),
    ],
    [],
)

OSC_ENGINES = {"None": 0, "FM": 1, "Classic": 2, "Modern": 3}
MOD_SOURCES = (
    "Amp",
    "Env 2",
    "Env 3",
    "LFO 1",
    "LFO 2",
    "Vel",
    "Key",
    "PB",
    "Press",
    "Mod",
    "Rand",
    "Note PB",
    "Slide",
)
WAVETABLE = Spec(
    "Wavetable",
    _by(["InstrumentVector"], ["oscillator_1_wavetable_index"]),
    [
        P(
            "filter_routing",
            "filter_routing",
            "enum",
            choices={"Serial": 0, "Parallel": 1, "Split": 2},
        ),
        P("mono_poly", "mono_poly", "enum", choices={"Mono": 0, "Poly": 1}),
        # Index into [2,3,4,5,6,7,8,16], not the count (Producer Pal, 12.4).
        C("poly_voices", "poly_voices", (2, 3, 4, 5, 6, 7, 8, 16), indexed=True),
        P(
            "unison_mode",
            "unison_mode",
            "enum",
            choices={
                "None": 0,
                "Classic": 1,
                "Shimmer": 2,
                "Noise": 3,
                "Phase Sync": 4,
                "Position Spread": 5,
                "Random Note": 6,
            },
        ),
        P("unison_voice_count", "unison_voice_count", "int", lo=2, hi=8),
        P("osc1_engine", "oscillator_1_effect_mode", "enum", choices=OSC_ENGINES),
        P("osc2_engine", "oscillator_2_effect_mode", "enum", choices=OSC_ENGINES),
        # Category first: it refills the wavetable list the next two index into.
        P(
            "osc1_category",
            "oscillator_1_wavetable_category",
            "enum",
            choices_attr="oscillator_wavetable_categories",
        ),
        P(
            "osc1_wavetable",
            "oscillator_1_wavetable_index",
            "enum",
            choices_attr="oscillator_1_wavetables",
        ),
        P(
            "osc2_category",
            "oscillator_2_wavetable_category",
            "enum",
            choices_attr="oscillator_wavetable_categories",
        ),
        P(
            "osc2_wavetable",
            "oscillator_2_wavetable_index",
            "enum",
            choices_attr="oscillator_2_wavetables",
        ),
    ],
    [],
)

DRIFT_SOURCES = ("Env 1", "Env 2", "LFO", "Key", "Vel", "Mod", "Press", "Slide")
DRIFT_TARGETS = (
    "None",
    "Osc 1 Gain",
    "Osc 1 Shape",
    "Osc 2 Gain",
    "Osc 2 Detune",
    "Noise Gain",
    "LP Frequency",
    "LP Resonance",
    "HP Frequency",
    "LFO Rate",
    "Cyc Env Rate",
    "Main Volume",
)


def _drift(name, middle, labels):
    attr = f"mod_matrix_{middle}"
    return P(
        name,
        attr + "_index",
        "enum",
        choices={label: i for i, label in enumerate(labels)},
        choices_attr=attr + "_list",
    )


DRIFT = Spec(
    "Drift",
    _by(["Drift"], ["voice_mode_index"]),
    [
        P(
            "voice_mode",
            "voice_mode_index",
            "enum",
            choices={"Poly": 0, "Mono": 1, "Stereo": 2, "Unison": 3},
            choices_attr="voice_mode_list",
        ),
        C(
            "voice_count",
            "voice_count_index",
            (4, 8, 16, 24, 32),
            indexed=True,
            list_attr="voice_count_list",
        ),
        P("pitch_bend_range", "pitch_bend_range", "int", lo=0, hi=48),
        _drift("filter_source_1", "filter_source_1", DRIFT_SOURCES),
        _drift("filter_source_2", "filter_source_2", DRIFT_SOURCES),
        _drift("lfo_source", "lfo_source", DRIFT_SOURCES),
        _drift("pitch_source_1", "pitch_source_1", DRIFT_SOURCES),
        _drift("pitch_source_2", "pitch_source_2", DRIFT_SOURCES),
        _drift("shape_source", "shape_source", DRIFT_SOURCES),
        _drift("mod_source_1", "source_1", DRIFT_SOURCES),
        _drift("mod_target_1", "target_1", DRIFT_TARGETS),
        _drift("mod_source_2", "source_2", DRIFT_SOURCES),
        _drift("mod_target_2", "target_2", DRIFT_TARGETS),
        _drift("mod_source_3", "source_3", DRIFT_SOURCES),
        _drift("mod_target_3", "target_3", DRIFT_TARGETS),
    ],
    [],
)

MONO_POLY = {"Mono": 0, "Poly": 1}
MELD = Spec(
    "Meld",
    _by(["InstrumentMeld"], ["unison_voices"]),
    [
        P("mono_poly", "mono_poly", "enum", choices=MONO_POLY),
        P("poly_voices", "poly_voices", "int", lo=1, hi=6),
        P("unison_voices", "unison_voices", "int", lo=0, hi=2),
        P("selected_engine", "selected_engine", "enum", choices={"A": 0, "B": 1}),
    ],
    [],
)

COMPRESSOR = Spec(
    "Compressor",
    _by(["Compressor2", "Compressor"], ["available_input_routing_types"]),
    [
        # The source first: the channel choices depend on it.
        Entry(
            Routing(
                "sidechain_source",
                "input_routing_type",
                "available_input_routing_types",
            ),
            None,
        ),
        Entry(
            Routing(
                "sidechain_channel",
                "input_routing_channel",
                "available_input_routing_channels",
            ),
            None,
        ),
    ],
    [],
)

EQ8 = Spec(
    "EQ Eight",
    _by(["Eq8"], ["global_mode"]),
    [
        P(
            "global_mode",
            "global_mode",
            "enum",
            choices={"Stereo": 0, "L/R": 1, "M/S": 2},
        ),
        P("oversample", "oversample", "bool"),
        P("edit_mode", "edit_mode", "enum", choices={"A": 0, "B": 1}),
        P("selected_band", "selected_band", "int", lo=0, hi=7),
    ],
    [],
)

HYBRID_REVERB = Spec(
    "Hybrid Reverb",
    _by(["Hybrid", "HybridReverb"], ["ir_category_index"]),
    [
        # Category first: choosing one resets the file to the category's first.
        P(
            "ir_category",
            "ir_category_index",
            "enum",
            choices_attr="ir_category_list",
        ),
        P("ir_file", "ir_file_index", "enum", choices_attr="ir_file_list"),
        P("ir_attack_time", "ir_attack_time", "float", lo=0.0, hi=3.0),
        P("ir_decay_time", "ir_decay_time", "float", lo=0.02, hi=20.0),
        P("ir_size_factor", "ir_size_factor", "float", lo=0.2, hi=5.0),
        P("ir_time_shaping_on", "ir_time_shaping_on", "bool"),
    ],
    [],
)

ROAR_MODES = (
    "Single",
    "Serial",
    "Parallel",
    "Multi Band",
    "Mid Side",
    "Feedback",
    "Delay",
)
ROAR = Spec(
    "Roar",
    _by(["Roar"], ["routing_mode_index"]),
    [
        P(
            "routing_mode",
            "routing_mode_index",
            "enum",
            choices={m: i for i, m in enumerate(ROAR_MODES)},
            choices_attr="routing_mode_list",
        ),
        P("env_listen", "env_listen", "bool"),
    ],
    [],
)

SHIFTER = Spec(
    "Shifter",
    _by(["Shifter"], ["pitch_mode_index"]),
    [
        P("pitch_bend_range", "pitch_bend_range", "int", lo=0, hi=48),
        # No fixed labels are known; the device lists them, or give the number.
        P("pitch_mode", "pitch_mode_index", "enum", choices_attr="pitch_mode_list"),
    ],
    [],
)

SPECTRAL_RESONATOR = Spec(
    "Spectral Resonator",
    _by(["Transmute"], ["frequency_dial_mode", "mod_mode"]),
    [
        P(
            "mod_mode",
            "mod_mode",
            "enum",
            choices={"None": 0, "Chorus": 1, "Wander": 2, "Granular": 3},
            choices_attr="mod_mode_list",
        ),
        P(
            "pitch_mode",
            "pitch_mode",
            "enum",
            choices={"Hertz": 0, "MIDI Note": 1},
            choices_attr="pitch_mode_list",
        ),
        P(
            "mono_poly",
            "mono_poly",
            "enum",
            choices=MONO_POLY,
            choices_attr="mono_poly_list",
        ),
        P(
            "midi_gate",
            "midi_gate",
            "enum",
            choices={"Off": 0, "On": 1},
            choices_attr="midi_gate_list",
        ),
        # Index into [2,4,8,16], like Wavetable's poly_voices.
        C("polyphony", "polyphony", (2, 4, 8, 16), indexed=True),
        P("pitch_bend_range", "pitch_bend_range", "int", lo=0, hi=24),
        P(
            "frequency_dial_mode",
            "frequency_dial_mode",
            "enum",
            choices={"Hz": 0, "Note": 1},
            choices_attr="frequency_dial_mode_list",
        ),
    ],
    [],
)

LOOPER = Spec(
    "Looper",
    _by(["Looper"], ["double_speed", "export_to_arrangement"]),
    [
        P("loop_length", "loop_length", "float", readonly=True),
        P("tempo", "tempo", "float", readonly=True),
        P("overdub_after_record", "overdub_after_record", "bool"),
        P(
            "record_length",
            "record_length_index",
            "enum",
            choices_attr="record_length_list",
        ),
    ],
    [
        Act(n, (), d, method=n)
        for n, d in (
            ("record", "Start recording."),
            ("overdub", "Start overdubbing."),
            ("play", "Play the loop."),
            ("stop", "Stop the loop."),
            ("clear", "Erase the loop."),
            ("undo", "Undo the last overdub."),
            ("double_speed", "Play twice as fast."),
            ("half_speed", "Play at half speed."),
            ("double_length", "Double the loop length."),
            ("half_length", "Halve the loop length."),
            ("export_to_arrangement", "Render the loop into the Arrangement."),
        )
    ],
)

PLUGIN = Spec(
    "Plug-in",
    _by([], ["get_parameter_names", "is_editor_open"]),
    [P("editor_open", "is_editor_open", "bool", readonly=True)],
    [
        Act(
            "list_plugin_parameters",
            (),
            "Every parameter name the plug-in has, including ones Live hides.",
            method="get_parameter_names",
        )
    ],
)

RACK = Spec(
    "Rack",
    _by([], [], ["can_have_chains"]),
    [
        P("is_showing_chains", "is_showing_chains", "bool"),
        P("can_show_chains", "can_show_chains", "bool", readonly=True),
        P("variation_count", "variation_count", "int", readonly=True),
        P("has_macro_mappings", "has_macro_mappings", "bool", readonly=True),
        P("drum_pads_scroll_position", "drum_pads_scroll_position", "int", lo=0),
        P("visible_drum_pads", "visible_drum_pads", "int", readonly=True),
    ],
    [],
)

# Chains, and the pads of a Drum Rack (which write to every chain stacked on them).
CHAIN = [
    P("name", "name", "str"),
    P("color_index", "color_index", "int", lo=0, hi=69),
    P("is_auto_colored", "is_auto_colored", "bool"),
    P("mute", "mute", "bool"),
    P("solo", "solo", "bool"),
    P("choke_group", "choke_group", "int", lo=0, hi=16),
    Entry(Note("in_note", "in_note"), None),
    Entry(Note("out_note", "out_note"), None),
]
PAD_SELF = ("mute", "solo")
PAD_BROADCAST = ("choke_group", "out_note", "color_index", "is_auto_colored")

# Notes appended to a setting's result.
NOTES = {
    "ir_category": "the IR file went back to the first file of the category",
    "osc1_category": "the wavetable list changed; pick osc1_wavetable again",
    "osc2_category": "the wavetable list changed; pick osc2_wavetable again",
}

SPECS = (
    SIMPLER,
    WAVETABLE,
    DRIFT,
    MELD,
    COMPRESSOR,
    EQ8,
    HYBRID_REVERB,
    ROAR,
    SHIFTER,
    SPECTRAL_RESONATOR,
    LOOPER,
    PLUGIN,
    RACK,
)


# --- action handlers -----------------------------------------------------------


def _json(value):
    """Plain JSON for whatever Live returns."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    try:
        return [_json(v) for v in value]
    except TypeError:
        return str(value)


def _whole(number):
    """Live's functions are typed: a whole number goes as an int."""
    return int(number) if float(number) == int(number) else float(number)


def _find_name(names, wanted):
    wanted = str(wanted).strip().casefold()
    for i, name in enumerate(names):
        if str(name).strip().casefold() == wanted:
            return i
    return None


def _compare_ab(device, args):
    if not props.get(device, "can_compare_ab", False):
        raise CommandError("not_supported", "this device has no A/B compare slot")
    device.save_preset_to_compare_ab_slot()
    return {"using_preset_b": bool(props.get(device, "is_using_compare_preset_b"))}


def _replace_sample(device, args):
    if props.get(device, "multi_sample_mode", False):
        raise CommandError(
            "not_supported", "this Simpler hosts a multi-sample preset: load a new one"
        )
    device.replace_sample(args["path"])
    sample = props.get(device, SAMPLE)
    return {"sample_file": props.get(sample, "file_path") if sample else None}


def _slice(name, *arg_names):
    """Sample-level slice function; times are in sample frames."""

    def run(device, args):
        sample = props.get(device, SAMPLE)
        method = props.get(sample, name) if sample is not None else None
        if not callable(method):
            raise CommandError("not_supported", f"this Simpler has no sample {name}")
        method(*[_whole(args[a]) for a in arg_names])
        return {"slices": _json(props.get(sample, "slices", []))}

    return run


def _targets(device):
    names_of = props.get(device, "get_modulation_target_parameter_name")
    if not callable(names_of):
        raise CommandError("not_supported", "this device has no modulation matrix")
    names = []
    for i in range(64):
        name = names_of(i)
        if not isinstance(name, str):  # Live answers the int 1 past the last row
            break
        names.append(name)
    return names


def _modulation_target(device, name):
    """The matrix row of a parameter, adding it when it is not there yet."""
    names = _targets(device)
    row = _find_name(names, name)
    if row is not None:
        return row, names
    hits = [p for p in device.parameters if p.name.casefold() == name.casefold()]
    if not hits:
        raise CommandError("not_found", f"{device.name} has no parameter {name!r}")
    check = props.get(device, "is_parameter_modulatable")
    if callable(check) and not check(hits[0]):
        raise CommandError("bad_value", f"{hits[0].name} cannot be modulated")
    device.add_parameter_to_modulation_matrix(hits[0])
    names = _targets(device)
    row = _find_name(names, hits[0].name)
    if row is None:
        raise CommandError("not_supported", f"Live did not add {hits[0].name}")
    return row, names


def _modulation_source(name):
    source = _find_name(MOD_SOURCES, name)
    if source is None:
        raise CommandError(
            "bad_value", f"source must be one of: {', '.join(MOD_SOURCES)}"
        )
    return source


def _set_modulation(device, args, amount=None):
    amount = args["amount"] if amount is None else amount
    if not -1.0 <= float(amount) <= 1.0:
        raise CommandError("bad_value", "amount must be -1 to 1")
    source = _modulation_source(args["source"])
    row, names = _modulation_target(device, args["target"])
    device.set_modulation_value(row, source, float(amount))
    return {
        "target": names[row],
        "source": MOD_SOURCES[source],
        "amount": device.get_modulation_value(row, source),
    }


def _add_modulation_target(device, args):
    row, names = _modulation_target(device, args["target"])
    return {"target": names[row]}


def _read_modulations(device, args):
    out = []
    for row, name in enumerate(_targets(device)):
        for source, label in enumerate(MOD_SOURCES):
            amount = device.get_modulation_value(row, source)
            if type(amount) is int:  # 0 is no modulation, 1 is Live's "no such cell"
                continue
            if amount:
                out.append({"target": name, "source": label, "amount": amount})
    return out


def _copy_pad(device, args):
    # Live crashes on a Drum Rack that has no pads (one nested in a pad).
    if not props.get(device, "can_have_drum_pads", False) or not props.get(
        device, "has_drum_pads", False
    ):
        raise CommandError(
            "not_supported", "copy_pad needs a Drum Rack with pads (not a nested one)"
        )
    source, target = args["source"], args["destination"]
    if source == target:
        raise CommandError("bad_value", "source and destination are the same pad")
    pads = {pad.note: pad for pad in device.drum_pads}
    if source not in pads or not list(pads[source].chains):
        raise CommandError("not_found", f"pad {objects.note_name(source)} is empty")
    device.copy_pad(source, target)
    return {"copied": objects.note_name(source), "to": objects.note_name(target)}


def _insert_chain(device, args):
    insert = props.get(device, "insert_chain")
    if not callable(insert):
        raise CommandError("not_supported", "this Live cannot insert chains")
    before = len(list(device.chains))
    index = args.get("index", before)
    if not 0 <= index <= before:
        raise CommandError("bad_value", f"index must be 0 to {before}")
    insert(index)
    return {"chains": len(list(device.chains)), "inserted_at": index}


def _method(name, *arg_names):
    def run(device, args):
        method = props.get(device, name)
        if not callable(method):
            raise CommandError("not_supported", f"not available in this Live: {name}")
        return method(*[args[a] for a in arg_names if a in args])

    return run


GENERIC.actions.append(
    Act(
        "compare_ab",
        (),
        "Save the current preset into the A/B compare slot.",
        handler=_compare_ab,
    )
)
SIMPLER.actions.extend(
    [
        Act("reverse", (), "Reverse the sample (destructive).", method="reverse"),
        Act("crop", (), "Trim the sample to its markers (destructive).", method="crop"),
        Act("warp_double", (), "Double the warp tempo.", method="warp_double"),
        Act("warp_half", (), "Halve the warp tempo.", method="warp_half"),
        Act(
            "warp_as",
            (Arg("beats", "float", "Beats the marked region should span", lo=0),),
            "Warp the marked region to span a number of beats.",
            method="warp_as",
        ),
        Act(
            "estimate_length",
            (),
            "Beats the sample probably spans, from its transients.",
            method="guess_playback_length",
        ),
        Act(
            "replace_sample",
            (Arg("path", "path", "Audio file (wav, aif, flac, mp3, ogg, m4a)"),),
            "Load another sample into this Simpler.",
            handler=_replace_sample,
        ),
        Act(
            "insert_slice",
            (Arg("time", "float", "Slice position in sample frames", lo=0),),
            "Add a slice marker.",
            handler=_slice("insert_slice", "time"),
        ),
        Act(
            "move_slice",
            (
                Arg("from_time", "float", "Slice position now, in sample frames", lo=0),
                Arg("to_time", "float", "New position, in sample frames", lo=0),
            ),
            "Move a slice marker.",
            handler=_slice("move_slice", "from_time", "to_time"),
        ),
        Act(
            "remove_slice",
            (Arg("time", "float", "Slice position in sample frames", lo=0),),
            "Remove a slice marker.",
            handler=_slice("remove_slice", "time"),
        ),
        Act("clear_slices", (), "Remove every slice.", handler=_slice("clear_slices")),
        Act(
            "reset_slices",
            (),
            "Back to the automatic slices.",
            handler=_slice("reset_slices"),
        ),
    ]
)
WAVETABLE.actions.extend(
    [
        Act(
            "set_modulation",
            (
                Arg("target", "str", "Parameter name, e.g. Osc 1 Pos"),
                Arg("source", "str", "One of: " + ", ".join(MOD_SOURCES)),
                Arg("amount", "float", "Amount from -1 to 1", lo=-1, hi=1),
            ),
            "Set one cell of the modulation matrix (the target is added if needed).",
            handler=_set_modulation,
        ),
        Act(
            "clear_modulation",
            (
                Arg("target", "str", "Parameter name, e.g. Osc 1 Pos"),
                Arg("source", "str", "One of: " + ", ".join(MOD_SOURCES)),
            ),
            "Set one modulation cell to 0.",
            handler=lambda device, args: _set_modulation(device, args, 0.0),
        ),
        Act(
            "add_modulation_target",
            (Arg("target", "str", "Parameter name to add as a matrix row"),),
            "Add a parameter to the modulation matrix without setting an amount.",
            handler=_add_modulation_target,
        ),
        Act(
            "read_modulations",
            (),
            "Every non-zero cell of the modulation matrix.",
            handler=_read_modulations,
        ),
    ]
)
RACK.actions.extend(
    [
        Act(
            "insert_chain",
            (
                Arg(
                    "index",
                    "int",
                    "Position from 0; default: at the end",
                    lo=0,
                    optional=True,
                ),
            ),
            "Add an empty chain to the rack.",
            handler=_insert_chain,
        ),
        Act(
            "randomize_macros",
            (),
            "Randomize the macro knobs.",
            handler=_method("randomize_macros"),
        ),
        Act(
            "delete_selected_variation",
            (),
            "Delete the selected macro variation.",
            handler=_method("delete_selected_variation"),
        ),
        Act(
            "recall_last_used_variation",
            (),
            "Recall the last used macro variation.",
            handler=_method("recall_last_used_variation"),
        ),
        Act(
            "copy_pad",
            (
                Arg("source", "note", "Pad to copy, a note like C1 or 36"),
                Arg("destination", "note", "Pad to copy it onto"),
            ),
            "Copy a Drum Rack pad's chains onto another pad.",
            handler=_copy_pad,
        ),
    ]
)
PAD_ACTIONS = [
    Act(
        "delete_all_chains",
        (),
        "Empty the pad (its slot stays).",
        method="delete_all_chains",
    )
]


# --- slots: the settings of one target -----------------------------------------
# A slot is a named setting bound to the objects it writes (a pad writes to every
# chain stacked on it). `single` slots refuse a pad with several layers.


def _is_prop(row):
    """A plain props row. Tested by elimination, not isinstance(row, props.Prop):
    the dispatcher reloads props, which would make rows built earlier look foreign."""
    return not isinstance(row, (Counted, Note, Routing, Mix))


Slot = namedtuple("Slot", "name entry targets single")


def _slots(kind, obj):
    if kind == "device":
        entries = list(GENERIC.entries)
        for spec in SPECS:
            if spec.match(obj):
                entries.extend(spec.entries)
        return [Slot(e.row.name, e, [obj], False) for e in entries]
    if kind == "chain":
        entries = CHAIN + _mixer_entries(obj)
        return [Slot(e.row.name, e, [obj], False) for e in entries]
    chains = list(props.get(obj, "chains", []) or [])
    out = [Slot(e.row.name, e, [obj], False) for e in CHAIN if e.row.name in PAD_SELF]
    if chains:
        for e in CHAIN:
            if e.row.name in PAD_BROADCAST:
                out.append(Slot(e.row.name, e, chains, False))
        for e in [CHAIN[0]] + _mixer_entries(chains[0]):
            out.append(Slot(e.row.name, e, chains, True))
    return out


def _mixer_entries(chain):
    mixer = props.get(chain, "mixer_device")
    if mixer is None:
        return []
    out = [
        Entry(Mix("volume", "volume", None), "mixer_device"),
        Entry(Mix("pan", "panning", None), "mixer_device"),
    ]
    for i in range(len(list(props.get(mixer, "sends", []) or []))):
        letter = objects.return_letter(i).lower()
        out.append(Entry(Mix(f"send_{letter}", "sends", i), "mixer_device"))
    return out


def _actions(kind, obj):
    if kind == "pad":
        return list(PAD_ACTIONS)
    if kind != "device":
        return []
    out = list(GENERIC.actions)
    for spec in SPECS:
        if spec.match(obj):
            out.extend(spec.actions)
    return out


# --- reading a setting ----------------------------------------------------------


def _object_of(obj, entry):
    return obj if entry.child is None else props.get(obj, entry.child)


def _label(option):
    return str(props.get(option, "display_name", option))


def _param_of(mixer, row):
    target = props.get(mixer, row.attr)
    if row.index is not None:
        sends = list(target or [])
        return sends[row.index] if row.index < len(sends) else None
    return target


def _counts(obj, row):
    listed = props.get(obj, row.list_attr) if row.list_attr else None
    if listed:
        try:
            return [int(float(x)) for x in listed]
        except (TypeError, ValueError):
            pass
    return list(row.values)


def read_slot(slot):
    """The value of a slot, or _NA when this Live object does not have it."""
    entry, row = slot.entry, slot.entry.row
    obj = _object_of(slot.targets[0], entry)
    if obj is None:
        return _NA
    if _is_prop(row):
        raw = props.get(obj, row.attr)
        if raw is None:
            return _NA
        return _json(props.shown(obj, row, raw))
    if isinstance(row, Mix):
        param = _param_of(obj, row)
        return _NA if param is None else params.display(param)
    raw = props.get(obj, row.attr)
    if raw is None:
        return _NA
    if isinstance(row, Counted):
        values = _counts(obj, row)
        return values[raw] if row.indexed and 0 <= raw < len(values) else raw
    if isinstance(row, Note):
        return objects.note_name(raw) if 0 <= raw <= 127 else raw
    return _label(raw)  # Routing


# --- writing a setting ----------------------------------------------------------


def _error(name, text):
    return {"field": name, "error": text}


def _check(obj, attr, raw, name, shown, same=None):
    """Write `raw`, read it back, say what Live holds."""
    try:
        setattr(obj, attr, raw)
    except Exception as err:
        return _error(name, props._why(err))
    now = props.get(obj, attr, raw)
    if same(now) if same else now == raw:
        return {"field": name, "now": shown(now)}
    return _error(name, f"Live kept {shown(now)!r} and did not accept the value")


def write_one(obj, entry, requested):
    """One result line for writing `requested` to a setting of `obj`."""
    row = entry.row
    name = row.name
    obj = _object_of(obj, entry)
    if obj is None:
        return _error(name, "not available in this Live")
    if getattr(row, "readonly", False):
        return _error(name, "read-only")
    if props.get(obj, getattr(row, "attr", ""), _NA) is _NA and not isinstance(
        row, Mix
    ):
        return _error(name, "not available in this Live")
    try:
        if _is_prop(row):
            if row.kind == "enum" and [
                label for label, _ in props.choices(obj, row)
            ] == ["<empty>"]:
                return _error(name, "there are no files in this category")
            out = props.write_one(obj, row, requested)
            if "now" in out and name in NOTES and "error" not in out:
                out["note"] = NOTES[name]
            return out
        if isinstance(row, Counted):
            return _write_counted(obj, row, requested)
        if isinstance(row, Note):
            return _write_note(obj, row, requested)
        if isinstance(row, Mix):
            return _write_mix(obj, row, requested)
        return _write_routing(obj, row, requested)
    except CommandError as err:
        return _error(name, str(err))


def _write_counted(obj, row, requested):
    values = _counts(obj, row)
    try:
        number = float(requested)
        ok = number == int(number)
    except (TypeError, ValueError, OverflowError):
        ok = False
    if not ok or int(number) not in values:
        raise CommandError("bad_value", f"use one of: {', '.join(map(str, values))}")
    raw = values.index(int(number)) if row.indexed else int(number)

    def shown(now):
        return values[now] if row.indexed and 0 <= now < len(values) else now

    return _check(obj, row.attr, raw, row.name, shown)


def _write_note(obj, row, requested):
    text = str(requested).strip()
    number = int(text) if re.fullmatch(r"-?\d+", text) else objects.note_number(text)
    if not 0 <= number <= 127:
        raise CommandError("bad_value", "a note is 0-127 or a name like C1")
    return _check(
        obj,
        row.attr,
        number,
        row.name,
        lambda now: objects.note_name(now) if 0 <= now <= 127 else now,
    )


def _write_routing(obj, row, requested):
    options = list(props.get(obj, row.options_attr, []) or [])
    labels = [_label(o) for o in options]
    if not options:
        raise CommandError("not_found", f"Live offers no {row.name} choices right now")
    want = str(requested).strip().casefold()
    hits = [
        o for o, label in zip(options, labels, strict=False) if label.casefold() == want
    ]
    if not hits:  # "Bass" for a routing shown as "1-Bass"
        hits = [
            o
            for o, label in zip(options, labels, strict=False)
            if label.split("-", 1)[-1].strip().casefold() == want
        ]
    if len(hits) != 1:
        what = "no" if not hits else "several"
        raise CommandError(
            "not_found", f"{what} {row.name} {requested!r}; options: {labels}"
        )
    wanted = _label(hits[0])
    return _check(
        obj, row.attr, hits[0], row.name, _label, same=lambda n: _label(n) == wanted
    )


def _write_mix(mixer, row, requested):
    param = _param_of(mixer, row)
    if param is None:
        raise CommandError("not_found", "this chain has no such mixer control")
    text = str(requested).strip()
    if row.name == "pan":
        text = _pan(text)
    else:
        text = "-inf dB" if text.lower() in ("-inf", "off") else _db(text)
    raw, note = params.value_for(param, text)
    try:
        param.value = raw
    except Exception as err:
        return _error(row.name, props._why(err))
    out = {"field": row.name, "now": params.display(param)}
    if note:
        out["note"] = note
    return out


def _db(text):
    return text if text.lower().endswith("db") else text + " dB"


def _pan(text):
    if re.fullmatch(r"[+-]?\d+(\.\d*)?", text):
        number = float(text)
        return "C" if number == 0 else f"{abs(number):g}{'L' if number < 0 else 'R'}"
    return text


def write_slot(slot, requested):
    if slot.single and len(slot.targets) > 1:
        return _error(
            slot.name,
            f"this pad has {len(slot.targets)} layers: address one, e.g. pC1/c0",
        )
    results = [write_one(target, slot.entry, requested) for target in slot.targets]
    first_error = next((r for r in results if "error" in r), None)
    if first_error:
        return first_error
    out = results[0]
    if len(results) > 1:
        out["layers"] = len(results)
    return out


# --- actions ---------------------------------------------------------------------


def _arg_value(arg, raw):
    kind = arg.kind
    if kind == "str":
        return str(raw)
    if kind == "note":
        text = str(raw).strip()
        number = (
            int(text) if re.fullmatch(r"-?\d+", text) else objects.note_number(text)
        )
        if not 0 <= number <= 127:
            raise CommandError("bad_value", f"{arg.name}: a note is 0-127 or a name")
        return number
    if kind == "path":
        return _audio_path(raw)
    try:
        number = float(raw)
    except (TypeError, ValueError):
        raise CommandError("bad_value", f"{arg.name} must be a number") from None
    if number != number or number in (float("inf"), float("-inf")):
        raise CommandError("bad_value", f"{arg.name} must be finite")
    if arg.lo is not None and number < arg.lo or arg.hi is not None and number > arg.hi:
        raise CommandError("bad_value", f"{arg.name} must be {_span(arg)}")
    if kind == "int":
        if number != int(number):
            raise CommandError("bad_value", f"{arg.name} must be a whole number")
        return int(number)
    return _whole(number)


def _span(arg):
    lo = "" if arg.lo is None else f"{arg.lo:g}"
    hi = "" if arg.hi is None else f"{arg.hi:g}"
    return f"{lo or '-inf'} to {hi or 'inf'}"


def _audio_path(raw):
    path = os.path.realpath(os.path.expanduser(str(raw).strip()))
    if os.path.splitext(path)[1].lower() not in AUDIO_EXTENSIONS:
        raise CommandError(
            "bad_value", "path must be an audio file: " + ", ".join(AUDIO_EXTENSIONS)
        )
    if not os.path.isfile(path):
        raise CommandError("not_found", f"no file at {path}")
    return path


def _arg_pairs(raw):
    """{name: value} from [{name, value}], [{name: value}] or {name: value}."""
    if raw in (None, "", []):
        return {}
    items = [raw] if isinstance(raw, dict) else raw
    out = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        if "name" in item and "value" in item:
            out[_norm(item["name"])] = item["value"]
        else:
            out.update({_norm(k): v for k, v in item.items()})
    return out


def _parse_args(act, raw):
    given = _arg_pairs(raw)
    unknown = [k for k in given if k not in {a.name for a in act.args}]
    if unknown:
        names = ", ".join(a.name for a in act.args) or "none"
        raise CommandError("bad_params", f"{act.name} takes: {names}; not {unknown}")
    args = {}
    for arg in act.args:
        if given.get(arg.name) in (None, ""):
            if arg.optional:
                continue
            raise CommandError("bad_params", f"{act.name} needs {arg.name}: {arg.doc}")
        args[arg.name] = _arg_value(arg, given[arg.name])
    return args


def run_action(obj, acts, name, raw_args):
    wanted = _norm(name)
    act = next((a for a in acts if a.name == wanted), None)
    if act is None:
        have = [a.name for a in acts]
        return {
            "action": name,
            "ok": False,
            "error": f"no such action; actions: {have}",
        }
    try:
        args = _parse_args(act, raw_args)
        if act.handler is not None:
            result = act.handler(obj, args)
        else:
            target = obj if act.child is None else props.get(obj, act.child)
            method = props.get(target, act.method) if target is not None else None
            if not callable(method):
                raise CommandError(
                    "not_supported", f"{act.method} is not available in this Live"
                )
            result = method(*[args[a.name] for a in act.args if a.name in args])
    except CommandError as err:
        return {"action": act.name, "ok": False, "error": str(err)}
    except Exception as err:
        return {"action": act.name, "ok": False, "error": props._why(err)}
    out = {"action": act.name, "ok": True}
    if result is not None:
        out["result"] = _json(result)
    return out


# --- the command -------------------------------------------------------------------


def _norm(name):
    """gain, Gain, sample gain and sampleGain all name sample_gain."""
    text = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", str(name).strip())
    return re.sub(r"[\s\-./]+", "_", text).lower()


def _pairs(raw):
    """[(setting, value)] from [{setting, value}], {name: value} or a list of those."""
    if raw in (None, "", []):
        return []
    out = []
    for item in [raw] if isinstance(raw, dict) else raw:
        if not isinstance(item, dict):
            continue
        key = next(
            (k for k in ("setting", "name", "param", "field") if k in item), None
        )
        if key and "value" in item:
            out.append((item[key], item["value"]))
        else:
            out.extend(item.items())
    return out


def configure_device(song, p):
    """Read what a device offers, set class-level settings, run one action."""
    kind, obj, path = objects.resolve(song, p.get("target") or "")
    if kind == "track":
        raise CommandError(
            "bad_target",
            f"{path} is a track: use update_track, or {path}/d0 for a device",
        )
    pairs = _pairs(p.get("settings"))
    action = str(p.get("action") or "").strip()
    slots, acts = _slots(kind, obj), _actions(kind, obj)
    head = {"target": path, "kind": kind, "name": obj.name}
    if kind == "device":
        head["class"] = props.get(obj, "class_name", "")
    if not pairs and not action:
        return {**head, **_help(slots, acts)}
    by_name = {s.name: s for s in slots}
    wanted, results = {}, []
    for name, value in pairs:
        slot = by_name.get(_norm(name))
        if slot is None:
            similar = difflib.get_close_matches(_norm(name), list(by_name))
            results.append(
                {"field": str(name), "error": "no such setting", "similar": similar}
            )
        else:
            wanted[slot.name] = value
    with undo_step(song):
        for slot in slots:  # table order: a category before its file
            if slot.name in wanted:
                results.append(write_slot(slot, wanted[slot.name]))
        out = {**head, "results": results}
        if action:
            out["action"] = run_action(obj, acts, action, p.get("args"))
    return out


def _help(slots, acts):
    settings, missing = [], []
    for slot in slots:
        value = read_slot(slot)
        if value is _NA:
            missing.append(slot.name)
            continue
        settings.append(_describe_slot(slot, value))
    return {
        "settings": settings,
        "not_available": missing,
        "actions": [
            {
                "name": a.name,
                "doc": a.doc,
                "args": [
                    {
                        "name": g.name,
                        "kind": g.kind,
                        "doc": g.doc,
                        "optional": g.optional,
                    }
                    for g in a.args
                ],
            }
            for a in acts
        ],
    }


def _describe_slot(slot, value):
    row = slot.entry.row
    obj = _object_of(slot.targets[0], slot.entry)
    line = {"name": slot.name, "value": value}
    if _is_prop(row):
        line.update(props.describe(obj, [row])[0])
        line["name"] = slot.name
    elif isinstance(row, Counted):
        line["kind"] = "choice"
        line["options"] = _counts(obj, row)
    elif isinstance(row, Note):
        line["kind"] = "note"
    elif isinstance(row, Mix):
        line["kind"] = "mixer"
    else:
        line["kind"] = "routing"
        line["options"] = [
            _label(o) for o in props.get(obj, row.options_attr, []) or []
        ]
    if slot.single:
        line["single_layer_only"] = True
    return line


def describe(device):
    """The non-parameter settings this device has now ({} for most devices)."""
    out = {}
    try:
        for spec in SPECS:
            if not spec.match(device):
                continue
            for entry in spec.entries:
                slot = Slot(entry.row.name, entry, [device], False)
                value = read_slot(slot)
                if value is not _NA:
                    out[slot.name] = value
    except Exception:
        return out
    return out
