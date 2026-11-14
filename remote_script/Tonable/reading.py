"""read_set, read_track and read_device. Main thread only; nothing here changes Live."""

import difflib

from . import edit, objects, params, props, specialized
from . import song as song_module
from .server import CommandError

# Device.type
DEVICE_KINDS = {1: "instrument", 2: "audio_effect", 4: "midi_effect"}


def read_set(song):
    """The Set at a glance: transport, tracks, returns, scenes and their clips."""
    tracks = list(song.tracks)
    scenes = []
    for s, scene in enumerate(song.scenes):
        entry = {"index": s, "name": scene.name}
        if _get(scene, "tempo_enabled", False):
            entry["tempo"] = scene.tempo
        if _get(scene, "time_signature_enabled", False):
            entry["time_signature"] = (
                f"{scene.time_signature_numerator}/{scene.time_signature_denominator}"
            )
        clips = {}
        for t, track in enumerate(tracks):
            slots = list(track.clip_slots)
            if s < len(slots) and slots[s].has_clip:
                clips[f"t{t}"] = slots[s].clip.name
        entry["clips"] = clips
        scenes.append(entry)
    out = {
        "tempo": song.tempo,
        "time_signature": f"{song.signature_numerator}/{song.signature_denominator}",
        "is_playing": bool(song.is_playing),
        "loop": {
            "on": bool(song.loop),
            "start_beats": song.loop_start,
            "length_beats": song.loop_length,
        },
        "tracks": [_track_summary(song, track) for track in tracks],
        "returns": [
            {"path": "r" + objects.return_letter(i), "name": track.name}
            for i, track in enumerate(song.return_tracks)
        ],
        "master": {"path": "m", "name": song.master_track.name},
        "scenes": scenes,
        "locators": [
            {"name": cue.name, "time_beats": cue.time} for cue in song.cue_points
        ],
    }
    settings = props.read(song, song_module.SET_PROPS)
    if settings:
        out["settings"] = settings
    facts = song_module.set_facts(song)
    if facts:
        out["facts"] = facts
    return out


def read_track(song, ref):
    """One track: mixer, routing, the device tree and its clips."""
    track = objects.track(song, ref)
    path = objects.track_path(song, track) if ref != "m" else "m"
    out = _track_summary(song, track)
    out["path"] = path
    out["mixer"] = _mixer(song, track)
    settings = edit.track_settings(track)
    if settings:
        out["settings"] = settings
    routing = _routing(track)
    if routing:
        out["routing"] = routing
    out["devices"] = _devices(track, path)
    clips = [
        _clip(i, slot.clip)
        for i, slot in enumerate(_get(track, "clip_slots", []) or [])
        if slot.has_clip
    ]
    if path.startswith("t"):
        out["session_clips"] = clips
        out["arrangement_clips"] = [
            {"name": c.name, "start_beats": c.start_time, "end_beats": c.end_time}
            for c in _get(track, "arrangement_clips", []) or []
        ]
    return out


def read_device(song, path, wanted=None, all_params=False):
    """A device, chain or pad. Racks show their macros; other devices all parameters.

    `wanted` lists parameter names to show (any device); `all_params` shows every
    parameter of a rack too.
    """
    kind, obj, path = objects.resolve(song, path)
    if kind == "track":
        raise CommandError(
            "bad_address",
            f"{path} is a track: use read_track, or {path}/d0 for a device",
        )
    if kind in ("chain", "pad"):
        out = {"path": path, "kind": kind, "name": obj.name}
        if kind == "pad":
            out["note"] = objects.note_name(obj.note)
        for flag in ("mute", "solo"):
            if _get(obj, flag, False):
                out[flag] = True
        if kind == "chain":
            out["devices"] = _devices(obj, path)
        else:
            out["chains"] = _chains(obj, path)
        return out

    device = obj
    plist = list(device.parameters)
    out = {"path": path, **_device_head(device)}
    if plist:
        out["on"] = _is_on(plist[0])
    settings = specialized.describe(device)
    if settings:
        out["settings"] = settings
    is_rack = bool(_get(device, "can_have_chains", False))
    if is_rack:
        out["macros"] = _macros(device, plist)
        out["chains"] = _chains(device, path)
    if wanted:
        out["parameters"] = _pick(plist, wanted)
    elif all_params or not is_rack:
        # Parameter 0 is Device On, already shown as "on".
        out["parameters"] = [params.describe(p, i) for i, p in enumerate(plist) if i]
    return out


# --- pieces ------------------------------------------------------------------


def _track_summary(song, track):
    out = {"path": objects.track_path(song, track), "name": track.name}
    out["kind"] = _track_kind(track)
    for flag in ("mute", "solo", "arm"):
        if _get(track, flag, False):
            out[flag] = True
    if _get(track, "is_grouped", False) and track.group_track is not None:
        out["group"] = objects.track_path(song, track.group_track)
    devices = list(track.devices)
    if devices:
        out["device_names"] = [d.name for d in devices]
    return out


def _track_kind(track):
    if _get(track, "is_foldable", False):
        return "group"
    if _get(track, "has_midi_input", False):
        return "midi"
    if _get(track, "has_audio_input", False):
        return "audio"
    return "return_or_master"


def _mixer(song, track):
    mixer = track.mixer_device
    out = {
        "volume": params.display(mixer.volume),
        "pan": params.display(mixer.panning),
    }
    sends = list(_get(mixer, "sends", []) or [])
    if sends:
        out["sends"] = [
            {"return": objects.return_letter(i), "level": params.display(send)}
            for i, send in enumerate(sends)
        ]
    return out


def _routing(track):
    out = {}
    for key, attr in (
        ("input", "input_routing_type"),
        ("output", "output_routing_type"),
        ("input_channel", "input_routing_channel"),
        ("output_channel", "output_routing_channel"),
    ):
        value = _get(track, attr, None)
        name = _get(value, "display_name", None)
        if name:
            out[key] = name
    return out


def _clip(slot, clip):
    out = {"slot": slot, "name": clip.name, "length_beats": clip.length}
    out["type"] = "midi" if clip.is_midi_clip else "audio"
    if clip.looping:
        out["looping"] = True
    if clip.is_playing:
        out["playing"] = True
    return out


def _device_head(device):
    out = {"name": device.name, "class": device.class_name}
    kind = DEVICE_KINDS.get(int(_get(device, "type", 0)))
    if kind:
        out["kind"] = kind
    if _get(device, "can_have_drum_pads", False):
        out["rack"] = "drum_rack"
    elif _get(device, "can_have_chains", False):
        out["rack"] = "rack"
    return out


def _devices(holder, prefix):
    """The device tree below a track or chain, with racks opened up."""
    out = []
    for i, device in enumerate(holder.devices):
        path = f"{prefix}/d{i}"
        entry = {"path": path, **_device_head(device)}
        plist = list(device.parameters)
        if plist and not _is_on(plist[0]):
            entry["on"] = False
        if _get(device, "can_have_chains", False):
            entry["chains"] = _chains(device, path)
        out.append(entry)
    return out


def _chains(device, path):
    """Chains of a rack, or the filled pads of a Drum Rack, each with its devices."""
    if _get(device, "can_have_drum_pads", False):
        pads = []
        for pad in device.drum_pads:
            chains = list(pad.chains)
            if not chains:
                continue
            pad_path = f"{path}/p{objects.note_name(pad.note)}"
            entry = {
                "path": pad_path,
                "name": pad.name,
                "note": objects.note_name(pad.note),
                "devices": _devices(chains[0], pad_path + "/c0"),
            }
            if len(chains) > 1:
                entry["chain_count"] = len(chains)
            pads.append(entry)
        return pads
    out = []
    for c, chain in enumerate(_get(device, "chains", []) or []):
        chain_path = f"{path}/c{c}"
        out.append(
            {
                "path": chain_path,
                "name": chain.name,
                "devices": _devices(chain, chain_path),
            }
        )
    return out


def _macros(rack, plist):
    """The rack's visible, mapped macro knobs (Live 12 racks have up to 16)."""
    macros = plist[1:]
    visible = _get(rack, "visible_macro_count", len(macros))
    mapped = list(_get(rack, "macros_mapped", []) or [True] * len(macros))
    out = []
    for i, param in enumerate(macros[:visible]):
        if i < len(mapped) and mapped[i]:
            out.append(params.describe(param, i + 1))
    return out


def _pick(plist, wanted):
    """Parameters by name (case-insensitive), with close matches for typos."""
    by_name = {}
    for i, p in enumerate(plist):
        by_name.setdefault(p.name.casefold(), (i, p))
    out = []
    for name in wanted:
        hit = by_name.get(str(name).strip().casefold())
        if hit:
            out.append(params.describe(hit[1], hit[0]))
        else:
            out.append(
                {
                    "name": name,
                    "error": "no such parameter",
                    "similar": _similar(name, plist),
                }
            )
    return out


def _similar(name, plist):
    # difflib's defaults: up to 3 names, similarity 0.6 or more.
    return difflib.get_close_matches(str(name), [p.name for p in plist])


def _is_on(device_on):
    """Parameter 0 of every device is Device On, quantized Off/On."""
    return device_on.value > device_on.min


def _get(obj, name, default=None):
    """An optional Live property. Live raises RuntimeError, not AttributeError, for
    some that a track type lacks (the master's mute, a return's arm)."""
    try:
        return getattr(obj, name)
    except Exception:
        return default
