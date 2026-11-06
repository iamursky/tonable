"""What is inside a .adg / .adv preset, read from the file without Live.

A preset is gzip-compressed XML. A rack (GroupDevicePreset) holds its device, macro
names and BranchPresets (chains); each chain holds DevicePresets, which may be racks
again. Drum Rack pads keep their note as ReceivingNote = 128 - MIDI note (a Carbonized
Kit has Kick at 92 = C1, Snare at 90 = D1).

Only files in folders Live's browser shows are read (see docs/plan.md):
the User Library, the packs and the Core Library.
"""

import gzip
import os
import xml.etree.ElementTree as ET
from pathlib import Path

from tonable import cli

SUFFIXES = (".adg", ".adv")
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
CORE_LIBRARY = Path(
    "/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/Core Library"
)


class PresetError(Exception):
    pass


def allowed_folders():
    """The User Library, every pack folder Live knows, and the Core Library."""
    prefs, _ = cli.live_preferences()
    folders = [cli.user_library(prefs), CORE_LIBRARY]
    if prefs is not None:
        try:
            root = ET.parse(Path(prefs) / "Library.cfg").getroot()
        except (OSError, ET.ParseError):
            root = None
        if root is not None:
            for slice_info in root.iter("LibrarySliceInfo"):
                if slice_info.get("Path"):
                    folders.append(Path(slice_info.get("Path")))
            preferred = root.find(".//PreferredFactoryPacksInstallationPath")
            if preferred is not None and preferred.get("Value"):
                folders.append(Path(preferred.get("Value")))
    return [Path(os.path.realpath(f)) for f in folders if f is not None]


def inspect(path, folders=None):
    file = Path(os.path.realpath(os.path.expanduser(str(path))))
    if file.suffix.lower() not in SUFFIXES:
        raise PresetError("only .adg and .adv presets can be read")
    folders = allowed_folders() if folders is None else folders
    if not any(file.is_relative_to(f) for f in folders):
        raise PresetError(
            f"{file} is outside the folders Live's browser shows (User Library, "
            "packs, Core Library)"
        )
    if not file.is_file():
        raise PresetError(f"no file {file}")
    try:
        with gzip.open(file) as f:
            root = ET.parse(f).getroot()
    except (OSError, EOFError, ET.ParseError) as err:
        raise PresetError(f"cannot read {file.name}: {err}") from None
    preset = root[0] if len(root) else None
    if preset is None:
        raise PresetError(f"{file.name} holds no device")
    out = {"file": str(file), "created_by": root.get("Creator")}
    out.update(_preset(preset))
    return out


def _preset(preset):
    """A device preset or a rack preset, with its chains."""
    holder = preset.find("Device")
    device = holder[0] if holder is not None and len(holder) else None
    if device is None:
        return {"device": preset.tag}
    out = {"device": _name(device), "class": device.tag}
    if preset.tag == "GroupDevicePreset":
        out["macros"] = _macros(device)
        chains = []
        branches = preset.find("BranchPresets")
        for i, branch in enumerate(branches if branches is not None else []):
            presets = branch.find("DevicePresets")
            devices = [_preset(p) for p in (presets if presets is not None else [])]
            # An unnamed chain shows its first device's name in Live.
            first = devices[0]["device"] if devices else None
            entry = {"name": _value(branch.find("Name")) or first or f"Chain {i + 1}"}
            note = branch.find("ZoneSettings/ReceivingNote")
            if branch.tag == "DrumBranchPreset" and note is not None:
                entry["note"] = _note_name(128 - int(note.get("Value")))
            entry["devices"] = devices
            chains.append(entry)
        out["pads" if device.tag == "DrumGroupDevice" else "chains"] = chains
    return out


def _macros(device):
    count = device.find("NumVisibleMacroControls")
    visible = int(count.get("Value")) if count is not None else 0
    names = []
    for i in range(visible):
        name = device.find(f"MacroDisplayNames.{i}")
        names.append(_value(name) or f"Macro {i + 1}")
    return names


def _name(device):
    return _value(device.find("UserName")) or device.tag


def _value(element):
    return element.get("Value") if element is not None else None


def _note_name(number):
    return f"{NOTE_NAMES[number % 12]}{number // 12 - 2}"
