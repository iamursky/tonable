"""Session clips and their notes: read_clip and write_clip. Main thread only.

A clip is addressed by its track (t0) and slot (the scene row, from 0). Times are in
beats from the clip start. Pitches are MIDI numbers or names with C3 = 60.
"""

import math

from . import clipref, objects
from .clipprops import audio_details, clip_settings, is_audio
from .server import CommandError
from .song import undo_step

try:
    import Live
except ImportError:  # imported by the tests, outside Live
    Live = None


def read_clip(song, track_ref=None, slot_index=None, clip_address=None):
    """A Session clip (track and slot) or any clip by address (t0/s2, t0/a1)."""
    track, slot, where = _resolve(
        song, {"track": track_ref, "slot": slot_index, "clip": clip_address}
    )
    if not slot.has_clip:
        raise CommandError("not_found", f"{where} is empty")
    clip = slot.clip
    out = {"track": objects.track_path(song, track)}
    out.update(_address(song, track, clip, slot_index))
    out.update(_clip_info(clip))
    settings = clip_settings(clip)
    if settings:
        out["settings"] = settings
    if is_audio(clip):
        out.update(audio_details(clip))
    if clip.is_midi_clip:
        out["notes"] = [_note_out(n) for n in _sorted(clip.get_all_notes_extended())]
    return out


def write_clip(song, params):
    """Create a MIDI clip or change one, and write notes, as one undo step."""
    slot_index = params.get("slot")
    mode = params.get("mode") or "replace"
    if mode not in ("replace", "add"):
        raise CommandError("bad_params", "mode must be replace or add")
    track, slot, where = _resolve(song, params)
    if not getattr(track, "has_midi_input", False):
        raise CommandError("bad_target", f"{where}: {track.name} is not a MIDI track")

    notes, rejected = parse_notes(params.get("notes") or [])
    length = _beats(params.get("length_beats"), "length_beats", allow_zero=True)
    name = params.get("name") or ""

    with undo_step(song):
        created = not slot.has_clip
        if created:
            slot.create_clip(length or fit_length(song, notes))
        clip = slot.clip
        if not clip.is_midi_clip:
            raise CommandError("bad_target", f"{where} holds an audio clip")
        if length and not created:
            _set_length(clip, length)
        removed = 0
        if mode == "replace":
            old = list(clip.get_all_notes_extended())
            if old:
                clip.remove_notes_by_id(tuple(n.note_id for n in old))
            removed = len(old)
        if notes:
            clip.add_new_notes(tuple(_note_spec(n) for n in notes))
        if name:
            clip.name = name

    out = {
        "track": objects.track_path(song, track),
        **_address(song, track, clip, slot_index),
        "created": created,
        **_clip_info(clip),
        "notes_added": len(notes),
        "notes_removed": removed,
        "notes_total": len(list(clip.get_all_notes_extended())),
    }
    late = [i for i, n in enumerate(notes) if n["start"] >= clip.length]
    if late:
        out["warning"] = (
            f"{len(late)} note(s) start after the clip end ({clip.length:g} beats) and "
            "will not play; give a longer length_beats"
        )
    if rejected:
        out["rejected"] = rejected
    return out


# --- notes -----------------------------------------------------------------


def parse_notes(raw):
    """(good notes, rejected notes). One bad note never rejects the others."""
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raise CommandError("bad_params", "notes must be a list of note objects")
    good, rejected = [], []
    for i, item in enumerate(raw):
        try:
            good.append(parse_note(item))
        except CommandError as err:
            rejected.append({"index": i, "note": item, "error": str(err)})
    return good, rejected


def parse_note(item):
    if not isinstance(item, dict):
        raise CommandError(
            "bad_note", "a note must be an object with pitch, start, length"
        )
    note = {
        "pitch": parse_pitch(_field(item, "pitch", "note")),
        "start": _beats(_field(item, "start", "start_beats", "time"), "start", True),
        "length": _beats(_field(item, "length", "duration", "length_beats"), "length"),
        "velocity": _velocity(_field(item, "velocity", "vel")),
        "mute": bool(item.get("mute") or False),
    }
    for key, low, high in EXTRA_NOTE_FIELDS:
        value = item.get(key)
        if value not in (None, ""):
            note[key] = _ranged(value, key, low, high)
    return note


def parse_pitch(value):
    if value is None or value == "":
        raise CommandError("bad_note", "pitch is required (60 or C3)")
    if isinstance(value, bool):
        raise CommandError("bad_note", "pitch must be a number or a note name")
    if isinstance(value, (int, float)) or str(value).strip().lstrip("-").isdigit():
        number = float(value)
        if number != int(number) or not 0 <= number <= 127:
            raise CommandError("bad_note", f"pitch {value} is not a MIDI note 0-127")
        return int(number)
    return objects.note_number(str(value).strip())


def fit_length(song, notes):
    """Whole bars that hold every note; one bar when there are none."""
    bar = song.signature_numerator * 4.0 / song.signature_denominator
    end = max((n["start"] + n["length"] for n in notes), default=0.0)
    return max(1, math.ceil(end / bar)) * bar


# Live 12 note properties beyond pitch, time, velocity and mute: (name, low, high).
EXTRA_NOTE_FIELDS = (
    ("probability", 0.0, 1.0),
    ("velocity_deviation", -127.0, 127.0),
    ("release_velocity", 0.0, 127.0),
)


def _ranged(value, name, low, high):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise CommandError("bad_note", f"{name} must be a number") from None
    if not low <= number <= high:
        raise CommandError("bad_note", f"{name} {value} is outside {low:g}-{high:g}")
    return number


def _field(item, *names):
    for name in names:
        if item.get(name) not in (None, ""):
            return item[name]
    return None


def _beats(value, name, allow_zero=False):
    if value is None or value == "":
        if allow_zero:
            return 0.0
        raise CommandError("bad_note", f"{name} is required (in beats)")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise CommandError("bad_note", f"{name} must be a number of beats") from None
    if not math.isfinite(number) or number < 0 or (number == 0 and not allow_zero):
        raise CommandError(
            "bad_note", f"{name} must be {'0 or more' if allow_zero else 'more than 0'}"
        )
    return number


def _velocity(value):
    if value is None or value == "":
        raise CommandError("bad_note", "velocity is required (1-127)")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise CommandError("bad_note", "velocity must be a number 1-127") from None
    if not 1 <= number <= 127:
        raise CommandError("bad_note", f"velocity {value} is outside 1-127")
    return number


def _note_spec(note):
    extra = {key: note[key] for key, _, _ in EXTRA_NOTE_FIELDS if key in note}
    return Live.Clip.MidiNoteSpecification(
        pitch=note["pitch"],
        start_time=note["start"],
        duration=note["length"],
        velocity=note["velocity"],
        mute=note["mute"],
        **extra,
    )


def _note_out(note):
    out = {
        "pitch": objects.note_name(note.pitch),
        "midi": note.pitch,
        "start": note.start_time,
        "length": note.duration,
        "velocity": note.velocity,
    }
    if note.mute:
        out["mute"] = True
    # Only what differs from Live's defaults, so plain notes stay short.
    for key, default in (
        ("probability", 1.0),
        ("velocity_deviation", 0.0),
        ("release_velocity", 64.0),
    ):
        value = getattr(note, key, default)
        if value != default:
            out[key] = value
    return out


def _sorted(notes):
    return sorted(notes, key=lambda n: (n.start_time, n.pitch))


# --- clips and slots ---------------------------------------------------------


def _slot(song, track_ref, slot_index):
    return clipref.slot_for(song, track_ref, slot_index)


def _resolve(song, params):
    return clipref.resolve(song, params)


def _address(song, track, clip, slot_index=None):
    return clipref.address(song, track, clip, slot_index)


def _clip_info(clip):
    out = {
        "name": clip.name,
        "type": "midi" if clip.is_midi_clip else "audio",
        "length_beats": clip.length,
        "looping": bool(clip.looping),
    }
    if clip.looping:
        out["loop"] = {"start_beats": clip.loop_start, "end_beats": clip.loop_end}
    return out


def _set_length(clip, length):
    """Make the clip `length` beats long from its loop start."""
    end = clip.loop_start + length
    if end > clip.end_marker:
        clip.end_marker = end
        clip.loop_end = end
    else:
        clip.loop_end = end
        clip.end_marker = end


# --- edit_notes -------------------------------------------------------------

EDIT_ACTIONS = (
    "delete",
    "transpose",
    "shift",
    "quantize",
    "velocity",
    "length",
    "mute",
    "unmute",
    "probability",
    "velocity_deviation",
    "release_velocity",
)


def edit_notes(song, params):
    """Change the notes in a time and pitch range, as one undo step.

    The range: from_beats (inclusive) to to_beats (exclusive) by note start, and
    pitches (names or numbers); empty means all notes.
    """
    action = params.get("action")
    if action not in EDIT_ACTIONS:
        raise CommandError(
            "bad_params", "action must be one of: " + ", ".join(EDIT_ACTIONS)
        )
    track, slot, where = _resolve(song, params)
    if not slot.has_clip or not slot.clip.is_midi_clip:
        raise CommandError("not_found", f"{where} has no MIDI clip")
    clip = slot.clip
    notes = clip.get_all_notes_extended()
    chosen = [n for n in notes if _in_range(n, params)]
    skipped = []
    with undo_step(song):
        if action == "delete":
            if chosen:
                clip.remove_notes_by_id(tuple(n.note_id for n in chosen))
        else:
            change = _change(action, params)
            for note in chosen:
                reason = change(note)
                if reason:
                    skipped.append(
                        {
                            "pitch": objects.note_name(note.pitch),
                            "start": note.start_time,
                            "reason": reason,
                        }
                    )
            clip.apply_note_modifications(notes)
    out = {
        "track": objects.track_path(song, track),
        **_address(song, track, clip, params.get("slot")),
        "action": action,
        "notes_matched": len(chosen),
        "notes_total": len(list(clip.get_all_notes_extended())),
    }
    if skipped:
        out["skipped"] = skipped
    return out


def _in_range(note, params):
    start, end = params.get("from_beats"), params.get("to_beats")
    if start not in (None, "") and note.start_time < float(start):
        return False
    if end not in (None, "") and note.start_time >= float(end):
        return False
    pitches = params.get("pitches")
    if pitches not in (None, "", []):
        if not isinstance(pitches, list):
            pitches = [pitches]
        if note.pitch not in {parse_pitch(p) for p in pitches}:
            return False
    return True


def _change(action, params):
    """A function that changes one note and returns why it could not, or None."""
    if action == "transpose":
        steps = int(_number(params, "semitones"))

        def apply(note):
            if not 0 <= note.pitch + steps <= 127:
                return "would leave MIDI notes 0-127"
            note.pitch += steps

    elif action == "shift":
        beats = _number(params, "beats")

        def apply(note):
            if note.start_time + beats < 0:
                return "would start before the clip"
            note.start_time += beats

    elif action == "quantize":
        grid = _number(params, "grid_beats")
        if grid <= 0:
            raise CommandError(
                "bad_params", "grid_beats must be more than 0, e.g. 0.25"
            )

        def apply(note):
            note.start_time = round(note.start_time / grid) * grid

    elif action == "velocity":
        velocity = _velocity(params.get("velocity"))

        def apply(note):
            note.velocity = velocity

    elif action in ("mute", "unmute"):
        muted = action == "mute"

        def apply(note):
            note.mute = muted

    elif action in ("probability", "velocity_deviation", "release_velocity"):
        low, high = next((lo, hi) for key, lo, hi in EXTRA_NOTE_FIELDS if key == action)
        value = _ranged(params.get("value"), "value", low, high)

        def apply(note):
            setattr(note, action, value)

    else:  # length
        length = _beats(params.get("length_beats"), "length_beats")

        def apply(note):
            note.duration = length

    return apply


def _number(params, name):
    value = params.get(name)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise CommandError("bad_params", f"{name} is required (a number)") from None
