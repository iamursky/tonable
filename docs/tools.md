# Tonable tools

Tonable 0.5.2 exposes 24 MCP tools. Use `live_status` first, then read the target
before editing it. Tool descriptions and input schemas provide the full argument
lists. Most edits form one Live undo step; `batch` groups several edits into one.
Undo history is shared with every person and controller working in the Set.

## Addresses and time

| Address | Meaning |
|---|---|
| `t0` | First track; track and device indices start at zero |
| `rA` | Return track A |
| `m` | Master track |
| `t0/d1` | Second device on the first track |
| `t0/d0/c1/d0` | First device in the second chain of a rack |
| `t0/d0/pC1` | Drum Rack pad C1 |
| `t0/s2` | Session clip in slot 2 on the first track |
| `s2` | Scene 2 |
| `t0/d0:Release` | Release parameter of that device, for an envelope |

Times are quarter-note beats unless an argument says bars. `at_bar` starts at 1;
responses may also use `bar|beat`, such as `17|1`. MIDI note names use **C3 = 60**.
Read addresses again after inserting, moving or deleting objects.

## Set and transport

| Tool | Purpose |
|---|---|
| `live_status` | Connection, versions, tempo and Set dimensions |
| `read_set` | Tracks, returns, scenes and clips, locators and loop |
| `update_set` | Tempo, time signature, loop, metronome and scale |
| `transport` | Start, stop, continue, launch clips or scenes, stop a track, jump, restore automation |
| `undo` | Undo or redo a step in the shared Live history |
| `scene` | Create, rename, set color or tempo, duplicate, capture playing clips |

## Tracks

| Tool | Purpose |
|---|---|
| `read_track` | Mixer, routing, device tree, Session and Arrangement clips |
| `create_track` | Create a MIDI, audio or return track |
| `update_track` | Name, color, dB volume, pan, sends, mute/solo/arm and routing |
| `delete` | Delete a track, return, device, clip or scene; requires its exact name |
| `duplicate` | Copy a track, scene, clip or device |

## Library and devices

| Tool | Purpose |
|---|---|
| `find_in_library` | Search Live's browser; all matches by default, optional `limit` and cache `refresh` |
| `load_device` | Load a built-in device by name, or a preset by browser path, name or permitted file path |
| `read_device` | Parameters with Live display values; rack macros and chains |
| `set_device_params` | Set named parameters using display text or raw values; report actual values |
| `update_device` | Enable, rename, move, change macro visibility/variations, mute or solo chains/pads |
| `inspect_preset_file` | Read devices, macros, chains and pads from `.adg`/`.adv` files without Live |

The first library search walks and caches the browser; it took about five seconds
in an earlier Live 12.4.16 run. Timing depends on installed content. Built-in
devices accept a position; presets load through the browser. Loading an instrument
can replace the existing instrument, which is reported in `replaced`.

## Clips and envelopes

| Tool | Purpose |
|---|---|
| `read_clip` | Read a Session clip, loop and all MIDI notes |
| `write_clip` | Create or update a Session MIDI clip, replacing or adding notes |
| `edit_notes` | Delete, transpose, shift, quantize, set velocity or length in a selected range |
| `read_envelope` | Read parameter automation points from a Session clip |
| `write_envelope` | Replace or clear mixer, device or macro automation; supports jumps and curves |

## Arrangement and grouped actions

| Tool | Purpose |
|---|---|
| `arrangement` | List timeline clips; place a scene, copy/create/delete clips, add/rename/delete locators |
| `batch` | Run several commands in order as one undo step |

`batch` returns a result for each action. With `stop_on_error: true`, it stops at
the first failed action; it does not roll back earlier successful actions. Nested
batches and script reloads are excluded.

## Examples

These are tool names and JSON arguments, not shell commands. Use a disposable Set
and replace addresses with those returned by `read_set` or `create_track`.

Create a MIDI track with `create_track`:

```json
{"kind": "midi", "name": "Sketch"}
```

If it returns `t2`, call `write_clip`:

```json
{
  "track": "t2",
  "slot": 0,
  "name": "Sketch chord",
  "length_beats": 16,
  "mode": "replace",
  "notes": [
    {"pitch": "C3", "start": 0, "length": 4, "velocity": 90},
    {"pitch": "E3", "start": 0, "length": 4, "velocity": 90},
    {"pitch": "G3", "start": 0, "length": 4, "velocity": 90}
  ]
}
```

Read it back with `read_clip`:

```json
{"track": "t2", "slot": 0}
```

Search with `find_in_library`, then pass a returned path to `load_device`:

```json
{"query": "Electric Bass", "limit": 10}
```

Write a volume ramp with `write_envelope`:

```json
{
  "track": "t2",
  "slot": 0,
  "parameter": "volume",
  "points": [{"time": 0, "value": "-18 dB"}, {"time": 16, "value": "-6 dB"}]
}
```

## Values and errors

- Mixer values accept numbers or display text: `-6`, `"-6"` and `"-6 dB"` for
  volume; `"25L"`, `"C"` and `"30R"` for pan. Device parameters accept display
  values such as `"400 ms"` and `"On"` where Live supports them.
- Optional fields accept `null` and `""` as omitted; clearing operations are
  documented explicitly, such as empty `points` clearing an envelope.
- Invalid notes, parameters or batch actions are reported individually. Other
  valid items can still be applied; inspect `rejected` and per-action errors.
- `timeout_not_started` means the queued command was cancelled before execution.
  For `timeout_running` or `connection_lost`, read the state before retrying.

## Limitations

- Places folders were not visible through the Python browser API in Live
  12.4.16. Put presets in User Library or Packs. Offline preset inspection also
  allows Core Library; its discovery currently assumes the standard macOS Live
  12 Suite application path.
- Direct MIDI CC envelopes are unavailable. For sustain, use CC Control before
  the instrument and automate Custom A; verify in Live that it targets CC 64.
- Arrangement automation cannot be read back. Session envelopes can be copied
  with clips using `arrangement` actions `place_scene` or `copy_clip`.
- `write_clip` and `read_clip` address Session clips. Use `arrangement` to create
  timeline MIDI clips and list them.
- Saving Sets, audio export and freezing tracks are unavailable.
