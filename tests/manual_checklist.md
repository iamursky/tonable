# Manual checks inside Ableton Live

Run these after changing the Remote Script or upgrading Live. Use a disposable
empty Set (File → New Live Set) and your own test tracks. Coordinate with anyone
else controlling Live: its undo history is shared.

## Setup

1. Install the package with `uv tool install --force .`, then run
   `tonable install` and `tonable doctor`. Restart Live when the socket code
   changes; otherwise command reload is available from version 0.3.0.
2. Reconnect Tonable in your MCP client so it discovers the current 24 tools.
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

Stop playback, remove test tracks and locators, and check `arrangement list` for
leftovers. Close the disposable Set without saving if it is no longer needed.

## Evidence record

A development run on 6 November 2026 exercised the main editing flow above in
Live 12.4.16. This is historical evidence; it is not a new live test of the
publication changes. For a new run, record the commit, macOS and Live versions,
client/version, commands, pass/fail per check, and listening or visual results.
Keep raw reports private until local paths and Set names have been reviewed.
