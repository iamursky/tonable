"""The MCP server: tool descriptions for the model, calls forwarded to Live over stdio.

Tool descriptions never change at run time: clients cache the tool list
(see docs/clients.md). The tools live in tonable/tools/.
"""

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from tonable import __version__
from tonable.bridge import Bridge, BridgeError

INSTRUCTIONS = """\
Tonable controls Ableton Live 12 on this computer through a Remote Script inside Live.
Call live_status first: it says whether Live is connected and what Set is open.
Addresses: t0 is the first track (numbers from 0), rA return track A, m the master.
Devices: t0/d0 first device; inside racks t0/d0/c1/d0 (chain 1, device 0);
Drum Rack pads t0/d0/pC1 (note names with C3 = MIDI 60).
Times are in beats (quarter notes) unless a field says bars.
Read before you change anything, and quote the address and name to the user.
If a call fails with code not_running, tell the user to choose Tonable in Live's
Settings -> Link, Tempo & MIDI -> Control Surface.
A timeout_not_started error means nothing changed. timeout_running or
connection_lost means the command may still have run: read the state before
repeating it.
"""


def read_only(title):
    """Annotations for a tool that only reads Live."""
    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


mcp = FastMCP("tonable", instructions=INSTRUCTIONS)
# FastMCP would report the mcp library's version. Clients may cache the tool list
# by server name and version, so report ours: a new release then looks new.
mcp._mcp_server.version = __version__
bridge = Bridge()


def call(command, params=None, long=False):
    """Run a command in Live; a failure becomes a tool error the model can read."""
    try:
        try:
            return bridge.request(command, params, long=long)
        except BridgeError as err:
            # The command needed one more Live tick (the playhead, for locators).
            if err.code != "retry":
                raise
            return bridge.request(command, params, long=long)
    except BridgeError as err:
        text = f"{err.code}: {err}"
        if err.hint:
            text += f" {err.hint}"
        raise ToolError(text) from None


def run():
    mcp.run("stdio")


# Importing the modules registers their tools on `mcp`.
from tonable.tools import (  # noqa: E402, F401
    arrangement,
    batch,
    clips,
    devices,
    envelopes,
    session,
    tracks,
)
