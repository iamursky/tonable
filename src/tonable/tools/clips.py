"""read_clip and write_clip: Session clips and their notes."""

from typing import Annotated, Literal

from mcp.types import ToolAnnotations
from pydantic import BeforeValidator, Field, WithJsonSchema

from tonable.server import call, mcp, read_only
from tonable.tools import TrackAddress, changes, empty_to, objects_or_names, text

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
    },
    "required": ["pitch", "start", "length", "velocity"],
}


def _note_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, dict):
        return [value]
    return value


Slot = Annotated[
    int,
    Field(
        description="Clip slot: the scene row, from 0. Example: 0 for the first scene"
    ),
]

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
def read_clip(track: TrackAddress, slot: Slot) -> dict:
    """A Session clip: name, length, loop, and for a MIDI clip every note with pitch
    name and number, start and length in beats, and velocity.

    Use it before changing notes and to check what write_clip did.
    """
    return call("read_clip", {"track": track, "slot": slot})


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
    track: TrackAddress,
    slot: Slot,
    notes: Notes = [],  # noqa: B006 - pydantic copies defaults
    mode: Mode = "replace",
    length_beats: LengthBeats = 0,
    name: ClipName = "",
) -> dict:
    """Create a MIDI clip in a Session slot, or change one, and write its notes.

    An empty slot gets a new clip. mode=replace (default) leaves exactly the given
    notes in the clip; mode=add keeps the existing ones. All of it is one undo step.
    Notes that fail a check come back in "rejected" with the reason; the rest are
    written. Works on MIDI tracks only; read_set shows the tracks and scenes.
    """
    return call(
        "write_clip",
        {
            "track": track,
            "slot": slot,
            "notes": notes,
            "mode": mode,
            "length_beats": length_beats,
            "name": name,
        },
    )


@mcp.tool(annotations=changes("Edit notes", destructive=True))
def edit_notes(
    track: TrackAddress,
    slot: Slot,
    action: Annotated[
        Literal["delete", "transpose", "shift", "quantize", "velocity", "length"],
        Field(description="What to do with the chosen notes."),
    ],
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
) -> dict:
    """Change some notes of a MIDI clip without rewriting it: delete, transpose,
    shift in time, quantize starts to a grid, set velocity or set length.

    Choose notes by start time (from_beats/to_beats) and pitches; with neither, all
    notes. Notes that would leave the MIDI range or the clip start are skipped and
    listed. One undo step. To replace all notes use write_clip.
    """
    return call(
        "edit_notes",
        {
            "track": track,
            "slot": slot,
            "action": action,
            "from_beats": from_beats,
            "to_beats": to_beats,
            "pitches": pitches,
            "semitones": semitones,
            "beats": beats,
            "grid_beats": grid_beats,
            "velocity": velocity,
            "length_beats": length_beats,
        },
    )
