"""arrangement: clips and locators on the timeline."""

from typing import Annotated, Literal

from pydantic import Field

from tonable.server import call, mcp
from tonable.tools import changes, objects_list, text
from tonable.tools.clips import NOTE_SCHEMA


@mcp.tool(annotations=changes("Arrangement", destructive=True))
def arrangement(
    action: Annotated[
        Literal[
            "list",
            "place_scene",
            "copy_clip",
            "create_clip",
            "delete_clip",
            "add_locator",
            "rename_locator",
            "delete_locator",
        ],
        Field(description="What to do; see the tool description."),
    ],
    at_bar: text("Where: bar number from 1, as Live shows it (17 = bar 17).") = "",
    at_beats: text("Where, in beats from the start, instead of at_bar.") = "",
    scene: text("For place_scene: scene number from 0 or its exact name.") = "",
    track: text("For copy_clip, create_clip, delete_clip: t0, t1...") = "",
    slot: text("For copy_clip: the Session slot to copy, from 0.") = "",
    length_beats: text("For create_clip: length in beats. Empty: fit the notes.") = "",
    notes: objects_list("For create_clip: notes, as in write_clip.", NOTE_SCHEMA) = [],  # noqa: B006 - pydantic copies defaults
    name: text(
        "Clip or locator name; for delete_clip the clip's name as a check."
    ) = "",
    locator: text("For rename_locator, delete_locator: the locator's name.") = "",
) -> dict:
    """Work on the Arrangement timeline.

    list: clips per track, locators, loop. place_scene: copy every clip of a Session
    scene to the timeline at a bar, in one undo step (envelopes come along as track
    automation). copy_clip: one Session clip to a bar. create_clip: a MIDI clip on
    the timeline with notes. delete_clip: by track, start and name. add_locator,
    rename_locator, delete_locator. Times answer as bar|beat ("17|1") and beats.
    Live cannot read Arrangement automation back.
    """
    return call(
        "arrangement",
        {
            "action": action,
            "at_bar": at_bar,
            "at_beats": at_beats,
            "scene": scene,
            "track": track,
            "slot": slot,
            "length_beats": length_beats,
            "notes": notes,
            "name": name,
            "locator": locator,
        },
    )
