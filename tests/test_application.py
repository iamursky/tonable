"""The app command and its MCP tool, against stand-ins for Live's application."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "remote_script"))

import fake_live  # noqa: E402
from Tonable import application, library  # noqa: E402
from Tonable.server import CommandError  # noqa: E402


class FakeView:
    def __init__(self):
        self.shown = {"Session": True, "Browser": True}
        self.calls = []

    def is_view_visible(self, name):
        return self.shown.get(name, False)

    def available_main_views(self):
        return ["Browser", "Arranger", "Session", "Detail"]

    def show_view(self, name):
        self.calls.append(("show", name))
        self.shown[name] = True

    def hide_view(self, name):
        self.calls.append(("hide", name))
        self.shown[name] = False

    def focus_view(self, name):
        self.calls.append(("focus", name))

    def toggle_browse(self):
        self.shown["Browser"] = not self.shown["Browser"]

    def scroll_view(self, direction, name, modifier):
        self.calls.append(("scroll", direction, name, modifier))

    def zoom_view(self, direction, name, modifier):
        self.calls.append(("zoom", direction, name, modifier))


def make_app():
    messages = []
    browser = SimpleNamespace(
        previewed=[],
        preview_item=lambda item: browser.previewed.append(item.name),
        stop_preview=lambda: browser.previewed.append("stopped"),
    )
    app = SimpleNamespace(
        get_major_version=lambda: 12,
        get_minor_version=lambda: 4,
        get_bugfix_version=lambda: 16,
        get_build_id=lambda: "build-1",
        get_variant=lambda: "Suite",
        average_process_usage=0.123456789,
        peak_process_usage=0.5,
        open_dialog_count=0,
        current_dialog_message="",
        unavailable_features=[],
        view=FakeView(),
        browser=browser,
        show_message=messages.append,
    )
    app.messages = messages
    return app


def make_song():
    song = fake_live.song()
    for t in [*song.tracks, *song.return_tracks, song.master_track]:
        t.view = SimpleNamespace(selected_device=None)
    song.view = SimpleNamespace(
        selected_track=song.tracks[0],
        selected_scene=song.scenes[0],
        highlighted_clip_slot=None,
        detail_clip=None,
        selected_parameter=None,
        follow_song=False,
        draw_mode=False,
    )

    def select_device(device):
        # Like Live: the device is selected on the selected track.
        song.view.selected_track.view.selected_device = device

    song.view.select_device = select_device
    return song


def run(song, app, **p):
    return application.application(song, p, app)


def test_info_reports_version_cpu_dialogs_and_selection():
    song, app = make_song(), make_app()
    out = run(song, app, action="info")
    assert out["live"] == {"version": "12.4.16", "build": "build-1", "variant": "Suite"}
    assert out["cpu"] == {"average": 0.1235, "peak": 0.5}
    assert out["dialogs"] == {"open": 0}
    assert out["selection"]["track"] == "t0"
    assert out["selection"]["scene"] == {"index": 0, "name": "Verse"}
    assert out["view"]["follow_song"] is False
    assert out["view"]["visible"]["Session"] is True


def test_info_shows_an_open_dialog_message_but_never_presses_it():
    app = make_app()
    app.open_dialog_count = 1
    app.current_dialog_message = "Save changes?"
    out = run(make_song(), app, action="info")
    assert out["dialogs"] == {"open": 1, "message": "Save changes?"}
    assert not hasattr(application, "press_dialog")


def test_info_works_without_an_application_object():
    out = application.application(make_song(), {"action": "info"}, None)
    assert "live" not in out and out["selection"]["track"] == "t0"


def test_select_a_track_scene_and_clip():
    song, app = make_song(), make_app()
    out = run(song, app, action="select", target="rA")
    assert song.view.selected_track is song.return_tracks[0]
    assert out["selection"]["track"] == "rA"
    run(song, app, action="select", target="s2")
    assert song.view.selected_scene is song.scenes[2]
    out = run(song, app, action="select", target="t0/s1")
    assert out["selection"]["clip_slot"] == "t0/s1"
    assert out["selection"]["detail_clip"] == "t0/s1"
    assert out["selection"]["track"] == "t0"


def test_select_an_empty_slot_highlights_it_without_a_clip():
    song = make_song()
    out = run(song, make_app(), action="select", target="t3/s1")
    assert out["selection"]["clip_slot"] == "t3/s1"
    assert "detail_clip" not in out["selection"]


def test_select_a_device_selects_its_track_first():
    song = make_song()
    out = run(song, make_app(), action="select", target="t3/d0")
    assert song.view.selected_track is song.tracks[3]
    assert out["selection"]["device"] == "t3/d0"


def test_select_a_device_inside_a_rack():
    song = make_song()
    out = run(song, make_app(), action="select", target="t0/d0/c0/d1")
    assert out["selection"]["device"] == "t0/d0/c0/d1"


def test_select_a_parameter_reports_its_device():
    song = make_song()
    out = run(song, make_app(), action="select", target="t3/d0:Osc-A Level")
    assert song.view.selected_parameter.name == "Osc-A Level"
    assert out["selection"]["parameter"] == {
        "name": "Osc-A Level",
        "device": "t3/d0:Osc-A Level",
    }


def test_a_selection_live_ignores_is_an_error_line():
    song = make_song()

    class Stubborn(SimpleNamespace):
        def __setattr__(self, name, value):
            if name == "selected_scene":
                return
            super().__setattr__(name, value)

    song.view = Stubborn(**vars(song.view))
    out = run(song, make_app(), action="select", target="s1")
    assert "kept the old selection" in out["results"][0]["error"]


def test_select_errors():
    song, app = make_song(), make_app()
    with pytest.raises(CommandError):
        run(song, app, action="select", target="")
    with pytest.raises(CommandError):
        run(song, app, action="select", target="t9")
    with pytest.raises(CommandError):
        run(song, app, action="select", target="t3/d0:Nope")
    with pytest.raises(CommandError):
        run(song, app, action="select", target="t0/d0/c0")


def test_view_actions_use_canonical_names():
    song, app = make_song(), make_app()
    out = run(song, app, action="hide_view", view="browser")
    assert out == {"done": "hide_view", "view": "Browser", "visible": False}
    run(song, app, action="show_view", view="ARRANGER")
    run(song, app, action="focus_view", view="Detail")
    assert app.view.calls == [
        ("hide", "Browser"),
        ("show", "Arranger"),
        ("focus", "Detail"),
    ]
    assert run(song, app, action="toggle_browse")["visible"] is True


def test_scroll_and_zoom_pass_direction_and_modifier():
    song, app = make_song(), make_app()
    run(song, app, action="scroll_view", view="Arranger", direction="down")
    run(
        song,
        app,
        action="zoom_view",
        view="Arranger",
        direction="left",
        modifier="true",
    )
    assert app.view.calls == [
        ("scroll", 1, "Arranger", False),
        ("zoom", 2, "Arranger", True),
    ]
    with pytest.raises(CommandError):
        run(song, app, action="scroll_view", view="Arranger", direction="sideways")


def test_unknown_view_lists_the_choices():
    with pytest.raises(CommandError) as err:
        run(make_song(), make_app(), action="show_view", view="Mixer")
    assert "Arranger" in str(err.value)
    with pytest.raises(CommandError):
        run(make_song(), make_app(), action="show_view", view="")


def test_views_need_an_application():
    with pytest.raises(CommandError) as err:
        run(make_song(), None, action="hide_view", view="Browser")
    assert err.value.code == "not_supported"


def test_set_view_reads_back():
    song = make_song()
    out = run(song, make_app(), action="set_view", follow_song="true")
    assert out["results"] == [{"field": "follow_song", "now": True}]
    assert song.view.follow_song is True
    with pytest.raises(CommandError):
        run(song, make_app(), action="set_view")


def test_show_message():
    app = make_app()
    assert run(make_song(), app, action="show_message", message="Hi")["shown"] == "Hi"
    assert app.messages == ["Hi"]
    with pytest.raises(CommandError):
        run(make_song(), app, action="show_message")
    app.show_message = None
    del app.show_message
    with pytest.raises(CommandError) as err:
        run(make_song(), app, action="show_message", message="Hi")
    assert err.value.code == "not_supported"


def test_preview_and_stop(monkeypatch):
    app = make_app()
    seen = {}

    def lookup(ref, refresh):
        seen["args"] = (ref, refresh)
        return SimpleNamespace(name="Wurly"), "browser path"

    monkeypatch.setattr(library, "_browser_item", lookup)
    out = run(make_song(), app, action="preview", item="Sounds/Wurly", refresh="true")
    assert out["previewing"] == "Wurly" and seen["args"] == ("Sounds/Wurly", True)
    assert run(make_song(), app, action="stop_preview") == {"done": "stop_preview"}
    assert app.browser.previewed == ["Wurly", "stopped"]
    with pytest.raises(CommandError):
        run(make_song(), app, action="preview")


def test_unknown_action():
    with pytest.raises(CommandError):
        run(make_song(), make_app(), action="press_dialog_button")


def test_tool_schema():
    from tonable import server
    from tonable.tools import application as tool  # noqa: F401

    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    t = tools["app"]
    assert len(t.description) > 40 and t.annotations is not None
    assert "anyOf" not in str(t.inputSchema)
    for name, prop in t.inputSchema["properties"].items():
        assert prop.get("description"), name
