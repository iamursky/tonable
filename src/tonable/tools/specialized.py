"""configure_device: settings and actions that live outside a device's parameters."""

from tonable.server import call, mcp
from tonable.tools import ObjectAddress, changes, objects_list, text

SETTING_SCHEMA = {
    "type": "object",
    "properties": {
        "setting": {
            "type": "string",
            "description": "Setting name from the discovery list, e.g. playback_mode",
        },
        "value": {
            "type": "string",
            "description": 'The label or number to set: "One-Shot", "M/S", 8, true',
        },
    },
    "required": ["setting", "value"],
}

ARG_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Argument name, e.g. beats"},
        "value": {"type": "string", "description": "Its value: 4, Osc 1 Pos, C1"},
    },
    "required": ["name", "value"],
}


@mcp.tool(annotations=changes("Configure a device", destructive=True))
def configure_device(
    target: ObjectAddress,
    settings: objects_list(
        'Settings to set. Example: [{"setting": "global_mode", "value": "M/S"}, '
        '{"setting": "oversample", "value": true}]. Leave empty, with no action, to '
        "list what this target offers.",
        SETTING_SCHEMA,
    ) = [],  # noqa: B006 - pydantic copies defaults
    action: text(
        "One action to run after the settings, e.g. reverse, copy_pad, set_modulation."
    ) = "",
    args: objects_list(
        'Arguments of the action. Example: [{"name": "beats", "value": 4}]',
        ARG_SCHEMA,
    ) = [],  # noqa: B006 - pydantic copies defaults
) -> dict:
    """Read, set and run the device-specific things that are not parameters: Simpler
    playback mode, sample, slices and warp actions; Wavetable voices, oscillator
    wavetables and modulation matrix; Drift and Meld voicing and modulation sources;
    Compressor sidechain source; EQ Eight mode; Hybrid Reverb impulse responses; Roar,
    Shifter, Spectral Resonator and Looper; rack chains, Drum Rack pads and copy_pad;
    a device's collapsed state and A/B compare.

    Call it with only a target to see the settings (current value, options or range)
    and actions that target has on this Live. Settings are checked and read back:
    each gets its own result line, a value Live refuses says so, and the others
    still apply. Targets: a device, a rack chain (t0/d0/c1) or a Drum Rack pad
    (t0/d0/pC1, which writes to every chain on the pad). The actions reverse, crop,
    clear and delete_all_chains change content; one undo step undoes them.
    """
    return call(
        "configure_device",
        {"target": target, "settings": settings, "action": action, "args": args},
    )
