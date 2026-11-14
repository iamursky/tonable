"""live_api: guarded access to any Live Object Model object. Main thread only.

The curated tools cover what people ask for most; this one reaches the long tail
(a Song property no tool names, a device method, a view setting) by walking from
a root object to the member you want:

    path       song, app, or a Tonable address (t0, rA, m, t0/d1, t0/d0/c1/d0,
               t0/d0/pC1, s2 = scene, t0/s2 = clip slot, t0/a1 = Arrangement
               clip), then optional `.member` steps. A number indexes a list:
               t0.mixer_device.sends.1, song.view.selected_track, song.cue_points.0
    operation  info (list members), get, set, call, list (children of a list)

Rules, all enforced here:
- Names starting with `_` are refused everywhere. There is no import, file, eval
  or module access: only attributes of objects reached from song, app or a Tonable
  address are visible, and only objects whose class lives in the `Live` package
  (see `is_live_object`) are walked into. Anything else is summarised by type.
- `set` and `call` need write=true and run as one undo step. Methods whose names
  start with delete, remove, clear or stop_all also need confirm=true. Undo step
  calls are refused (the tools manage undo themselves).
- Results are JSON-safe: Live objects become {"object", "name", "address"}, long
  lists and strings are cut, nothing else leaks.
- `set` reads the value back: Live silently keeps the old value for some invalid
  writes, so a difference is reported as a warning.

Not verified against a running Live: the traversal, write and confirm rules are
tested against stand-in objects only. Live's own classes are recognised by their
module name (`Live.*`); if a class reports a different module, `info` will show it
as a plain summary and the path will stop there.
"""

import difflib
import math
import re

from . import clipref, objects
from .props import as_bool, get
from .server import CommandError
from .song import find_scene, undo_step

try:
    import Live
except ImportError:  # imported by the tests, outside Live
    Live = None

OPERATIONS = ("info", "get", "set", "call", "list")
MAX_ITEMS = 200
MAX_TEXT = 500
MAX_DEPTH = 3
DEFAULT_LIMIT = 100
MAX_LIMIT = 500
DESTRUCTIVE_PREFIXES = ("delete", "remove", "clear", "stop_all")
BLOCKED_METHODS = ("begin_undo_step", "end_undo_step")
_MEMBER = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_SCENE = re.compile(r"[sS]\d+")
_CLIP = re.compile(r".+/[sSaA]\d+")


def live_api(song, params, app=None):
    operation = params.get("operation")
    if operation not in OPERATIONS:
        raise CommandError(
            "bad_params", "operation must be one of: " + ", ".join(OPERATIONS)
        )
    if app is None:
        app = _application()
    path = str(params.get("path") or "").strip()
    obj = resolve_path(song, app, path)
    name = str(params.get("name") or "").strip()
    handler = {
        "info": _info,
        "get": _get,
        "set": _set,
        "call": _call,
        "list": _list,
    }[operation]
    out = {"path": path, "operation": operation}
    out.update(handler(song, app, obj, name, params))
    return out


# --- is this ours to walk? -----------------------------------------------------


def is_live_object(obj):
    """True for instances of Live's own classes (module Live or Live.*)."""
    module = getattr(type(obj), "__module__", "") or ""
    return module == "Live" or module.startswith("Live.")


def is_sequence(obj):
    if isinstance(obj, (list, tuple)):
        return True
    return (
        is_live_object(obj) and hasattr(obj, "__len__") and hasattr(obj, "__getitem__")
    )


def _application():
    if Live is None:
        return None
    try:
        return Live.Application.get_application()
    except Exception:
        return None


# --- paths -----------------------------------------------------------------------


def resolve_path(song, app, path):
    """The object a path names. Also used for {"ref": path} arguments."""
    text = str(path or "").strip()
    if not text:
        raise CommandError(
            "bad_params", "path is required: song, app, t0, t0/d1, t0.mixer_device ..."
        )
    base, _, chain = text.partition(".")
    obj = _base(song, app, base.strip())
    if chain:
        for segment in chain.split("."):
            obj = _step(obj, segment.strip())
    return obj


def _base(song, app, base):
    if base == "song":
        return song
    if base == "app":
        if app is None:
            raise CommandError(
                "not_found", "the Live application object is unavailable"
            )
        return app
    if _SCENE.fullmatch(base):
        return find_scene(song, base[1:])[1]
    if _CLIP.fullmatch(base):
        ref = clipref.locate(song, base, need_clip=False)
        return ref.slot if ref.kind == "session" else ref.clip
    return objects.resolve(song, base)[1]


def _step(obj, segment):
    if not segment:
        raise CommandError("bad_address", "empty step in the path (two dots in a row?)")
    if segment.isdigit():
        if not is_sequence(obj):
            raise CommandError(
                "bad_target",
                f"{_what(obj)} is not a list, so {segment} cannot index it",
            )
        index = int(segment)
        if index >= len(obj):
            raise CommandError(
                "not_found", f"index {index} is out of range: {len(obj)} item(s)"
            )
        return obj[index]
    member = _member(segment)
    _require_live(obj, member)
    value = _fetch(obj, member)
    if _is_method(value):
        raise CommandError(
            "bad_target", f"{member} is a method: use operation call, not a path step"
        )
    return value


def _member(name):
    if not _MEMBER.fullmatch(name) or name.startswith("_"):
        raise CommandError(
            "forbidden",
            f"{name!r} is not a member name: letters, digits and underscores, "
            "never starting with an underscore",
        )
    return name


def _require_live(obj, what):
    if not is_live_object(obj):
        raise CommandError(
            "forbidden",
            f"{what}: {_what(obj)} is not a Live object, so it is not opened",
        )


def _fetch(obj, member):
    try:
        return getattr(obj, member)
    except AttributeError:
        raise CommandError("not_found", _unknown(obj, member)) from None
    except Exception as err:
        raise CommandError("live_refused", f"reading {member}: {_why(err)}") from None


def _unknown(obj, member):
    similar = difflib.get_close_matches(member, _public(obj), n=5)
    hint = (
        f"; similar: {similar}" if similar else "; use operation info to list members"
    )
    return f"{_what(obj)} has no member {member!r}{hint}"


def _public(obj):
    try:
        return [n for n in dir(obj) if not n.startswith("_")]
    except Exception:
        return []


def _is_method(value):
    return callable(value) and not is_live_object(value)


def _what(obj):
    return type(obj).__name__


# --- operations ------------------------------------------------------------------


def _info(song, app, obj, name, params):
    _require_live(obj, "info")
    members = [n for n in _public(obj) if not name or name.casefold() in n.casefold()]
    offset, limit = _page(params)
    page = members[offset : offset + limit]
    rows = [_member_row(obj, n) for n in page]
    return {
        "object": summary(song, obj),
        "members": rows,
        "total": len(members),
        "offset": offset,
        "more": offset + limit < len(members),
    }


def _member_row(obj, member):
    row = {"name": member}
    try:
        value = getattr(obj, member)
    except Exception as err:
        row.update(kind="property", unreadable=_trim(_why(err)))
        return row
    if _is_method(value):
        row["kind"] = "function"
        doc = _first_line(value)
        if doc:
            row["doc"] = doc
        return row
    row["kind"] = "property"
    row["value"] = {"length": len(value)} if is_sequence(value) else to_json(value, 2)
    declared = getattr(type(obj), member, None)
    if isinstance(declared, property):
        row["writable"] = declared.fset is not None
    return row


def _get(song, app, obj, name, params):
    if not name:
        return {"value": to_json(obj, 0, song)}
    _require_live(obj, name)
    value = _fetch(obj, _member(name))
    if _is_method(value):
        raise CommandError(
            "bad_target", f"{name} is a method: use operation call (write=true)"
        )
    return {"name": name, "value": to_json(value, 0, song)}


def _list(song, app, obj, name, params):
    target = obj
    if name:
        _require_live(obj, name)
        target = _fetch(obj, _member(name))
    if not is_sequence(target):
        raise CommandError(
            "bad_target",
            f"{name or 'the path'} is a {_what(target)}, not a list; use get or info",
        )
    offset, limit = _page(params)
    items = []
    for i in range(offset, min(len(target), offset + limit)):
        item = target[i]
        row = {"index": i}
        if _is_simple(item):
            row["value"] = to_json(item, MAX_DEPTH)
        else:
            row.update(summary(song, item) if is_live_object(item) else _plain(item))
        items.append(row)
    return {
        "name": name or None,
        "items": items,
        "total": len(target),
        "offset": offset,
        "more": offset + limit < len(target),
    }


def _set(song, app, obj, name, params):
    _need_write(params, "set")
    if not name:
        raise CommandError("bad_params", "name is required: the property to set")
    _require_live(obj, name)
    member = _member(name)
    current = _fetch(obj, member)
    if _is_method(current):
        raise CommandError("bad_target", f"{name} is a method: use operation call")
    raw = params.get("value")
    if raw is None or raw == "":
        raise CommandError("bad_params", "value is required")
    if isinstance(raw, str) and raw.startswith("ref:"):
        wanted = resolve_path(song, app, raw[4:])
    else:
        wanted = _coerce(current, raw)
    with undo_step(song):
        try:
            setattr(obj, member, wanted)
        except Exception as err:
            raise CommandError("live_refused", f"setting {name}: {_why(err)}") from None
    now = _fetch(obj, member)
    out = {"name": name, "value": to_json(now, 0, song)}
    if not _same(now, wanted):
        out["warning"] = (
            f"Live now holds {to_json(now, MAX_DEPTH, song)!r}, not what was asked: "
            "it silently keeps the old value for invalid writes, or snapped to a step"
        )
    return out


def _call(song, app, obj, name, params):
    _need_write(params, "call")
    if not name:
        raise CommandError("bad_params", "name is required: the method to call")
    _require_live(obj, name)
    member = _member(name)
    if member in BLOCKED_METHODS:
        raise CommandError("forbidden", f"{member} is managed by Tonable: not callable")
    if member.startswith(DESTRUCTIVE_PREFIXES) and not as_bool(params.get("confirm")):
        raise CommandError(
            "needs_confirm",
            f"{member} removes things: read the target first, then repeat with "
            "confirm=true (one undo step brings it back)",
        )
    method = _fetch(obj, member)
    if not _is_method(method):
        raise CommandError("bad_target", f"{name} is a property: use get or set")
    args = [_argument(song, app, a) for a in _as_list(params.get("args"))]
    with undo_step(song):
        try:
            result = method(*args)
        except CommandError:
            raise
        except TypeError as err:
            doc = _first_line(method)
            raise CommandError(
                "bad_params",
                f"{name} refused the {len(args)} argument(s): {_why(err)}"
                + (f" ({doc})" if doc else ""),
            ) from None
        except Exception as err:
            raise CommandError("live_refused", f"{name}: {_why(err)}") from None
    return {"name": name, "result": to_json(result, 0, song), "args": len(args)}


# --- arguments and values ----------------------------------------------------------


def _need_write(params, operation):
    if not as_bool(params.get("write")):
        raise CommandError(
            "needs_write",
            f"{operation} changes the Set: repeat with write=true if you mean it",
        )


def _as_list(raw):
    if raw in (None, ""):
        return []
    return [raw] if isinstance(raw, dict) else list(raw)


def _argument(song, app, item):
    if isinstance(item, dict):
        if "ref" in item:
            return resolve_path(song, app, item["ref"])
        if "value" in item:
            return _plain_value(item["value"])
        raise CommandError(
            "bad_params", 'an argument is {"value": ...} or {"ref": ...}'
        )
    return _plain_value(item)


def _plain_value(value):
    """Numbers like 3.0 become 3: Live methods taking ints refuse floats."""
    if isinstance(value, float) and math.isfinite(value) and value == int(value):
        return int(value)
    return value


def _coerce(current, value):
    """Text from a client becomes the type the property already has."""
    if not isinstance(value, str):
        return _plain_value(value)
    text = value.strip()
    if isinstance(current, bool):
        return as_bool(text)
    if isinstance(current, int):
        return _number(text, int)
    if isinstance(current, float):
        return _number(text, float)
    if isinstance(current, str):
        return value
    # Unknown current type (None, an enum, an object): guess from the text.
    low = text.lower()
    if low in ("true", "false"):
        return low == "true"
    for kind in (int, float):
        try:
            return kind(text)
        except ValueError:
            continue
    return value


def _number(text, kind):
    try:
        number = float(text)
    except ValueError:
        raise CommandError("bad_value", f"{text!r} is not a number") from None
    if kind is int:
        if number != int(number):
            raise CommandError("bad_value", f"{text!r} is not a whole number")
        return int(number)
    return number


def _same(now, wanted):
    if isinstance(wanted, bool) or isinstance(now, bool):
        return bool(now) == bool(wanted)
    if isinstance(wanted, (int, float)) and isinstance(now, (int, float)):
        return abs(float(now) - float(wanted)) <= 1e-6 * max(1.0, abs(float(wanted)))
    if is_live_object(wanted):
        return now == wanted
    return now == wanted


def _page(params):
    return _int(params, "offset", 0, 0, 10**9), _int(
        params, "limit", DEFAULT_LIMIT, 1, MAX_LIMIT
    )


def _int(params, name, default, low, high):
    raw = params.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        raise CommandError("bad_params", f"{name} must be a whole number") from None
    return max(low, min(high, value))


# --- JSON-safe output ----------------------------------------------------------------


def _is_simple(value):
    return value is None or isinstance(value, (bool, int, float, str))


def to_json(value, depth=0, song=None):
    """A JSON-safe picture of any value. Never raises, never returns a Live object."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        return _trim(value)
    if is_sequence(value):
        if depth >= MAX_DEPTH:
            return {"length": _length(value)}
        out = []
        try:
            total = len(value)
            for item in list(value)[:MAX_ITEMS]:
                out.append(to_json(item, depth + 1, song))
        except Exception as err:
            return {"unreadable": _trim(_why(err))}
        if total > MAX_ITEMS:
            out.append(f"... {total - MAX_ITEMS} more")
        return out
    if is_live_object(value):
        return summary(song, value)
    return _plain(value)


def _plain(value):
    return {"type": type(value).__name__}


def _length(value):
    try:
        return len(value)
    except Exception:
        return None


def summary(song, obj):
    """{"object": class name, "name": ..., "address": ...} for a Live object."""
    out = {"object": _what(obj)}
    name = get(obj, "name", None)
    if isinstance(name, str) and name:
        out["name"] = _trim(name)
    address = address_of(song, obj) if song is not None else None
    if address:
        out["address"] = address
    return out


def address_of(song, obj, depth=0):
    """The Tonable address of a track, scene, device, chain or clip, or None."""
    if depth > 6:
        return None
    try:
        for i, track in enumerate(song.tracks):
            if track == obj:
                return f"t{i}"
        for i, track in enumerate(song.return_tracks):
            if track == obj:
                return "r" + objects.return_letter(i)
        if song.master_track == obj:
            return "m"
        for i, scene in enumerate(song.scenes):
            if scene == obj:
                return f"s{i}"
        parent = get(obj, "canonical_parent", None)
        if parent is None:
            return None
        base = address_of(song, parent, depth + 1)
        if base is None:
            return None
        for attr, letter in (
            ("devices", "d"),
            ("chains", "c"),
            ("clip_slots", "s"),
            ("arrangement_clips", "a"),
        ):
            for i, item in enumerate(get(parent, attr, None) or []):
                if item == obj:
                    return f"{base}/{letter}{i}"
        if get(parent, "clip", None) == obj:
            return base  # a clip lives at its slot's address
    except Exception:
        return None
    return None


def _trim(text):
    text = str(text)
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "..."


def _first_line(fn):
    doc = getattr(fn, "__doc__", None)
    if not isinstance(doc, str):
        return ""
    for line in doc.splitlines():
        if line.strip():
            return _trim(line.strip())[:200]
    return ""


def _why(err):
    return str(err) or type(err).__name__
