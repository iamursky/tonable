"""Tools end to end: MCP arguments -> bridge request -> command table -> fake Live.

The bridge is replaced by a call into the real command table, so a parameter that a
tool sends under one name and a command reads under another fails here, not in Live.
"""

import asyncio
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "remote_script"))

import fake_live  # noqa: E402
from Tonable import clips, dispatch  # noqa: E402
from tonable import bridge, server  # noqa: E402
from Tonable.server import CommandError  # noqa: E402

TOOLS_DIR = Path(__file__).resolve().parents[1] / "src" / "tonable" / "tools"


class DirectBridge:
    """Stands in for the socket: runs the command table in-process."""

    def __init__(self, song):
        self.table = dispatch.commands(SimpleNamespace(song=song, live_version="x"))

    def request(self, command, params=None, long=False):
        handler = self.table.get(command)
        if handler is None:
            raise bridge.BridgeError("unknown_command", command)
        try:
            # a JSON round trip, as on the wire
            result = handler(json.loads(json.dumps(params or {})))
        except CommandError as err:
            raise bridge.BridgeError(err.code, str(err)) from None
        return json.loads(json.dumps(result))


def run_tool(_tool, **arguments):
    result = asyncio.run(server.mcp.call_tool(_tool, arguments))
    if isinstance(result, tuple):
        content, structured = result
        if structured is not None:
            return structured
    else:
        content = result
    return json.loads(content[0].text)


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(clips, "Live", fake_live.FAKE_LIVE_MODULE)
    s = fake_live.writable_song()
    s.tempo = 120.0
    s.is_playing = False
    s.loop = False
    s.loop_start, s.loop_length = 0.0, 16.0
    s.cue_points = []
    s.scenes = [SimpleNamespace(name="Verse", tempo=120.0, tempo_enabled=False)] * 4
    s.record_mode = False
    s.groove_amount = 0.0
    s.view = SimpleNamespace(selected_track=None, selected_scene=None)
    monkeypatch.setattr(server, "bridge", DirectBridge(s))
    return s


def test_every_tool_calls_a_command_that_exists():
    table = dispatch.commands(SimpleNamespace(song=fake_live.song(), live_version="x"))
    called = set()
    for path in TOOLS_DIR.glob("*.py"):
        called |= set(re.findall(r'call\(\s*"([a-z_]+)"', path.read_text()))
    assert called, "found no call(...) sites"
    assert called <= set(table), called - set(table)


def test_every_command_has_a_tool():
    table = dispatch.commands(SimpleNamespace(song=fake_live.song(), live_version="x"))
    tools = {t.name for t in asyncio.run(server.mcp.list_tools())}
    # status is live_status; batch calls the others by name.
    expected = set(table) - {"status", "reload"}
    assert expected <= tools, expected - tools


def test_update_set_arguments_reach_the_command(live):
    out = run_tool("update_set", record="true", punch_in="true", tempo="100")
    assert live.tempo == 100.0 and live.record_mode is True
    assert "tempo" in out["changed"] and "record" in out["changed"]


def test_scene_time_signature_reaches_the_command(live):
    live.scenes = [
        SimpleNamespace(
            name="A",
            tempo=120.0,
            tempo_enabled=False,
            time_signature_enabled=False,
            time_signature_numerator=4,
            time_signature_denominator=4,
        )
    ]
    out = run_tool("scene", action="update", scene="0", time_signature="6/8")
    assert out["time_signature"] == "6/8"


def test_clip_tools_agree_on_names(live):
    run_tool(
        "write_clip",
        track="t0",
        slot="0",
        notes=[
            {
                "pitch": "C3",
                "start": 0,
                "length": 1,
                "velocity": 90,
                "probability": 0.5,
            }
        ],
    )
    read = run_tool("read_clip", clip="t0/s0")
    assert read["notes"][0]["probability"] == 0.5
    run_tool("edit_notes", action="release_velocity", clip="t0/s0", value="20")
    assert (
        run_tool("read_clip", track="t0", slot="0")["notes"][0]["release_velocity"]
        == 20
    )
    live.tracks[0].clip_slots[0].clip.muted = False
    live.tracks[0].clip_slots[0].clip.launch_mode = 0
    out = run_tool("update_clip", clip="t0/s0", name="Riff", launch_mode="Toggle")
    assert out["name"] == "Riff" and out["settings"]["launch_mode"] == "Toggle"


def test_update_track_new_fields_reach_the_command(live):
    track = live.tracks[0]
    track.current_monitoring_state = 1
    track.mixer_device = SimpleNamespace(
        volume=fake_live.Param("V", 0.85, show="0 dB"),
        panning=fake_live.Param("P", 0.0, -1.0, 1.0, show="C"),
        sends=[],
    )
    out = run_tool("update_track", track="t0", monitoring="Off")
    assert out["results"] == [{"field": "monitoring", "now": "Off"}]


def test_arrangement_clip_param_reaches_the_command(live):
    track = live.tracks[0]
    clip = fake_live.MidiClip(4.0)
    clip.name, clip.start_time, clip.end_time = "Intro", 0.0, 4.0
    track.arrangement_clips = [clip]
    track.duplicate_clip_to_arrangement = lambda c, at: c
    out = run_tool("arrangement", action="copy_clip", clip="t0/a0", at_beats="16")
    assert out["copied"] == "t0/a0"


def test_live_api_refuses_objects_that_are_not_lives(live):
    with pytest.raises(Exception) as err:
        run_tool("live_api", path="song", operation="get", name="tempo")
    assert "not a Live object" in str(err.value)


def test_live_api_arguments_reach_the_command(live, monkeypatch):
    from Tonable import liveapi

    # The fakes are not Live classes; let this one test walk them.
    monkeypatch.setattr(
        liveapi, "is_live_object", lambda obj: type(obj).__name__ == "UndoSong"
    )
    out = run_tool("live_api", path="song", operation="get", name="tempo")
    assert out["value"] == 120.0
    with pytest.raises(Exception) as err:
        run_tool("live_api", path="song", operation="set", name="tempo", value="90")
    assert "needs_write" in str(err.value)
    out = run_tool(
        "live_api", path="song", operation="set", name="tempo", value="90", write=True
    )
    assert live.tempo == 90.0 and out["value"] == 90.0


def test_update_clip_on_an_empty_slot_is_a_readable_error(live):
    with pytest.raises(Exception) as err:
        run_tool("update_clip", clip="t0/s0", name="x")
    assert "empty" in str(err.value)


def test_batch_accepts_the_new_commands(live):
    out = run_tool(
        "batch",
        actions=[
            {"command": "update_set", "params": {"overdub": "true"}},
            {"command": "update_clip", "params": {"clip": "t0/s0", "name": "x"}},
        ],
    )
    assert out["ran"] == 2 and out["failed"] == 1
    assert out["results"][0]["ok"] is True
