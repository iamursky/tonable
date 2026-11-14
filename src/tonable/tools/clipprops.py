"""update_clip and create_audio_clip: clip settings, actions and audio files."""

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field

from tonable.server import call, mcp
from tonable.tools import changes, empty_to, text

ClipAddress = text(
    "The clip: t0/s2 (Session slot 2 of t0) or t0/a1 (the second timeline clip of "
    "t0, see arrangement list). Or give track and slot instead."
)


@mcp.tool(annotations=changes("Change a clip", destructive=True))
def update_clip(
    clip: ClipAddress = "",
    track: text("Track of a Session clip, e.g. t0 (with slot).") = "",
    slot: text("Session slot (scene row) from 0, with track.") = "",
    name: text("New clip name.") = "",
    color_index: text("Live's color number, 0-69.") = "",
    muted: text("Clip deactivated: true / false.") = "",
    looping: text("Loop on or off: true / false.") = "",
    loop_start: text("Loop start in beats.") = "",
    loop_end: text("Loop end in beats.") = "",
    start_marker: text("Start marker in beats.") = "",
    end_marker: text("End marker in beats.") = "",
    time_signature: text("Clip time signature such as 3/4.") = "",
    launch_mode: text("Trigger, Gate, Toggle or Repeat.") = "",
    launch_quantization: text(
        "Global, None, 8 Bars, 4 Bars, 2 Bars, 1 Bar, 1/2, 1/2T, 1/4, 1/4T, 1/8, "
        "1/8T, 1/16, 1/16T or 1/32."
    ) = "",
    legato: text("Legato launch: true / false.") = "",
    velocity_amount: text("How much launch velocity scales the clip, -1 to 1.") = "",
    groove: text("A groove from the pool by number or exact name (see groove).") = "",
    warping: text("Audio: warp on or off: true / false.") = "",
    warp_mode: text(
        "Audio: Beats, Tones, Texture, Re-Pitch, Complex or Complex Pro."
    ) = "",
    gain: text("Audio: gain 0-1 (Live's raw scale; the answer shows dB).") = "",
    pitch_coarse: text("Audio: transpose in semitones, -48 to 48.") = "",
    pitch_fine: text("Audio: detune in cents, -50 to 50.") = "",
    scale_mode: text("Clip scale highlighting on or off: true / false.") = "",
    root_note: text("Clip scale root as a number 0 (C) to 11 (B).") = "",
    scale_name: text("Clip scale name as Live shows it: Major, Minor...") = "",
    ram_mode: text("Audio: load the sample into RAM: true / false.") = "",
    stop_button: text(
        "Session slot: show or hide its stop button (works on an empty slot)."
    ) = "",
    action: Annotated[
        Literal[
            "",
            "fire",
            "stop",
            "crop",
            "duplicate_loop",
            "quantize",
            "clear_envelopes",
            "move_playing_position",
            "add_warp_marker",
            "move_warp_marker",
            "remove_warp_marker",
        ],
        BeforeValidator(empty_to("")),
        Field(description="Optional action to run after the settings."),
    ] = "",
    grid: text(
        "For quantize: None, 1/4, 1/8, 1/8T, 1/8 + 1/8T, 1/16, 1/16T, "
        "1/16 + 1/16T or 1/32."
    ) = "",
    amount: text("For quantize: strength 0-1 (default 1).") = "",
    time_beats: text(
        "For move_playing_position and the warp marker actions: a position in beats."
    ) = "",
    sample_time: text("For add_warp_marker: the sample position in seconds.") = "",
    distance_beats: text("For move_warp_marker: how far to move it, in beats.") = "",
) -> dict:
    """Change a clip's settings and optionally run an action; every field you leave
    empty stays as it is. Works on Session and timeline clips, MIDI and audio.

    Settings: name, color, mute, loop and marker positions, time signature, launch
    mode and quantization, legato, clip scale, groove; for audio also warping,
    warp mode, gain, pitch and RAM mode. Actions: fire, stop, crop to the loop,
    duplicate_loop, quantize (grid, amount), clear_envelopes, move_playing_position,
    and warp markers (add, move, remove). Each field gets a result line with what
    Live holds afterwards; Live keeps the old value for something it refuses and the
    line says so. Loop markers that Live refuses in one order are tried again after
    the others. One undo step.
    """
    return call(
        "update_clip",
        {
            "clip": clip,
            "track": track,
            "slot": slot,
            "name": name,
            "color_index": color_index,
            "muted": muted,
            "looping": looping,
            "loop_start": loop_start,
            "loop_end": loop_end,
            "start_marker": start_marker,
            "end_marker": end_marker,
            "time_signature": time_signature,
            "launch_mode": launch_mode,
            "launch_quantization": launch_quantization,
            "legato": legato,
            "velocity_amount": velocity_amount,
            "groove": groove,
            "warping": warping,
            "warp_mode": warp_mode,
            "gain": gain,
            "pitch_coarse": pitch_coarse,
            "pitch_fine": pitch_fine,
            "scale_mode": scale_mode,
            "root_note": root_note,
            "scale_name": scale_name,
            "ram_mode": ram_mode,
            "stop_button": stop_button,
            "action": action,
            "grid": grid,
            "amount": amount,
            "time_beats": time_beats,
            "sample_time": sample_time,
            "distance_beats": distance_beats,
        },
    )


@mcp.tool(annotations=changes("Create an audio clip"))
def create_audio_clip(
    path: Annotated[
        str,
        Field(
            description=(
                "Absolute path of an audio file (wav, aif, aiff, flac, mp3, ogg, "
                "m4a, aac). ~ is expanded. Library samples: take the file path "
                "from your own file system, not the browser path."
            )
        ),
    ],
    track: text("An audio track, e.g. t3. Needed for a bar; with clip, optional.") = "",
    slot: text("Session: the empty slot (scene row) from 0, with track.") = "",
    clip: text("Session slot by address instead of track and slot: t3/s0.") = "",
    at_bar: text("Arrangement: place the clip at this bar (from 1) instead.") = "",
    at_beats: text("Arrangement: place the clip at this beat instead of a bar.") = "",
    name: text("Clip name. Empty: the file name.") = "",
) -> dict:
    """Put an audio file on an audio track as a Session clip (empty slot) or as a
    timeline clip (at_bar or at_beats). Say the clip's address and its audio details.

    The track must be an audio track; MIDI tracks load samples through load_device.
    Only audio files are accepted. One undo step.
    """
    return call(
        "create_audio_clip",
        {
            "path": path,
            "track": track,
            "slot": slot,
            "clip": clip,
            "at_bar": at_bar,
            "at_beats": at_beats,
            "name": name,
        },
    )
