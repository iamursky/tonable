"""The stage 0 probe outside Live: refuse a busy Set, keep a finished report."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "probe"))

import TonableProbe as probe  # noqa: E402


class FakeTrack:
    def __init__(self, name, devices=(), clips=0):
        self.name = name
        self.devices = list(devices)
        self.clip_slots = [SimpleNamespace(has_clip=i < clips) for i in range(8)]
        self.arrangement_clips = []


class FakeCInstance:
    def __init__(self, tracks):
        self._song = SimpleNamespace(tracks=tracks)
        self.messages = []

    def song(self):
        return self._song

    def show_message(self, message):
        self.messages.append(message)

    def log_message(self, message):
        pass


@pytest.fixture
def report_path(tmp_path, monkeypatch):
    path = tmp_path / "tonable" / "probe-report.json"
    monkeypatch.setattr(probe, "REPORT_PATH", str(path))
    app = SimpleNamespace(
        get_major_version=lambda: 12,
        get_minor_version=lambda: 4,
        get_bugfix_version=lambda: 16,
    )
    fake_live = SimpleNamespace(
        Application=SimpleNamespace(get_application=lambda: app)
    )
    monkeypatch.setattr(probe, "Live", fake_live)
    return path


def run_ticks(surface, ticks):
    for _ in range(ticks):
        surface.update_display()


def test_refuses_a_set_with_devices(report_path):
    c = FakeCInstance([FakeTrack("1-MIDI", devices=["Operator"])])
    surface = probe.create_instance(c)
    run_ticks(surface, 3)

    report = json.loads(report_path.read_text())
    assert report["status"] == "refused"
    assert report["not_empty"] == ["1-MIDI: devices"]
    assert report["live_version"] == "12.4.16"
    assert [s["step"] for s in report["steps"]] == ["start"]


def test_refuses_a_set_with_clips(report_path):
    c = FakeCInstance([FakeTrack("1-MIDI"), FakeTrack("2-MIDI", clips=1)])
    run_ticks(probe.create_instance(c), 1)

    report = json.loads(report_path.read_text())
    assert report["not_empty"] == ["2-MIDI: session clips"]


def test_keeps_a_finished_report(report_path):
    report_path.parent.mkdir()
    report_path.write_text(json.dumps({"status": "done", "checks": {"1": {}}}))
    c = FakeCInstance([FakeTrack("1-MIDI")])
    run_ticks(probe.create_instance(c), 3)

    assert json.loads(report_path.read_text()) == {
        "status": "done",
        "checks": {"1": {}},
    }
    assert c.messages == ["TonableProbe: report exists, nothing to do"]


def test_a_failing_step_does_not_stop_the_run(report_path):
    c = FakeCInstance([FakeTrack("1-MIDI")])
    surface = probe.create_instance(c)
    # The fake app has no browser, so the walk fails; the next step still runs.
    run_ticks(surface, 3)

    report = json.loads(report_path.read_text())
    assert report["status"] == "running"
    steps = report["steps"]
    assert [s["step"] for s in steps] == ["start", "browser_walk", "native_devices"]
    assert steps[0]["ok"] is True
    assert steps[1]["ok"] is False
    assert report["checks"]["7"]["script_file"].endswith("TonableProbe/__init__.py")


def test_plain_name_drops_preset_suffix():
    assert probe.plain_name("Basic Wurly DI.adg") == "basic wurly di"
    assert probe.plain_name("Electric Bass Soft") == "electric bass soft"
