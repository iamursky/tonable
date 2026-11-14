# Tonable

![Tonable — connect your assistant to Ableton Live](https://raw.githubusercontent.com/iamursky/tonable/v0.6.0/assets/tonable-logo.svg)

Tonable connects a local MCP assistant to **Ableton Live 12.4+**. Read a Live Set,
load devices and presets, write MIDI notes, shape automation and arrange scenes
through 31 tools. Tonable runs on your Mac: the assistant starts an MCP server over
stdio, and a Remote Script executes commands inside Live.

Version **0.6.0**. The tools were exercised in Live **12.4.16**, including most of
the 0.6 additions (everything marked *new* in the
[tool reference](https://github.com/iamursky/tonable/blob/v0.6.0/docs/tools.md)); the
tool reference and the [manual checklist](https://github.com/iamursky/tonable/blob/v0.6.0/tests/manual_checklist.md)
list what has not been run in Live yet. Repeat the checklist on your installation in a
disposable Set. Tonable is an independent project, unaffiliated with Ableton AG.

## What you can do

- Inspect tracks, rack chains, Drum Rack pads, parameters, clips and scenes.
- Search Core Library, Packs and User Library; load devices and presets.
- Change mixer settings, routing (with channels), monitoring, crossfader
  assignment, device parameters and rack macros.
- Control the Set: record, overdub, punch, quantization, groove amount,
  Link, scale mode, locators, and transport actions such as capture MIDI.
- Create and edit MIDI clips (Session or timeline) with note probability, velocity
  deviation and release velocity; transpose, shift, quantize and mute notes.
- Set every clip property: loop and markers, launch mode and quantization,
  clip scale, groove; for audio clips warp mode and markers, gain and pitch.
- Put audio files on audio tracks; convert audio to MIDI, Simpler or Drum Rack.
- Configure device internals no parameter exposes: Simpler, Wavetable, Drift,
  Meld, Compressor sidechain, EQ Eight, Hybrid Reverb, Roar, Looper, rack chains.
- Read and write Session automation, including ramps, jumps and curves.
- Copy or move timeline clips, copy whole scenes to Arrangement, add take lanes
  and locators.
- Drive Live's windows, selection and browser preview; tune the groove pool.
- Reach any other Live API member with the guarded `live_api` tool.
- Group edits into one undo step with `batch`; inspect `.adg` and `.adv` files
  without opening Live.

See the [tool reference and examples](https://github.com/iamursky/tonable/blob/v0.6.0/docs/tools.md) for addresses, arguments and
limitations.

## Requirements

- **macOS** for the validated Live workflow. The installer recognizes macOS and
  Windows library locations and accepts an explicit path on any OS. Windows
  discovery is unit-tested; end-to-end Live support on Windows is unverified.
  Preset discovery still uses macOS Core Library paths.
- **Ableton Live 12.4 or newer**, installed and started at least once. Devices and
  presets must be available in your Live edition and installed packs. Max for Live
  is only needed for devices that require it.
- [uv](https://docs.astral.sh/uv/) with Python **3.11+**. The commands below ask uv
  to provide Python 3.11 if needed; no separate Python setup is required.
- A local MCP client that can launch a **stdio** process under the same macOS user
  as Live. Client accounts and subscriptions are separate from Tonable.

## Install without a checkout

Get the wheel, source archive and SHA-256 checksums from the
[GitHub release](https://github.com/iamursky/tonable/releases/tag/v0.6.0).
CI builds and checks each release before publishing its files. You can run the
versioned wheel URL directly, without cloning the repository:


```sh
uvx --python 3.11 --from https://github.com/iamursky/tonable/releases/download/v0.6.0/tonable-0.6.0-py3-none-any.whl tonable libraries
uvx --python 3.11 --from https://github.com/iamursky/tonable/releases/download/v0.6.0/tonable-0.6.0-py3-none-any.whl tonable install
```

The installer lists existing libraries found in Live's preferences. If there are
several, select one; then confirm the displayed path. It only offers the existing
OS default when no configured path is known. An unavailable configured path is
reported; reconnect its drive or pass a verified path explicitly. The installer
never creates a guessed library. In unattended use, supply `--user-library PATH`; `--yes` can confirm a
single detected candidate but cannot resolve ambiguity.

To check a specific destination before copying, use the **User Library root**
from Live's **Settings → Library**, not the `Remote Scripts` folder:

```sh
uvx --python 3.11 --from https://github.com/iamursky/tonable/releases/download/v0.6.0/tonable-0.6.0-py3-none-any.whl tonable install \
  --user-library "/path/to/User Library" --dry-run
```

Remove `--dry-run` to install. An explicit path can create a new library folder,
which is also useful for staging. Files are copied from the package into
`<User Library>/Remote Scripts/Tonable`. Existing Tonable files require
`--replace`; other Remote Scripts stay in place. Symlinked script destinations
are refused. Copying is staged before replacement. The installer does not change
Live preferences, select a Control Surface or contact Live unless you add
`--reload`. Close Live before replacing a component for a release check.

1. Restart Live after installing.
2. Open **Settings → Link, Tempo & MIDI → Control Surface** and choose **Tonable**.
   Leave Input and Output set to **None**.
3. Run `tonable doctor` using the persistent install below, or run `doctor` through
   the same `uvx --from ... tonable` command. For a custom library, pass
   `--user-library "/path/to/User Library"`. All checks should show `OK`.

For a persistent CLI, independent of both the checkout and the wheel's location:

```sh
uv tool install --python 3.11 https://github.com/iamursky/tonable/releases/download/v0.6.0/tonable-0.6.0-py3-none-any.whl
uv tool dir --bin
```

Use the `tonable` executable in that bin directory for setup and client commands.
You can replace the URL with an absolute path to a downloaded wheel. For `uvx`,
keep a local wheel at the configured path: its environment may need to be rebuilt.
See the [official uv tools guide](https://docs.astral.sh/uv/guides/tools/) for tool
isolation.

PyPI publication uses a separate Trusted Publishing job. Once version 0.6.0 is
listed on [the project's PyPI page](https://pypi.org/project/tonable/0.6.0/), you
can use a pinned registry source:

```sh
uvx --python 3.11 --from 'tonable==0.6.0' tonable install
uvx --python 3.11 --from 'tonable==0.6.0' tonable serve
```

The release workflow verifies the registry upload, file hashes and tool discovery.
If PyPI publication has not succeeded, use the GitHub wheel URL above.

### Install from source for development

```sh
uv sync --locked
uv run tonable install --dry-run
uv run tonable install
```

## Connect an assistant

Tonable exposes MCP over **stdio only**. Use the local setup for your client:

- [Codex CLI and IDE extension](https://github.com/iamursky/tonable/blob/v0.6.0/docs/clients.md#codex)
- [Claude Code](https://github.com/iamursky/tonable/blob/v0.6.0/docs/clients.md#claude-code)
- [Claude Desktop](https://github.com/iamursky/tonable/blob/v0.6.0/docs/clients.md#claude-desktop)
- [Other local MCP clients](https://github.com/iamursky/tonable/blob/v0.6.0/docs/clients.md#other-local-mcp-clients)

The examples follow official client documentation. They describe a compatible
transport; they do not certify every client version. Tonable has no HTTP/SSE
endpoint or hosted connector. The private loopback socket inside Live is not an
MCP URL. See [client setup](https://github.com/iamursky/tonable/blob/v0.6.0/docs/clients.md) for sources and verification steps.

Start with a read-only request:

> Use Tonable to check the Live connection and summarize the open Set. Do not edit it.

For an editing example, use a disposable empty Set:

> Create a MIDI track called Sketch. Add a four-bar Session clip with C3, E3 and G3
> on its first beat. Read the clip back and report any rejected notes. Do not start playback.

A MIDI clip needs an instrument before it produces sound. Ask the assistant to
read the current addresses before editing; track and device indices can change.

## Updates and removal

Obtain the new trusted wheel, close Live, and replace the persistent package:

```sh
uv tool install --force --python 3.11 /absolute/path/to/new-tonable.whl
tonable install --replace
tonable doctor
```

Restart Live before running `doctor`, then reconnect the MCP server so the client
refreshes its tools. For an existing component from 0.3.0 onward,
`tonable install --replace --reload` can request a command-module reload. It does
not replace a restart for socket-layer changes or a failed reload. With a `uvx`
client configuration, update its wheel path as well.

To remove the component, run `tonable uninstall`, confirm the library and removal,
then set its Control Surface slot to **None** and remove the MCP client entry.
For unattended removal, use `tonable uninstall --user-library PATH --yes`.
`--dry-run` previews removal. To remove the persistent CLI, use
`uv tool uninstall tonable`. Runtime reports and `~/.tonable` are left in place.

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
uv run python scripts/check_distribution.py \
  --wheel dist/tonable-0.6.0-py3-none-any.whl \
  --sdist dist/tonable-0.6.0.tar.gz --python 3.11
```

Tests use a fake Live API and local loopback sockets. They do not prove audio
quality or replace [checks inside Live](https://github.com/iamursky/tonable/blob/v0.6.0/tests/manual_checklist.md). The optional
[Live API probe](https://github.com/iamursky/tonable/blob/v0.6.0/probe/README.md) is developer diagnostics; normal installation
does not need it and the installed wheel excludes it.

See [architecture](https://github.com/iamursky/tonable/blob/v0.6.0/docs/plan.md) and [publication checks](https://github.com/iamursky/tonable/blob/v0.6.0/docs/publishing.md).

## Acknowledgments and license

Tonable draws on techniques from
[ableton-live-mcp](https://github.com/wstierhout/ableton-live-mcp) and
[Producer Pal](https://github.com/adamjmurray/producer-pal). Attribution and their
MIT notices are in [THIRD_PARTY_NOTICES.md](https://github.com/iamursky/tonable/blob/v0.6.0/THIRD_PARTY_NOTICES.md).

Tonable is licensed under [MIT](https://github.com/iamursky/tonable/blob/v0.6.0/LICENSE), © 2026 Ilya Amursky. Ableton software and
content are not included and remain subject to their own licenses.
