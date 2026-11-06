"""The bridge end to end without Live: the real Remote Script server and client over a
loopback socket, with a fake Song and a thread standing in for Live's main-thread ticks.
"""

import json
import os
import socket
import stat
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "remote_script"))

import Tonable  # noqa: E402
import tonable  # noqa: E402
from Tonable import server as remote  # noqa: E402
from tonable import bridge  # noqa: E402

# How often the fake Live calls update_display; test-only.
TICK = 0.01


class FakeCInstance:
    def __init__(self):
        self._song = SimpleNamespace(
            tempo=120.0,
            signature_numerator=4,
            signature_denominator=4,
            tracks=[object()] * 3,
            return_tracks=[object()] * 2,
            scenes=[object()] * 8,
            is_playing=False,
        )
        self.messages = []
        self.logs = []

    def song(self):
        return self._song

    def show_message(self, message):
        self.messages.append(message)

    def log_message(self, message):
        self.logs.append(message)


class FakeLive:
    """Runs Tonable's update_display on a thread, like Live's main thread."""

    def __init__(self, surface):
        self.surface = surface
        self.ticking = threading.Event()
        self.ticking.set()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            if self.ticking.is_set():
                self.surface.update_display()
            time.sleep(TICK)

    def close(self):
        self._stop.set()
        self._thread.join()
        self.surface.disconnect()


@pytest.fixture
def session_path(tmp_path, monkeypatch):
    path = tmp_path / "tonable" / "session.json"
    monkeypatch.setattr(remote, "SESSION_PATH", str(path))
    return path


@pytest.fixture
def live(session_path):
    c = FakeCInstance()
    fake = FakeLive(Tonable.create_instance(c))
    yield fake
    fake.close()


def raw_connect(session_path):
    session = json.loads(session_path.read_text())
    return socket.create_connection(("127.0.0.1", session["port"]), timeout=2), session


def test_constants_match_on_both_sides():
    for name in (
        "HOST",
        "AUTH_TIMEOUT",
        "DEFAULT_TIMEOUT",
        "LONG_TIMEOUT",
        "MAX_MESSAGE_BYTES",
    ):
        assert getattr(remote, name) == getattr(bridge, name), name
    assert remote.HOST == "127.0.0.1"


def test_script_version_matches_package():
    from Tonable.version import VERSION

    assert VERSION == tonable.__version__


def test_session_file_is_owner_only(live, session_path):
    assert stat.S_IMODE(os.stat(session_path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(session_path.parent).st_mode) == 0o700
    session = json.loads(session_path.read_text())
    assert len(bytes.fromhex(session["key"])) == remote.KEY_BYTES
    assert session["script_version"] == tonable.__version__


def test_status_round_trip(live, session_path):
    link = bridge.Bridge(session_path)
    status = link.request("status")
    assert status["script_version"] == tonable.__version__
    assert status["set"] == {
        "tempo": 120.0,
        "time_signature": "4/4",
        "tracks": 3,
        "return_tracks": 2,
        "scenes": 8,
        "is_playing": False,
    }
    # The same connection serves the next request.
    assert link.request("status")["set"]["scenes"] == 8
    link.close()


def test_wrong_key_is_refused(live, session_path):
    sock, _ = raw_connect(session_path)
    sock.sendall(b'{"key": "nope"}\n')
    reply = json.loads(sock.makefile().readline())
    assert reply == {"ok": False, "code": "bad_key", "error": "wrong key"}
    assert sock.recv(1) == b""


def test_http_request_gets_no_answer(live, session_path):
    sock, _ = raw_connect(session_path)
    sock.sendall(b"POST /mcp HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
    assert sock.recv(1024) == b""


def test_silent_client_is_dropped_after_auth_timeout(live, session_path, monkeypatch):
    monkeypatch.setattr(remote, "AUTH_TIMEOUT", 0.2)
    sock, _ = raw_connect(session_path)
    assert sock.recv(1) == b""


def test_unknown_command(live, session_path):
    link = bridge.Bridge(session_path)
    with pytest.raises(bridge.BridgeError) as err:
        link.request("delete_everything")
    assert err.value.code == "unknown_command"
    # An error reply leaves the connection usable.
    assert link.request("status")["set"]["tracks"] == 3


def test_oversized_message_closes_connection(live, session_path, monkeypatch):
    monkeypatch.setattr(remote, "MAX_MESSAGE_BYTES", 1000)
    sock, session = raw_connect(session_path)
    sock.sendall(json.dumps({"key": session["key"]}).encode() + b"\n")
    reader = sock.makefile()
    assert json.loads(reader.readline())["ok"] is True
    sock.sendall(b"x" * 5000)
    assert json.loads(reader.readline())["code"] == "too_large"


def test_command_not_started_in_time_is_cancelled(live, session_path, monkeypatch):
    monkeypatch.setattr(remote, "DEFAULT_TIMEOUT", 0.2)
    ran = []
    live.surface._server._commands["mark"] = lambda params: ran.append(1)
    live.ticking.clear()  # Live is busy, e.g. a dialog is open
    link = bridge.Bridge(session_path)
    with pytest.raises(bridge.BridgeError) as err:
        link.request("mark")
    assert err.value.code == "timeout_not_started"
    live.ticking.set()
    time.sleep(TICK * 10)
    assert ran == []  # never runs late


def test_handler_error_is_reported(live, session_path):
    def broken(params):
        raise KeyError("nothing here")

    live.surface._server._commands["broken"] = broken
    link = bridge.Bridge(session_path)
    with pytest.raises(bridge.BridgeError) as err:
        link.request("broken")
    assert err.value.code == "internal"
    assert "KeyError" in str(err.value)


def test_reconnects_after_live_restart(session_path):
    first = FakeLive(Tonable.create_instance(FakeCInstance()))
    link = bridge.Bridge(session_path)
    assert link.request("status")
    first.close()
    assert not session_path.exists()  # removed on disconnect

    with pytest.raises(bridge.BridgeError) as err:
        link.request("status")
    assert err.value.code == "not_running"

    second = FakeLive(Tonable.create_instance(FakeCInstance()))
    try:
        assert link.request("status")["set"]["tracks"] == 3
    finally:
        second.close()


def test_stale_session_file(session_path):
    session_path.parent.mkdir(parents=True)
    # A port nobody listens on: take one, then free it.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    session_path.write_text(json.dumps({"port": port, "key": "00"}))
    with pytest.raises(bridge.BridgeError) as err:
        bridge.Bridge(session_path).request("status")
    assert err.value.code == "not_running"
    assert err.value.hint == bridge.NOT_RUNNING_HINT


def test_no_session_file(session_path):
    with pytest.raises(bridge.BridgeError) as err:
        bridge.Bridge(session_path).request("status")
    assert err.value.code == "not_running"


def test_reload_keeps_the_connection(live, session_path):
    link = bridge.Bridge(session_path)
    before = link.request("status")
    out = link.request("reload")
    assert out["script_version"] == tonable.__version__
    assert {"reload", "status", "write_clip", "read_clip"} <= set(out["commands"])
    # Same connection, fresh command table.
    assert link.request("status")["set"] == before["set"]
    link.close()
