"""Addresses for Live objects (see docs/tools.md). Main thread only.

t0            first track (numbers from 0)
rA            return track A
m             master track
t0/d1         second device on t0
t0/d0/c1/d0   first device in the rack's second chain
t0/d0/pC1     the Drum Rack pad on note C1 (C3 = MIDI 60, as Live shows it)
"""

import re

from .server import CommandError

NOTE_NAMES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_NOTE = re.compile(r"([A-Ga-g])([#b]?)(-?\d+)")


def note_number(name):
    """MIDI note for a name like C1, F#-1 or Bb3, in Live's octave numbering."""
    match = _NOTE.fullmatch(name)
    if not match:
        raise CommandError("bad_address", f"{name!r} is not a note name like C1 or F#2")
    letter, accidental, octave = match.groups()
    number = (int(octave) + 2) * 12 + NOTE_NAMES[letter.upper()]
    number += {"#": 1, "b": -1, "": 0}[accidental]
    if not 0 <= number <= 127:
        raise CommandError("bad_address", f"note {name} is outside MIDI notes 0-127")
    return number


def note_name(number):
    """Live's name for a MIDI note: 36 -> C1, 61 -> C#3."""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{names[number % 12]}{number // 12 - 2}"


def return_letter(index):
    return chr(ord("A") + index)


def track_path(song, track):
    """The address of a track object: t3, rB or m."""
    for i, t in enumerate(song.tracks):
        if t == track:
            return f"t{i}"
    for i, t in enumerate(song.return_tracks):
        if t == track:
            return "r" + return_letter(i)
    return "m"


def track(song, ref):
    """The track for `t0`, `rA` or `m`."""
    ref = str(ref).strip()
    if ref == "m":
        return song.master_track
    match = re.fullmatch(r"t(\d+)", ref)
    if match:
        tracks = list(song.tracks)
        i = int(match.group(1))
        if i >= len(tracks):
            raise CommandError("not_found", f"no {ref}: {_range('t', len(tracks))}")
        return tracks[i]
    match = re.fullmatch(r"r([A-Za-z])", ref)
    if match:
        returns = list(song.return_tracks)
        i = ord(match.group(1).upper()) - ord("A")
        if i >= len(returns):
            letters = [return_letter(n) for n in range(len(returns))]
            have = "returns " + ", ".join(letters) if letters else "no return tracks"
            raise CommandError("not_found", f"no {ref}: the Set has {have}")
        return returns[i]
    raise CommandError(
        "bad_address", f"{ref!r} is not a track address: use t0, rA or m"
    )


def resolve(song, path):
    """The object at `path` and the path in canonical form.

    Returns (kind, obj, path) where kind is track, device, chain or pad.
    """
    parts = [p for p in str(path).strip().split("/") if p]
    if not parts:
        raise CommandError("bad_address", "empty address")
    obj = track(song, parts[0])
    kind = "track"
    walked = [parts[0] if parts[0] == "m" else track_path(song, obj)]
    for part in parts[1:]:
        kind, obj = _step(kind, obj, part, "/".join(walked))
        walked.append(part if kind != "pad" else "p" + note_name(obj.note))
    return kind, obj, "/".join(walked)


def _step(kind, obj, part, where):
    if kind in ("track", "chain") and re.fullmatch(r"d\d+", part):
        return "device", _index(list(obj.devices), int(part[1:]), part, where, "d")
    if kind in ("device", "pad") and re.fullmatch(r"c\d+", part):
        chains = list(getattr(obj, "chains", []) or [])
        if kind == "device" and not getattr(obj, "can_have_chains", False):
            raise CommandError("not_found", f"{where} is not a rack: it has no chains")
        return "chain", _index(chains, int(part[1:]), part, where, "c")
    if kind == "device" and part.startswith("p"):
        if not getattr(obj, "can_have_drum_pads", False):
            raise CommandError(
                "not_found", f"{where} is not a Drum Rack: it has no pads"
            )
        number = note_number(part[1:])
        for pad in obj.drum_pads:
            if pad.note == number:
                return "pad", pad
        raise CommandError("not_found", f"{where} has no pad {part}")
    raise CommandError(
        "bad_address",
        f"{part!r} after {where} is not valid: tracks and chains hold devices (d0), "
        "racks hold chains (c0), Drum Racks hold pads (pC1)",
    )


def _index(items, i, part, where, letter):
    if i >= len(items):
        raise CommandError(
            "not_found", f"no {part} in {where}: {_range(letter, len(items))}"
        )
    return items[i]


def _range(letter, count):
    if count == 0:
        return "there are none"
    if count == 1:
        return f"only {letter}0"
    return f"{letter}0-{letter}{count - 1}"
