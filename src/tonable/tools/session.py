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
    scale_mode: text("Highlight scale notes in the MIDI editor: true / false.") = "",
    record: text("Arrangement record on or off: true / false.") = "",
    overdub: text("Arrangement overdub on or off: true / false.") = "",
    session_record: text("Session record on or off: true / false.") = "",
    automation_arm: text("Automation arm (session automation record).") = "",
    punch_in: text("Punch in: true / false.") = "",
    punch_out: text("Punch out: true / false.") = "",
    groove_amount: text("Global groove amount, 0 = off, 1 = 100 %.") = "",
    swing_amount: text("Swing amount 0-1 (older global swing).") = "",
    clip_trigger_quantization: text(
        "Global launch quantization: None, 8 Bars, 4 Bars, 2 Bars, 1 Bar, 1/2, "
        "1/2T, 1/4, 1/4T, 1/8, 1/8T, 1/16, 1/16T, 1/32."
    ) = "",
    midi_recording_quantization: text(
        "Record quantization: None, 1/4, 1/8, 1/8T, 1/8 + 1/8T, 1/16, 1/16T, "
        "1/16 + 1/16T, 1/32."
    ) = "",
    count_in: text("Count-in before recording: None, 1 Bar, 2 Bars, 4 Bars.") = "",
    select_on_launch: text("Select a clip when it is launched: true / false.") = "",
    exclusive_arm: text("Arming one track disarms the others: true / false.") = "",
    exclusive_solo: text("Soloing one track unsolos the others: true / false.") = "",
    link: text("Ableton Link on or off: true / false.") = "",
    link_start_stop_sync: text("Link start/stop sync: true / false.") = "",
) -> dict:
    """Change the Set's tempo, time signature, Arrangement loop, metronome, key,
    recording state (record, overdub, session record, punch, count-in, quantization),
    groove amount, Link and track-arming rules.

    Only the fields you give change; the answer shows the Set's state afterwards,
    with one result line for each recording or behavior field (Live keeps the old
    value for a setting it refuses, and the line says so). One undo step.
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
            "scale_mode": scale_mode,
            "record": record,
            "overdub": overdub,
            "session_record": session_record,
            "automation_arm": automation_arm,
            "punch_in": punch_in,
            "punch_out": punch_out,
            "groove_amount": groove_amount,
            "swing_amount": swing_amount,
            "clip_trigger_quantization": clip_trigger_quantization,
            "midi_recording_quantization": midi_recording_quantization,
            "count_in": count_in,
            "select_on_launch": select_on_launch,
            "exclusive_arm": exclusive_arm,
            "exclusive_solo": exclusive_solo,
            "link": link,
            "link_start_stop_sync": link_start_stop_sync,
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
            "stop_clip",
            "stop_track",
            "fire_scene",
            "stop_all_clips",
            "jump",
            "jump_by",
            "next_locator",
            "previous_locator",
            "jump_in_clip",
            "play_selection",
            "tap_tempo",
            "capture_midi",
            "trigger_session_record",
            "back_to_arranger",
            "re_enable_automation",
        ],
        Field(description="What to do; see the tool description."),
    ],
    track: text("For fire_clip, stop_clip, stop_track, jump_in_clip: t0, t1...") = "",
    slot: text("For fire_clip and stop_clip: the slot (scene row) from 0.") = "",
    scene: text("For fire_scene: scene number from 0 or its exact name.") = "",
    time_beats: text(
        "For jump: song position in beats. For jump_by: beats to move (negative "
        "goes back). For jump_in_clip: beats to jump inside the playing clip."
    ) = "",
    locator: text("For jump: a locator name instead of time_beats.") = "",
) -> dict:
    """Play, stop or continue; launch a clip (fire_clip track+slot, also records
    into an empty slot of an armed track) or a scene (fire_scene); stop one clip
    (stop_clip), one track's clips (stop_track) or all clips; jump to a time in
    beats (jump), by a distance (jump_by), to a locator, or to the next or previous
    locator; jump_in_clip inside the clip a track is playing; play_selection;
    tap_tempo; capture_midi (keep what was just played); trigger_session_record;
    back_to_arranger (leave Session playback); re_enable_automation after a
    parameter was moved by hand or by set_device_params.
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
    time_signature: text("Scene time signature such as 3/4, or off.") = "",
) -> dict:
    """Create a scene, rename it or set its tempo, time signature and color,
    duplicate it, or capture the playing clips into a new scene. Delete scenes with
    delete (target s2). Launch one with transport fire_scene. One undo step.
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
            "time_signature": time_signature,
        },
    )
