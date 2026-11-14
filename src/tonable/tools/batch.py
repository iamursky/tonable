"""batch: several commands in one request and one undo step."""

from typing import Annotated

from pydantic import BeforeValidator, Field

from tonable.server import call, mcp
from tonable.tools import changes, empty_to, objects_list

# Commands that may walk the browser get Live's long timeout.
LONG = {"find_in_library", "load_device", "app"}

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": "A Tonable tool name, e.g. write_clip, update_track",
        },
        "params": {
            "type": "object",
            "description": "That tool's arguments, as you would pass them to it",
        },
    },
    "required": ["command", "params"],
}


@mcp.tool(annotations=changes("Batch", destructive=True))
def batch(
    actions: objects_list(
        'Actions in order. Example: [{"command": "create_track", "params": {"name": '
        '"Bass"}}, {"command": "write_clip", "params": {"track": "t4", "slot": 0, '
        '"notes": [...]}}]',
        ACTION_SCHEMA,
    ),
    stop_on_error: Annotated[
        bool,
        BeforeValidator(empty_to(False)),
        Field(description="Stop at the first failed action. Default: run them all."),
    ] = False,
) -> dict:
    """Run several Tonable tools in one go, as ONE undo step (one Cmd+Z undoes them
    all). Each action gets its own result; a failed one does not stop the rest
    unless stop_on_error is set. Arguments are passed as given, so use the forms
    the tools document.
    """
    names = {str(a.get("command") or a.get("tool")) for a in actions}
    return call(
        "batch",
        {"actions": actions, "stop_on_error": stop_on_error},
        long=bool(names & LONG),
    )
