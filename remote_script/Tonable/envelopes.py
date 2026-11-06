"""read_envelope and write_envelope: automation in Session clips. Main thread only.

Live's API reaches envelopes of Session clips only, for mixer and device
parameters; MIDI CC envelopes are invisible (stage 0: use CC Control's Custom A,
CC 64 Sustain, for the pedal). To get automation into the Arrangement, copy the clip
there: Live writes the track automation for its span.

The parameter is one of:
    volume, pan, send A        the track's mixer
    t0/d0:Release              a device parameter by name (or index) on this track
Curves follow Producer Pal's findings: each event's control_coefficients
(x1, y1, x2, y2) shape the segment it starts, and (0.5, 0.5, 0.5, 0.5) is straight.
"""

import struct

from . import objects, params
from .clips import _slot
from .server import CommandError
from .song import undo_step

STRAIGHT = (0.5, 0.5, 0.5, 0.5)
# Reads cover events past the clip end too (Live keeps them). Live refuses larger
# ranges; this is its own limit for song time, from Track.create_midi_clip's doc.
LIVE_MAX_BEATS = 1576800.0


def read_envelope(song, p):
    track, clip, param, label = _target(song, p)
    env = clip.automation_envelope(param)
    out = {
        "track": objects.track_path(song, track),
        "slot": int(p.get("slot")),
        "parameter": label,
        "now": params.display(param),
    }
    if env is None:
        out["exists"] = False
        return out
    events = list(env.events_in_range(0.0, LIVE_MAX_BEATS))
    out["exists"] = True
    out["points"] = [_event_out(env, events, i, param) for i in range(len(events))]
    return out


def write_envelope(song, p):
    """Replace the envelope with `points` (or clear it), as one undo step."""
    track, clip, param, label = _target(song, p)
    raw_points = p.get("points") or []
    if isinstance(raw_points, dict):
        raw_points = [raw_points]
    points = [_point(param, item, i) for i, item in enumerate(raw_points)]
    if any(b["time"] < a["time"] for a, b in zip(points, points[1:], strict=False)):
        raise CommandError("bad_params", "point times must not go back")
    with undo_step(song):
        if clip.automation_envelope(param) is not None:
            clip.clear_envelope(param)
        if points:
            env = clip.create_automation_envelope(param)
            if env is None:
                raise CommandError(
                    "not_supported", f"Live gives no envelope for {label} in this clip"
                )
            _write_events(env, points)
            param.re_enable_automation()
    out = read_envelope(song, p)
    out["written"] = len(points)
    return out


# --- pieces ------------------------------------------------------------------


def _target(song, p):
    track, slot, where = _slot(song, p.get("track"), p.get("slot"))
    if not slot.has_clip:
        raise CommandError("not_found", f"{where} is empty")
    ref = str(p.get("parameter") or "").strip()
    if not ref:
        raise CommandError(
            "bad_params", "parameter is required: volume, pan, send A or t0/d0:Name"
        )
    mixer = track.mixer_device
    low = ref.casefold()
    if low == "volume":
        return track, slot.clip, mixer.volume, "volume"
    if low in ("pan", "panning"):
        return track, slot.clip, mixer.panning, "pan"
    if low.startswith("send"):
        letter = ref[4:].strip().upper()
        sends = list(mixer.sends)
        i = ord(letter) - ord("A") if len(letter) == 1 else -1
        if not 0 <= i < len(sends):
            raise CommandError(
                "not_found", f"no {ref}: the Set has {len(sends)} return tracks"
            )
        return track, slot.clip, sends[i], f"send {letter}"
    if ":" not in ref:
        raise CommandError(
            "bad_params", f"{ref!r}: use volume, pan, send A or t0/d0:Name"
        )
    device_path, name = ref.rsplit(":", 1)
    kind, device, path = objects.resolve(song, device_path)
    if kind != "device":
        raise CommandError("bad_target", f"{path} is not a device")
    if not path.startswith(objects.track_path(song, track) + "/"):
        raise CommandError(
            "bad_target", f"{path} is not on {objects.track_path(song, track)}"
        )
    plist = list(device.parameters)
    name = name.strip()
    hits = [x for x in plist if x.name.casefold() == name.casefold()]
    if not hits and name.isdigit() and int(name) < len(plist):
        hits = [plist[int(name)]]
    if not hits:
        raise CommandError("not_found", f"{device.name} has no parameter {name!r}")
    return track, slot.clip, hits[0], f"{path}:{hits[0].name}"


def _point(param, item, i):
    if not isinstance(item, dict):
        raise CommandError(
            "bad_params", f"point {i} must be an object with time and value"
        )
    try:
        time = float(item.get("time", item.get("time_beats")))
    except (TypeError, ValueError):
        raise CommandError(
            "bad_params", f"point {i}: time is required (beats)"
        ) from None
    if time < 0:
        raise CommandError("bad_params", f"point {i}: time must be 0 or more")
    if item.get("value") in (None, ""):
        raise CommandError("bad_params", f"point {i}: value is required")
    raw, _ = params.value_for(param, item["value"])
    curve = item.get("curve")
    if curve not in (None, "", []):
        if not (isinstance(curve, list) and len(curve) == 4):
            raise CommandError(
                "bad_params", f"point {i}: curve is 4 numbers x1, y1, x2, y2"
            )
        curve = tuple(float(c) for c in curve)
        if not all(0 <= c <= 1 for c in curve):
            raise CommandError("bad_params", f"point {i}: curve numbers are 0-1")
    else:
        curve = None
    return {"time": time, "value": raw, "jump": bool(item.get("jump")), "curve": curve}


def _write_events(env, points):
    """Create the events last time first: Live straightens a curve whose segment
    end doesn't exist yet. A jump is two events at one time: the previous value,
    then the new one."""
    from Live.Envelope import EnvelopeEvent, EnvelopeEventControlCoefficients

    events = []
    previous = None
    for point in points:
        if point["jump"] and previous is not None:
            events.append((point["time"], previous, None))
        events.append((point["time"], point["value"], point["curve"]))
        previous = point["value"]
    groups = []
    for event in events:
        if groups and groups[-1][0][0] == event[0]:
            groups[-1].append(event)
        else:
            groups.append([event])
    for group in reversed(groups):
        for time, value, curve in group:
            if curve is None:
                env.create_event(EnvelopeEvent(time, value))
            else:
                coefficients = EnvelopeEventControlCoefficients(*curve)
                env.create_event(EnvelopeEvent(time, value, coefficients))


def _event_out(env, events, i, param):
    event = events[i]
    # Two events at one time are a jump: sample just after it for the second.
    same_time = i > 0 and events[i - 1].time == event.time
    raw = env.value_at_time(event.time if not same_time else _after(event.time))
    out = {"time": event.time, "value": raw, "display": param.str_for_value(raw)}
    c = getattr(event, "control_coefficients", None)
    if c is not None and (c.x1, c.y1, c.x2, c.y2) != STRAIGHT:
        out["curve"] = [c.x1, c.y1, c.x2, c.y2]
    return out


def _after(time):
    """The next time Live can tell apart from `time`: it keeps envelope times as
    32-bit floats, so step to the next float32, not the next double."""
    (bits,) = struct.unpack("<I", struct.pack("<f", time))
    (later,) = struct.unpack("<f", struct.pack("<I", bits + 1))
    return later
