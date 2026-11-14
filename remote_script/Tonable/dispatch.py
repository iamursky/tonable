"""The command table: what the MCP server may ask Live to do. Main thread only."""

import importlib
import sys

# Reload every command module that is already loaded before importing them. A
# running Live reloads this module last (see __init__._reload), and the list in an
# older __init__ may not know the newer modules.
# Dependencies first: a module that does `from .x import name` keeps the old name if
# x is reloaded after it.
MODULES = (
    "version",
    "params",
    "props",
    "objects",
    "clipref",
    "song",
    "specialized",
    "clipprops",
    "clips",
    "edit",
    "reading",
    "devices",
    "library",
    "envelopes",
    "arrangement",
    "grooves",
    "conversions",
    "application",
    "liveapi",
)
for _name in MODULES:
    _module = sys.modules.get(f"{__package__}.{_name}")
    if _module is not None:
        importlib.reload(_module)

from . import (  # noqa: E402
    application,
    arrangement,
    clipprops,
    clips,
    conversions,
    devices,
    edit,
    envelopes,
    grooves,
    library,
    liveapi,
    reading,
    song,
    specialized,
)
from .server import CommandError  # noqa: E402
from .version import VERSION  # noqa: E402


def commands(surface):
    """Command name -> function of `params`, bound to the running control surface."""
    table = {
        "status": lambda params: status(surface),
        "read_set": lambda params: reading.read_set(surface.song),
        "read_track": lambda params: reading.read_track(
            surface.song, _required(params, "track")
        ),
        "read_device": lambda params: reading.read_device(
            surface.song,
            _required(params, "target"),
            wanted=params.get("params") or None,
            all_params=bool(params.get("all_params")),
        ),
        "read_clip": lambda params: clips.read_clip(
            surface.song, params.get("track"), params.get("slot"), params.get("clip")
        ),
        "update_clip": lambda params: clipprops.update_clip(surface.song, params),
        "create_audio_clip": lambda params: clipprops.create_audio_clip(
            surface.song, params
        ),
        "write_clip": lambda params: clips.write_clip(surface.song, params),
        "undo": lambda params: song.undo(surface.song, params),
        "transport": lambda params: song.transport(surface.song, params),
        "update_set": lambda params: song.update_set(surface.song, params),
        "scene": lambda params: song.scene(surface.song, params),
        "edit_notes": lambda params: clips.edit_notes(surface.song, params),
        "create_track": lambda params: edit.create_track(surface.song, params),
        "update_track": lambda params: edit.update_track(surface.song, params),
        "delete": lambda params: edit.delete(surface.song, params),
        "duplicate": lambda params: edit.duplicate(surface.song, params),
        "set_device_params": lambda params: devices.set_device_params(
            surface.song, params
        ),
        "update_device": lambda params: devices.update_device(surface.song, params),
        "find_in_library": lambda params: library.find_in_library(params),
        "load_device": lambda params: library.load_device(surface.song, params),
        "read_envelope": lambda params: envelopes.read_envelope(surface.song, params),
        "write_envelope": lambda params: envelopes.write_envelope(surface.song, params),
        "arrangement": lambda params: arrangement.arrangement(surface.song, params),
        "configure_device": lambda params: specialized.configure_device(
            surface.song, params
        ),
        "app": lambda params: application.application(surface.song, params, None),
        "groove": lambda params: grooves.groove(surface.song, params),
        "convert_audio": lambda params: conversions.convert_audio(surface.song, params),
        "live_api": lambda params: liveapi.live_api(surface.song, params),
    }
    table["batch"] = lambda params: batch(surface.song, table, params)
    return table


# Never inside a batch: they would nest batches or swap the table mid-run.
NOT_IN_BATCH = ("batch", "reload")


def batch(song_, table, params):
    """Run several commands in order as one undo step; each gets its own result.

    A failed action does not stop the rest unless stop_on_error is set.
    """
    actions = params.get("actions")
    if isinstance(actions, dict):
        actions = [actions]
    if not isinstance(actions, list) or not actions:
        raise CommandError(
            "bad_params", 'actions is required: [{"command": ..., "params": {...}}]'
        )
    stop = bool(params.get("stop_on_error"))
    results = []
    with song.undo_step(song_):
        for i, action in enumerate(actions):
            if not isinstance(action, dict):
                results.append(
                    {"index": i, "ok": False, "error": "an action is an object"}
                )
                continue
            name = action.get("command") or action.get("tool")
            handler = None if name in NOT_IN_BATCH else table.get(name)
            if handler is None:
                results.append(
                    {"index": i, "ok": False, "error": f"unknown command {name!r}"}
                )
            else:
                try:
                    out = handler(action.get("params") or action.get("args") or {})
                    results.append(
                        {"index": i, "command": name, "ok": True, "result": out}
                    )
                except CommandError as err:
                    results.append(
                        {
                            "index": i,
                            "command": name,
                            "ok": False,
                            "code": err.code,
                            "error": str(err),
                        }
                    )
            if stop and not results[-1]["ok"]:
                break
    return {
        "ran": len(results),
        "failed": sum(not r["ok"] for r in results),
        "results": results,
    }


def status(surface):
    """Versions and a one-line picture of the open Set, for live_status and doctor."""
    song = surface.song
    signature = f"{song.signature_numerator}/{song.signature_denominator}"
    return {
        "live_version": surface.live_version,
        "script_version": VERSION,
        "set": {
            "tempo": song.tempo,
            "time_signature": signature,
            "tracks": len(song.tracks),
            "return_tracks": len(song.return_tracks),
            "scenes": len(song.scenes),
            "is_playing": bool(song.is_playing),
        },
    }


def _required(params, name):
    value = params.get(name)
    if value is None or str(value).strip() == "":
        raise CommandError("bad_params", f"{name} is required")
    return str(value).strip()
