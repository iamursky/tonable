"""Tracks and the objects in them: create_track, update_track, delete, duplicate.

delete and duplicate take one address for anything they can act on:
    t0, rA          a track or return track
    t0/d1, ...      a device (inside racks too)
    t0/s2           the clip in slot 2 of t0
    s2              scene 2
"""

import re

from . import objects, params
from .server import CommandError
from .song import find_scene, undo_step

TRACK_KINDS = ("midi", "audio", "return")


def create_track(song, p):
    kind = p.get("kind") or "midi"
    if kind not in TRACK_KINDS:
        raise CommandError("bad_params", "kind must be midi, audio or return")
    with undo_step(song):
        if kind == "return":
            song.create_return_track()
            track = list(song.return_tracks)[-1]
        else:
            tracks = list(song.tracks)
            index = p.get("index")
            index = len(tracks) if index in (None, "", -1) else int(index)
            if not 0 <= index <= len(tracks):
                raise CommandError("not_found", f"index must be 0-{len(tracks)}")
            create = (
                song.create_midi_track if kind == "midi" else song.create_audio_track
            )
            create(index)
            track = list(song.tracks)[index]
        if p.get("name"):
            track.name = str(p["name"])
    return {
        "created": objects.track_path(song, track),
        "name": track.name,
        "kind": kind,
    }


def update_track(song, p):
    """Change only the given fields; one line per field in the answer."""
    track = objects.track(song, p.get("track") or "")
    path = objects.track_path(song, track) if p.get("track") != "m" else "m"
    results = []
    with undo_step(song):
        for field in ("name", "color_index", "mute", "solo", "arm"):
            if p.get(field) in (None, ""):
                continue
            results.append(_set_field(track, field, p[field]))
        mixer = track.mixer_device
        if p.get("volume_db") not in (None, ""):
            results.append(_set_param("volume", mixer.volume, _db(p["volume_db"])))
        if p.get("pan") not in (None, ""):
            results.append(_set_param("pan", mixer.panning, _pan(p["pan"])))
        for send in _sends(p.get("sends")):
            results.append(_set_send(song, mixer, send))
        for key, attr in (
            ("input", "input_routing_type"),
            ("output", "output_routing_type"),
        ):
            if p.get(key) not in (None, ""):
                results.append(_set_routing(track, key, attr, str(p[key])))
    if not results:
        raise CommandError("bad_params", "nothing to change: give at least one field")
    return {"track": path, "name": track.name, "results": results}


def delete(song, p):
    """Delete after checking `name` against the object's name, as one undo step."""
    target = str(p.get("target") or "").strip()
    confirm = str(p.get("name") or "").strip()
    kind, obj, holder, index, path = _locate(song, target)
    actual = obj.name if kind != "clip" else obj.clip.name
    if not confirm or confirm.casefold() != actual.strip().casefold():
        raise CommandError(
            "confirm_name",
            f"to delete {path} give its name exactly: {actual!r}",
        )
    with undo_step(song):
        if kind == "track":
            song.delete_track(index)
        elif kind == "return":
            song.delete_return_track(index)
        elif kind == "device":
            holder.delete_device(index)
        elif kind == "clip":
            obj.delete_clip()
        elif kind == "scene":
            song.delete_scene(index)
    return {"deleted": path, "kind": kind, "name": actual}


def duplicate(song, p):
    target = str(p.get("target") or "").strip()
    kind, obj, holder, index, path = _locate(song, target)
    with undo_step(song):
        if kind == "track":
            song.duplicate_track(index)
            return {"duplicated": path, "copy": f"t{index + 1}", "name": obj.name}
        if kind == "scene":
            song.duplicate_scene(index)
            return {"duplicated": path, "copy": f"s{index + 1}", "name": obj.name}
        if kind == "clip":
            to = p.get("to_slot")
            track = holder
            if to in (None, ""):
                track.duplicate_clip_slot(index)
                to = index + 1
            else:
                slots = list(track.clip_slots)
                to = int(to)
                if not 0 <= to < len(slots):
                    raise CommandError(
                        "not_found", f"no slot {to}: slots 0-{len(slots) - 1}"
                    )
                if slots[to].has_clip:
                    raise CommandError(
                        "slot_taken",
                        f"slot {to} holds {slots[to].clip.name!r}; delete it first",
                    )
                obj.duplicate_clip_to(slots[to])
            copy = path.rsplit("/", 1)[0] + f"/s{to}"
            return {"duplicated": path, "copy": copy, "name": obj.clip.name}
        if kind == "device":
            dup = getattr(holder, "duplicate_device", None)
            if dup is None:
                raise CommandError(
                    "not_supported",
                    "Live's API cannot duplicate a device; load it again",
                )
            dup(index)
            copy = path.rsplit("/", 1)[0] + f"/d{index + 1}"
            return {"duplicated": path, "copy": copy, "name": obj.name}
    raise CommandError("not_supported", f"cannot duplicate a {kind}")


# --- addresses -----------------------------------------------------------------


def _locate(song, target):
    """(kind, object, holder, index, path) for a delete/duplicate address."""
    if not target:
        raise CommandError(
            "bad_params", "target is required, e.g. t0, t0/d1, t0/s2, s2"
        )
    scene = re.fullmatch(r"[sS](\d+)", target)
    if scene:
        index, obj = find_scene(song, scene.group(1))
        return "scene", obj, song, index, f"s{index}"
    clip = re.fullmatch(r"(.+)/[sS](\d+)", target)
    if clip:
        track = objects.track(song, clip.group(1))
        path = objects.track_path(song, track)
        slots = list(track.clip_slots)
        index = int(clip.group(2))
        if not path.startswith("t") or not 0 <= index < len(slots):
            raise CommandError("not_found", f"no slot {index} on {path}")
        if not slots[index].has_clip:
            raise CommandError("not_found", f"{path}/s{index} is empty")
        return "clip", slots[index], track, index, f"{path}/s{index}"
    kind, obj, path = objects.resolve(song, target)
    if kind == "track":
        if path == "m":
            raise CommandError(
                "bad_target", "the master track cannot be deleted or copied"
            )
        if path.startswith("r"):
            return "return", obj, song, ord(path[1]) - ord("A"), path
        return "track", obj, song, int(path[1:]), path
    if kind == "device":
        parent_path, last = path.rsplit("/", 1)
        _, holder, _ = objects.resolve(song, parent_path)
        return "device", obj, holder, int(last[1:]), path
    raise CommandError(
        "bad_target", f"{path} is a {kind}; give a track, device, clip or scene"
    )


# --- fields --------------------------------------------------------------------


def _set_field(track, field, value):
    try:
        if field in ("mute", "solo", "arm"):
            setattr(track, field, _bool(value))
        elif field == "color_index":
            track.color_index = int(value)
        else:
            track.name = str(value)
    except Exception as err:
        return {"field": field, "error": _why(err)}
    return {"field": field, "now": getattr(track, field)}


def _set_param(field, param, text):
    try:
        raw, note = params.value_for(param, text)
        param.value = raw
    except CommandError as err:
        return {"field": field, "error": str(err)}
    except Exception as err:
        return {"field": field, "error": _why(err)}
    out = {"field": field, "now": params.display(param)}
    if note:
        out["note"] = note
    return out


def _set_send(song, mixer, send):
    letter = str(send.get("return") or "").strip().upper()
    sends = list(mixer.sends)
    i = ord(letter) - ord("A") if len(letter) == 1 else -1
    field = f"send {letter or '?'}"
    if not 0 <= i < len(sends):
        have = ", ".join(objects.return_letter(n) for n in range(len(sends))) or "none"
        return {"field": field, "error": f"no return {letter or '?'}; returns: {have}"}
    value = send.get("db", send.get("level"))
    if value in (None, ""):
        return {"field": field, "error": "give db, e.g. -12 or -inf"}
    return _set_param(field, sends[i], _db(value))


def _set_routing(track, key, attr, wanted):
    options = list(getattr(track, "available_" + attr + "s", []) or [])
    names = [o.display_name for o in options]
    for option in options:
        if option.display_name.strip().casefold() == wanted.strip().casefold():
            try:
                setattr(track, attr, option)
            except Exception as err:
                return {"field": key, "error": _why(err)}
            return {"field": key, "now": getattr(track, attr).display_name}
    return {"field": key, "error": f"no {key} {wanted!r}; options: {names}"}


def _sends(raw):
    if raw in (None, ""):
        return []
    if isinstance(raw, dict):
        # {"A": -12} or one send object
        if "return" in raw:
            return [raw]
        return [{"return": k, "db": v} for k, v in raw.items()]
    return [s for s in raw if isinstance(s, dict)]


def _db(value):
    text = str(value).strip()
    if text.lower() in ("-inf", "inf", "off"):
        return "-inf dB"
    return text if text.lower().endswith("db") else text + " dB"


def _pan(value):
    """Pan as Live shows it: C, 25L, 30R; numbers -50 (left) .. 50 (right) too."""
    text = str(value).strip()
    if re.fullmatch(r"[+-]?\d+(\.\d*)?", text):
        number = float(text)
        if number == 0:
            return "C"
        return f"{abs(number):g}{'L' if number < 0 else 'R'}"
    return text


def _bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ("true", "on", "yes", "1")
    return bool(value)


def _why(err):
    return (
        f"Live refused: {err}" if str(err) else f"Live refused ({type(err).__name__})"
    )
