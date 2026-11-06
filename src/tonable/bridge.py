"""The MCP server's connection to the Tonable Remote Script inside Live.

The Remote Script writes its port and key to ~/.tonable/session.json. We connect to
127.0.0.1 only, send the key as the first message, then one JSON request per line and
read one JSON reply per line.

The protocol limits are documented in docs/plan.md and must match
remote_script/Tonable/server.py (tests/test_bridge.py checks it).
"""

import json
import os
import socket
import threading
from pathlib import Path

HOST = "127.0.0.1"
CONNECT_TIMEOUT = 3.0
AUTH_TIMEOUT = 3.0
DEFAULT_TIMEOUT = 10.0
LONG_TIMEOUT = 30.0
MAX_MESSAGE_BYTES = 10 * 1024 * 1024
SESSION_PATH = Path("~/.tonable/session.json").expanduser()

NOT_RUNNING_HINT = (
    "Open Live and choose Tonable in Settings -> Link, Tempo & MIDI -> Control "
    "Surface. If Tonable is not in the list, run `tonable install` and restart Live."
)


class BridgeError(Exception):
    """A failure between us and Live: a stable `code`, and a `hint` on what to do."""

    def __init__(self, code, message, hint=None):
        super().__init__(message)
        self.code = code
        self.hint = hint

    def as_dict(self):
        out = {"code": self.code, "error": str(self)}
        if self.hint:
            out["hint"] = self.hint
        return out


def read_session(path=None):
    """The Remote Script's session file as a dict. Raises BridgeError("not_running")."""
    path = Path(path or SESSION_PATH)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BridgeError(
            "not_running", "Tonable is not running in Live", NOT_RUNNING_HINT
        ) from None
    except (OSError, ValueError) as err:
        raise BridgeError("bad_session", f"cannot read {path}: {err}") from None
    if not isinstance(data, dict) or not isinstance(data.get("port"), int):
        raise BridgeError("bad_session", f"{path} has no port")
    if not isinstance(data.get("key"), str):
        raise BridgeError("bad_session", f"{path} has no key")
    return data


class Bridge:
    """One connection to Live, opened on first use and reopened when Live restarts.

    Requests are sent one at a time; the lock keeps parallel tool calls in order.
    """

    def __init__(self, session_path=None):
        self._session_path = session_path
        self._sock = None
        self._buffer = bytearray()
        self._next_id = 1
        self._lock = threading.Lock()
        self.hello = None

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None
        self._buffer = bytearray()
        self.hello = None

    def request(self, command, params=None, long=False):
        """Run `command` in Live and return its result. Raises BridgeError."""
        with self._lock:
            if self._sock is not None and not self._alive():
                self.close()
            if self._sock is None:
                self._connect()
            request_id = self._next_id
            self._next_id += 1
            message = {"id": request_id, "command": command, "params": params or {}}
            if long:
                message["long"] = True
            # Live answers a timeout itself; we wait a connect timeout longer for it.
            wait = (LONG_TIMEOUT if long else DEFAULT_TIMEOUT) + CONNECT_TIMEOUT
            try:
                self._send(message)
                reply = self._receive(wait)
            except ValueError:
                self.close()
                raise BridgeError(
                    "protocol", "Live sent a reply that is not JSON"
                ) from None
            except (OSError, BridgeError) as err:
                self.close()
                if isinstance(err, BridgeError):
                    raise
                raise BridgeError(
                    "connection_lost",
                    f"the connection to Live broke during {command!r}: {err}. "
                    "The command may or may not have run.",
                    "Read the state before repeating it.",
                ) from None
            if reply.get("id") != request_id:
                self.close()
                raise BridgeError("protocol", "Live answered a different request")
            if not reply.get("ok"):
                raise BridgeError(
                    reply.get("code", "error"), reply.get("error", "unknown error")
                )
            return reply.get("result")

    # --- internals -------------------------------------------------------

    def _connect(self):
        session = read_session(self._session_path)
        try:
            sock = socket.create_connection(
                (HOST, session["port"]), timeout=CONNECT_TIMEOUT
            )
        except OSError:
            raise BridgeError(
                "not_running",
                "Tonable is not answering in Live (the session file is left from "
                "an earlier run)",
                NOT_RUNNING_HINT,
            ) from None
        self._sock = sock
        try:
            self._send({"key": session["key"]})
            hello = self._receive(AUTH_TIMEOUT)
        except (OSError, ValueError, BridgeError) as err:
            self.close()
            raise BridgeError(
                "not_running", f"Live did not accept the connection: {err}"
            ) from None
        if not hello.get("ok"):
            self.close()
            raise BridgeError(
                hello.get("code", "bad_key"),
                "Live refused the key from the session file",
                "Choose None and then Tonable again in Live's Control Surface list.",
            )
        self.hello = hello

    def _alive(self):
        """False when Live has closed our connection (e.g. after a restart)."""
        try:
            self._sock.setblocking(False)
            try:
                return self._sock.recv(1, socket.MSG_PEEK) != b""
            finally:
                self._sock.setblocking(True)
        except BlockingIOError:
            return True
        except OSError:
            return False

    def _send(self, message):
        data = json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n"
        if len(data) > MAX_MESSAGE_BYTES:
            raise BridgeError("too_large", f"request over {MAX_MESSAGE_BYTES} bytes")
        self._sock.sendall(data)

    def _receive(self, timeout):
        self._sock.settimeout(timeout)
        while True:
            end = self._buffer.find(b"\n")
            if end >= 0:
                line = bytes(self._buffer[:end])
                del self._buffer[: end + 1]
                return json.loads(line)
            if len(self._buffer) > MAX_MESSAGE_BYTES:
                raise BridgeError("too_large", "Live sent a reply over the size limit")
            try:
                chunk = self._sock.recv(65536)
            except TimeoutError:
                raise BridgeError(
                    "timeout",
                    f"Live did not answer within {timeout:g} s",
                    "Check Live for an open dialog, then read the state before "
                    "repeating the command.",
                ) from None
            if not chunk:
                raise OSError("Live closed the connection")
            self._buffer += chunk


def session_permissions_ok(path=None):
    """True when only the owner can read the session file (it holds the key)."""
    mode = os.stat(path or SESSION_PATH).st_mode & 0o777
    return mode == 0o600
