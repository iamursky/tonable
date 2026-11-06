"""read_envelope and write_envelope: automation in Session clips."""

from typing import Annotated

from pydantic import Field

from tonable.server import call, mcp, read_only
from tonable.tools import TrackAddress, changes, objects_list
from tonable.tools.clips import Slot

POINT_SCHEMA = {
    "type": "object",
    "properties": {
        "time": {"type": "number", "description": "Beats from the clip start"},
        "value": {
            "type": "string",
            "description": 'Display text ("-6 dB", "400 ms", "25L") or a raw number',
        },
        "jump": {
            "type": "boolean",
            "description": "Hold the previous value until this time, then jump",
        },
        "curve": {
            "type": "array",
            "items": {"type": "number"},
            "description": (
                "Optional bend of the segment from this point: x1, y1, x2, y2, each "
                "0-1 (0.5 four times is straight)"
            ),
        },
    },
    "required": ["time", "value"],
}

Parameter = Annotated[
    str,
    Field(
        description=(
            "volume, pan, send A, or a device parameter on the same track as "
            "t0/d0:Release (device address, colon, parameter name)"
        )
    ),
]


@mcp.tool(annotations=read_only("Read an envelope"))
def read_envelope(track: TrackAddress, slot: Slot, parameter: Parameter) -> dict:
    """The automation points of one parameter in a Session clip: time in beats,
    value as Live shows it, raw value, and curve bends. exists=false when the clip
    has no envelope for it.
    """
    return call("read_envelope", {"track": track, "slot": slot, "parameter": parameter})


@mcp.tool(annotations=changes("Write an envelope", destructive=True, idempotent=True))
def write_envelope(
    track: TrackAddress,
    slot: Slot,
    parameter: Parameter,
    points: objects_list(
        'Points in time order. Example: [{"time": 0, "value": "200 ms"}, '
        '{"time": 8, "value": "800 ms"}]. Empty: clear the envelope.',
        POINT_SCHEMA,
    ) = [],  # noqa: B006 - pydantic copies defaults
) -> dict:
    """Replace one parameter's automation in a Session clip with these points, or
    clear it with no points. Values ramp from point to point unless a point has
    jump=true. Works for the mixer (volume, pan, sends) and device parameters,
    including rack macros; MIDI CC is not reachable (use CC Control's Custom A, CC
    64 Sustain, for the pedal). Copy the clip to the Arrangement to keep the
    automation there. One undo step.
    """
    return call(
        "write_envelope",
        {"track": track, "slot": slot, "parameter": parameter, "points": points},
    )
