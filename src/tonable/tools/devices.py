"""read_device, set_device_params, update_device, find_in_library, load_device."""

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field

from tonable.server import call, mcp, read_only
from tonable.tools import (
    AllParameters,
    ObjectAddress,
    ParameterNames,
    changes,
    empty_to,
    objects_list,
    text,
)

PARAM_SCHEMA = {
    "type": "object",
    "properties": {
        "param": {
            "type": "string",
            "description": "Parameter name as Live shows it (Release), or its index",
        },
        "value": {
            "type": "string",
            "description": (
                'Display text: "400 ms", "-6 dB", "50 %", "On", "Sine"; or a raw number'
            ),
        },
    },
    "required": ["param", "value"],
}


@mcp.tool(annotations=read_only("Read a device"))
def read_device(
    target: ObjectAddress,
    params: ParameterNames = [],  # noqa: B006 - pydantic copies defaults
    all_params: AllParameters = False,
) -> dict:
    """A device's parameters as Live shows them ("262 ms", "-6.0 dB", "On"), with
    raw value and range, plus whether the device is on.

    For a rack: its visible mapped macro knobs and its chains, not every parameter
    (set all_params to see them all). For other devices: all parameters. Give
    params to see only some, by name; a wrong name comes back with similar names.
    A chain or pad address shows its devices instead.
    """
    return call(
        "read_device", {"target": target, "params": params, "all_params": all_params}
    )


@mcp.tool(annotations=changes("Set device parameters", idempotent=True))
def set_device_params(
    target: Annotated[str, Field(description="Device address: t0/d0, t1/d0/c0/d1")],
    params: objects_list(
        'Parameters to set. Example: [{"param": "Release", "value": "400 ms"}, '
        '{"param": "Decay", "value": "1.2 s"}]',
        PARAM_SCHEMA,
    ),
) -> dict:
    """Set one or more parameters of a device or rack macro, by name, in the units
    Live shows ("400 ms", "-6 dB", "50 %", "On") or as raw numbers.

    Each parameter gets its own line: "now" is what Live shows afterwards, a wrong
    name comes back with similar names, and one failure never stops the others. If
    a parameter has automation, Live stops playing it (the answer warns; use
    transport re_enable_automation). One undo step.
    """
    return call("set_device_params", {"target": target, "params": params})


@mcp.tool(annotations=changes("Change a device"))
def update_device(
    target: ObjectAddress,
    on: text("Device on: true / false. Empty: unchanged.") = "",
    name: text("New device name.") = "",
    move_to: text("Move into this track or chain: t2, t0/d0/c1.") = "",
    index: text("With move_to: position from 0. Empty: at the end.") = "",
    visible_macros: text("For a rack: how many macro knobs to show.") = "",
    variation: text("For a rack: store, or a variation number to recall.") = "",
    mute: text("For a chain or pad: true / false.") = "",
    solo: text("For a chain or pad: true / false.") = "",
) -> dict:
    """Turn a device on or off, rename it, move it to another track or chain, set a
    rack's visible macros, store or recall a macro variation, or mute and solo a
    rack chain or Drum Rack pad. Only given fields change. One undo step.
    """
    return call(
        "update_device",
        {
            "target": target,
            "on": on,
            "name": name,
            "move_to": move_to,
            "index": index,
            "visible_macros": visible_macros,
            "variation": variation,
            "mute": mute,
            "solo": solo,
        },
    )


@mcp.tool(annotations=read_only("Find in the library"))
def find_in_library(
    query: Annotated[
        str, Field(description="Words in the name, e.g. electric bass, reverb")
    ],
    limit: Annotated[
        int,
        BeforeValidator(empty_to(0)),
        Field(description="At most this many results. Empty or 0: all results."),
    ] = 0,
    kind: Annotated[
        Literal[
            "any",
            "instrument",
            "audio_effect",
            "midi_effect",
            "sound",
            "drum",
            "max_for_live",
            "plugin",
            "pack",
            "user_library",
        ],
        BeforeValidator(empty_to("any")),
        Field(description="Only one part of the browser; any searches all."),
    ] = "any",
    refresh: Annotated[
        bool,
        BeforeValidator(empty_to(False)),
        Field(description="Walk the browser again after adding presets or packs."),
    ] = False,
) -> dict:
    """Search Live's browser: devices, presets (.adg, .adv) and samples in the
    Core Library, Packs and User Library. Returns paths for load_device.

    The first search walks the whole browser (about 5 s, Live pauses briefly); later
    ones are instant. Exact names come first. Places are not searchable: Live does
    not show them to scripts.
    """
    return call(
        "find_in_library",
        {"query": query, "limit": limit, "kind": kind, "refresh": refresh},
        long=True,
    )


@mcp.tool(annotations=changes("Load a device or preset", destructive=True))
def load_device(
    target: Annotated[
        str,
        Field(description="Track (t0, rA, m) or, for built-in devices, a chain"),
    ],
    item: Annotated[
        str,
        Field(
            description=(
                "A built-in device name (Operator, Reverb, CC Control), a path from "
                "find_in_library (Instruments/Instrument Rack/Bass/Electric Bass "
                "Soft.adg), a preset name, or a file path in the User Library or Packs"
            )
        ),
    ],
    index: text("For built-in devices: position from 0. Empty: at the end.") = "",
) -> dict:
    """Load a device or preset onto a track and return its address and, for a rack,
    its macro names.

    Built-in devices go exactly at index. Presets load like a drag from the
    browser: an instrument replaces the track's instrument (the answer names what
    it replaced). A file outside the User Library and Packs is refused with a hint
    to move it into the User Library. Live selects the track it loads onto.
    """
    return call(
        "load_device", {"target": target, "item": item, "index": index}, long=True
    )


@mcp.tool(annotations=read_only("Inspect a preset file"))
def inspect_preset_file(
    path: Annotated[
        str,
        Field(
            description=(
                "A .adg or .adv file in the User Library, a pack or the Core "
                "Library, e.g. ~/Music/Ableton/User Library/Presets/Example.adg"
            )
        ),
    ],
) -> dict:
    """What a preset file holds, without loading it and without Live: the device,
    a rack's visible macro names, its chains (or Drum Rack pads with their notes)
    and the devices in each, nested racks included.
    """
    from mcp.server.fastmcp.exceptions import ToolError

    from tonable import presets

    try:
        return presets.inspect(path)
    except presets.PresetError as err:
        raise ToolError(str(err)) from None
