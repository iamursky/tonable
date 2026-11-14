"""The Arrangement: list clips, place a scene, copy or create clips, locators.

Times are given as at_bar (bars from 1, as Live numbers them) or at_beats; answers
show both, with bar|beat like Live's display ("17|1"). Live's API copies one clip at a
time (duplicate_clip_to_arrangement), so place_scene walks the tracks itself, as one
undo step. Envelopes in a Session clip become track automation on its span.
"""

from . import clipref, clips, objects, props
from .server import CommandError
from .song import find_scene, undo_step

ACTIONS = (
    "list",
    "place_scene",
    "copy_clip",
    "move_clip",
    "create_clip",
    "delete_clip",
    "add_take_lane",
    "add_locator",
    "rename_locator",
    "delete_locator",
)


def arrangement(song, p):
    action = p.get("action")
    if action not in ACTIONS:
        raise CommandError("bad_params", "action must be one of: " + ", ".join(ACTIONS))
    if action == "list":
        return _list(song)
    handler = {
        "place_scene": _place_scene,
        "copy_clip": _copy_clip,
        "move_clip": _move_clip,
        "create_clip": _create_clip,
        "delete_clip": _delete_clip,
        "add_take_lane": _add_take_lane,
        "add_locator": _add_locator,
        "rename_locator": _rename_locator,
        "delete_locator": _delete_locator,
    }[action]
    with undo_step(song):
        return handler(song, p)


def bar_beat(song, beats):
    """Live's bar|beat for a time in beats: 0 -> "1|1", 18 in 4/4 -> "5|3"."""
    bar_length = _bar(song)
    bar = int(beats // bar_length) + 1
    beat = beats - (bar - 1) * bar_length + 1
    return f"{bar}|{beat:g}"


def _list(song):
    tracks = []
    for t, track in enumerate(song.tracks):
        found = [
            _clip_out(song, c, f"t{t}/a{i}")
            for i, c in enumerate(getattr(track, "arrangement_clips", []) or [])
        ]
        lanes = _take_lanes(track)
        if found or lanes:
            entry = {"track": f"t{t}", "name": track.name, "clips": found}
            if lanes:
                entry["take_lanes"] = lanes
            tracks.append(entry)
    return {
        "time_signature": f"{song.signature_numerator}/{song.signature_denominator}",
        "tracks": tracks,
        "locators": [_locator_out(song, c) for c in song.cue_points],
        "loop": {
            "on": bool(song.loop),
            "start": bar_beat(song, song.loop_start),
            "length_beats": song.loop_length,
        },
    }


def _place_scene(song, p):
    index, scene = find_scene(song, p.get("scene"))
    at = _time(song, p)
    placed, end = [], at
    for t, track in enumerate(song.tracks):
        slots = list(track.clip_slots)
        if index < len(slots) and slots[index].has_clip:
            clip = slots[index].clip
            copy = track.duplicate_clip_to_arrangement(clip, at)
            placed.append({"track": f"t{t}", "clip": clip.name})
            end = max(end, copy.end_time if copy is not None else at + clip.length)
    if not placed:
        raise CommandError("not_found", f"scene {index} ({scene.name!r}) has no clips")
    return {
        "scene": {"index": index, "name": scene.name},
        "start": _time_out(song, at),
        "end": _time_out(song, end),
        "placed": placed,
    }


def _copy_clip(song, p):
    """A Session clip (track + slot, or clip t0/s2) or a timeline clip (clip t0/a1)."""
    track, slot, where = clipref.resolve(song, p)
    if not slot.has_clip:
        raise CommandError("not_found", f"{where} is empty")
    at = _time(song, p)
    copy = track.duplicate_clip_to_arrangement(slot.clip, at)
    return {
        "copied": where,
        "clip": _clip_out(song, copy) if copy is not None else None,
    }


def _move_clip(song, p):
    """Move a timeline clip: copy it to the new time, then delete the original.

    The copy replaces any clips under its new span (as place_scene does), so a move
    that would land on the clip's own old span is refused; copy_clip first instead.
    """
    ref = clipref.locate(song, p.get("clip"))
    if ref.kind != "arrangement":
        raise CommandError("bad_target", "move_clip needs a timeline clip: t0/a1")
    at = _time(song, p)
    clip, track = ref.clip, ref.track
    start, end = clip.start_time, clip.end_time
    if at == start:
        return {"moved": ref.path, "unchanged": True}
    if at < end and at + (end - start) > start:
        raise CommandError(
            "overlap", "the new place overlaps the clip's own span: move it further"
        )
    name = clip.name
    copy = track.duplicate_clip_to_arrangement(clip, at)
    track.delete_clip(clip)
    return {
        "moved": {"from": _time_out(song, start), "clip": name},
        "clip": _clip_out(song, copy) if copy is not None else None,
    }


def _add_take_lane(song, p):
    track = objects.track(song, p.get("track") or "")
    path = objects.track_path(song, track)
    create = getattr(track, "create_take_lane", None)
    if not path.startswith("t") or create is None:
        raise CommandError("not_supported", f"{path}: this Live cannot add take lanes")
    create()
    return {"track": path, "take_lanes": _take_lanes(track)}


def _create_clip(song, p):
    track = objects.track(song, p.get("track") or "")
    path = objects.track_path(song, track)
    if not path.startswith("t") or not getattr(track, "has_midi_input", False):
        raise CommandError("bad_target", f"{path} is not a MIDI track")
    at = _time(song, p)
    notes, rejected = clips.parse_notes(p.get("notes") or [])
    length = clips._beats(p.get("length_beats"), "length_beats", allow_zero=True)
    length = length or clips.fit_length(song, notes)
    clip = track.create_midi_clip(at, length)
    if notes:
        clip.add_new_notes(tuple(clips._note_spec(n) for n in notes))
    if p.get("name"):
        clip.name = str(p["name"])
    out = {"track": path, "clip": _clip_out(song, clip), "notes_added": len(notes)}
    if rejected:
        out["rejected"] = rejected
    return out


def _delete_clip(song, p):
    track = objects.track(song, p.get("track") or "")
    path = objects.track_path(song, track)
    at = _time(song, p)
    hits = [c for c in track.arrangement_clips if c.start_time == at]
    if not hits:
        starts = [bar_beat(song, c.start_time) for c in track.arrangement_clips]
        raise CommandError(
            "not_found",
            f"no clip starts at {bar_beat(song, at)} on {path}; starts: {starts}",
        )
    clip = hits[0]
    name = clip.name
    if str(p.get("name") or "").strip().casefold() != name.strip().casefold():
        raise CommandError(
            "confirm_name", f"to delete it give its name exactly: {name!r}"
        )
    track.delete_clip(clip)  # the clip object is dead afterwards
    return {"deleted": {"track": path, "name": name, "start": _time_out(song, at)}}


def _add_locator(song, p):
    at = _time(song, p)
    if any(c.time == at for c in song.cue_points):
        raise CommandError("exists", f"a locator is already at {bar_beat(song, at)}")
    _playhead_at(song, at)
    song.set_or_delete_cue()
    cue = next((c for c in song.cue_points if c.time == at), None)
    if cue is None:
        raise CommandError("not_supported", "Live did not add the locator")
    if p.get("name"):
        cue.name = str(p["name"])
    return {"added": _locator_out(song, cue), "note": "the playhead is now there"}


def _rename_locator(song, p):
    cue = _cue(song, p.get("locator"))
    if not p.get("name"):
        raise CommandError("bad_params", "name is required")
    cue.name = str(p["name"])
    return {"renamed": _locator_out(song, cue)}


def _delete_locator(song, p):
    cue = _cue(song, p.get("locator"))
    shown = _locator_out(song, cue)
    _playhead_at(song, cue.time)
    song.set_or_delete_cue()
    return {"deleted": shown}


def _playhead_at(song, beats):
    """Live adds and removes locators at the playhead, and a new playhead position
    only counts from the next tick. If it is elsewhere, move it and ask the MCP
    server to send the command again (code retry); the second call finds it there."""
    if song.current_song_time == beats:
        return
    if song.is_playing:
        raise CommandError(
            "playing", "stop playback first: locators go at the playhead"
        )
    song.current_song_time = beats
    raise CommandError("retry", "the playhead moves on the next tick; send again")


# --- helpers ---------------------------------------------------------------------


def _bar(song):
    return song.signature_numerator * 4.0 / song.signature_denominator


def _time(song, p):
    if p.get("at_bar") not in (None, ""):
        bar = float(p["at_bar"])
        if bar < 1:
            raise CommandError("bad_params", "at_bar counts from 1, like Live")
        return (bar - 1) * _bar(song)
    if p.get("at_beats") not in (None, ""):
        beats = float(p["at_beats"])
        if beats < 0:
            raise CommandError("bad_params", "at_beats must be 0 or more")
        return beats
    raise CommandError("bad_params", "give at_bar (from 1) or at_beats")


def _time_out(song, beats):
    return {"bar_beat": bar_beat(song, beats), "beats": beats}


def _clip_out(song, clip, address=None):
    out = {}
    if address:
        out["address"] = address
    out.update(
        {
            "name": clip.name,
            "start": bar_beat(song, clip.start_time),
            "start_beats": clip.start_time,
            "end_beats": clip.end_time,
        }
    )
    kind = props.get(clip, "is_midi_clip", None)
    if kind is not None:
        out["type"] = "midi" if kind else "audio"
    if props.get(clip, "muted", False):
        out["muted"] = True
    return out


def _take_lanes(track):
    lanes = props.get(track, "take_lanes", None)
    if not lanes:
        return []
    return [
        {
            "index": i,
            "name": props.get(lane, "name", ""),
            "clips": len(list(props.get(lane, "arrangement_clips", []) or [])),
        }
        for i, lane in enumerate(lanes)
    ]


def _locator_out(song, cue):
    return {"name": cue.name, "at": bar_beat(song, cue.time), "beats": cue.time}


def _cue(song, ref):
    text = str(ref or "").strip()
    if not text:
        raise CommandError("bad_params", "locator is required: its name")
    for cue in song.cue_points:
        if cue.name.strip().casefold() == text.casefold():
            return cue
    names = [c.name for c in song.cue_points]
    raise CommandError("not_found", f"no locator {text!r}; locators: {names}")
