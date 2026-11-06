"""find_in_library and load_device. Main thread only.

The browser tree is walked once and kept (stage 0: 60 115 items in 5.2 s); `refresh`
walks it again. Places are left out: Live 12.4 does not show them to scripts
(see docs/plan.md), so presets live in the User Library, Packs and the Core Library.
"""

import os
import time

from . import objects, reading
from .server import CommandError
from .song import undo_step

try:
    import Live
except ImportError:  # imported by the tests, outside Live
    Live = None

# Browser attribute -> the name used in paths and answers.
ROOTS = (
    ("instruments", "Instruments"),
    ("audio_effects", "Audio Effects"),
    ("midi_effects", "MIDI Effects"),
    ("sounds", "Sounds"),
    ("drums", "Drums"),
    ("max_for_live", "Max for Live"),
    ("plugins", "Plug-ins"),
    ("packs", "Packs"),
    ("user_library", "User Library"),
    ("current_project", "Current Project"),
)
KINDS = {
    "instrument": "Instruments",
    "audio_effect": "Audio Effects",
    "midi_effect": "MIDI Effects",
    "sound": "Sounds",
    "drum": "Drums",
    "max_for_live": "Max for Live",
    "plugin": "Plug-ins",
    "pack": "Packs",
    "user_library": "User Library",
}
SUFFIXES = (".adg", ".adv", ".amxd", ".aupreset", ".fxp")
# Live Sets in packs (demo songs) are loadable but not onto a track.
SETS = (".als",)
# This file is <User Library>/Remote Scripts/Tonable/library.py once installed.
_HERE = os.path.dirname(os.path.abspath(__file__))
USER_LIBRARY = os.path.dirname(os.path.dirname(_HERE))

_cache = {"items": None, "built": None, "seconds": None}


def browser():
    return Live.Application.get_application().browser


def index(refresh=False):
    """[(root name, path, item)] for every loadable item, walked once."""
    if _cache["items"] is None or refresh:
        started = time.perf_counter()
        items = []
        b = browser()
        for attr, label in ROOTS:
            root = getattr(b, attr, None)
            if root is not None:
                _walk(root, label, items)
        _cache.update(
            items=items,
            built=time.strftime("%H:%M:%S"),
            seconds=round(time.perf_counter() - started, 1),
        )
    return _cache["items"]


def _walk(item, path, out):
    for child in item.children:
        child_path = f"{path}/{child.name}"
        if child.is_loadable and not plain(child.name).endswith(SETS):
            out.append((path.split("/", 1)[0], child_path, child))
        # Folders hold items, and a device's children are its presets.
        _walk(child, child_path, out)


def plain(name):
    text = str(name).strip().casefold()
    for suffix in SUFFIXES:
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def find_in_library(p):
    query = str(p.get("query") or "").strip()
    if not query:
        raise CommandError("bad_params", "query is required, e.g. Electric Bass")
    limit = p.get("limit")
    try:
        limit = int(limit) if limit not in (None, "") else 0
    except (TypeError, ValueError):
        raise CommandError("bad_params", "limit must be a whole number") from None
    if limit < 0:
        raise CommandError("bad_params", "limit must be 0 (all) or more")
    # No limit (empty or 0) returns everything found.
    limit = limit or None
    kind = p.get("kind") or "any"
    if kind != "any" and kind not in KINDS:
        raise CommandError(
            "bad_params", "kind must be any or one of: " + ", ".join(KINDS)
        )
    words = plain(query).split()
    hits = []
    seen = set()
    for root, path, item in index(bool(p.get("refresh"))):
        if kind != "any" and root != KINDS[kind]:
            continue
        name = plain(item.name)
        if not all(w in name for w in words):
            continue
        key = _identity(item, path)
        if key in seen:
            continue
        seen.add(key)
        rank = 0 if name == plain(query) else 1 if name.startswith(words[0]) else 2
        hits.append((rank, len(path), path, item))
    hits.sort(key=lambda h: (h[0], h[1], h[2]))
    shown = [
        {"name": item.name, "path": path, "kind": _item_kind(item)}
        for _, _, path, item in hits[:limit]
    ]
    if p.get("show_uri"):
        for entry, (_, _, _, item) in zip(shown, hits, strict=False):
            entry["uri"] = getattr(item, "uri", None)
    out = {"query": query, "found": len(hits), "results": shown}
    if limit is not None and len(hits) > limit:
        out["more"] = len(hits) - limit
    out["index"] = {"items": len(_cache["items"]), "built": _cache["built"]}
    return out


def load_device(song, p):
    """Load a native device by name, a browser item by path, or a preset file."""
    item_ref = str(p.get("item") or "").strip()
    if not item_ref:
        raise CommandError(
            "bad_params", "item is required: Operator, a browser path or a file"
        )
    kind, holder, path = objects.resolve(song, p.get("target") or "")
    if kind not in ("track", "chain"):
        raise CommandError(
            "bad_target", f"{path} is a {kind}: load onto a track or chain"
        )
    position = p.get("index")
    before = list(holder.devices)
    before_names = [(d.name, d.class_name) for d in before]
    position = len(before) if position in (None, "", -1) else int(position)
    if not 0 <= position <= len(before):
        raise CommandError("bad_params", f"index must be 0-{len(before)}")

    with undo_step(song):
        how = _insert_native(holder, item_ref, position)
        if how is None:
            if kind != "track":
                raise CommandError(
                    "bad_target",
                    "Live loads presets onto tracks only; load it on the track, then "
                    "move it into the chain with update_device move_to",
                )
            item, how = _browser_item(item_ref, bool(p.get("refresh")))
            song.view.selected_track = holder
            browser().load_item(item)

    after = list(holder.devices)
    after_names = [(d.name, d.class_name) for d in after]
    new = [i for i, d in enumerate(after) if all(d != old for old in before)]
    replaced = None
    if not new and len(after) == len(before):
        # A track has one instrument: loading another one replaces it in place.
        changed = [i for i, n in enumerate(after_names) if n != before_names[i]]
        if changed:
            new = changed
            replaced = before_names[changed[0]][0]
    if not new:
        return {
            "loaded": item_ref,
            "how": how,
            "warning": "Live has not shown the device yet; check with read_track",
        }
    device_path = f"{path}/d{new[0]}"
    out = {"loaded": after[new[0]].name, "how": how, "path": device_path}
    if replaced:
        out["replaced"] = replaced
    info = reading.read_device(song, device_path)
    if "macros" in info:
        out["macros"] = [m["name"] for m in info["macros"]]
    out["note"] = "Live selects the track it loads onto"
    return out


def _insert_native(holder, name, position):
    """Insert a built-in device by name; None if Live doesn't know the name."""
    if "/" in name or plain(name) != name.strip().casefold():
        return None
    insert = getattr(holder, "insert_device", None)
    if insert is None:
        return None
    try:
        insert(name, position)
    except Exception:
        return None
    return "native device"


def _browser_item(ref, refresh):
    """The browser item for a file path, a browser path, or a unique name."""
    if ref.startswith(("/", "~")):
        return _by_file(os.path.expanduser(ref), refresh), "file"
    items = index(refresh)
    if "/" in ref:
        wanted = [plain(s) for s in ref.split("/") if s]
        for _, path, item in items:
            if [plain(s) for s in path.split("/")] == wanted:
                return item, "browser path"
        raise CommandError(
            "not_found",
            f"no browser item at {ref!r}; use find_in_library to get its path",
        )
    return _unique(items, plain(ref), ref), "name"


def _by_file(file_path, refresh):
    if not os.path.isfile(file_path):
        raise CommandError("not_found", f"no file {file_path}")
    items = index(refresh)
    segments = [s for s in os.path.realpath(file_path).split(os.sep) if s]
    library = [s for s in os.path.realpath(USER_LIBRARY).split(os.sep) if s]
    if segments[: len(library)] == library:
        wanted = ["user library"] + [plain(s) for s in segments[len(library) :]]
        for _, path, item in items:
            if [plain(s) for s in path.split("/")] == wanted:
                return item
    for _, path, item in items:
        parts = [plain(s) for s in path.split("/")]
        if parts[0] == "packs":
            pack = parts[1]
            if pack in [plain(s) for s in segments]:
                tail = [
                    plain(s)
                    for s in segments[[plain(s) for s in segments].index(pack) + 1 :]
                ]
                if parts[2:] == tail:
                    return item
    # The Core Library and anything else: by file name, if only one file has it.
    try:
        return _unique(items, plain(segments[-1]), file_path)
    except CommandError as err:
        if err.code != "not_found":
            raise
    raise CommandError(
        "outside_library",
        f"{file_path} is not in a folder Live's browser shows. Move it into the User "
        f"Library ({USER_LIBRARY}/Presets/...) and try again.",
    )


def _unique(items, name, shown):
    matches = {}
    for _, path, item in items:
        if plain(item.name) == name:
            matches.setdefault(_identity(item, path), (path, item))
    if not matches:
        raise CommandError("not_found", f"nothing named {shown!r} in the library")
    # The category views (Instruments, Sounds...) list the Core Library and the
    # packs again, with a FileId in the uri. One FileId item plus same-named items
    # under Packs is one file seen twice.
    filed = [m for key, m in matches.items() if key.startswith("FileId_")]
    rest = [m for key, m in matches.items() if not key.startswith("FileId_")]
    if len(filed) == 1 and all(path.startswith("Packs/") for path, _ in rest):
        return filed[0][1]
    if len(matches) > 1:
        paths = sorted(path for path, _ in matches.values())
        raise CommandError(
            "ambiguous", f"{len(paths)} items are named {shown!r}; give a path: {paths}"
        )
    return next(iter(matches.values()))[1]


def _identity(item, path):
    """The same file shows up in several folders (Instrument Rack/Bass and
    Simpler/Bass); its uri ends with the same FileId."""
    uri = getattr(item, "uri", "") or ""
    if "FileId_" in uri:
        return uri[uri.rindex("FileId_") :]
    return uri or path


def _item_kind(item):
    if item.is_device:
        return "device"
    return "preset" if plain(item.name) != item.name.strip().casefold() else "item"
