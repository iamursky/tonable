"""set_device_params and update_device. Main thread only."""

from . import objects, params, reading
from .server import CommandError
from .song import undo_step


def set_device_params(song, p):
    """Write parameters by name or index; one result line per parameter.

    One bad parameter never stops the others. Values are raw numbers or display
    text ("400 ms", "-6 dB", "On"); each line says what Live shows afterwards.
    """
    kind, device, path = objects.resolve(song, p.get("target") or "")
    if kind != "device":
        raise CommandError("bad_target", f"{path} is a {kind}, not a device")
    wanted = _param_list(p.get("params"))
    if not wanted:
        raise CommandError(
            "bad_params",
            'params is required: [{"param": "Release", "value": "400 ms"}]',
        )
    plist = list(device.parameters)
    results = []
    with undo_step(song):
        for item in wanted:
            results.append(_write_one(plist, item))
    return {"target": path, "device": device.name, "results": results}


def update_device(song, p):
    """Turn on/off, rename, move, store or recall a variation, show macros, or mute
    and solo a chain or pad. Only given fields change."""
    kind, obj, path = objects.resolve(song, p.get("target") or "")
    results = []
    with undo_step(song):
        if kind in ("chain", "pad"):
            for flag in ("mute", "solo"):
                if p.get(flag) not in (None, ""):
                    setattr(obj, flag, _bool(p[flag]))
                    results.append({"field": flag, "now": bool(getattr(obj, flag))})
        elif kind == "device":
            results.extend(_update_device(song, obj, path, p))
        else:
            raise CommandError("bad_target", f"{path} is a track: use update_track")
    if not results:
        raise CommandError("bad_params", "nothing to change: give at least one field")
    return {"target": path, "results": results}


def _update_device(song, device, path, p):
    out = []
    if p.get("on") not in (None, ""):
        switch = device.parameters[0]
        switch.value = switch.max if _bool(p["on"]) else switch.min
        out.append({"field": "on", "now": switch.value > switch.min})
    if p.get("name") not in (None, ""):
        device.name = str(p["name"])
        out.append({"field": "name", "now": device.name})
    if p.get("visible_macros") not in (None, ""):
        out.append(_visible_macros(device, int(p["visible_macros"])))
    variation = p.get("variation")
    if variation not in (None, ""):
        out.append(_variation(device, variation))
    if p.get("move_to") not in (None, ""):
        out.append(_move(song, device, str(p["move_to"]), p.get("index")))
    return out


def _write_one(plist, item):
    ref = item.get("param", item.get("name", item.get("index")))
    value = item.get("value")
    label = str(ref)
    param = _find(plist, ref)
    if param is None:
        names = [x.name for x in plist]
        similar = reading._similar(str(ref), plist) if names else []
        return {"param": label, "error": "no such parameter", "similar": similar}
    label = param.name
    if value in (None, ""):
        return {"param": label, "error": "value is required"}
    if not param.is_enabled:
        return {"param": label, "error": "disabled: a macro or modulation controls it"}
    try:
        raw, note = params.value_for(param, value)
        param.value = raw
    except CommandError as err:
        return {"param": label, "error": str(err)}
    except Exception as err:
        return {"param": label, "error": f"Live refused: {err}"}
    out = {"param": label, "now": params.display(param), "value": param.value}
    if note:
        out["note"] = note
    if int(getattr(param, "automation_state", 0)) == 1:
        out["warning"] = (
            "this parameter has automation, which Live now ignores until "
            "transport re_enable_automation"
        )
    return out


def _find(plist, ref):
    if isinstance(ref, bool) or ref in (None, ""):
        return None
    if isinstance(ref, int) or str(ref).strip().isdigit():
        i = int(ref)
        return plist[i] if 0 <= i < len(plist) else None
    wanted = str(ref).strip().casefold()
    for param in plist:
        if param.name.casefold() == wanted:
            return param
    return None


def _param_list(raw):
    """[{param, value}] from a list, one object, or {"Release": "400 ms"} (also
    when a client wraps that mapping in a list)."""
    if raw in (None, ""):
        return []
    if isinstance(raw, dict):
        raw = [raw]
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if any(key in item for key in ("param", "name", "index")):
            out.append(item)
        else:
            out.extend({"param": k, "value": v} for k, v in item.items())
    return out


def _visible_macros(rack, count):
    if not getattr(rack, "can_have_chains", False):
        return {"field": "visible_macros", "error": "only racks have macros"}
    try:
        while rack.visible_macro_count < count:
            rack.add_macro()
        while rack.visible_macro_count > count:
            rack.remove_macro()
    except Exception as err:
        return {"field": "visible_macros", "error": f"Live refused: {err}"}
    return {"field": "visible_macros", "now": rack.visible_macro_count}


def _variation(rack, action):
    if not hasattr(rack, "store_variation"):
        return {"field": "variation", "error": "only racks have macro variations"}
    text = str(action).strip().lower()
    try:
        if text == "store":
            rack.store_variation()
        elif text.isdigit():
            rack.selected_variation_index = int(text)
            rack.recall_selected_variation()
        else:
            return {
                "field": "variation",
                "error": "use store or a variation number from 0",
            }
    except Exception as err:
        return {"field": "variation", "error": f"Live refused: {err}"}
    return {
        "field": "variation",
        "now": {
            "selected": rack.selected_variation_index,
            "count": rack.variation_count,
        },
    }


def _move(song, device, holder_path, index):
    kind, holder, path = objects.resolve(song, holder_path)
    if kind not in ("track", "chain"):
        return {"field": "move_to", "error": f"{path} cannot hold devices"}
    count = len(list(holder.devices))
    index = count if index in (None, "", -1) else int(index)
    try:
        song.move_device(device, holder, index)
    except Exception as err:
        return {"field": "move_to", "error": f"Live refused: {err}"}
    return {"field": "move_to", "now": f"{path}/d{min(index, count)}"}


def _bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ("true", "on", "yes", "1")
    return bool(value)
