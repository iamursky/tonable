"""The `app` command: Live's application, its views, the selection, browser previews.

Actions: info, select, show_view, hide_view, focus_view, toggle_browse, scroll_view,
zoom_view, set_view, show_message, preview, stop_preview. Main thread only.

Dialogs are read only on purpose: `info` reports open_dialog_count and the dialog's
message, but nothing here presses a dialog button. A dialog (save changes, quit, a
missing file) is the user's decision, not an assistant's.

Member names. Verified by Producer Pal's notes
(local/producer-pal/dev/live-api/python-remote-script-api/python-only-candidates.md):
Application.browser, get_build_id, get_variant, show_message, unavailable_features.
From memory of the Live Object Model, NOT verified against a running Live:
Application.get_major/minor/bugfix_version, average_process_usage,
peak_process_usage, open_dialog_count, current_dialog_message, Application.View
(show_view, hide_view, focus_view, toggle_browse, scroll_view, zoom_view,
is_view_visible, available_main_views, NavDirection), Song.View (selected_track,
selected_scene, highlighted_clip_slot, detail_clip, selected_parameter, select_device,
follow_song, draw_mode), Browser.preview_item and stop_preview. Every write is read
back; a member a Live version lacks gives an error line, never a crash.
"""

from . import clipref, library, objects, props
from .server import CommandError
from .song import find_scene

try:
    import Live
except ImportError:  # imported by the tests, outside Live
    Live = None

ACTIONS = (
    "info",
    "select",
    "show_view",
    "hide_view",
    "focus_view",
    "toggle_browse",
    "scroll_view",
    "zoom_view",
    "set_view",
    "show_message",
    "preview",
    "stop_preview",
)

# View names Live documents. available_main_views() may list more.
VIEWS = (
    "Browser",
    "Arranger",
    "Session",
    "Detail",
    "Detail/Clip",
    "Detail/DeviceChain",
)
DIRECTIONS = ("up", "down", "left", "right")

SONG_VIEW = [
    props.prop("follow_song", "follow_song", "bool"),
    props.prop("draw_mode", "draw_mode", "bool"),
]


def get_app():
    """Live's Application object, or None outside Live."""
    if Live is None:
        return None
    return Live.Application.get_application()


def application(song, p, app=None):
    action = p.get("action")
    if action not in ACTIONS:
        raise CommandError("bad_params", "action must be one of: " + ", ".join(ACTIONS))
    app = app if app is not None else get_app()
    if action == "info":
        return info(song, app)
    if action == "select":
        return select(song, p)
    if action == "set_view":
        return set_view(song, p)
    if action == "show_message":
        return show_message(app, p)
    if action in ("preview", "stop_preview"):
        return preview(app, p, action)
    return view_action(app, p, action)


# --- info ------------------------------------------------------------------------


def info(song, app):
    out = {}
    if app is not None:
        out["live"] = _version(app)
        usage = {}
        for key, attr in (
            ("average", "average_process_usage"),
            ("peak", "peak_process_usage"),
        ):
            value = props.get(app, attr, None)
            if value is not None:
                usage[key] = round(value, 4) if isinstance(value, float) else value
        if usage:
            out["cpu"] = usage
        dialogs = {}
        count = props.get(app, "open_dialog_count", None)
        if count is not None:
            dialogs["open"] = count
        if count:
            dialogs["message"] = props.get(app, "current_dialog_message", "")
        if dialogs:
            out["dialogs"] = dialogs
        missing = props.get(app, "unavailable_features", None)
        if missing:
            out["unavailable_features"] = [str(m) for m in missing]
    out["selection"] = selection(song)
    out["view"] = _view_state(song, app)
    return out


def _version(app):
    parts = [
        props.get(app, name, None)
        for name in ("get_major_version", "get_minor_version", "get_bugfix_version")
    ]
    numbers = []
    for part in parts:
        try:
            numbers.append(part())
        except Exception:
            numbers.append(None)
    out = {}
    if all(n is not None for n in numbers):
        out["version"] = ".".join(str(n) for n in numbers)
    for key, name in (("build", "get_build_id"), ("variant", "get_variant")):
        fn = props.get(app, name, None)
        if fn is not None:
            try:
                out[key] = fn()
            except Exception:
                pass
    return out


def _view_state(song, app):
    out = props.read(song.view, SONG_VIEW)
    view = props.get(app, "view", None) if app is not None else None
    if view is not None:
        visible = {}
        for name in VIEWS:
            try:
                visible[name] = bool(view.is_view_visible(name))
            except Exception:
                continue
        if visible:
            out["visible"] = visible
    return out


# --- selection -------------------------------------------------------------------


def selection(song):
    """What is selected in Live, as Tonable addresses where there is one."""
    view = song.view
    out = {}
    track = props.get(view, "selected_track", None)
    if track is not None:
        out["track"] = objects.track_path(song, track)
    scene = props.get(view, "selected_scene", None)
    if scene is not None:
        for i, s in enumerate(song.scenes):
            if s == scene:
                out["scene"] = {"index": i, "name": s.name}
                break
    slot = props.get(view, "highlighted_clip_slot", None)
    if slot is not None:
        found = _slot_path(song, slot)
        if found:
            out["clip_slot"] = found
    clip = props.get(view, "detail_clip", None)
    if clip is not None:
        for t in song.tracks:
            path = clipref.path_of(song, t, clip)
            if path:
                out["detail_clip"] = path
                break
    if track is not None:
        device = props.get(props.get(track, "view", None), "selected_device", None)
        if device is not None:
            out["device"] = _device_path(song, device) or device.name
    param = props.get(view, "selected_parameter", None)
    if param is not None:
        entry = {"name": param.name}
        owner = _parameter_owner(song, param)
        if owner:
            entry["device"] = owner
        out["parameter"] = entry
    return out


def _slot_path(song, slot):
    for t, track in enumerate(song.tracks):
        for s, candidate in enumerate(props.get(track, "clip_slots", []) or []):
            if candidate == slot:
                return f"t{t}/s{s}"
    return None


def walk_devices(song):
    """(address, device) for every device in the Set, racks opened up."""
    holders = [(f"t{i}", t) for i, t in enumerate(song.tracks)]
    holders += [
        ("r" + objects.return_letter(i), t) for i, t in enumerate(song.return_tracks)
    ]
    holders.append(("m", song.master_track))
    for prefix, holder in holders:
        yield from _devices_in(holder, prefix)


def _devices_in(holder, prefix):
    for i, device in enumerate(props.get(holder, "devices", []) or []):
        path = f"{prefix}/d{i}"
        yield path, device
        if props.get(device, "can_have_drum_pads", False):
            for pad in device.drum_pads:
                chains = list(props.get(pad, "chains", []) or [])
                for c, chain in enumerate(chains):
                    pad_path = f"{path}/p{objects.note_name(pad.note)}/c{c}"
                    yield from _devices_in(chain, pad_path)
        elif props.get(device, "can_have_chains", False):
            for c, chain in enumerate(props.get(device, "chains", []) or []):
                yield from _devices_in(chain, f"{path}/c{c}")


def _device_path(song, device):
    for path, candidate in walk_devices(song):
        if candidate == device:
            return path
    return None


def _parameter_owner(song, param):
    for path, device in walk_devices(song):
        for p in props.get(device, "parameters", []) or []:
            if p == param:
                return f"{path}:{param.name}"
    return None


def select(song, p):
    target = str(p.get("target") or "").strip()
    if not target:
        raise CommandError(
            "bad_params",
            "target is required: t0, rA, m, s2, t0/s2, t0/a1, t0/d1 or t0/d1:Release",
        )
    view = song.view
    lines = []
    if ":" in target:
        device_path, name = target.rsplit(":", 1)
        kind, device, path = objects.resolve(song, device_path)
        if kind != "device":
            raise CommandError("bad_target", f"{path} is a {kind}, not a device")
        param = _find_parameter(device, name)
        _select_track(song, view, path, lines)
        lines.append(_assign(view, "selected_parameter", param, f"{path}:{param.name}"))
    elif _is_scene(target):
        index, scene = find_scene(song, target[1:])
        lines.append(_assign(view, "selected_scene", scene, f"s{index}"))
    elif _is_clip(target):
        ref = clipref.locate(song, target, need_clip=False)
        _select_track(song, view, ref.path, lines)
        if ref.slot is not None:
            lines.append(_assign(view, "highlighted_clip_slot", ref.slot, ref.path))
        if ref.clip is not None:
            lines.append(_assign(view, "detail_clip", ref.clip, ref.path))
    else:
        kind, obj, path = objects.resolve(song, target)
        if kind == "track":
            lines.append(_assign(view, "selected_track", obj, path))
        elif kind == "device":
            _select_track(song, view, path, lines)
            try:
                view.select_device(obj)
                lines.append({"field": "device", "now": path})
            except Exception as err:
                lines.append({"field": "device", "error": _why(err)})
        else:
            raise CommandError(
                "bad_target",
                f"{path} is a {kind}: select a track, scene, clip or device",
            )
    return {"target": target, "results": lines, "selection": selection(song)}


def _is_scene(target):
    return len(target) > 1 and target[0] in "sS" and target[1:].isdigit()


def _is_clip(target):
    parts = target.rsplit("/", 1)
    return (
        len(parts) == 2
        and len(parts[1]) > 1
        and parts[1][0] in "sSaA"
        and parts[1][1:].isdigit()
    )


def _select_track(song, view, path, lines):
    track = objects.track(song, path.split("/")[0])
    if props.get(view, "selected_track", None) != track:
        lines.append(_assign(view, "selected_track", track, path.split("/")[0]))


def _assign(view, attr, value, label):
    try:
        setattr(view, attr, value)
    except Exception as err:
        return {"field": attr, "error": _why(err)}
    if props.get(view, attr, None) != value:
        return {
            "field": attr,
            "error": f"Live kept the old selection; {label} not selected",
        }
    return {"field": attr, "now": label}


def _find_parameter(device, name):
    plist = list(device.parameters)
    name = name.strip()
    for p in plist:
        if p.name.casefold() == name.casefold():
            return p
    if name.isdigit() and int(name) < len(plist):
        return plist[int(name)]
    raise CommandError("not_found", f"{device.name} has no parameter {name!r}")


# --- views -----------------------------------------------------------------------


def view_action(app, p, action):
    view = props.get(app, "view", None) if app is not None else None
    if view is None:
        raise CommandError("not_supported", "Live's view is not available here")
    if action == "toggle_browse":
        view.toggle_browse()
        return {"done": action, "visible": _visible(view, "Browser")}
    name = _view_name(view, p.get("view"))
    try:
        if action == "show_view":
            view.show_view(name)
        elif action == "hide_view":
            view.hide_view(name)
        elif action == "focus_view":
            view.focus_view(name)
        else:
            direction = _direction(p.get("direction"))
            modifier = props.as_bool(p.get("modifier"))
            fn = view.scroll_view if action == "scroll_view" else view.zoom_view
            fn(direction, name, modifier)
    except CommandError:
        raise
    except Exception as err:
        raise CommandError("refused", _why(err)) from None
    return {"done": action, "view": name, "visible": _visible(view, name)}


def _visible(view, name):
    try:
        return bool(view.is_view_visible(name))
    except Exception:
        return None


def _view_name(view, ref):
    text = str(ref or "").strip()
    if not text:
        raise CommandError("bad_params", "view is required: " + ", ".join(VIEWS))
    known = list(VIEWS)
    listed = props.get(view, "available_main_views", None)
    try:
        extra = list(listed()) if callable(listed) else list(listed or [])
    except Exception:
        extra = []
    known += [str(v) for v in extra if str(v) not in known]
    for name in known:
        if name.casefold() == text.casefold():
            return name
    raise CommandError("bad_params", f"unknown view {text!r}; views: {known}")


def _direction(value):
    text = str(value or "").strip().lower()
    if text not in DIRECTIONS:
        raise CommandError("bad_params", "direction must be up, down, left or right")
    enum = None
    if Live is not None:
        nav = props.get(Live.Application.Application.View, "NavDirection", None)
        enum = props.get(nav, text, None)
    return enum if enum is not None else DIRECTIONS.index(text)


def set_view(song, p):
    results = props.write(song.view, SONG_VIEW, p)
    if not results:
        raise CommandError(
            "bad_params", "nothing to change: give follow_song or draw_mode"
        )
    return {"results": results, "view": props.read(song.view, SONG_VIEW)}


def show_message(app, p):
    message = str(p.get("message") or "").strip()
    if not message:
        raise CommandError("bad_params", "message is required")
    fn = props.get(app, "show_message", None) if app is not None else None
    if fn is None:
        raise CommandError("not_supported", "this Live has no status-bar message")
    try:
        fn(message)
    except Exception as err:
        raise CommandError("refused", _why(err)) from None
    return {"shown": message}


# --- browser preview -------------------------------------------------------------


def preview(app, p, action):
    browser = props.get(app, "browser", None) if app is not None else None
    if browser is None:
        browser = library.browser()
    if action == "stop_preview":
        try:
            browser.stop_preview()
        except Exception as err:
            raise CommandError("refused", _why(err)) from None
        return {"done": action}
    ref = str(p.get("item") or "").strip()
    if not ref:
        raise CommandError(
            "bad_params", "item is required: a path from find_in_library"
        )
    item, how = library._browser_item(ref, props.as_bool(p.get("refresh")))
    try:
        browser.preview_item(item)
    except Exception as err:
        raise CommandError("refused", _why(err)) from None
    return {"done": action, "previewing": item.name, "how": how}


def _why(err):
    return (
        f"Live refused: {err}" if str(err) else f"Live refused ({type(err).__name__})"
    )
