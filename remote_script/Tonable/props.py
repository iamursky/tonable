"""Table-driven properties of Live objects: read them, write them, read them back.

Live's Python API has hundreds of plain properties (a clip's launch mode, a song's
record mode, a track's monitoring state). Instead of one hand-written setter each,
a module lists them as `Prop` rows and `write` does the rest: it converts the value,
refuses what is out of range, writes, reads the value back and says what Live now
holds. Live silently keeps the old value for some invalid writes, so the read-back
is what tells the caller the truth.

Enum properties take the label Live shows ("Gate", "1 Bar") or its number. Where
the object lists its own labels (`choices_attr`), those win over the built-in
`choices`, which are only a fallback for Live versions without the list.
"""

import math
import re
from collections import namedtuple

from .server import CommandError

Prop = namedtuple(
    "Prop",
    "name attr kind lo hi choices choices_attr readonly",
    defaults=(None, None, None, None, False),
)


def prop(name, attr, kind, **kwargs):
    """A row for a property table. kind: bool, int, float, str or enum."""
    return Prop(name, attr, kind, **kwargs)


def given(params, name):
    return params.get(name) not in (None, "")


def as_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ("true", "on", "yes", "1")
    return bool(value)


# --- reading ---------------------------------------------------------------------


def get(obj, name, default=None):
    """An optional Live property. Live raises RuntimeError, not AttributeError, for
    some that an object type lacks (the master track's mute, a return track's arm)."""
    try:
        return getattr(obj, name)
    except Exception:
        return default


def choices(obj, p):
    """[(label, value)] for an enum row, from the object when it lists them.

    Live gives these lists in two shapes: a list of labels (index = value), and, for
    the mixer, a Boost.Python enum class whose `values` map numbers to members. Any
    other shape, or a failure reading it, falls back to the row's own choices."""
    listed = get(obj, p.choices_attr, None) if p.choices_attr else None
    found = _listed_labels(listed)
    return found if found else list((p.choices or {}).items())


def _listed_labels(listed):
    if listed is None:
        return []
    try:
        if isinstance(listed, type):
            values = getattr(listed, "values", None)
            if not isinstance(values, dict):
                return []
            return [
                (str(getattr(v, "name", v)), int(k)) for k, v in sorted(values.items())
            ]
        return [(str(label), i) for i, label in enumerate(listed)]
    except Exception:
        return []


def shown(obj, p, raw):
    """The value as a caller sees it: an enum's label, a number, a flag, a string."""
    if p.kind == "enum":
        for label, value in choices(obj, p):
            if value == raw:
                return label
        return raw
    if p.kind == "bool":
        return bool(raw)
    if p.kind == "float" and isinstance(raw, float) and math.isfinite(raw):
        return round(raw, 6)
    return raw


def read(obj, table, only=None):
    """{name: value} for every property of `table` this Live object has."""
    out = {}
    for p in table:
        if only is not None and p.name not in only:
            continue
        raw = get(obj, p.attr, None)
        if raw is None:
            continue
        out[p.name] = shown(obj, p, raw)
    return out


# --- writing ---------------------------------------------------------------------


def write(obj, table, params, sync=None):
    """Write every property of `table` that `params` names, one result line each.

    A line is {"field", "now"} or {"field", "error"}; "note" says when Live held a
    value other than the one asked for but close to it (its nearest allowed step).
    Fields not named in `params` are untouched. A bad value never stops the others.
    """
    results = []
    for p in table:
        if not given(params, p.name):
            continue
        results.append(write_one(obj, p, params[p.name], sync))
    return results


def write_one(obj, p, requested, sync=None):
    if p.readonly:
        return {"field": p.name, "error": "read-only"}
    if get(obj, p.attr, None) is None:
        return {"field": p.name, "error": "this Live object does not have it"}
    try:
        value = convert(obj, p, requested)
    except CommandError as err:
        return {"field": p.name, "error": str(err)}
    try:
        setattr(obj, p.attr, value)
    except Exception as err:
        return {"field": p.name, "error": _why(err)}
    now_raw = get(obj, p.attr, value)
    if not same(p, now_raw, value) and sync is not None:
        # Some Song properties only show a new value after Live has processed the
        # change (Song.sync_parameter_changes, new in Live 12.4).
        try:
            sync()
        except Exception:
            pass
        now_raw = get(obj, p.attr, value)
    now = shown(obj, p, now_raw)
    out = {"field": p.name, "now": now}
    if not same(p, now_raw, value):
        if p.kind in ("int", "float"):
            out["note"] = (
                f"asked for {requested}; Live holds the nearest value it allows"
            )
        else:
            return {
                "field": p.name,
                "now": now,
                "error": (
                    f"Live still shows {now!r} after the write of {requested!r}: it "
                    "either refused it or applies it a moment later; read it again"
                ),
            }
    return out


def convert(obj, p, requested):
    """The raw value to write for `requested`, or CommandError saying why not."""
    if p.kind == "bool":
        if isinstance(requested, bool):
            return requested
        text = str(requested).strip().lower()
        if text in ("true", "on", "yes", "1"):
            return True
        if text in ("false", "off", "no", "0"):
            return False
        raise CommandError("bad_value", "use true or false")
    if p.kind == "str":
        return str(requested)
    if p.kind in ("int", "float"):
        try:
            number = float(requested)
        except (TypeError, ValueError):
            raise CommandError("bad_value", "give a number") from None
        if not math.isfinite(number):
            raise CommandError("bad_value", "the value must be finite")
        if p.lo is not None and number < p.lo or p.hi is not None and number > p.hi:
            raise CommandError("bad_value", f"must be {_range(p)}")
        if p.kind == "int":
            if number != int(number):
                raise CommandError("bad_value", "give a whole number")
            return int(number)
        return number
    if p.kind == "enum":
        return enum_value(obj, p, requested)
    raise CommandError("bad_value", f"unknown kind {p.kind}")


def enum_value(obj, p, requested):
    options = choices(obj, p)
    if isinstance(requested, bool):
        raise CommandError("bad_value", f"use one of: {_labels(options)}")
    text = _key(requested)
    for label, value in options:
        if _key(label) == text:
            return value
    if re.fullmatch(r"-?\d+", str(requested).strip()):
        number = int(str(requested).strip())
        if any(value == number for _, value in options) or not options:
            return number
    raise CommandError("bad_value", f"use one of: {_labels(options)}")


def same(p, now, wanted):
    if p.kind == "float" or p.kind == "int":
        try:
            return abs(float(now) - float(wanted)) <= 1e-6 * max(
                1.0, abs(float(wanted))
            )
        except (TypeError, ValueError):
            return False
    if p.kind == "bool":
        return bool(now) == bool(wanted)
    return now == wanted


def names(table):
    return [p.name for p in table]


def describe(obj, table):
    """For an error or a help line: each row with its allowed values."""
    out = []
    for p in table:
        line = {"name": p.name, "kind": p.kind}
        if p.kind == "enum":
            line["options"] = [label for label, _ in choices(obj, p)]
        elif p.lo is not None or p.hi is not None:
            line["range"] = _range(p)
        if p.readonly:
            line["readonly"] = True
        out.append(line)
    return out


# --- helpers ---------------------------------------------------------------------


def _key(value):
    return re.sub(r"[\s_\-]+", " ", str(value).strip().casefold())


def _labels(options):
    return ", ".join(label for label, _ in options) or "(none)"


def _range(p):
    lo = "-inf" if p.lo is None else f"{p.lo:g}"
    hi = "inf" if p.hi is None else f"{p.hi:g}"
    return f"{lo} to {hi}"


def _why(err):
    return (
        f"Live refused: {err}" if str(err) else f"Live refused ({type(err).__name__})"
    )
