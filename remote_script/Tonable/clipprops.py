"""Clip settings and actions: update_clip, create_audio_clip, and what read_clip shows.

Covers Session and Arrangement clips, MIDI and audio: name, color, mute, loop and
marker positions, launch mode and quantization, legato, time
signature, scale, groove, warp (mode, markers), gain and pitch, plus actions such as
fire, stop, crop, quantize and clear envelopes.

Names and enum numbers come from the Live Object Model as remembered; Live reports
the real value after each write, and update_clip passes any refusal on. Launch and
quantization enums are the least certain, so a write that Live
keeps at the old value comes back as an error line, never as a success. Warp markers,
`available_warp_modes` and `Clip.quantize(grid, amount)` follow Producer Pal's notes
(local/producer-pal/dev/live-api). Main thread only.
"""

import os

from . import clipref, props
from .server import CommandError
from .song import RECORD_QUANTIZATION, undo_step

try:
    import Live
except ImportError:  # imported by the tests, outside Live
    Live = None

AUDIO_EXTENSIONS = (".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg", ".m4a", ".aac")

LAUNCH_MODE = {"Trigger": 0, "Gate": 1, "Toggle": 2, "Repeat": 3}
LAUNCH_QUANTIZATION = {
    "Global": 0,
    "None": 1,
    "8 Bars": 2,
    "4 Bars": 3,
    "2 Bars": 4,
    "1 Bar": 5,
    "1/2": 6,
    "1/2T": 7,
    "1/4": 8,
    "1/4T": 9,
    "1/8": 10,
    "1/8T": 11,
    "1/16": 12,
    "1/16T": 13,
    "1/32": 14,
}
WARP_MODE = {
    "Beats": 0,
    "Tones": 1,
    "Texture": 2,
    "Re-Pitch": 3,
    "Complex": 4,
    "Complex Pro": 6,
}

# Where the clip plays from and loops. Written in this order; a refused write is
# tried once more after the others, because Live checks start < end.
POSITION_PROPS = [
    props.prop("looping", "looping", "bool"),
    props.prop("loop_end", "loop_end", "float", lo=0.0),
    props.prop("end_marker", "end_marker", "float", lo=0.0),
    props.prop("loop_start", "loop_start", "float", lo=0.0),
    props.prop("start_marker", "start_marker", "float", lo=0.0),
]
CLIP_PROPS = [
    props.prop("name", "name", "str"),
    props.prop("color_index", "color_index", "int", lo=0, hi=69),
    props.prop("muted", "muted", "bool"),
    props.prop("launch_mode", "launch_mode", "enum", choices=LAUNCH_MODE),
    props.prop(
        "launch_quantization",
        "launch_quantization",
        "enum",
        choices=LAUNCH_QUANTIZATION,
    ),
    props.prop("legato", "legato", "bool"),
    props.prop("velocity_amount", "velocity_amount", "float", lo=-1.0, hi=1.0),
    props.prop("ram_mode", "ram_mode", "bool"),
    props.prop("warping", "warping", "bool"),
    props.prop("gain", "gain", "float", lo=0.0, hi=1.0),
    props.prop("pitch_coarse", "pitch_coarse", "int", lo=-48, hi=48),
    props.prop("pitch_fine", "pitch_fine", "float", lo=-50.0, hi=50.0),
    props.prop("scale_mode", "scale_mode", "bool"),
    props.prop("root_note", "root_note", "int", lo=0, hi=11),
    props.prop("scale_name", "scale_name", "str"),
]
WARP_MODE_PROP = props.prop("warp_mode", "warp_mode", "enum", choices=WARP_MODE)
STOP_BUTTON = props.prop("stop_button", "has_stop_button", "bool")
QUANTIZE_GRID = props.prop("grid", "grid", "enum", choices=RECORD_QUANTIZATION)
CLIP_FACTS = [
    props.prop("is_playing", "is_playing", "bool", readonly=True),
    props.prop("is_recording", "is_recording", "bool", readonly=True),
    props.prop("is_overdubbing", "is_overdubbing", "bool", readonly=True),
    props.prop("has_envelopes", "has_envelopes", "bool", readonly=True),
    props.prop("playing_position", "playing_position", "float", readonly=True),
    props.prop("start_time", "start_time", "float", readonly=True),
    props.prop("end_time", "end_time", "float", readonly=True),
]

ACTIONS = (
    "fire",
    "stop",
    "crop",
    "duplicate_loop",
    "quantize",
    "clear_envelopes",
    "move_playing_position",
    "add_warp_marker",
    "move_warp_marker",
    "remove_warp_marker",
)
FIELD_NAMES = [p.name for p in CLIP_PROPS + POSITION_PROPS] + [
    "warp_mode",
    "time_signature",
    "groove",
    "stop_button",
]


# --- reading ---------------------------------------------------------------------


def is_audio(clip):
    return bool(props.get(clip, "is_audio_clip", False))


def clip_settings(clip):
    """Everything about a clip beyond its name and notes, as read_clip shows it."""
    out = props.read(clip, CLIP_PROPS + POSITION_PROPS + CLIP_FACTS)
    out.pop("name", None)
    if is_audio(clip):
        mode = props.get(clip, "warp_mode", None)
        if mode is not None:
            out["warp_mode"] = props.shown(clip, WARP_MODE_PROP, mode)
    num = props.get(clip, "signature_numerator", None)
    den = props.get(clip, "signature_denominator", None)
    if num is not None and den is not None:
        out["time_signature"] = f"{num}/{den}"
    groove = props.get(clip, "groove", None)
    if groove is not None:
        out["groove"] = props.get(groove, "name", "")
    return out


def audio_details(clip):
    """The sample behind an audio clip and its warp markers."""
    audio = {}
    for key, attr in (("file", "file_path"), ("sample_rate", "sample_rate")):
        value = props.get(clip, attr, None)
        if value not in (None, ""):
            audio[key] = value
    shown = props.get(clip, "gain_display_string", None)
    if shown:
        audio["gain_display"] = shown
    markers = props.get(clip, "warp_markers", None)
    if markers is not None:
        listed = list(markers)
        audio["warp_markers"] = [
            {"beat_time": m.beat_time, "sample_time": m.sample_time}
            for m in listed[:64]
        ]
        if len(listed) > 64:
            audio["warp_markers_total"] = len(listed)
    return {"audio": audio} if audio else {}


# --- update_clip -----------------------------------------------------------------


def update_clip(song, p):
    """Change clip settings and/or run one action, as one undo step.

    The clip is `clip` (t0/s2, t0/a1) or `track` + `slot`. An empty Session slot can
    only take `stop_button`.
    """
    ref = clipref.from_params(song, p, need_clip=False)
    action = p.get("action") or ""
    if action and action not in ACTIONS:
        raise CommandError("bad_params", "action must be one of: " + ", ".join(ACTIONS))
    clip = ref.clip
    wants_clip = action or any(
        props.given(p, name) for name in FIELD_NAMES if name != "stop_button"
    )
    if clip is None and wants_clip:
        raise CommandError("not_found", f"{ref.path} is empty")
    results = []
    with undo_step(song):
        if props.given(p, "stop_button"):
            if ref.slot is None:
                results.append(
                    {"field": "stop_button", "error": "only Session slots have one"}
                )
            else:
                results.append(props.write_one(ref.slot, STOP_BUTTON, p["stop_button"]))
        if clip is not None:
            results.extend(_write_fields(song, clip, p))
            if action:
                results.append(_run(clip, action, p))
    if not results:
        raise CommandError("bad_params", "nothing to change: give a field or an action")
    out = {"clip": ref.path, "results": results}
    if clip is not None:
        out["name"] = clip.name
        out["settings"] = clip_settings(clip)
    return out


def _write_fields(song, clip, p):
    results = props.write(clip, CLIP_PROPS, p)
    results.extend(_write_positions(clip, p))
    if props.given(p, "warp_mode"):
        results.append(_write_warp_mode(clip, p["warp_mode"]))
    if props.given(p, "time_signature"):
        results.append(_write_signature(clip, p["time_signature"]))
    if props.given(p, "groove"):
        results.append(_write_groove(song, clip, p["groove"]))
    return results


def _write_positions(clip, p):
    first = props.write(clip, POSITION_PROPS, p)
    failed = {r["field"] for r in first if "error" in r}
    if not failed:
        return first
    # Live checks the markers against each other, so a write can fail only because
    # of the order. Try the failed ones again now the others have landed.
    again = props.write(clip, [x for x in POSITION_PROPS if x.name in failed], p)
    return [r for r in first if r["field"] not in failed] + again


def _write_warp_mode(clip, requested):
    if not is_audio(clip):
        return {"field": "warp_mode", "error": "only audio clips have a warp mode"}
    try:
        value = props.convert(clip, WARP_MODE_PROP, requested)
    except CommandError as err:
        return {"field": "warp_mode", "error": str(err)}
    available = props.get(clip, "available_warp_modes", None)
    if available is not None and value not in list(available):
        labels = [
            label for label, number in WARP_MODE.items() if number in list(available)
        ]
        return {
            "field": "warp_mode",
            "error": f"this clip cannot use that mode; available: {labels}",
        }
    return props.write_one(clip, WARP_MODE_PROP, requested)


def _write_signature(clip, requested):
    text = str(requested).replace(" ", "")
    try:
        num, den = (int(part) for part in text.split("/"))
    except ValueError:
        return {"field": "time_signature", "error": "use a form like 4/4 or 6/8"}
    try:
        clip.signature_numerator = num
        clip.signature_denominator = den
    except Exception as err:
        return {"field": "time_signature", "error": props._why(err)}
    return {
        "field": "time_signature",
        "now": f"{clip.signature_numerator}/{clip.signature_denominator}",
    }


def _write_groove(song, clip, requested):
    try:
        from . import grooves
    except ImportError:
        return {"field": "groove", "error": "this Tonable has no groove support"}
    try:
        clip.groove = grooves.find_groove(song, requested)
    except CommandError as err:
        return {"field": "groove", "error": str(err)}
    except Exception as err:
        return {"field": "groove", "error": props._why(err)}
    return {"field": "groove", "now": props.get(clip.groove, "name", "")}


def _run(clip, action, p):
    out = {"action": action}
    try:
        if action in ("fire", "stop", "crop", "duplicate_loop"):
            getattr(clip, action)()
        elif action == "clear_envelopes":
            clip.clear_all_envelopes()
        elif action == "quantize":
            grid = props.enum_value(None, QUANTIZE_GRID, p.get("grid") or "")
            amount = _number(p.get("amount"), "amount", default=1.0)
            clip.quantize(grid, amount)
            out["grid"] = props.shown(None, QUANTIZE_GRID, grid)
        elif action == "move_playing_position":
            clip.move_playing_pos(_number(p.get("time_beats"), "time_beats"))
        else:
            out.update(_warp_marker(clip, action, p))
    except CommandError as err:
        return {"action": action, "error": str(err)}
    except Exception as err:
        return {"action": action, "error": props._why(err)}
    out["done"] = True
    return out


def _warp_marker(clip, action, p):
    if not is_audio(clip):
        raise CommandError("bad_target", "only audio clips have warp markers")
    at = _number(p.get("time_beats"), "time_beats")
    if action == "add_warp_marker":
        if props.given(p, "sample_time"):
            seconds = _number(p["sample_time"], "sample_time")
        else:
            seconds = _interpolated_seconds(clip, at)
        clip.add_warp_marker(_warp_marker_object(clip, seconds, at))
    elif action == "move_warp_marker":
        clip.move_warp_marker(at, _number(p.get("distance_beats"), "distance_beats"))
    else:
        clip.remove_warp_marker(at)
    return audio_details(clip)


def _warp_marker_object(clip, sample_time, beat_time):
    """Live's add_warp_marker wants a Clip.WarpMarker. Its positional order is
    (sample_time, beat_time), the reverse of how people say it, so use the names."""
    kind = getattr(getattr(Live, "Clip", None), "WarpMarker", None)
    if kind is None:
        kind = type(list(clip.warp_markers)[0])
    return kind(sample_time=sample_time, beat_time=beat_time)


def _interpolated_seconds(clip, beat):
    """Where in the sample a new marker at `beat` belongs: between its neighbours."""
    markers = sorted(
        ((m.beat_time, m.sample_time) for m in clip.warp_markers), key=lambda m: m[0]
    )
    if len(markers) < 2:
        raise CommandError(
            "bad_target", "the clip has too few warp markers; give sample_time"
        )
    before = [m for m in markers if m[0] <= beat]
    after = [m for m in markers if m[0] > beat]
    (b0, s0), (b1, s1) = (
        (before[-1], after[0]) if before and after else (markers[-2], markers[-1])
    )
    if b1 == b0:
        return s0
    return s0 + (s1 - s0) * (beat - b0) / (b1 - b0)


# --- create_audio_clip -----------------------------------------------------------


def create_audio_clip(song, p):
    """Put an audio file on an audio track: a Session slot, or a bar on the timeline."""
    path = _audio_path(p.get("path"))
    arrangement = props.given(p, "at_bar") or props.given(p, "at_beats")
    with undo_step(song):
        if arrangement:
            track = _audio_track(song, p.get("track"))
            at = _position(song, p)
            clip = track.create_audio_clip(path, at)
        else:
            ref = clipref.from_params(song, p, need_clip=False)
            if ref.slot is None:
                raise CommandError("bad_target", "give a Session slot or a bar")
            if ref.clip is not None:
                raise CommandError(
                    "slot_taken", f"{ref.path} holds {ref.clip.name!r}; delete it first"
                )
            _audio_track(song, ref.track)
            ref.slot.create_audio_clip(path)
            clip = ref.slot.clip
            track = ref.track
        if props.given(p, "name"):
            clip.name = str(p["name"])
    where = clipref.path_of(song, track, clip)
    out = {"created": where, "name": clip.name, "file": path}
    out.update(audio_details(clip))
    return out


def _audio_path(raw):
    text = os.path.expanduser(str(raw or "").strip())
    if not text:
        raise CommandError("bad_params", "path is required: an audio file")
    full = os.path.abspath(text)
    if not os.path.isfile(full):
        raise CommandError("not_found", f"no file at {full}")
    if not full.lower().endswith(AUDIO_EXTENSIONS):
        raise CommandError(
            "bad_target", "only audio files: " + ", ".join(AUDIO_EXTENSIONS)
        )
    return full


def _audio_track(song, track):
    from . import objects

    obj = track if not isinstance(track, str) else objects.track(song, track)
    where = objects.track_path(song, obj)
    if not where.startswith("t") or not props.get(obj, "has_audio_input", False):
        raise CommandError("bad_target", f"{where} is not an audio track")
    return obj


def _position(song, p):
    bar_length = song.signature_numerator * 4.0 / song.signature_denominator
    if props.given(p, "at_bar"):
        bar = _number(p["at_bar"], "at_bar")
        if bar < 1:
            raise CommandError("bad_params", "at_bar counts from 1, like Live")
        return (bar - 1) * bar_length
    beats = _number(p.get("at_beats"), "at_beats")
    if beats < 0:
        raise CommandError("bad_params", "at_beats must be 0 or more")
    return beats


def _number(value, name, default=None):
    if value in (None, ""):
        if default is not None:
            return default
        raise CommandError("bad_params", f"{name} is required (a number)")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise CommandError("bad_params", f"{name} must be a number") from None
