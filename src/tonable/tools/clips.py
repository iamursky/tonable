"""read_clip and write_clip: Session clips and their notes."""

from typing import Annotated, Literal

from mcp.types import ToolAnnotations
from pydantic import BeforeValidator, Field, WithJsonSchema

from tonable.server import call, mcp, read_only
from tonable.tools import changes, empty_to, objects_or_names, text

NOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "pitch": {
            "type": "string",
            "description": 'MIDI number or note name, C3 = 60. Example: "60" or "C3"',
        },
        "start": {
            "type": "number",
            "description": "Start in beats from the clip start",
        },
        "length": {"type": "number", "description": "Length in beats, more than 0"},
        "velocity": {"type": "number", "description": "1-127"},
        "mute": {"type": "boolean", "description": "Optional: a muted note"},
        "probability": {
            "type": "number",
            "description": "Optional: chance the note plays, 0-1 (default 1)",
        },
        "velocity_deviation": {
            "type": "number",
            "description": "Optional: random velocity range, -127 to 127 (default 0)",
        },
        "release_velocity": {
            "type": "number",
            "description": "Optional: release velocity, 0-127 (default 64)",
        },
    },
    "required": ["pitch", "start", "length", "velocity"],
}


def _note_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, dict):
        return [value]
    return value


Slot = text("Clip slot: the scene row, from 0. Example: 0 for the first scene.")
TrackOrNone = text("Track address of a Session clip, e.g. t0 (with slot).")
ClipAddress = text(
    "A clip by address instead of track and slot: t0/s2 (Session slot 2 of t0) or "
    "t0/a1 (the second timeline clip of t0, see arrangement list)."
)

# Notes are checked one by one in Live, so one bad note never rejects the call.
Notes = Annotated[
    list[dict],
    BeforeValidator(_note_list),
    WithJsonSchema(
        {
            "type": "array",
            "items": NOTE_SCHEMA,
            "description": (
                'Notes to write. Example: [{"pitch": "C3", "start": 0, "length": 1, '
                '"velocity": 100}, {"pitch": "E3", "start": 1, "length": 1, '
                '"velocity": 90}]'
            ),
        }
    ),
]

Mode = Annotated[
    Literal["replace", "add"],
    BeforeValidator(empty_to("replace")),
    Field(
        description=(
            "replace: the clip ends up with exactly these notes (old ones removed). "
            "add: keep the old notes and add these."
        )
    ),
]

LengthBeats = Annotated[
    float,
    BeforeValidator(empty_to(0)),
    Field(
        description=(
            "Clip length in beats (16 = four 4/4 bars). 0 or empty: a new clip gets "
            "whole bars that fit the notes, an existing clip keeps its length."
        )
    ),
]

ClipName = Annotated[
    str,
    BeforeValidator(empty_to("")),
    Field(description="Optional new clip name; empty keeps the current name."),
]


@mcp.tool(annotations=read_only("Read a clip"))
def read_clip(track: TrackOrNone = "", slot: Slot = "", clip: ClipAddress = "") -> dict:
    """A clip, Session (track + slot, or clip t0/s2) or timeline (clip t0/a1): name,
    length, loop, and under settings its color, mute, markers, launch mode and
    quantization, legato, scale, time signature and groove. An audio clip
    adds its file, warp mode, gain, pitch and warp markers. A MIDI clip lists every
    note with pitch name and number, start and length in beats, velocity, and (when
    not default) probability, velocity deviation and release velocity.

    Use it before changing notes and to check what write_clip or update_clip did.
    """
    return call("read_clip", {"track": track, "slot": slot, "clip": clip})


@mcp.tool(
    annotations=ToolAnnotations(
        title="Write a clip",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    )
)
def write_clip(
    track: TrackOrNone = "",
    slot: Slot = "",
    notes: Notes = [],  # noqa: B006 - pydantic copies defaults
    mode: Mode = "replace",
    length_beats: LengthBeats = 0,
    name: ClipName = "",
    clip: ClipAddress = "",
) -> dict:
    """Create a MIDI clip in a Session slot, or change one (also a timeline clip,
    clip t0/a1), and write its notes.

    An empty slot gets a new clip. mode=replace (default) leaves exactly the given
    notes in the clip; mode=add keeps the existing ones. All of it is one undo step.
    Notes that fail a check come back in "rejected" with the reason; the rest are
    written. Works on MIDI tracks only; read_set shows the tracks and scenes. Notes
    may carry probability, velocity_deviation and release_velocity.
    """
    return call(
        "write_clip",
        {
            "track": track,
            "slot": slot,
            "clip": clip,
            "notes": notes,
            "mode": mode,
            "length_beats": length_beats,
            "name": name,
        },
    )


@mcp.tool(annotations=changes("Edit notes", destructive=True))
def edit_notes(
    action: Annotated[
        Literal[
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
        ],
        Field(description="What to do with the chosen notes."),
    ],
    track: TrackOrNone = "",
    slot: Slot = "",
    clip: ClipAddress = "",
    from_beats: text("Only notes starting at or after this beat.") = "",
    to_beats: text("Only notes starting before this beat.") = "",
    pitches: objects_or_names(
        'Only these pitches, e.g. ["C3", "E3"] or ["60"]. Empty: all pitches.'
    ) = [],  # noqa: B006 - pydantic copies defaults
    semitones: text("For transpose: e.g. 12 or -5.") = "",
    beats: text("For shift: move by this many beats, e.g. 0.5 or -1.") = "",
    grid_beats: text("For quantize: grid in beats, e.g. 0.25 for 1/16 notes.") = "",
    velocity: text("For velocity: new velocity 1-127.") = "",
    length_beats: text("For length: new note length in beats.") = "",
    value: text(
        "For probability (0-1), velocity_deviation (-127 to 127) and "
        "release_velocity (0-127)."
    ) = "",
) -> dict:
    """Change some notes of a MIDI clip without rewriting it: delete, transpose,
    shift in time, quantize starts to a grid, set velocity or length, mute or
    unmute, set probability, velocity deviation or release velocity.

    Choose notes by start time (from_beats/to_beats) and pitches; with neither, all
    notes. Notes that would leave the MIDI range or the clip start are skipped and
    listed. One undo step. To replace all notes use write_clip.
    """
    return call(
        "edit_notes",
        {
            "track": track,
            "slot": slot,
            "clip": clip,
            "action": action,
            "from_beats": from_beats,
            "to_beats": to_beats,
            "pitches": pitches,
            "semitones": semitones,
            "beats": beats,
            "grid_beats": grid_beats,
            "velocity": velocity,
            "length_beats": length_beats,
            "value": value,
        },
    )
