"""The `convert_audio` command: Live.Conversions, what Push's Convert button does.

Actions: audio_to_midi (harmony | melody | drums), to_simpler, to_drum_rack,
slices_to_drum_rack, pad_to_track, move_devices_to_drum_rack. Main thread only.

Verified by Producer Pal
(local/producer-pal/dev/live-api/conversions.md, Live 12.4.6, and
python-remote-script-api/python-only-candidates.md): Live.Conversions has
audio_to_midi_clip(song, clip, type) with harmony_to_midi 0, melody_to_midi 1,
drums_to_midi 2; create_midi_track_with_simpler(song, clip);
create_drum_rack_from_audio_clip(song, clip); sliced_simpler_to_drum_rack(song,
simpler); move_devices_on_track_to_new_drum_rack_pad(song, track_index);
create_midi_track_from_drum_pad(song, drum_pad); is_convertible_to_midi(song, clip),
which raises for MIDI clips. Every call returns None at once and does its work on a
later tick, so the new track is usually not visible when the command answers.
Not verified: the AudioToMidiType member names on the enum (the documented numbers are
the fallback) and that the slice/pad/devices calls behave as their names say; Producer
Pal does not use them. The module may be missing from older Lives: a clear error then.
"""

from . import clipref, objects
from .server import CommandError
from .song import undo_step

try:
    import Live
except ImportError:  # imported by the tests, outside Live
    Live = None

ACTIONS = (
    "audio_to_midi",
    "to_simpler",
    "to_drum_rack",
    "slices_to_drum_rack",
    "pad_to_track",
    "move_devices_to_drum_rack",
)
# Name -> number, the documented order.
TYPES = {"harmony": 0, "melody": 1, "drums": 2}


def convert_audio(song, p):
    action = p.get("action")
    if action not in ACTIONS:
        raise CommandError("bad_params", "action must be one of: " + ", ".join(ACTIONS))
    conv = _conversions()
    before = list(song.tracks)
    with undo_step(song):
        done = _HANDLERS[action](song, conv, p)
    out = {"done": action, **done}
    out.update(_new_tracks(song, before))
    return out


def _conversions():
    conv = getattr(Live, "Conversions", None) if Live is not None else None
    if conv is None:
        raise CommandError(
            "not_supported", "this Live version has no Live.Conversions (needs 12.x)"
        )
    return conv


def _fn(conv, name):
    fn = getattr(conv, name, None)
    if fn is None:
        raise CommandError("not_supported", f"this Live has no Conversions.{name}")
    return fn


def _call(fn, *args):
    try:
        fn(*args)
    except CommandError:
        raise
    except Exception as err:
        message = str(err)
        raise CommandError(
            "refused", f"Live refused: {message}" if message else "Live refused"
        ) from None


def _audio_clip(song, p):
    ref = clipref.locate(song, p.get("clip"))
    clip = ref.clip
    if getattr(clip, "is_midi_clip", False) or not getattr(clip, "is_audio_clip", True):
        raise CommandError(
            "bad_target", f"{ref.path} is a MIDI clip: only audio converts"
        )
    if getattr(clip, "is_recording", False):
        raise CommandError("busy", f"{ref.path} is recording: stop it first")
    return ref, clip


def _audio_to_midi(song, conv, p):
    ref, clip = _audio_clip(song, p)
    kind = str(p.get("type") or "").strip().lower()
    if kind not in TYPES:
        raise CommandError("bad_params", "type must be harmony, melody or drums")
    convertible = getattr(conv, "is_convertible_to_midi", None)
    if convertible is not None and not _call_bool(convertible, song, clip):
        raise CommandError("not_supported", f"Live cannot convert {ref.path} to MIDI")
    _call(_fn(conv, "audio_to_midi_clip"), song, clip, _type_value(conv, kind))
    return {"clip": ref.path, "type": kind}


def _call_bool(fn, *args):
    try:
        return bool(fn(*args))
    except Exception as err:
        raise CommandError("refused", f"Live refused: {err}") from None


def _type_value(conv, kind):
    enum = getattr(conv, "AudioToMidiType", None)
    member = getattr(enum, f"{kind}_to_midi", None)
    if member is not None:
        return member
    values = getattr(enum, "values", None)
    if isinstance(values, dict) and TYPES[kind] in values:
        return values[TYPES[kind]]
    return TYPES[kind]


def _to_simpler(song, conv, p):
    ref, clip = _audio_clip(song, p)
    _call(_fn(conv, "create_midi_track_with_simpler"), song, clip)
    return {"clip": ref.path}


def _to_drum_rack(song, conv, p):
    ref, clip = _audio_clip(song, p)
    _call(_fn(conv, "create_drum_rack_from_audio_clip"), song, clip)
    return {"clip": ref.path}


def _slices_to_drum_rack(song, conv, p):
    kind, device, path = objects.resolve(song, p.get("target") or "")
    if kind != "device" or getattr(device, "class_name", "") != "OriginalSimpler":
        raise CommandError(
            "bad_target", f"{path} is not a Simpler: give a Simpler device address"
        )
    _call(_fn(conv, "sliced_simpler_to_drum_rack"), song, device)
    return {"simpler": path}


def _pad_to_track(song, conv, p):
    kind, pad, path = objects.resolve(song, p.get("target") or "")
    if kind != "pad":
        raise CommandError(
            "bad_target", f"{path} is a {kind}: give a Drum Rack pad like t0/d0/pC1"
        )
    _call(_fn(conv, "create_midi_track_from_drum_pad"), song, pad)
    return {"pad": path}


def _move_devices(song, conv, p):
    track = objects.track(song, p.get("track") or "")
    path = objects.track_path(song, track)
    if not path.startswith("t"):
        raise CommandError("bad_target", f"{path} is not a regular track (t0, t1...)")
    _call(
        _fn(conv, "move_devices_on_track_to_new_drum_rack_pad"),
        song,
        int(path[1:]),
    )
    return {"track": path}


_HANDLERS = {
    "audio_to_midi": _audio_to_midi,
    "to_simpler": _to_simpler,
    "to_drum_rack": _to_drum_rack,
    "slices_to_drum_rack": _slices_to_drum_rack,
    "pad_to_track": _pad_to_track,
    "move_devices_to_drum_rack": _move_devices,
}


def _new_tracks(song, before):
    """The tracks that appeared, if Live has already made them. It usually has not
    (the work runs on a later tick), so the answer then says to read the Set."""
    after = list(song.tracks)
    new = [t for t in after if all(t != old for old in before)]
    if new:
        return {
            "new_tracks": [
                {"path": objects.track_path(song, t), "name": t.name} for t in new
            ]
        }
    return {
        "note": (
            "Live does the conversion on its next tick (about a second): read_set "
            "shows the new track, and the track numbers after it may have moved"
        )
    }
