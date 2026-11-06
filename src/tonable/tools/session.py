"""live_status, read_set, update_set, transport, undo and scene."""

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field

from tonable import __version__
from tonable.bridge import BridgeError
from tonable.server import call, mcp, read_only
from tonable.tools import changes, empty_to, text


@mcp.tool(annotations=read_only("Live status"))
def live_status() -> dict:
    """Check the connection to Ableton Live and show the open Set.

    Returns whether Live is connected, the Live and Tonable versions, and the Set's
    tempo, time signature and numbers of tracks, return tracks and scenes. When Live
    is not reachable it returns connected=false with the reason and what to do.
    Use it first in a conversation and after any connection error.
    """
    from tonable import server

    try:
        status = server.bridge.request("status")
    except BridgeError as err:
        return {"connected": False, "server_version": __version__, **err.as_dict()}
    out = {"connected": True, "server_version": __version__, **status}
    if status.get("script_version") != __version__:
        out["warning"] = (
            f"The Remote Script in Live is version {status.get('script_version')}, "
            f"the server is {__version__}. Run `tonable install` and restart Live."
        )
    return out


@mcp.tool(annotations=read_only("Read the Set"))
def read_set() -> dict:
    """Overview of the open Live Set: tempo, time signature, loop, tracks, return
    tracks, scenes and locators.

    Each scene lists the clips in its row as {track address: clip name}; empty slots
    are left out. Each track shows its address, name, kind (midi, audio, group) and
    device names. Use read_track for one track's mixer, devices and clips.
    """
    return call("read_set")


@mcp.tool(annotations=changes("Change the Set"))
def update_set(
    tempo: text("BPM, e.g. 92. Empty: unchanged.") = "",
    time_signature: text("e.g. 4/4, 3/4, 6/8. Empty: unchanged.") = "",
    loop: text("Arrangement loop on or off: true / false. Empty: unchanged.") = "",
    loop_start_beats: text("Loop start in beats. Empty: unchanged.") = "",
    loop_length_beats: text("Loop length in beats (16 = four 4/4 bars).") = "",
    metronome: text("true / false. Empty: unchanged.") = "",
    root_note: text(
        "Key root for Live's scale mode: C, F#, Bb. Empty: unchanged."
    ) = "",
    scale: text("Scale name as Live shows it: Major, Minor, Dorian...") = "",
) -> dict:
    """Change the Set's tempo, time signature, Arrangement loop, metronome or key.

    Only the fields you give change; the answer shows the Set's state afterwards.
    One undo step.
    """
    return call(
        "update_set",
        {
            "tempo": tempo,
            "time_signature": time_signature,
            "loop": loop,
            "loop_start_beats": loop_start_beats,
            "loop_length_beats": loop_length_beats,
            "metronome": metronome,
            "root_note": root_note,
            "scale": scale,
        },
    )


@mcp.tool(annotations=changes("Transport"))
def transport(
    action: Annotated[
        Literal[
            "play",
            "stop",
            "continue",
            "fire_clip",
            "stop_track",
            "fire_scene",
            "stop_all_clips",
            "jump",
            "re_enable_automation",
        ],
        Field(description="What to do; see the tool description."),
    ],
    track: text("For fire_clip and stop_track: t0, t1...") = "",
    slot: text("For fire_clip: the slot (scene row) from 0.") = "",
    scene: text("For fire_scene: scene number from 0 or its exact name.") = "",
    time_beats: text("For jump: song position in beats.") = "",
    locator: text("For jump: a locator name instead of time_beats.") = "",
) -> dict:
    """Play, stop or continue; launch a clip (fire_clip track+slot) or a scene
    (fire_scene); stop one track's clips (stop_track) or all clips; jump to a time
    in beats or to a locator; re_enable_automation after a parameter was moved by
    hand or by set_device_params.
    """
    return call(
        "transport",
        {
            "action": action,
            "track": track,
            "slot": slot,
            "scene": scene,
            "time_beats": time_beats,
            "locator": locator,
        },
    )


@mcp.tool(annotations=changes("Undo"))
def undo(
    action: Annotated[
        Literal["undo", "redo"],
        BeforeValidator(empty_to("undo")),
        Field(description="undo (Cmd+Z) or redo (Shift+Cmd+Z)."),
    ] = "undo",
) -> dict:
    """Undo or redo one step in Live, like Cmd+Z. Every Tonable change is one step
    (a batch too). Live's undo history is shared with everyone working in the Set,
    so read the state afterwards to see what changed.
    """
    return call("undo", {"action": action})


@mcp.tool(annotations=changes("Scene"))
def scene(
    action: Annotated[
        Literal["create", "update", "duplicate", "capture"],
        Field(description="create, update (rename, tempo, color), duplicate, capture."),
    ],
    scene: text("For update and duplicate: number from 0 or exact name.") = "",
    index: text("For create: where to insert, from 0. Empty: at the end.") = "",
    name: text("New name.") = "",
    tempo: text("Scene tempo in BPM, or off. Empty: unchanged.") = "",
    color_index: text("Live's color number. Empty: unchanged.") = "",
) -> dict:
    """Create a scene, rename it or set its tempo and color, duplicate it, or capture
    the playing clips into a new scene. Delete scenes with delete (target s2).
    Launch one with transport fire_scene. One undo step.
    """
    return call(
        "scene",
        {
            "action": action,
            "scene": scene,
            "index": index,
            "name": name,
            "tempo": tempo,
            "color_index": color_index,
        },
    )
