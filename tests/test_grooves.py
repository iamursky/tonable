"""The groove command against a stand-in pool."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "remote_script"))

from Tonable import grooves  # noqa: E402
from Tonable.server import CommandError  # noqa: E402


def make_groove(name, base=3):
    return SimpleNamespace(
        name=name,
        base=base,
        timing_amount=100.0,
        quantization_amount=100.0,
        random_amount=0.0,
        velocity_amount=0.0,
    )


def make_song(**extra):
    return SimpleNamespace(
        groove_pool=SimpleNamespace(
            grooves=[make_groove("MPC 16 Swing-58"), make_groove("Swing 8", base=1)]
        ),
        groove_amount=1.0,
        **extra,
    )


def test_list_shows_every_groove_and_the_set_amount():
    out = grooves.groove(make_song(), {"action": "list"})
    assert out["groove_amount"] == 1.0
    assert out["grooves"][0] == {
        "index": 0,
        "name": "MPC 16 Swing-58",
        "base": "1/16",
        "timing_amount": 100.0,
        "quantization_amount": 100.0,
        "random_amount": 0.0,
        "velocity_amount": 0.0,
    }
    assert out["grooves"][1]["base"] == "1/8"


def test_update_by_name_reads_back():
    song = make_song()
    out = grooves.groove(
        song,
        {"action": "update", "groove": "swing 8", "base": "1/16T", "timing_amount": 40},
    )
    assert out["results"] == [
        {"field": "base", "now": "1/16T"},
        {"field": "timing_amount", "now": 40.0},
    ]
    assert song.groove_pool.grooves[1].base == 4
    assert out["grooves"][1]["timing_amount"] == 40.0


def test_update_by_index_and_rename():
    song = make_song()
    grooves.groove(song, {"action": "update", "groove": "0", "name": "Mine"})
    assert song.groove_pool.grooves[0].name == "Mine"


def test_amount_range_and_bad_base_are_per_field_errors():
    song = make_song()
    out = grooves.groove(
        song,
        {"action": "update", "groove": 0, "random_amount": 150, "base": "1/64"},
    )
    errors = {r["field"]: r["error"] for r in out["results"]}
    assert "0 to 100" in errors["random_amount"] and "1/32" in errors["base"]
    assert song.groove_pool.grooves[0].random_amount == 0.0


def test_set_groove_amount_alone():
    song = make_song()
    out = grooves.groove(song, {"action": "update", "groove_amount": "0.5"})
    assert out["results"] == [{"field": "groove_amount", "now": 0.5}]
    assert song.groove_amount == 0.5


def test_a_field_without_a_groove_is_refused():
    with pytest.raises(CommandError):
        grooves.groove(make_song(), {"action": "update", "base": "1/8"})
    with pytest.raises(CommandError):
        grooves.groove(make_song(), {"action": "update"})


def test_find_groove():
    song = make_song()
    assert grooves.find_groove(song, 1) is song.groove_pool.grooves[1]
    assert grooves.find_groove(song, "MPC 16 SWING-58") is song.groove_pool.grooves[0]
    for bad in ("Nope", 9, ""):
        with pytest.raises(CommandError):
            grooves.find_groove(song, bad)


def test_no_pool_is_not_supported():
    with pytest.raises(CommandError) as err:
        grooves.groove(SimpleNamespace(), {"action": "list"})
    assert err.value.code == "not_supported"


def test_tool_schema():
    from tonable import server
    from tonable.tools import grooves as tool  # noqa: F401

    t = {t.name: t for t in asyncio.run(server.mcp.list_tools())}["groove"]
    assert len(t.description) > 40 and t.annotations is not None
    assert "anyOf" not in str(t.inputSchema)
    for name, prop in t.inputSchema["properties"].items():
        assert prop.get("description"), name
