"""Device parameters as the model should see them: name, display text, raw value."""

import math
import re

from .server import CommandError

# DeviceParameter.automation_state
AUTOMATION_STATES = {0: None, 1: "automated", 2: "overridden"}


def describe(param, index=None):
    """One parameter: display text first, then the raw value and its range."""
    out = {}
    if index is not None:
        out["index"] = index
    out["name"] = param.name
    out["display"] = display(param)
    out["value"] = param.value
    if param.is_quantized:
        out["options"] = [str(item) for item in param.value_items]
    else:
        out["min"] = param.min
        out["max"] = param.max
    if not param.is_enabled:
        out["enabled"] = False
    state = AUTOMATION_STATES.get(int(getattr(param, "automation_state", 0)))
    if state:
        out["automation"] = state
    return out


def display(param):
    """The text Live shows for the current value ("262 ms", "-6.0 dB", "On")."""
    try:
        return param.str_for_value(param.value)
    except Exception:
        return str(param)


# --- display text -> raw value ------------------------------------------------

# Base unit for each unit Live shows, and the factor to get there.
UNITS = {
    "hz": ("hz", 1.0),
    "khz": ("hz", 1000.0),
    "ms": ("ms", 1.0),
    "s": ("ms", 1000.0),
    "db": ("db", 1.0),
    "%": ("%", 1.0),
    "": ("", 1.0),
}
_NUMBER = re.compile(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)|-?inf)\s*([a-zA-Z%]*)\s*")
_PAN = re.compile(r"\s*(\d+(?:\.\d*)?)\s*([LR])\s*|\s*(C)\s*", re.I)


def parse_display(text):
    """("number", base unit) for display text like "22.0 kHz", "-inf dB", "25L", "C".

    Pan is a number from left (negative) to right. Returns None if not numeric.
    """
    text = str(text)
    pan = _PAN.fullmatch(text)
    if pan:
        if pan.group(3):
            return 0.0, "pan"
        sign = -1.0 if pan.group(2).upper() == "L" else 1.0
        return sign * float(pan.group(1)), "pan"
    match = _NUMBER.fullmatch(text)
    if not match:
        return None
    number = match.group(1).lower()
    unit = match.group(2).lower()
    if unit not in UNITS:
        return None
    base, factor = UNITS[unit]
    value = float("-inf") if number == "-inf" else float(number) * factor
    return value, base


def value_for(param, requested):
    """(raw value, note or None) for a JSON number (raw) or display text.

    Text is matched against what Live shows: an option name for switches
    ("On", "Sine"), or a number with or without its unit ("400 ms", "-6", "25L").
    Nothing is written here; the caller writes and reads the result back.
    """
    if isinstance(requested, bool):
        if param.is_quantized and len(list(param.value_items)) == 2:
            return (param.max if requested else param.min), None
        requested = "On" if requested else "Off"
    if isinstance(requested, (int, float)):
        raw = float(requested)
        if not math.isfinite(raw):
            raise CommandError("bad_value", "the value must be finite")
        if param.min <= raw <= param.max:
            return raw, None
        # Out of the raw range: most likely meant as shown (-6 for -6 dB, 400 for
        # 400 ms, 30 for 30R), so try it as display text before clamping.
        if not param.is_quantized:
            try:
                return _search(param, f"{raw:g}")
            except CommandError:
                pass
        clamped = min(max(raw, param.min), param.max)
        return clamped, "clamped to the range"
    text = str(requested).strip()
    if param.is_quantized:
        return _option(param, text), None
    return _search(param, text)


def _option(param, text):
    items = [str(item) for item in param.value_items]
    for i, item in enumerate(items):
        if item.strip().casefold() == text.casefold():
            return param.min + i
    if text.lstrip("-").isdigit() and param.min <= int(text) <= param.max:
        return float(int(text))
    raise CommandError("bad_value", f"{text!r} is not an option; options: {items}")


def _search(param, text):
    target = parse_display(text)
    if target is None:
        raise CommandError(
            "bad_value",
            f"{text!r} is not a value like 400 ms, -6 dB, 50 %, 25L or a number",
        )
    want, unit = target
    lo_shown = parse_display(param.str_for_value(param.min))
    hi_shown = parse_display(param.str_for_value(param.max))
    if lo_shown is None or hi_shown is None:
        raise CommandError(
            "bad_value",
            f"{param.name} shows {display(param)!r}; give a raw number from "
            f"{param.min:g} to {param.max:g}",
        )
    shown_unit = lo_shown[1]
    if unit and shown_unit and unit != shown_unit:
        raise CommandError(
            "bad_value",
            f"{param.name} is in {shown_unit or 'plain numbers'}, not {unit}",
        )
    rising = hi_shown[0] >= lo_shown[0]
    lo, hi = param.min, param.max
    low_end, high_end = sorted((lo_shown[0], hi_shown[0]))
    if want <= low_end:
        return (lo if rising else hi), _edge_note(want, low_end)
    if want >= high_end:
        return (hi if rising else lo), _edge_note(want, high_end)
    # Bisect until the floats run out; keep the closest display seen.
    best = (math.inf, param.value)
    while True:
        mid = (lo + hi) / 2
        if mid in (lo, hi):
            break
        shown = parse_display(param.str_for_value(mid))
        if shown is None:
            break
        best = min(best, (abs(shown[0] - want), mid))
        if (shown[0] < want) == rising:
            lo = mid
        else:
            hi = mid
    return best[1], None


def _edge_note(want, edge):
    return None if want == edge else "outside the range: set to the nearest end"
