# Architecture and implementation notes

This document describes Tonable 0.5.2. It replaces early planning notes with the
implemented design. See [tools](tools.md) for the public API and
[client setup](clients.md) for integration.

## Two local processes

1. `src/tonable/` runs under Python 3.11+ outside Live. FastMCP exposes tools over
   stdio. The CLI installs the Remote Script and diagnoses its connection.
2. `remote_script/Tonable/` runs in Live's embedded Python. Socket threads handle
   messages; `update_display` executes queued commands on Live's main thread.

MCP clients start the first process. Live starts the second when Tonable is
selected as a Control Surface. There is no HTTP server and no hosted service.
`inspect_preset_file` reads permitted files locally without a Live connection.

## Bridge protocol

The Remote Script binds to `127.0.0.1` with an OS-assigned port. It generates a
32-byte random key and writes a session file at `~/.tonable/session.json` with
mode `0600`. The MCP process reads this file and authenticates with the key in
its first JSON message. HTTP-looking requests are rejected.

Requests and replies are UTF-8 JSON, one message per line. Requests contain
`id`, `command`, `params` and optionally `long`. Replies carry the same `id` and
`ok`, with a `result` or a stable error `code` and message.

| Limit | Value |
|---|---|
| Connection timeout | 3 seconds |
| Authentication timeout | 3 seconds |
| Ordinary command deadline | 10 seconds |
| Long command deadline | 30 seconds |
| Client reply wait | Command deadline plus 3 seconds |
| Maximum message size | 10 MiB |

The constants in both bridge implementations must agree; socket tests check
this. Requests are serialized by the MCP bridge. A queued command that misses
its deadline is cancelled. A command already running may complete after the
caller times out. Clients must read state before repeating an uncertain edit.

## Public API stability

The server and package are named `tonable`, the Control Surface folder is
`Tonable`, and the session path remains `~/.tonable/session.json`. Tool names,
argument names, object addresses, wire commands and error codes remain unchanged
during publication preparation. No protocol or configuration migration is needed.

Tools have static descriptions and schemas because clients may cache discovery.
The MCP initialization response reports Tonable's version, not the SDK version.
Reconnect the MCP server after an upgrade. Schemas use plain JSON types; optional
fields accept empty values without forcing clients to construct unions.

## Editing model

Object addresses use zero-based indices and rack paths; see [tools](tools.md).
Reads return names alongside addresses. Deletion checks the supplied exact name
against the current object. Each editing operation uses Live's undo step; only
the outermost call opens a step so a `batch` remains one undo operation.
Partial failures are reported, not rolled back. Undo history belongs to the
entire Set and can include edits made outside Tonable.

Parameter conversion uses Live's display strings and reports the actual applied
value. Envelope events are written from the last time backward so segment ends
exist before curve coefficients are set. Coincident events preserve jump order;
readback accounts for Live's float32 event times.

## Libraries and installation

Live's browser is indexed on first use and cached until `refresh`. The search
returns every match unless `limit` is supplied; duplicate browser views of the
same preset are collapsed. Native devices can be inserted at a requested index.
Presets load through Live's browser and can replace an existing instrument.

The installer finds the newest Live preferences in `~/Library/Preferences/Ableton`
and reads the User Library from `Library.cfg`. It replaces the Tonable Remote
Script folder there. The configured library can be outside the default Music
folder. Offline preset reads resolve symlinks and restrict access to User Library,
configured Packs and the standard Live 12 Suite Core Library path.

`tonable install --reload` asks an active script to reload command modules.
Installation alone only copies files. Socket code is
not reloaded; changes to it require a Live restart. The installed wheel includes
the Remote Script source, so normal use does not need the repository checkout.

## Live API evidence and limits

Development checks recorded on 6 November 2026 in Live 12.4.16 found:

- Native device insertion, Session MIDI note editing and parameter display
  conversion worked.
- Session mixer and macro envelopes supported curves and jumps. Copying Session
  clips to Arrangement carried automation, but Arrangement automation could not
  be read through this API.
- CC Control exposed Custom A rather than a named Sustain parameter. A listening
  check confirmed the pedal behavior with Custom A set to CC 64 in Live.
- Browser traversal took about five seconds for roughly 60,000 items. Core
  Library, Packs and User Library were usable; Places was not exposed to scripts
  in those runs.
- Batch edits were undone in a single step. Reloading command modules worked
  without restarting Live.

These are historical observations, not results from publication preparation.
Repeat the [manual checklist](../tests/manual_checklist.md) after Live upgrades.
The optional [probe](../probe/README.md) preserves direct API diagnostics and
writes reports locally; tests check its guards without running Live.
