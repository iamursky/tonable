"""MCP tools, one module per group (see docs/tools.md).

Argument types are shared so every tool explains them the same way. They use
plain JSON types without anyOf; null or "" in an optional field means "not given".
"""

from typing import Annotated

from pydantic import BeforeValidator, Field, WithJsonSchema


def _names(value):
    """null/"" -> [], one string -> [it], {"a": ..} -> its keys; lists unchanged."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return list(value)
    return value


def empty_to(default):
    """A BeforeValidator body: null or "" become `default`."""

    def convert(value):
        return default if value is None or value == "" else value

    return convert


def _flag(value):
    if value is None or value == "":
        return False
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return value


TrackAddress = Annotated[
    str,
    Field(
        description=(
            "Track address: t0 for the first track (numbers from 0), rA for return "
            "track A, m for the master. Example: t2"
        )
    ),
]

ObjectAddress = Annotated[
    str,
    Field(
        description=(
            "Device, rack chain or Drum Rack pad address. Examples: t0/d0 (first "
            "device on t0), t1/d0/c1/d0 (first device in chain 1 of that rack), "
            "t2/d0/pC1 (Drum Rack pad C1), rA/d0, m/d0"
        )
    ),
]

ParameterNames = Annotated[
    list[str],
    BeforeValidator(_names),
    Field(
        description=(
            "Only these parameters, by name as Live shows them. Example: "
            '["Release", "Decay"]. Leave empty for the default view.'
        )
    ),
]

AllParameters = Annotated[
    bool,
    BeforeValidator(_flag),
    Field(description="For a rack: list every parameter, not only the macros."),
]


def _to_text(value):
    """null -> "", true/false -> "true"/"false", numbers -> their text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return f"{value:g}" if isinstance(value, float) else str(value)
    return value


def text(description):
    """An optional field sent as text; empty means "leave unchanged".

    JSON numbers and booleans are accepted too, so a client that sends 120 or true
    for a text field is not refused.
    """
    return Annotated[str, BeforeValidator(_to_text), Field(description=description)]


def objects_list(description, item_schema):
    """A list of objects, checked one by one in Live (a bad item never rejects the
    call). null, "" and a single object are accepted."""

    def convert(value):
        if value is None or value == "":
            return []
        if isinstance(value, dict):
            return [value]
        return value

    return Annotated[
        list[dict],
        BeforeValidator(convert),
        WithJsonSchema(
            {"type": "array", "items": item_schema, "description": description}
        ),
    ]


def changes(title, destructive=False, idempotent=False):
    """Annotations for a tool that changes the Set."""
    from mcp.types import ToolAnnotations

    return ToolAnnotations(
        title=title,
        readOnlyHint=False,
        destructiveHint=destructive,
        idempotentHint=idempotent,
        openWorldHint=False,
    )


def objects_or_names(description):
    """A list of names: one string, numbers or null are accepted too."""

    def convert(value):
        if value is None or value == "":
            return []
        if not isinstance(value, list):
            value = [value]
        return [str(v) for v in value]

    return Annotated[
        list[str], BeforeValidator(convert), Field(description=description)
    ]
