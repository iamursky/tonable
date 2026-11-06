# Tonable

![Tonable — connect your assistant to Ableton Live](assets/tonable-logo.svg)

Tonable connects a local MCP assistant to **Ableton Live 12.4+**. Read a Live Set,
load devices and presets, write MIDI notes, shape automation and arrange scenes
through 24 tools. Tonable runs on your Mac: the assistant starts an MCP server over
stdio, and a Remote Script executes commands inside Live.

Version **0.5.1**. Earlier development runs exercised the tools in Live **12.4.16**;
see the [manual checklist](tests/manual_checklist.md) for checks to repeat on your
installation. Tonable is an independent project, unaffiliated with Ableton AG.

## What you can do

- Inspect tracks, rack chains, Drum Rack pads, parameters, clips and scenes.
- Search Core Library, Packs and User Library; load devices and presets.
- Change mixer settings, routing, device parameters and rack macros.
- Create and edit Session MIDI clips; transpose, shift and quantize notes.
- Read and write Session automation, including ramps, jumps and curves.
- Copy clips or entire scenes to Arrangement; create timeline clips and locators.
- Group edits into one undo step with `batch`; inspect `.adg` and `.adv` files
  without opening Live.

See the [tool reference and examples](docs/tools.md) for addresses, arguments and
limitations.

## Requirements

- **macOS**. Installation and library discovery currently use macOS paths;
  Windows and Linux are not supported by the installer.
- **Ableton Live 12.4 or newer**, installed and started at least once. Devices and
  presets must be available in your Live edition and installed packs. Max for Live
  is only needed for devices that require it.
- **Python 3.11+** and [uv](https://docs.astral.sh/uv/).
- A local MCP client that can launch a **stdio** process under the same macOS user
  as Live. Client accounts and subscriptions are separate from Tonable.

## Install from this repository

Download or clone the repository, open a terminal in its root, then run:

```sh
uv sync --locked
uv run tonable install
```

The installer reads Live's newest preferences and copies the Remote Script into
`<User Library>/Remote Scripts/Tonable`. It falls back to
`~/Music/Ableton/User Library` when no configured library is found.

1. Restart Live after the first install.
2. Open **Settings → Link, Tempo & MIDI → Control Surface** and choose **Tonable**.
   Leave Input and Output set to **None**.
3. Run `uv run tonable doctor`. All checks should show `OK`.

For a persistent command independent of the checkout, install the local package:

```sh
uv tool install .
uv tool dir --bin
```

Use the `tonable` executable in that bin directory when configuring your client.
Do not assume a package with this name on a public registry is this project.

## Connect an assistant

Tonable exposes MCP over **stdio only**. Use the local setup for your client:

- [Codex CLI and IDE extension](docs/clients.md#codex)
- [Claude Code](docs/clients.md#claude-code)
- [Claude Desktop](docs/clients.md#claude-desktop)
- [Other local MCP clients](docs/clients.md#other-local-mcp-clients)

The examples follow official client documentation. They describe a compatible
transport; they do not certify every client version. Tonable has no HTTP/SSE
endpoint or hosted connector. The private loopback socket inside Live is not an
MCP URL. See [client setup](docs/clients.md) for sources and verification steps.

Start with a read-only request:

> Use Tonable to check the Live connection and summarize the open Set. Do not edit it.

For an editing example, use a disposable empty Set:

> Create a MIDI track called Sketch. Add a four-bar Session clip with C3, E3 and G3
> on its first beat. Read the clip back and report any rejected notes. Do not start playback.

A MIDI clip needs an instrument before it produces sound. Ask the assistant to
read the current addresses before editing; track and device indices can change.

## Updates and removal

After updating the checkout:

```sh
uv sync --locked
uv tool install --force .
tonable install
tonable doctor
```

An active Remote Script from version 0.3.0 onward can reload command modules
without restarting Live. Restart Live for socket-layer changes, or when reload
fails. Reconnect the MCP server or restart the client session to refresh its tools.

To remove Tonable, run `tonable uninstall`, set its Control Surface slot to
**None**, and remove the MCP entry from your client. If installed with uv, run
`uv tool uninstall tonable`.

## Data and editing behavior

The Remote Script binds only to `127.0.0.1` on an OS-assigned port. It generates a
random access key and writes `~/.tonable/session.json` with owner-only permissions.
Tonable itself has no hosted service and requires no API key. Your MCP client may
send tool results, including Set names and preset paths, to its model provider.
Never share the session file or commit local reports without reviewing them.

Edits use Live's shared undo history. `batch` groups changes into one step but is
not a transaction: successful actions remain applied if another action fails.
After a timeout or lost connection, read the state before retrying an edit.
Saving Sets, exporting audio and freezing tracks are outside Tonable's API.

## Development

```sh
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

Tests use a fake Live API and local loopback sockets. They do not prove audio
quality or replace [checks inside Live](tests/manual_checklist.md). The optional
[Live API probe](probe/README.md) is developer diagnostics; normal installation
does not need it and the installed wheel excludes it.

See [architecture](docs/plan.md) and [publication checks](docs/publishing.md).

## Acknowledgments and license

Tonable draws on techniques from
[ableton-live-mcp](https://github.com/wstierhout/ableton-live-mcp) and
[Producer Pal](https://github.com/adamjmurray/producer-pal). Attribution and their
MIT notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Tonable is licensed under [MIT](LICENSE), © 2026 Ilya Amursky. Ableton software and
content are not included and remain subject to their own licenses.
