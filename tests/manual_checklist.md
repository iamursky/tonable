# Manual checks inside Ableton Live

Run these after changing the Remote Script or upgrading Live. Use a disposable
empty Set (File → New Live Set) and your own test tracks. Coordinate with anyone
else controlling Live: its undo history is shared.

## Setup

1. Close Live. Install the approved wheel with
   `uv tool install --force --python 3.11 /absolute/path/to/tonable.whl`.
   Run `tonable install --replace --dry-run`, confirm the User Library path,
   then run `tonable install --replace`. Restart Live, select Tonable as a Control
   Surface (Input and Output: None), and run `tonable doctor`. For a custom
   library, pass `--user-library PATH` to installation and doctor.
2. Reconnect Tonable in your MCP client so it discovers the current 31 tools.
3. Call `live_status` and `read_set`; compare the result with Live.

## Editing checks

- `create_track` → `write_clip` with a chord and one invalid note (`H3`) →
  `read_clip`. Confirm the valid notes are written and the invalid one is rejected.
- `edit_notes`: transpose, quantize and change velocity for selected pitches.
- `update_track`: volume `-6` reads as `-6.0 dB`, pan `25L`, send A `-12`.
- `find_in_library`: search with and without `limit`, refresh the cache.
- `load_device`: Reverb by name, a preset by browser path and name, and a pack
  preset by file path. A file outside supported library folders must be refused.
- `set_device_params`: set Release to `400 ms`, then read it back. A misspelled
  name such as `Releas` should suggest the correct parameter.
- `write_envelope` → `read_envelope`: volume curve, macro jump and send envelope.
- `scene`: create and rename; `duplicate`: clip and device; `transport`:
  `fire_clip` and `stop_track`; `delete`: reject an incorrect confirmation name
  and accept the exact current name.
- `batch`: two edits followed by one `undo` must undo both. Check that a failed
  action is reported and that `stop_on_error` stops later actions.
- `arrangement`: `place_scene` at bar 65, `create_clip`, `delete_clip`,
  `add_locator`, `rename_locator`, `delete_locator`. Confirm copied automation
  visually in Live; it cannot be read back through the API.
- `inspect_preset_file`: inspect a permitted `.adg`/`.adv`; reject a file outside
  the supported library roots.

## Checks for the 0.6 additions

Run in Live 12.4.16 (Suite, macOS, a disposable Set) on 14 November 2026: everything
below except `tap_tempo`, `trigger_session_record` and `capture_midi` with recorded MIDI, `link`, `convert_audio` `slices_to_drum_rack` / `pad_to_track` / `move_devices_to_drum_rack`, Looper recording, `copy_pad` and `insert_chain`, Simpler sample actions that change content, `app` scroll, zoom, browse and preview, and audio-track channel routing. That run found and fixed: Live's classes report their module
as `Song`, `Track` and so on (not `Live.*`); the mixer's choice lists are enum classes;
Clip has no follow-action members in this Live; `count_in_duration` has no setter;
`punch_in` and similar Song writes show up after `sync_parameter_changes`; Live's
`add_warp_marker` needs a `Clip.WarpMarker` built with named arguments; and a `batch`
needed the same flush to be one undo step. Repeat it after Live upgrades.

For every write, compare the `now` value in the answer with what Live shows, and treat
any `error` line saying Live did not take the value as a finding, not a failure of the check.
Also look at one clip in Live: its launch mode, launch quantization and legato must match
what `update_clip` reported.

- `live_api`: `info` on `song`. If it answers `not a Live object`, the assumption
  that Live's classes report a module starting with `Live` is wrong; record the
  module name from `live_api` `info`. Then `get` `tempo`; `set` without `write`
  must be refused; `set` with `write: true` and `call` of a `delete_*` method
  without `confirm` must be refused.
- `update_set`: `record`, `overdub`, `punch_in`, `clip_trigger_quantization`,
  `midi_recording_quantization`, `groove_amount`. Check that each label maps to the
  value Live shows (the numbers are from memory of the Object Model).
- `transport`: `jump_by` (negative too), `next_locator`, `previous_locator`,
  `tap_tempo`, `capture_midi` after playing a few notes, `stop_clip`,
  `back_to_arranger` while a Session clip plays.
- `update_track`: `monitoring`, `crossfade`, `panning_mode` with `pan_left` and
  `pan_right`, `folded` on a group, `input_channel`, and `cue_volume_db` and
  `crossfader` on `m`.
- `scene`: set `time_signature` to `3/4`, then `off`.
- `write_clip` with `probability`, `velocity_deviation` and `release_velocity`;
  `read_clip` returns them; `edit_notes` `probability`, `mute`, `unmute`.
- `update_clip` on a MIDI and an audio clip: launch mode and quantization labels,
  loop and
  marker changes in both orders, `time_signature`, `groove` (after `groove` list),
  `warp_mode` (an unavailable mode must be refused), `gain`, `pitch_coarse`,
  actions `quantize`, `crop`, `clear_envelopes`, and warp marker add, move, remove.
- `create_audio_clip`: a Session slot and a bar on the timeline; a MIDI track and a
  non-audio file must be refused.
- `read_clip`, `write_clip` and `edit_notes` on a timeline clip (`t0/a0`).
- `arrangement`: `list` shows addresses and take lanes; `copy_clip` and `move_clip`
  on a timeline clip (`move_clip` onto its own span must be refused); `add_take_lane`.
- `convert_audio`: `audio_to_midi` for drums, melody and harmony on a short audio
  clip, `to_simpler`, `to_drum_rack`, `slices_to_drum_rack`. Read the track list
  after each; the new track appears a moment after the answer.
- `configure_device`: call it with only a target on a Simpler, Wavetable, Drift,
  Compressor, EQ Eight and a Drum Rack pad. Change one setting on each and check
  Live. Members listed as unverified in `specialized.py` (Looper, the Simpler sample
  child, `selected_band`, chain properties) need particular attention.
- `app`: `info`, `select` a track and a device, `show_view` / `hide_view` for
  Browser and Detail, `preview` a library sound and `stop_preview`.
- `groove`: `list`, then `update` one groove's `timing_amount` and the Set's
  `groove_amount`.

Stop playback, remove test tracks and locators, and check `arrangement list` for
leftovers. Close the disposable Set without saving if it is no longer needed.

## Evidence record

A development run on 6 November 2026 exercised the main editing flow above in
Live 12.4.16. This is historical evidence; it is not a new live test of the
publication changes. For a new run, record the commit, macOS and Live versions,
client/version, commands, pass/fail per check, and listening or visual results.
Keep raw reports private until local paths and Set names have been reviewed.
