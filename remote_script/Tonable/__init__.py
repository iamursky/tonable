"""Tonable: the Remote Script half of the Tonable MCP server for Ableton Live 12.4+.

`tonable install` copies this folder to <User Library>/Remote Scripts/Tonable. Choose
Tonable in Live's Settings -> Link, Tempo & MIDI -> Control Surface. The script opens a
loopback port (see server.py) and writes its number and a key to
~/.tonable/session.json for the MCP server.
"""

import importlib
import sys

from . import dispatch, version
from .server import BridgeServer
from .version import VERSION

# `tonable install` reloads these in a running Live; dispatch then reloads the
# command modules it lists. server.py is never reloaded: it owns the open socket.
RELOADABLE = ("version", "dispatch")

try:
    import Live
except ImportError:  # imported by the tests, outside Live
    Live = None


def create_instance(c_instance):
    """Live calls this once when Tonable is chosen in the Control Surface list."""
    return Tonable(c_instance)


class Tonable:
    def __init__(self, c_instance):
        self._c_instance = c_instance
        self.live_version = self._read_live_version()
        self._commands = dispatch.commands(self)
        self._commands["reload"] = self._reload
        self._server = BridgeServer(
            self._commands,
            {"script_version": VERSION, "live_version": self.live_version},
            self.log,
        )
        try:
            self._server.start()
        except Exception as err:
            self.log(f"could not start: {type(err).__name__}: {err}")
            self.show_message(f"Tonable could not start: {err}")
            self._server = None
            return
        self.log(f"{VERSION} listening on 127.0.0.1:{self._server.port}")
        self.show_message("Tonable is ready")

    def _reload(self, params):
        """Load the newly installed command modules without restarting Live."""
        for name in RELOADABLE:
            module = sys.modules.get(f"{__name__}.{name}")
            if module is None:
                importlib.import_module(f".{name}", __name__)
            else:
                importlib.reload(module)
        fresh = dispatch.commands(self)
        fresh["reload"] = self._reload
        self._commands.clear()
        self._commands.update(fresh)
        self.log(f"reloaded {version.VERSION}")
        return {"script_version": version.VERSION, "commands": sorted(fresh)}

    @property
    def song(self):
        return self._c_instance.song()

    def log(self, message):
        self._c_instance.log_message("[Tonable] " + str(message))

    def _read_live_version(self):
        if Live is None:
            return None
        app = Live.Application.get_application()
        parts = (
            app.get_major_version(),
            app.get_minor_version(),
            app.get_bugfix_version(),
        )
        return ".".join(str(p) for p in parts)

    # --- Live calls these ---------------------------------------------

    def update_display(self):
        """Live calls this about ten times a second on its main thread."""
        if self._server is not None:
            self._server.run_pending()

    def disconnect(self):
        if self._server is not None:
            self._server.stop()
            self._server = None

    def connect_script_instances(self, instances):
        pass

    def can_lock_to_devices(self):
        return False

    def lock_to_device(self, device):
        pass

    def unlock_from_device(self, device):
        pass

    def toggle_lock(self):
        pass

    def set_appointed_device(self, device):
        pass

    def suggest_input_port(self):
        return ""

    def suggest_output_port(self):
        return ""

    def suggest_map_mode(self, cc_no, channel):
        return Live.MidiMap.MapMode.absolute

    def supports_pad_translation(self):
        return False

    def show_message(self, message):
        self._c_instance.show_message(message)

    def request_rebuild_midi_map(self):
        self._c_instance.request_rebuild_midi_map()

    def build_midi_map(self, midi_map_handle):
        pass

    def receive_midi(self, midi_bytes):
        pass

    def handle_sysex(self, midi_bytes):
        pass

    def refresh_state(self):
        pass

    def is_extension(self):
        return False
