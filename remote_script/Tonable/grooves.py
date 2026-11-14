"""The `groove` command: list and tune the Set's groove pool. Main thread only.

Live cannot create or remove a groove, and cannot clear a clip's groove (Producer Pal:
local/producer-pal/dev/live-api/python-remote-script-api/python-only-candidates.md,
"Grooves and tuning systems"). That note is also the source for the property list:
Groove.name, base, timing / quantization / random / velocity amounts (0-100, out of
range values are clamped by Live), and base 0 = 1/4, 1 = 1/8, 2 = 1/8T, 3 = 1/16,
4 = 1/16T, 5 = 1/32. Verified by that doc: those Groove members. From memory of the
LOM, NOT verified: Song.groove_pool.grooves and Song.groove_amount (its range is not
checked here; Live's own clamp shows in the read-back note).
"""

from . import props
from .server import CommandError
from .song import undo_step

ACTIONS = ("list", "update")

BASES = {"1/4": 0, "1/8": 1, "1/8T": 2, "1/16": 3, "1/16T": 4, "1/32": 5}

GROOVE = [
    props.prop("name", "name", "str"),
    props.prop("base", "base", "enum", choices=BASES),
    props.prop("timing_amount", "timing_amount", "float", lo=0, hi=100),
    props.prop("quantization_amount", "quantization_amount", "float", lo=0, hi=100),
    props.prop("random_amount", "random_amount", "float", lo=0, hi=100),
    props.prop("velocity_amount", "velocity_amount", "float", lo=0, hi=100),
]
GROOVE_AMOUNT = props.prop("groove_amount", "groove_amount", "float", lo=0)


def groove(song, p):
    action = p.get("action")
    if action not in ACTIONS:
        raise CommandError("bad_params", "action must be one of: " + ", ".join(ACTIONS))
    if action == "list":
        return _list(song)
    return _update(song, p)


def pool_grooves(song):
    pool = props.get(song, "groove_pool", None)
    items = props.get(pool, "grooves", None)
    if items is None:
        raise CommandError("not_supported", "this Live has no groove pool for scripts")
    return list(items)


def find_groove(song, ref):
    """A groove of the pool by index (0) or exact name, for tools that assign one."""
    grooves = pool_grooves(song)
    text = str(ref if ref is not None else "").strip()
    if not text:
        raise CommandError("bad_params", "groove is required: an index or a name")
    if text.isdigit():
        index = int(text)
        if index >= len(grooves):
            raise CommandError(
                "not_found", f"no groove {index}: the pool has {len(grooves)} (0-based)"
            )
        return grooves[index]
    hits = [g for g in grooves if str(g.name).strip().casefold() == text.casefold()]
    if len(hits) != 1:
        names = [g.name for g in grooves]
        what = "no groove named" if not hits else "several grooves named"
        raise CommandError("not_found", f"{what} {text!r}; grooves: {names}")
    return hits[0]


def _list(song):
    out = {
        "grooves": [
            {"index": i, **props.read(g, GROOVE)}
            for i, g in enumerate(pool_grooves(song))
        ]
    }
    out.update(props.read(_amount_owner(song), [GROOVE_AMOUNT]))
    return out


def _update(song, p):
    results = []
    owner = _amount_owner(song)
    with undo_step(song):
        if props.given(p, "groove_amount"):
            results.append(props.write_one(owner, GROOVE_AMOUNT, p["groove_amount"]))
        if props.given(p, "groove"):
            target = find_groove(song, p["groove"])
            lines = props.write(target, GROOVE, p)
            results.extend(lines)
        elif any(props.given(p, row.name) for row in GROOVE):
            raise CommandError(
                "bad_params", "groove is required to change a groove: index or name"
            )
    if not results:
        raise CommandError(
            "bad_params", "nothing to change: give groove_amount, or groove and a field"
        )
    return {"results": results, **_list(song)}


def _amount_owner(song):
    if props.get(song, "groove_amount", None) is not None:
        return song
    pool = props.get(song, "groove_pool", None)
    return pool if pool is not None else song
