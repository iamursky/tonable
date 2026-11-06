# Optional Live API diagnostics

`TonableProbe` is a developer Remote Script for checking assumptions about Live's
Python API after an upgrade. It is **not an MCP server**, opens no network socket
and does not run during normal Tonable use. It is retained in the source
repository because fake-Live unit tests cannot confirm browser visibility,
automation rendering or audible sustain. It ships in the source archive for
developers, but not in the installed wheel.

The probe creates test tracks, devices, MIDI clips and automation. It refuses to
run when regular tracks contain devices or Session/Arrangement clips, and skips a
finished report. These guards are tested in `tests/test_probe.py`. Always use a
disposable empty Set; this is a writing diagnostic, not a read-only health check.

## Requirements and installation

Use macOS, uv and Live 12.4+. The full diagnostic expects Operator, Reverb,
CC Control, the Core Library presets **Electric Bass Soft** and **Ac Piano Upright**,
and **Electric Keyboards/Sounds/Wurly Piano/Basic Wurly DI.adg** in Packs. Missing
content is reported as a failed check; it is not downloaded or bundled.

From the repository root:

```sh
probe/install.sh
```

The installer uses the User Library from Live's newest `Library.cfg`, just like
`tonable install`. It installs only `Remote Scripts/TonableProbe` there. To enable
the optional Places experiment, supply an existing local `.adg` preset:

```sh
probe/install.sh --places-preset /absolute/path/to/preset.adg
```

It copies that file to `~/.tonable/probe-places/Tonable Probe Places.adg`. Add
`~/.tonable/probe-places` to Places in Live before selecting the probe. Without
this optional setup, the Places check reports the folder as missing. The Packs
check navigates the browser by relative path and needs no machine-specific disk
location. The Packs result now records `browser_path` instead of the old
workstation-only `file_exists` field. Scripts that parse probe reports must use
that relative browser path; the MCP tools and bridge protocol are unchanged.

If an older probe was installed into several User Libraries, disable it in Live
and remove extra `Remote Scripts/TonableProbe` copies manually. The current
uninstaller only touches the configured library.

## Run and inspect

1. Save any work, restart Live, and choose **File → New Live Set**.
2. Set a Control Surface slot to **TonableProbe** with Input and Output **None**.
3. Wait for `TonableProbe: done, report in ~/.tonable/probe-report.json`. Browser
   traversal can briefly freeze Live. Steps run on successive Live ticks; a
   failed step is recorded and later steps still run.
4. In Session View, play **Pedal: off bars 1-2, on bars 3-4** on **Probe Sustain**.
   Compare short notes in bars 1–2 with sustain in bars 3–4. Check which CC
   **Custom A** targets in CC Control; the intended setting is **64 Sustain**.
5. Play **Release macro: low to high** on **Probe Bass** and listen for a longer
   release toward the end.
6. In Arrangement View, inspect **Probe Operator** in bars 1–4 for track volume
   automation. Record what you hear and see alongside the JSON results.
7. Stop playback, set the probe Control Surface slot to **None**, and close the
   disposable Set without saving.

Checks cover browser traversal and Places exposure; native device insertion;
loading Core/Packs presets; rack macro names; sustain, macro and mixer envelopes;
the actual Remote Script location; and Arrangement clip creation/copying.
Historical observations from Live 12.4.16 are summarized in
[architecture notes](../docs/plan.md#live-api-evidence-and-limits).

A `done` status means the run finished, not that every check passed. Review each
step and check, plus the listening/visual results. The report is updated after
every step and survives failures. To rerun, disable the probe, remove your local
`~/.tonable/probe-report.json`, open another empty Set and select it again.

## Privacy and cleanup

Reports can include absolute paths, browser URIs, installed content names, Python
version and tracebacks. They stay under `~/.tonable`; review and redact them before
sharing. Never copy runtime reports, presets or Live Sets into the repository.

```sh
probe/install.sh uninstall
```

This removes only the installed probe script. It preserves reports and optional
Places files; remove those manually when no longer needed and remove the Places
entry in Live. It does not change the production Tonable Control Surface slot.
