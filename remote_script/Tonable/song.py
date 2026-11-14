"""The Set as a whole: undo, transport, update_set and scene. Main thread only."""

from . import objects, props
from .server import CommandError

UNDO_ACTIONS = ("undo", "redo")
TRANSPORT_ACTIONS = (
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
)
SCENE_ACTIONS = ("create", "update", "duplicate", "capture")

# Launch and recording quantization as Live numbers them (Live Object Model).
CLIP_TRIGGER_QUANTIZATION = {
    "None": 0,
    "8 Bars": 1,
    "4 Bars": 2,
    "2 Bars": 3,
    "1 Bar": 4,
    "1/2": 5,
    "1/2T": 6,
    "1/4": 7,
    "1/4T": 8,
    "1/8": 9,
    "1/8T": 10,
    "1/16": 11,
    "1/16T": 12,
    "1/32": 13,
}
RECORD_QUANTIZATION = {
    "None": 0,
    "1/4": 1,
    "1/8": 2,
    "1/8T": 3,
    "1/8 + 1/8T": 4,
    "1/16": 5,
    "1/16T": 6,
    "1/16 + 1/16T": 7,
    "1/32": 8,
}
COUNT_IN = {"None": 0, "1 Bar": 1, "2 Bars": 2, "4 Bars": 3}

# Song properties update_set can write, beyond tempo/loop/metronome/key.
SET_PROPS = [
    props.prop("record", "record_mode", "bool"),
    props.prop("overdub", "arrangement_overdub", "bool"),
    props.prop("session_record", "session_record", "bool"),
    props.prop("automation_arm", "session_automation_record", "bool"),
    props.prop("punch_in", "punch_in", "bool"),
    props.prop("punch_out", "punch_out", "bool"),
    props.prop("groove_amount", "groove_amount", "float", lo=0.0),
    props.prop("swing_amount", "swing_amount", "float", lo=0.0, hi=1.0),
    props.prop(
        "clip_trigger_quantization",
        "clip_trigger_quantization",
        "enum",
        choices=CLIP_TRIGGER_QUANTIZATION,
    ),
    props.prop(
        "midi_recording_quantization",
        "midi_recording_quantization",
        "enum",
        choices=RECORD_QUANTIZATION,
    ),
    props.prop("count_in", "count_in_duration", "enum", choices=COUNT_IN),
    props.prop("scale_mode", "scale_mode", "bool"),
    props.prop("select_on_launch", "select_on_launch", "bool"),
    props.prop("exclusive_arm", "exclusive_arm", "bool"),
    props.prop("exclusive_solo", "exclusive_solo", "bool"),
    props.prop("link", "is_ableton_link_enabled", "bool"),
    props.prop(
        "link_start_stop_sync", "is_ableton_link_start_stop_sync_enabled", "bool"
    ),
]
# What Live reports about the Set but does not let a script change.
SET_FACTS = [
    props.prop("song_length_beats", "song_length", "float", readonly=True),
    props.prop("last_event_beats", "last_event_time", "float", readonly=True),
    props.prop("position_beats", "current_song_time", "float", readonly=True),
    props.prop("is_counting_in", "is_counting_in", "bool", readonly=True),
    props.prop("can_capture_midi", "can_capture_midi", "bool", readonly=True),
    props.prop("can_undo", "can_undo", "bool", readonly=True),
    props.prop("can_redo", "can_redo", "bool", readonly=True),
]


class undo_step:
    """Everything inside is one step for Cmd+Z in Live.

    Live's undo steps do not nest (a batch's inner step would close the outer one),
    so only the outermost step talks to Live. Commands run one at a time on Live's
    main thread, so a plain counter is enough.
    """

    depth = 0

    def __init__(self, song):
        self._song = song

    def __enter__(self):
        if undo_step.depth == 0:
            begin = getattr(self._song, "begin_undo_step", None)
            if begin is not None:
                begin()
        undo_step.depth += 1

    def __exit__(self, *exc):
        undo_step.depth -= 1
        if undo_step.depth == 0:
            end = getattr(self._song, "end_undo_step", None)
            if end is not None:
                end()
        return False


def undo(song, params):
    action = params.get("action") or "undo"
    if action not in UNDO_ACTIONS:
        raise CommandError("bad_params", "action must be undo or redo")
    can = song.can_undo if action == "undo" else song.can_redo
    if not can:
        raise CommandError("nothing_to_" + action, f"there is nothing to {action}")
    (song.undo if action == "undo" else song.redo)()
    return {
        "done": action,
        "can_undo": bool(song.can_undo),
        "can_redo": bool(song.can_redo),
    }


def transport(song, params):
    action = params.get("action")
    if action not in TRANSPORT_ACTIONS:
        raise CommandError(
            "bad_params", "action must be one of: " + ", ".join(TRANSPORT_ACTIONS)
        )
    out = {"done": action}
    if action == "play":
        song.start_playing()
    elif action == "stop":
        song.stop_playing()
    elif action == "continue":
        song.continue_playing()
    elif action == "stop_all_clips":
        song.stop_all_clips()
    elif action == "re_enable_automation":
        song.re_enable_automation()
    elif action in ("fire_clip", "stop_clip", "stop_track", "jump_in_clip"):
        track = objects.track(song, _need(params, "track"))
        path = objects.track_path(song, track)
        if not path.startswith("t"):
            raise CommandError("bad_target", f"{path} has no clips to launch")
        if action == "stop_track":
            track.stop_all_clips()
        elif action == "jump_in_clip":
            beats = _number(_need(params, "time_beats"), "time_beats")
            _call(track, "jump_in_running_session_clip", beats)
        else:
            slot = _slot(track, params.get("slot"), path)
            if action == "stop_clip":
                slot.stop()
            else:
                slot.fire()
            out["clip"] = slot.clip.name if slot.has_clip else None
        out["track"] = path
    elif action == "fire_scene":
        index, scene = find_scene(song, params.get("scene"))
        scene.fire()
        out["scene"] = {"index": index, "name": scene.name}
    elif action == "jump":
        out.update(_jump(song, params))
    elif action == "jump_by":
        _call(song, "jump_by", _number(_need(params, "time_beats"), "time_beats"))
    elif action == "next_locator":
        _call(song, "jump_to_next_cue")
    elif action == "previous_locator":
        _call(song, "jump_to_prev_cue")
    elif action == "play_selection":
        _call(song, "play_selection")
    elif action == "tap_tempo":
        _call(song, "tap_tempo")
        out["tempo"] = song.tempo
    elif action == "capture_midi":
        if props.get(song, "can_capture_midi", True) is False:
            raise CommandError(
                "nothing_to_capture", "Live has no recently played MIDI to capture"
            )
        _call(song, "capture_midi")
    elif action == "trigger_session_record":
        _call(song, "trigger_session_record")
    elif action == "back_to_arranger":
        song.back_to_arranger = False
    out["is_playing"] = bool(song.is_playing)
    return out


def _call(obj, name, *args):
    """Call a method that older Live versions may lack."""
    method = getattr(obj, name, None)
    if method is None:
        raise CommandError("not_supported", f"this Live version has no {name}")
    return method(*args)


def update_set(song, params):
    """Tempo, time signature, loop, metronome, key. Only given fields change."""
    changed = []
    with undo_step(song):
        if _given(params, "tempo"):
            song.tempo = _number(params["tempo"], "tempo")
            changed.append("tempo")
        if _given(params, "time_signature"):
            num, den = _signature(params["time_signature"])
            song.signature_numerator = num
            song.signature_denominator = den
            changed.append("time_signature")
        if _given(params, "loop"):
            song.loop = _bool(params["loop"])
            changed.append("loop")
        if _given(params, "loop_start_beats"):
            song.loop_start = _number(params["loop_start_beats"], "loop_start_beats")
            changed.append("loop_start_beats")
        if _given(params, "loop_length_beats"):
            song.loop_length = _number(params["loop_length_beats"], "loop_length_beats")
            changed.append("loop_length_beats")
        if _given(params, "metronome"):
            song.metronome = _bool(params["metronome"])
            changed.append("metronome")
        if _given(params, "root_note"):
            song.root_note = _root_note(params["root_note"])
            changed.append("root_note")
        if _given(params, "scale"):
            song.scale_name = str(params["scale"]).strip()
            changed.append("scale")
        results = props.write(song, SET_PROPS, params)
    changed.extend(r["field"] for r in results if "error" not in r)
    if not changed and not results:
        raise CommandError("bad_params", "nothing to change: give at least one field")
    out = {"changed": changed, **set_state(song)}
    if results:
        out["results"] = results
    return out


def set_state(song):
    out = {
        "tempo": song.tempo,
        "time_signature": f"{song.signature_numerator}/{song.signature_denominator}",
        "loop": {
            "on": bool(song.loop),
            "start_beats": song.loop_start,
            "length_beats": song.loop_length,
        },
        "metronome": bool(getattr(song, "metronome", False)),
    }
    root = getattr(song, "root_note", None)
    if root is not None:
        out["key"] = {
            "root": objects.note_name(int(root) % 12 + 60)[:-1],
            "scale": getattr(song, "scale_name", ""),
        }
    settings = props.read(song, SET_PROPS)
    if settings:
        out["settings"] = settings
    return out


def set_facts(song):
    """Read-only facts about the Set: length, position, what can be undone."""
    return props.read(song, SET_FACTS)


def scene(song, params):
    action = params.get("action")
    if action not in SCENE_ACTIONS:
        raise CommandError(
            "bad_params", "action must be one of: " + ", ".join(SCENE_ACTIONS)
        )
    with undo_step(song):
        if action == "create":
            scenes = list(song.scenes)
            index = params.get("index")
            index = len(scenes) if index in (None, "", -1) else int(index)
            if not 0 <= index <= len(scenes):
                raise CommandError("not_found", f"index must be 0-{len(scenes)}")
            song.create_scene(index)
        elif action == "capture":
            song.capture_and_insert_scene()
            index = list(song.scenes).index(song.view.selected_scene)
        else:
            index, _ = find_scene(song, params.get("scene"))
            if action == "duplicate":
                song.duplicate_scene(index)
                index += 1
        target = list(song.scenes)[index]
        _update_scene(target, params)
    return {"done": action, **_scene_info(index, target)}


def find_scene(song, ref):
    """A scene by index (0) or exact name ("Verse")."""
    scenes = list(song.scenes)
    if ref is None or str(ref).strip() == "":
        raise CommandError("bad_params", "scene is required: an index from 0 or a name")
    text = str(ref).strip()
    if text.lstrip("-").isdigit():
        index = int(text)
        if not 0 <= index < len(scenes):
            raise CommandError(
                "not_found", f"no scene {index}: scenes are 0-{len(scenes) - 1}"
            )
        return index, scenes[index]
    hits = [
        i for i, s in enumerate(scenes) if s.name.strip().casefold() == text.casefold()
    ]
    if len(hits) != 1:
        names = [s.name for s in scenes if s.name]
        what = "no scene named" if not hits else "several scenes named"
        raise CommandError("not_found", f"{what} {text!r}; scenes: {names}")
    return hits[0], scenes[hits[0]]


# --- helpers -----------------------------------------------------------------


def _update_scene(target, params):
    if _given(params, "name"):
        target.name = str(params["name"])
    if _given(params, "color_index"):
        target.color_index = int(params["color_index"])
    if _given(params, "tempo"):
        tempo = params["tempo"]
        if str(tempo).strip().lower() in ("off", "none", "0"):
            target.tempo_enabled = False
        else:
            target.tempo = _number(tempo, "tempo")
            target.tempo_enabled = True
    if _given(params, "time_signature"):
        signature = str(params["time_signature"]).strip().lower()
        if signature in ("off", "none"):
            target.time_signature_enabled = False
        else:
            num, den = _signature(signature)
            target.time_signature_numerator = num
            target.time_signature_denominator = den
            target.time_signature_enabled = True


def _scene_info(index, target):
    out = {"index": index, "name": target.name}
    if getattr(target, "tempo_enabled", False):
        out["tempo"] = target.tempo
    if getattr(target, "time_signature_enabled", False):
        out["time_signature"] = (
            f"{target.time_signature_numerator}/{target.time_signature_denominator}"
        )
    return out


def _jump(song, params):
    if _given(params, "locator"):
        name = str(params["locator"]).strip().casefold()
        cues = [c for c in song.cue_points if c.name.strip().casefold() == name]
        if not cues:
            names = [c.name for c in song.cue_points]
            raise CommandError(
                "not_found", f"no locator {params['locator']!r}; locators: {names}"
            )
        cues[0].jump()
        return {"locator": cues[0].name, "time_beats": cues[0].time}
    time = _number(_need(params, "time_beats"), "time_beats")
    if time < 0:
        raise CommandError("bad_params", "time_beats must be 0 or more")
    song.current_song_time = time
    return {"time_beats": time}


def _slot(track, slot_index, path):
    try:
        index = int(slot_index)
    except (TypeError, ValueError):
        raise CommandError(
            "bad_params", "slot is required: a scene row from 0"
        ) from None
    slots = list(track.clip_slots)
    if not 0 <= index < len(slots):
        raise CommandError(
            "not_found", f"no slot {index} on {path}: slots 0-{len(slots) - 1}"
        )
    return slots[index]


def _given(params, name):
    return params.get(name) not in (None, "")


def _need(params, name):
    if not _given(params, name):
        raise CommandError("bad_params", f"{name} is required")
    return params[name]


def _number(value, name):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise CommandError("bad_params", f"{name} must be a number") from None


def _bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ("true", "on", "yes", "1")
    return bool(value)


def _signature(value):
    text = str(value).replace(" ", "")
    try:
        num, den = (int(part) for part in text.split("/"))
    except ValueError:
        raise CommandError(
            "bad_params", "time_signature must look like 4/4 or 6/8"
        ) from None
    return num, den


def _root_note(value):
    text = str(value).strip()
    if text.isdigit():
        return int(text) % 12
    return objects.note_number(text + "3") % 12
