"""read_track, create_track, update_track, delete and duplicate."""

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field

from tonable.server import call, mcp, read_only
from tonable.tools import TrackAddress, changes, empty_to, objects_list, text

SEND_SCHEMA = {
    "type": "object",
    "properties": {
        "return": {"type": "string", "description": "Return track letter: A, B..."},
        "db": {"type": "string", "description": 'Send level in dB: "-12", "-inf"'},
    },
    "required": ["return", "db"],
}

Target = Annotated[
    str,
    Field(
        description=(
            "What to act on: a track (t0, rA), a device (t0/d1, t0/d0/c1/d0), a clip "
            "(t0/s2 = the clip in slot 2 of t0) or a scene (s2)."
        )
    ),
]


@mcp.tool(annotations=read_only("Read a track"))
def read_track(track: TrackAddress) -> dict:
    """One track in detail: mixer (volume, pan, sends to each return), input and
    output routing, the device tree with rack chains and Drum Rack pads, Session
    clips by slot, and Arrangement clips.

    Every device comes with its address (t1/d0/c0/d1) for read_device. Also shows
    monitoring, crossfader assignment, freeze state and the playing slot. Works for
    return tracks (rA) and the master (m) too.
    """
    return call("read_track", {"track": track})


@mcp.tool(annotations=changes("Create a track"))
def create_track(
    kind: Annotated[
        Literal["midi", "audio", "return"],
        BeforeValidator(empty_to("midi")),
        Field(description="midi, audio or return (a return track for sends)."),
    ] = "midi",
    name: text("Track name. Empty: Live's default name.") = "",
    index: text("Where to insert, from 0. Empty: after the last track.") = "",
) -> dict:
    """Add a MIDI, audio or return track and say its address. A new return track
    gets the next letter (rB after rA); load an effect on it with load_device and
    send to it with update_track sends. One undo step.
    """
    return call("create_track", {"kind": kind, "name": name, "index": index})


@mcp.tool(annotations=changes("Change a track"))
def update_track(
    track: TrackAddress,
    name: text("New name.") = "",
    volume_db: text('Volume in dB: "-6", "0", "-inf". Empty: unchanged.') = "",
    pan: text('Pan as Live shows it: "C", "25L", "30R" (or -50..50).') = "",
    sends: objects_list(
        'Send levels. Example: [{"return": "A", "db": "-12"}]', SEND_SCHEMA
    ) = [],  # noqa: B006 - pydantic copies defaults
    mute: text("true / false. Empty: unchanged.") = "",
    solo: text("true / false. Empty: unchanged.") = "",
    arm: text("Record arm: true / false. Empty: unchanged.") = "",
    color_index: text("Live's color number. Empty: unchanged.") = "",
    input: text("Input routing by the name Live shows, e.g. All Ins.") = "",
    output: text("Output routing by the name Live shows, e.g. Master.") = "",
    input_channel: text("Input channel by the name Live shows, e.g. 1/2.") = "",
    output_channel: text("Output channel by the name Live shows, e.g. 1/2.") = "",
    monitoring: text("Monitoring: In, Auto or Off.") = "",
    crossfade: text("Crossfader assignment: A, None or B.") = "",
    panning_mode: text("stereo or stereo_split.") = "",
    pan_left: text("Split stereo: left pan, like pan (e.g. 25L).") = "",
    pan_right: text("Split stereo: right pan, like pan (e.g. 30R).") = "",
    folded: text("Group track: true folds it, false opens it.") = "",
    implicit_arm: text("Implicit arm (Push-style arm): true / false.") = "",
    cue_volume_db: text("Master only: the cue/preview volume in dB.") = "",
    crossfader: text("Master only: crossfader position -1 (A) to 1 (B).") = "",
) -> dict:
    """Change a track's name, color, volume, pan (or split-stereo pans), sends,
    mute, solo, arm, monitoring, crossfader assignment, group folding or routing
    (input and output, with channels). On the master it also sets the cue volume
    and crossfader.

    Only the fields you give change, each with its own result line ("now" shows
    what Live displays afterwards; a field that fails says why and the others still
    apply). Works for return tracks (rA) and the master (m). One undo step.
    """
    return call(
        "update_track",
        {
            "track": track,
            "name": name,
            "volume_db": volume_db,
            "pan": pan,
            "sends": sends,
            "mute": mute,
            "solo": solo,
            "arm": arm,
            "color_index": color_index,
            "input": input,
            "output": output,
            "input_channel": input_channel,
            "output_channel": output_channel,
            "monitoring": monitoring,
            "crossfade": crossfade,
            "panning_mode": panning_mode,
            "pan_left": pan_left,
            "pan_right": pan_right,
            "folded": folded,
            "implicit_arm": implicit_arm,
            "cue_volume_db": cue_volume_db,
            "crossfader": crossfader,
        },
    )


@mcp.tool(annotations=changes("Delete", destructive=True))
def delete(
    target: Target,
    name: Annotated[
        str,
        Field(
            description=(
                "The exact name of what you delete, as a check (read it first). "
                "A wrong name deletes nothing and the error shows the real name."
            )
        ),
    ],
) -> dict:
    """Delete a track, return track, device, clip (t0/s2) or scene (s2).

    Give its current name as a check: without the right name nothing is deleted.
    One undo step; undo brings it back.
    """
    return call("delete", {"target": target, "name": name})


@mcp.tool(annotations=changes("Duplicate"))
def duplicate(
    target: Target,
    to_slot: text("For a clip: copy into this empty slot. Empty: the next slot.") = "",
) -> dict:
    """Copy a track, scene, clip or device; the copy goes right after the original
    (a clip can go to another empty slot with to_slot). Says the copy's address.
    One undo step.
    """
    return call("duplicate", {"target": target, "to_slot": to_slot})
