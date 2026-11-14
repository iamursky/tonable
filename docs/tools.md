# Tonable tools

Tonable 0.6.0 exposes 31 MCP tools. Use `live_status` first, then read the target
before editing it. Tool descriptions and input schemas provide the full argument
lists. Most edits form one Live undo step; `batch` groups several edits into one.
Undo history is shared with every person and controller working in the Set.

**Status of the 0.6 additions.** Items marked *new* were added in 0.6.0 and have run
only against a stand-in for Live's API. Live silently keeps the old value for many
invalid writes, so every write is read back and answered as a result line with what
Live now holds (`now`), or an `error` when it kept the old value. Check the
[manual checklist](../tests/manual_checklist.md) in a disposable Set first.

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
| `t0/a1` | *New.* Second Arrangement clip on the first track, in timeline order (see `arrangement` `list`) |
| `s2` | Scene 2 |
| `t0/d0:Release` | Release parameter of that device, for an envelope |

Times are quarter-note beats unless an argument says bars. `at_bar` starts at 1;
responses may also use `bar|beat`, such as `17|1`. MIDI note names use **C3 = 60**.
Read addresses again after inserting, moving or deleting objects.

## Set and transport

| Tool | Purpose |
|---|---|
| `live_status` | Connection, versions, tempo and Set dimensions |
| `read_set` | Tracks, returns, scenes and clips, locators and loop; *new:* recording and quantization settings and Set facts (length, position, what can be undone) |
| `update_set` | Tempo, time signature, loop, metronome, scale; *new:* record, overdub, session record, automation arm, punch in/out, count-in, launch and record quantization, groove and swing amount, scale mode, select-on-launch, exclusive arm/solo, Link |
| `transport` | Start, stop, continue, launch clips or scenes, stop a track, jump, restore automation; *new:* `stop_clip`, `jump_by`, `next_locator`, `previous_locator`, `jump_in_clip`, `play_selection`, `tap_tempo`, `capture_midi`, `trigger_session_record`, `back_to_arranger` |
| `undo` | Undo or redo a step in the shared Live history |
| `scene` | Create, rename, set color, tempo or *new:* time signature, duplicate, capture playing clips |

## Tracks

| Tool | Purpose |
|---|---|
| `read_track` | Mixer, routing, device tree, Session and Arrangement clips; *new:* monitoring, crossfader assignment, freeze state, playing slot |
| `create_track` | Create a MIDI, audio or return track |
| `update_track` | Name, color, dB volume, pan, sends, mute/solo/arm and routing; *new:* input/output channels, monitoring, crossfader assignment, panning mode with split-stereo pans, group folding, implicit arm, master cue volume and crossfader |
| `delete` | Delete a track, return, device, clip or scene; requires its exact name |
| `duplicate` | Copy a track, scene, clip or device |

## Library and devices

| Tool | Purpose |
|---|---|
| `find_in_library` | Search Live's browser; all matches by default, optional `limit` and cache `refresh` |
| `load_device` | Load a built-in device by name, or a preset by browser path, name or permitted file path |
| `read_device` | Parameters with Live display values; rack macros and chains; *new:* `settings` for devices with internals outside the parameters |
| `set_device_params` | Set named parameters using display text or raw values; report actual values |
| `update_device` | Enable, rename, move, change macro visibility/variations, mute or solo chains/pads |
| `inspect_preset_file` | Read devices, macros, chains and pads from `.adg`/`.adv` files without Live |

The first library search walks and caches the browser; it took about five seconds
in an earlier Live 12.4.16 run. Timing depends on installed content. Built-in
devices accept a position; presets load through the browser. Loading an instrument
can replace the existing instrument, which is reported in `replaced`.

| `configure_device` | *New.* Device-specific settings and actions that are not parameters; call it with only a target to list what that device offers |

`configure_device` covers Simpler (playback mode, sample, slices, reverse/crop/warp
actions), Wavetable (voices, oscillator wavetables, modulation matrix), Drift and
Meld voicing, Compressor sidechain source, EQ Eight modes, Hybrid Reverb impulse
responses, Roar, Shifter, Spectral Resonator, Looper, rack chains (color, choke
group, notes), Drum Rack pads and `copy_pad`, plug-in editors, and any device's
collapsed state and A/B compare. A pad writes to every chain on it. Names marked as
unverified in the module docstring come from the Live Object Model as remembered,
not from a probe.

## Clips and envelopes

| Tool | Purpose |
|---|---|
| `read_clip` | Read a clip (`track` + `slot`, or `clip` `t0/s2` / `t0/a1`) with loop, settings and all MIDI notes; audio clips add file, warp and markers |
| `write_clip` | Create or update a MIDI clip (also a timeline clip), replacing or adding notes; notes may carry *new:* `probability`, `velocity_deviation`, `release_velocity` |
| `edit_notes` | Delete, transpose, shift, quantize, set velocity or length, *new:* mute, unmute, probability, velocity deviation, release velocity |
| `update_clip` | *New.* Name, color, mute, loop and markers, time signature, launch mode and quantization, legato, follow actions, groove, stop button; audio warping, warp mode, gain, pitch; actions fire, stop, crop, duplicate loop, quantize, clear envelopes, move playing position, warp markers |
| `create_audio_clip` | *New.* Put an audio file on an audio track, in a Session slot or at a bar |
| `convert_audio` | *New.* Audio to MIDI (drums, melody, harmony), to Simpler, to Drum Rack, slices to Drum Rack, pad to track |
| `read_envelope` | Read parameter automation points from a Session clip |
| `write_envelope` | Replace or clear mixer, device or macro automation; supports jumps and curves |

## Arrangement and grouped actions

| Tool | Purpose |
|---|---|
| `arrangement` | List timeline clips (with `t0/a1` addresses, types and take lanes); place a scene, copy or *new:* move clips, create/delete clips, *new:* add a take lane, add/rename/delete locators |
| `batch` | Run several commands in order as one undo step |

## Interface, grooves and the long tail

| Tool | Purpose |
|---|---|
| `app` | *New.* Live version, CPU load, open dialogs (read only), the current selection; select a track, scene, clip, device or parameter; show, hide, focus, scroll and zoom views; follow song and draw mode; status-bar message; browser preview |
| `groove` | *New.* List the groove pool and tune its grooves and the Set's groove amount; assign a groove to a clip with `update_clip` |
| `live_api` | *New.* Read, set or call any member of Live's object model by path, for what no dedicated tool covers |

`live_api` paths start at `song`, `app` or a Tonable address (`t0`, `rA`, `m`,
`t0/d1`, `s2` for a scene, `t0/s2` for a clip slot, `t0/a1` for a timeline clip)
and continue with `.member` steps; a number indexes a list
(`t0.mixer_device.sends.1`, `song.view.selected_track`). Operations are `info`,
`get`, `set`, `call` and `list`. `set` and `call` need `write: true` and are one
undo step; methods starting with `delete`, `remove`, `clear` or `stop_all` also
need `confirm: true`. Arguments are `[{"value": 4}, {"ref": "t0/d1"}]`. Names that
start with an underscore, modules, files and anything that is not a Live object
are never reachable. The Live-object test (class module `Live`/`Live.*`) is an
assumption checked only against stand-ins; if it fails in Live, `live_api` refuses
rather than opens too much. Prefer a dedicated tool when one exists.

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
  with clips using `arrangement` actions `place_scene` or `copy_clip`. Envelopes
  (`read_envelope`, `write_envelope`) work on Session clips only.
- Saving Sets, exporting audio and freezing or flattening tracks are not exposed by
  Live's Python API. `read_track` shows whether a track is frozen.
- Live cannot create or remove grooves or tuning systems, or clear a clip's groove.
  Group tracks cannot be created from a script; an existing group can be folded.
- `app` never presses a dialog button, and selection or view changes are not undo
  steps. Conversions in `convert_audio` finish a moment after the answer: call
  `read_set` to find the new track.
- `move_clip` copies and deletes, so it refuses a new place that overlaps the clip's
  own span, and the copy replaces timeline clips under its new span.
- Members that older Live versions lack (take lanes, some follow-action fields,
  Link, `capture_midi`) answer with a "this Live does not have it" line, not an
  error that stops the other fields.
