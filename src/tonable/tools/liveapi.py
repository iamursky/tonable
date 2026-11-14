"""live_api: get, set or call any member of Live's object model, with guards."""

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field

from tonable.server import call, mcp
from tonable.tools import changes, empty_to, objects_list, text

ARG_SCHEMA = {
    "type": "object",
    "properties": {
        "value": {
            "description": "A number, true/false or text passed to the method",
        },
        "ref": {
            "type": "string",
            "description": (
                "Instead of value: the path or address of a Live object to pass, "
                "e.g. t0/d1 or song.view.selected_track"
            ),
        },
    },
}


@mcp.tool(annotations=changes("Live API", destructive=True))
def live_api(
    path: Annotated[
        str,
        Field(
            description=(
                "The object: song, app, or an address (t0, rA, m, t0/d1, "
                "t0/d0/c1/d0, t0/d0/pC1, s2 = scene, t0/s2 = clip slot, t0/a1 = "
                "Arrangement clip), then optional .member steps; a number indexes "
                "a list. Examples: song.view, t0.mixer_device.sends.1, "
                "t0/s2.clip, song.cue_points.0"
            )
        ),
    ],
    operation: Annotated[
        Literal["info", "get", "set", "call", "list"],
        Field(
            description=(
                "info: members of the object. get: read property name. set: write "
                "property name = value. call: run method name with args. list: the "
                "items of a list property (or of the path itself)."
            )
        ),
    ],
    name: text(
        "The property or method. For info: only members containing this text."
    ) = "",
    value: text("For set: the new value. ref:t0/d1 passes a Live object.") = "",
    args: objects_list(
        'For call: the arguments in order. Example: [{"value": 4}, {"ref": "t0"}]',
        ARG_SCHEMA,
    ) = [],  # noqa: B006 - pydantic copies defaults
    write: Annotated[
        bool,
        BeforeValidator(empty_to(False)),
        Field(description="Must be true for set and call. Reads never need it."),
    ] = False,
    confirm: Annotated[
        bool,
        BeforeValidator(empty_to(False)),
        Field(
            description=(
                "Also needed to call a method starting with delete, remove, clear "
                "or stop_all."
            )
        ),
    ] = False,
    limit: text("For info and list: items per page (default 100, at most 500).") = "",
    offset: text("For info and list: skip this many items.") = "",
) -> dict:
    """Escape hatch to Live's object model for anything the other tools do not
    cover: Song, view, device, clip or mixer properties and methods.

    Start with info on the object to see its members, then get, set or call. Set
    and call need write=true, change one undo step, and say what Live holds after
    (Live silently keeps the old value for some invalid writes). Prefer the
    dedicated tools when one exists; they check more. Results are plain JSON:
    Live objects come back as {object, name, address}. Underscore names, modules
    and files are never reachable.
    """
    return call(
        "live_api",
        {
            "path": path,
            "operation": operation,
            "name": name,
            "value": value,
            "args": args,
            "write": write,
            "confirm": confirm,
            "limit": limit,
            "offset": offset,
        },
    )
