"""Clip addresses for every tool that works on one clip. Main thread only.

    t0/s2     the Session clip in slot 2 of t0 (slots count from 0, like scenes)
    t0/a1     the second Arrangement clip of t0, in timeline order

Older tools take `track` and `slot` instead; `from_params` accepts both, so a tool
can offer an optional `clip` address next to them.
"""

import re
from collections import namedtuple

from . import objects
from .server import CommandError

ClipRef = namedtuple("ClipRef", "kind track path clip slot index")


def parse(address):
    """(track address, "s" or "a", index) for t0/s2 or t0/a1."""
    match = re.fullmatch(r"\s*(.+?)/([sSaA])(\d+)\s*", str(address or ""))
    if not match:
        raise CommandError(
            "bad_address",
            f"{address!r} is not a clip address: use t0/s2 (Session slot 2 of t0) "
            "or t0/a1 (second Arrangement clip of t0)",
        )
    return match.group(1), match.group(2).lower(), int(match.group(3))


def locate(song, address, need_clip=True):
    """The clip at an address. With need_clip=False an empty Session slot is fine
    (clip is None), for tools that act on the slot itself."""
    track_ref, letter, index = parse(address)
    track = objects.track(song, track_ref)
    base = objects.track_path(song, track)
    if not base.startswith("t"):
        raise CommandError("bad_target", f"{base} has no clips: use a track t0, t1...")
    if letter == "s":
        slots = list(track.clip_slots)
        if not 0 <= index < len(slots):
            raise CommandError(
                "not_found",
                f"no slot {index} on {base}: slots 0-{len(slots) - 1}; "
                "add a scene first",
            )
        slot = slots[index]
        path = f"{base}/s{index}"
        if not slot.has_clip:
            if need_clip:
                raise CommandError("not_found", f"{path} is empty")
            return ClipRef("session", track, path, None, slot, index)
        return ClipRef("session", track, path, slot.clip, slot, index)
    clips = list(getattr(track, "arrangement_clips", []) or [])
    if not 0 <= index < len(clips):
        have = f"a0-a{len(clips) - 1}" if clips else "none"
        raise CommandError(
            "not_found", f"no Arrangement clip {index} on {base}; clips: {have}"
        )
    return ClipRef("arrangement", track, f"{base}/a{index}", clips[index], None, index)


def from_params(song, params, need_clip=True):
    """`clip` (t0/s2, t0/a1) or the older `track` + `slot` pair, as a ClipRef."""
    address = params.get("clip")
    if address not in (None, ""):
        return locate(song, address, need_clip)
    track, slot = params.get("track"), params.get("slot")
    if track in (None, "") or slot in (None, ""):
        raise CommandError(
            "bad_params", "give clip (t0/s2 or t0/a1), or track and slot"
        )
    try:
        slot = int(slot)
    except (TypeError, ValueError):
        raise CommandError("bad_params", "slot must be a scene number from 0") from None
    return locate(song, f"{str(track).strip()}/s{slot}", need_clip)


def path_of(song, track, clip):
    """The address of a clip object on a track: t0/s2 or t0/a1, or None."""
    base = objects.track_path(song, track)
    for i, slot in enumerate(getattr(track, "clip_slots", []) or []):
        if slot.has_clip and slot.clip == clip:
            return f"{base}/s{i}"
    for i, other in enumerate(getattr(track, "arrangement_clips", []) or []):
        if other == clip:
            return f"{base}/a{i}"
    return None


# --- the older track + slot form, shared by the clip tools --------------------------


class Existing:
    """A stand-in slot for a clip that lives on the timeline, so code written for a
    Session slot (has_clip, clip) works on it too."""

    has_clip = True

    def __init__(self, clip):
        self.clip = clip


def slot_for(song, track_ref, slot_index):
    """(track, slot, where) for `t0` and a scene row; errors name the problem."""
    if track_ref is None or str(track_ref).strip() == "":
        raise CommandError("bad_params", "track is required (t0)")
    track = objects.track(song, track_ref)
    path = objects.track_path(song, track)
    if not path.startswith("t"):
        raise CommandError(
            "bad_target", f"{path} has no clip slots: use a track t0, t1..."
        )
    try:
        index = int(slot_index)
    except (TypeError, ValueError):
        raise CommandError("bad_params", "slot must be a scene number from 0") from None
    slots = list(track.clip_slots)
    if not 0 <= index < len(slots):
        raise CommandError(
            "not_found",
            f"no slot {index} on {path}: the Set has {len(slots)} scenes (slots 0-"
            f"{len(slots) - 1}); add a scene first",
        )
    return track, slots[index], f"{path} slot {index}"


def resolve(song, params):
    """(track, slot, where) from `clip` (t0/s2 or t0/a1) or `track` + `slot`.

    An Arrangement clip comes back as an Existing slot; an empty Session slot is
    returned as it is, so a writer can create the clip there."""
    address = params.get("clip")
    if address in (None, ""):
        return slot_for(song, params.get("track"), params.get("slot"))
    ref = locate(song, address, need_clip=False)
    if ref.kind == "arrangement":
        return ref.track, Existing(ref.clip), ref.path
    return ref.track, ref.slot, ref.path


def address(song, track, clip, slot_index=None):
    """How an answer names a clip: {"clip": "t0/s2", "slot": 2} or {"clip": "t0/a1"}."""
    path = path_of(song, track, clip)
    out = {}
    if path:
        out["clip"] = path
    if slot_index not in (None, ""):
        out["slot"] = int(slot_index)
    elif path and "/s" in path:
        out["slot"] = int(path.rsplit("/s", 1)[1])
    return out
