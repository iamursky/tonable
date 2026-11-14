"""convert_audio: Live's audio-to-MIDI and sample-to-instrument conversions."""

from typing import Annotated, Literal

from pydantic import Field

from tonable.server import call, mcp
from tonable.tools import changes, text


@mcp.tool(annotations=changes("Convert audio"))
def convert_audio(
    action: Annotated[
        Literal[
            "audio_to_midi",
            "to_simpler",
            "to_drum_rack",
            "slices_to_drum_rack",
            "pad_to_track",
            "move_devices_to_drum_rack",
        ],
        Field(description="Which conversion; see the tool description."),
    ],
    clip: text(
        "For audio_to_midi, to_simpler, to_drum_rack: the audio clip, t0/s2 "
        "(Session slot 2 of t0) or t0/a1 (second Arrangement clip of t0)."
    ) = "",
    type: text("For audio_to_midi: harmony, melody or drums.") = "",
    target: text(
        "For slices_to_drum_rack: a Simpler device address (t0/d0). For pad_to_track: "
        "a Drum Rack pad address (t0/d0/pC1)."
    ) = "",
    track: text("For move_devices_to_drum_rack: the track, t0, t1...") = "",
) -> dict:
    """The conversions behind Live's Convert menu. audio_to_midi: an audio clip
    becomes a MIDI clip on a new track (drums, melody or harmony). to_simpler: a new
    MIDI track with a Simpler holding the clip's sample. to_drum_rack: a new track
    with a Drum Rack, the sample on pad C1. slices_to_drum_rack: a sliced Simpler
    becomes a Drum Rack with a pad per slice. pad_to_track: a Drum Rack pad's chain
    gets its own MIDI track. move_devices_to_drum_rack: a track's devices move onto
    pad C1 of a new Drum Rack.

    Live runs the conversion a moment after the answer, so use read_set afterwards to
    find the new track; track numbers after it may shift. MIDI clips and clips that
    are recording are refused. One undo step.
    """
    return call(
        "convert_audio",
        {
            "action": action,
            "clip": clip,
            "type": type,
            "target": target,
            "track": track,
        },
    )
