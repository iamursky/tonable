"""The Remote Script's socket side: loopback only, a key, one JSON message per line.

Socket threads only read and write. Every command runs on Live's main thread, which
calls `run_pending` from `update_display`. A command that Live hasn't started when its
time is up is cancelled, so it can never run late and reorder edits (an idea from
ableton-live-mcp).

The protocol limits are documented in docs/plan.md. The MCP server keeps the same
values in src/tonable/bridge.py; tests/test_bridge.py checks that they match.
"""

import hmac
import json
import os
import queue
import secrets
import socket
import threading
import time
import traceback

# Fixed: never read from settings or the environment.
HOST = "127.0.0.1"
AUTH_TIMEOUT = 3.0
DEFAULT_TIMEOUT = 10.0
LONG_TIMEOUT = 30.0
MAX_MESSAGE_BYTES = 10 * 1024 * 1024
KEY_BYTES = 32
SESSION_PATH = os.path.expanduser("~/.tonable/session.json")

# A web page can make a browser send these to a loopback port; we never answer them.
HTTP_METHODS = (
    b"GET ",
    b"POST ",
    b"PUT ",
    b"HEAD ",
    b"DELETE ",
    b"OPTIONS ",
    b"PATCH ",
    b"CONNECT ",
    b"TRACE ",
)


class CommandError(Exception):
    """An error the client should see as is: `code` for programs, message for people."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class MessageTooLarge(Exception):
    pass


class LineReader:
    """Reads newline-terminated messages, each at most MAX_MESSAGE_BYTES."""

    def __init__(self, sock):
        self._sock = sock
        self._buffer = bytearray()

    def peek_start(self, size):
        """Up to `size` first bytes, without consuming them."""
        while len(self._buffer) < size and b"\n" not in self._buffer:
            chunk = self._sock.recv(65536)
            if not chunk:
                break
            self._buffer += chunk
        return bytes(self._buffer[:size])

    def read_line(self):
        """The next message without its newline, or None when the peer closed."""
        while True:
            end = self._buffer.find(b"\n")
            if end >= 0:
                line = bytes(self._buffer[:end])
                del self._buffer[: end + 1]
                return line
            if len(self._buffer) > MAX_MESSAGE_BYTES:
                raise MessageTooLarge()
            chunk = self._sock.recv(65536)
            if not chunk:
                return None
            self._buffer += chunk


def encode(message):
    return json.dumps(message, ensure_ascii=False, default=str).encode("utf-8") + b"\n"


class Job:
    """One command waiting for Live's main thread."""

    def __init__(self, handler, params):
        self.handler = handler
        self.params = params
        self.state = "queued"  # queued -> running -> done, or queued -> cancelled
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.reply = None

    def run(self, log):
        with self.lock:
            if self.state != "queued":
                return
            self.state = "running"
        try:
            self.reply = {"ok": True, "result": self.handler(self.params)}
        except CommandError as err:
            self.reply = {"ok": False, "code": err.code, "error": str(err)}
        except Exception as err:
            log("command failed:\n" + traceback.format_exc())
            self.reply = {
                "ok": False,
                "code": "internal",
                "error": f"{type(err).__name__}: {err}",
            }
        with self.lock:
            self.state = "done"
        self.done.set()

    def wait(self, timeout):
        """The reply, or a timeout error that says whether Live changed anything."""
        if self.done.wait(timeout):
            return self.reply
        with self.lock:
            if self.state == "queued":
                self.state = "cancelled"
                return {
                    "ok": False,
                    "code": "timeout_not_started",
                    "error": (
                        f"Live did not start the command within {timeout:g} s, "
                        "so nothing changed. A dialog may be open in Live."
                    ),
                }
        return {
            "ok": False,
            "code": "timeout_running",
            "error": (
                f"The command is still running in Live after {timeout:g} s. It may "
                "still finish: read the state before repeating it."
            ),
        }


class BridgeServer:
    """Listens on a free loopback port and hands commands to Live's main thread.

    `commands` maps a command name to a function of `params`; `hello` is extra data
    for the reply to a good key.
    """

    def __init__(self, commands, hello, log, session_path=None):
        self._commands = commands
        self._hello = hello
        self._log = log
        self._session_path = session_path or SESSION_PATH
        self._jobs = queue.Queue()
        self._clients = set()
        self._clients_lock = threading.Lock()
        self._listener = None
        self._running = False
        self.port = None
        self.key = None

    # --- lifecycle (main thread) ---------------------------------------

    def start(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind((HOST, 0))
        listener.listen()
        self._listener = listener
        self.port = listener.getsockname()[1]
        self.key = secrets.token_hex(KEY_BYTES)
        self._write_session()
        self._running = True
        threading.Thread(
            target=self._accept_loop, name="Tonable accept", daemon=True
        ).start()

    def stop(self):
        self._running = False
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
        with self._clients_lock:
            clients = list(self._clients)
        for conn in clients:
            try:
                conn.shutdown(socket.SHUT_RDWR)
                conn.close()
            except OSError:
                pass
        self._remove_session()
        # Wake any socket thread still waiting on a job.
        self.run_pending(cancel=True)

    def run_pending(self, cancel=False):
        """Run every queued command. Live's main thread calls this on each tick."""
        while True:
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                return
            if cancel:
                with job.lock:
                    if job.state == "queued":
                        job.state = "cancelled"
                        job.reply = {
                            "ok": False,
                            "code": "stopped",
                            "error": "Tonable was switched off in Live",
                        }
                        job.done.set()
                continue
            job.run(self._log)

    # --- session file ---------------------------------------------------

    def _write_session(self):
        folder = os.path.dirname(self._session_path)
        os.makedirs(folder, mode=0o700, exist_ok=True)
        os.chmod(folder, 0o700)
        data = {
            "port": self.port,
            "key": self.key,
            "pid": os.getpid(),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        data.update(self._hello)
        tmp = self._session_path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, self._session_path)

    def _remove_session(self):
        """Remove the session file, unless another Live has written its own since."""
        try:
            with open(self._session_path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("port") == self.port and data.get("key") == self.key:
                os.remove(self._session_path)
        except (OSError, ValueError):
            pass

    # --- socket threads -------------------------------------------------

    def _accept_loop(self):
        while self._running:
            try:
                conn, _ = self._listener.accept()
            except OSError:
                return
            threading.Thread(
                target=self._serve, args=(conn,), name="Tonable client", daemon=True
            ).start()

    def _serve(self, conn):
        with self._clients_lock:
            self._clients.add(conn)
        try:
            reader = LineReader(conn)
            if self._authenticate(conn, reader):
                self._command_loop(conn, reader)
        except (OSError, MessageTooLarge, ValueError):
            pass
        finally:
            with self._clients_lock:
                self._clients.discard(conn)
            try:
                conn.close()
            except OSError:
                pass

    def _authenticate(self, conn, reader):
        conn.settimeout(AUTH_TIMEOUT)
        start = reader.peek_start(max(len(m) for m in HTTP_METHODS))
        if any(start.startswith(m) for m in HTTP_METHODS):
            self._log("closed an HTTP request on the bridge port")
            return False
        line = reader.read_line()
        if line is None:
            return False
        message = json.loads(line)
        key = message.get("key") if isinstance(message, dict) else None
        if not isinstance(key, str) or not hmac.compare_digest(key, self.key):
            conn.sendall(encode({"ok": False, "code": "bad_key", "error": "wrong key"}))
            return False
        conn.sendall(encode(dict(self._hello, ok=True)))
        conn.settimeout(None)
        return True

    def _command_loop(self, conn, reader):
        while self._running:
            try:
                line = reader.read_line()
            except MessageTooLarge:
                conn.sendall(
                    encode(
                        {
                            "ok": False,
                            "code": "too_large",
                            "error": f"message over {MAX_MESSAGE_BYTES} bytes",
                        }
                    )
                )
                return
            if line is None:
                return
            conn.sendall(encode(self._handle(line)))

    def _handle(self, line):
        try:
            message = json.loads(line)
        except ValueError:
            return {"ok": False, "code": "bad_json", "error": "message is not JSON"}
        if not isinstance(message, dict):
            return {
                "ok": False,
                "code": "bad_json",
                "error": "message is not an object",
            }
        reply = {"id": message.get("id")}
        name = message.get("command")
        handler = self._commands.get(name)
        if handler is None:
            reply.update(
                ok=False,
                code="unknown_command",
                error=f"unknown command {name!r}",
            )
            return reply
        params = message.get("params") or {}
        if not isinstance(params, dict):
            reply.update(ok=False, code="bad_params", error="params must be an object")
            return reply
        timeout = LONG_TIMEOUT if message.get("long") is True else DEFAULT_TIMEOUT
        job = Job(handler, params)
        self._jobs.put(job)
        reply.update(job.wait(timeout))
        return reply
