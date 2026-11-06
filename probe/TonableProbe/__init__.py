"""TonableProbe: an optional Live API diagnostic Remote Script (see probe/README.md).

Select it in Live's Control Surface list with an empty Live Set open. It builds a few
test tracks, runs the API checks one step per Live tick and writes the results to
~/.tonable/probe-report.json after every step. It refuses to touch a Set that already
has clips or devices on its tracks, and does nothing once a finished report exists
(delete the report to run again).
"""

import json
import os
import sys
import time
import traceback

try:
    import Live
except ImportError:  # imported by the tests, outside Live
    Live = None

PROBE_VERSION = "0.3"
REPORT_PATH = os.path.expanduser("~/.tonable/probe-report.json")

# What the checks look for. Paths are the files' places on disk; the probe finds the
# matching browser items.
CORE_PRESET = "Electric Bass Soft"
CORE_PIANO = "Ac Piano Upright"
EXPECTED_MACROS = [
    "Filter Cutoff",
    "Filter Reso",
    "LFO Rate",
    "Volume LFO",
    "Decay",
    "Release",
    "Chorus",
    "Saturate",
]
PACK_PRESET = "Electric Keyboards/Sounds/Wurly Piano/Basic Wurly DI.adg"
PLACES_DIR = os.path.expanduser("~/.tonable/probe-places")
PLACES_PRESET = "Tonable Probe Places.adg"
NATIVE_DEVICES = ["Operator", "Reverb", "CC Control"]
SUSTAIN_FALLBACK = "Custom A"

# The test clips: a note on every beat of four 4/4 bars.
CLIP_BEATS = 16.0
NOTE_PITCH = 60
NOTE_BEATS = 0.25
NOTE_VELOCITY = 100

# Browser sections walked by check 8, as Live's Browser attributes.
BROWSER_ROOTS = [
    "instruments",
    "audio_effects",
    "midi_effects",
    "sounds",
    "drums",
    "packs",
    "user_library",
    "current_project",
    "plugins",
    "max_for_live",
]

PRESET_SUFFIXES = (".adg", ".adv", ".amxd")


def create_instance(c_instance):
    return Probe(c_instance)


def plain_name(name):
    """A browser or file name without a preset suffix, lowercase."""
    lowered = str(name).strip().lower()
    for suffix in PRESET_SUFFIXES:
        if lowered.endswith(suffix):
            return lowered[: -len(suffix)]
    return lowered


def describe_param(param):
    out = {"name": param.name}
    for key in ("min", "max", "value", "is_quantized", "is_enabled"):
        out[key] = _safe(lambda k=key: getattr(param, k))
    out["display"] = _safe(lambda: param.str_for_value(param.value))
    if out.get("is_quantized"):
        out["items"] = _safe(lambda: list(param.value_items))
    return out


def describe_device(device):
    return {
        "name": device.name,
        "class_name": _safe(lambda: device.class_name),
        "type": _safe(lambda: int(device.type)),
        "can_have_chains": _safe(lambda: bool(device.can_have_chains)),
    }


def _safe(get):
    try:
        return get()
    except Exception as err:
        return f"<{type(err).__name__}: {err}>"


class Probe:
    def __init__(self, c_instance):
        self._c_instance = c_instance
        self._steps = [
            self._step_start,
            self._step_browser_walk,
            self._step_native_devices,
            self._step_load_core,
            self._step_load_pack,
            self._step_browser_layout,
            self._step_load_places,
            self._step_sustain_track,
            self._step_sustain_cc_control,
            self._step_sustain_envelope,
            self._step_rack_macros,
            self._step_macro_envelope,
            self._step_mixer_envelopes,
            self._step_arrangement,
            self._step_finish,
        ]
        self._next = 0
        self._stopped = False
        self._index = {}
        self._tracks = {}
        self.report = {
            "probe_version": PROBE_VERSION,
            "status": "running",
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "checks": {},
            "steps": [],
        }

    # --- Live calls these ---------------------------------------------

    def update_display(self):
        """Live calls this 10x a second on its main thread: one step a call."""
        if self._stopped or self._next >= len(self._steps):
            return
        step = self._steps[self._next]
        self._next += 1
        started = time.perf_counter()
        entry = {"step": step.__name__[len("_step_") :]}
        try:
            step()
            entry["ok"] = True
        except Exception as err:
            entry["ok"] = False
            entry["error"] = f"{type(err).__name__}: {err}"
            entry["traceback"] = traceback.format_exc()
            self.log("step {} failed: {}".format(entry["step"], entry["error"]))
        entry["seconds"] = round(time.perf_counter() - started, 3)
        self.report["steps"].append(entry)
        # A skipped run leaves the finished report alone.
        if self.report["status"] != "skipped":
            self.write_report()

    def disconnect(self):
        if self.report["status"] == "running" and self._next > 1:
            self.report["status"] = "interrupted"
            self.write_report()

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

    # --- helpers --------------------------------------------------------

    @property
    def song(self):
        return self._c_instance.song()

    @property
    def app(self):
        return Live.Application.get_application()

    def log(self, message):
        self._c_instance.log_message("[TonableProbe] " + str(message))

    def check(self, number, **fields):
        self.report["checks"].setdefault(str(number), {}).update(fields)

    def write_report(self):
        folder = os.path.dirname(REPORT_PATH)
        os.makedirs(folder, mode=0o700, exist_ok=True)
        tmp = REPORT_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.report, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, REPORT_PATH)

    def stop(self, status, message):
        self._stopped = True
        self.report["status"] = status
        self.report["message"] = message
        self.log(message)
        self.show_message("TonableProbe: " + message)

    def new_midi_track(self, key, name):
        song = self.song
        song.create_midi_track(len(song.tracks))
        track = song.tracks[len(song.tracks) - 1]
        track.name = name
        self._tracks[key] = track
        return track

    def load_onto(self, track, item):
        self.song.view.selected_track = track
        self.app.browser.load_item(item)

    def device_names(self, track):
        return [d.name for d in track.devices]

    def find_in_index(self, name):
        return self._index.get(plain_name(name), [])

    def make_clip(self, track):
        slot = track.clip_slots[0]
        if slot.has_clip:
            slot.delete_clip()
        slot.create_clip(CLIP_BEATS)
        clip = slot.clip
        starts = [float(beat) for beat in range(int(CLIP_BEATS))]
        try:
            notes = tuple(
                Live.Clip.MidiNoteSpecification(
                    pitch=NOTE_PITCH,
                    start_time=start,
                    duration=NOTE_BEATS,
                    velocity=NOTE_VELOCITY,
                )
                for start in starts
            )
            clip.add_new_notes(notes)
            method = "add_new_notes"
        except Exception:
            clip.set_notes(
                tuple((NOTE_PITCH, s, NOTE_BEATS, NOTE_VELOCITY, False) for s in starts)
            )
            method = "set_notes"
        return clip, method

    def envelope_for(self, clip, param):
        """The clip's envelope for `param`, created if needed, and how it was got."""
        env = clip.automation_envelope(param)
        if env is not None:
            return env, "existing"
        env = clip.create_automation_envelope(param)
        if env is not None:
            return env, "create_automation_envelope"
        # ableton-live-mcp says Live only creates one for the clip shown in Detail View.
        self.song.view.detail_clip = clip
        env = clip.create_automation_envelope(param)
        return env, "create_automation_envelope after selecting detail_clip"

    def write_events(self, env, points):
        """Write (time, value, coefficients or None) points, the last time first.

        Producer Pal found that Live straightens a curve whose segment end doesn't
        exist yet, and that an event at a taken time goes after the existing ones.
        """
        from Live.Envelope import EnvelopeEvent, EnvelopeEventControlCoefficients

        groups = []
        for point in points:
            if groups and groups[-1][0][0] == point[0]:
                groups[-1].append(point)
            else:
                groups.append([point])
        for group in reversed(groups):
            for t, v, coefficients in group:
                if coefficients is None:
                    env.create_event(EnvelopeEvent(t, v))
                else:
                    c = EnvelopeEventControlCoefficients(*coefficients)
                    env.create_event(EnvelopeEvent(t, v, c))

    def read_events(self, env, param):
        events = []
        for event in env.events_in_range(0.0, CLIP_BEATS * 4):
            item = {"time": event.time, "value": event.value}
            c = _safe(lambda e=event: e.control_coefficients)
            if not isinstance(c, str):
                item["coefficients"] = [c.x1, c.y1, c.x2, c.y2]
            events.append(item)
        samples = []
        for t in (0.0, CLIP_BEATS / 4, CLIP_BEATS / 2, CLIP_BEATS * 3 / 4):
            raw = env.value_at_time(t)
            samples.append(
                {"time": t, "value": raw, "display": param.str_for_value(raw)}
            )
        return {"events": events, "samples": samples}

    def walk_path(self, root, segments):
        """The item at `segments` below `root` (suffixes optional), and the walk."""
        item = root
        walked = []
        for segment in segments:
            wanted = plain_name(segment)
            children = list(item.children)
            match = next((c for c in children if plain_name(c.name) == wanted), None)
            if match is None:
                return None, {
                    "walked": walked,
                    "missing": segment,
                    "choices": [c.name for c in children],
                }
            item = match
            walked.append(match.name)
        return item, {"walked": walked, "uri": _safe(lambda: item.uri)}

    # --- steps ----------------------------------------------------------

    def _step_start(self):
        if os.path.exists(REPORT_PATH):
            try:
                with open(REPORT_PATH, encoding="utf-8") as f:
                    previous = json.load(f)
            except Exception:
                previous = {}
            if previous.get("status") == "done":
                self._stopped = True
                self.report["status"] = "skipped"
                self.log("a finished report exists; delete it to run again")
                self.show_message("TonableProbe: report exists, nothing to do")
                return

        app = self.app
        version = (
            app.get_major_version(),
            app.get_minor_version(),
            app.get_bugfix_version(),
        )
        self.report["live_version"] = ".".join(str(v) for v in version)
        self.report["python_version"] = sys.version
        # Check 7: which Remote Scripts folder Live loaded this copy from.
        self.check(7, script_file=os.path.abspath(__file__))

        busy = []
        for track in self.song.tracks:
            if len(track.devices) > 0:
                busy.append(f"{track.name}: devices")
            if any(slot.has_clip for slot in track.clip_slots):
                busy.append(f"{track.name}: session clips")
            if len(_safe(lambda t=track: list(t.arrangement_clips)) or []) > 0:
                busy.append(f"{track.name}: arrangement clips")
        if busy:
            self.report["not_empty"] = busy
            self.stop("refused", "the Live Set is not empty, open a new empty Set")
            return

        self.report["api_docs"] = {
            name: _safe(lambda n=name: _doc(n))
            for name in (
                "Track.Track.insert_device",
                "Track.Track.create_midi_clip",
                "Track.Track.duplicate_clip_to_arrangement",
                "Clip.Clip.create_automation_envelope",
                "Clip.Clip.add_new_notes",
                "Envelope.Envelope.create_event",
                "Browser.Browser.load_item",
            )
        }
        self.show_message("TonableProbe: running, Live may freeze for a while")

    def _step_browser_walk(self):
        """Check 8: how long walking the whole browser takes."""
        browser = self.app.browser
        roots = [(name, getattr(browser, name, None)) for name in BROWSER_ROOTS]
        roots += [("places:" + r.name, r) for r in browser.user_folders]
        per_root = {}
        total = 0
        started = time.perf_counter()
        for label, root in roots:
            if root is None:
                per_root[label] = "missing"
                continue
            t0 = time.perf_counter()
            count, depth = self._walk(label, root, "", 0)
            total += count
            per_root[label] = {
                "items": count,
                "max_depth": depth,
                "seconds": round(time.perf_counter() - t0, 3),
            }
        self.check(
            8,
            total_items=total,
            total_seconds=round(time.perf_counter() - started, 3),
            per_root=per_root,
            places=[
                {"name": r.name, "uri": _safe(lambda r=r: r.uri)}
                for r in browser.user_folders
            ],
        )

    def _walk(self, label, item, path, depth):
        count = 0
        deepest = depth
        for child in item.children:
            count += 1
            child_path = path + "/" + child.name if path else child.name
            self._index.setdefault(plain_name(child.name), []).append(
                (label, child_path, child)
            )
            sub_count, sub_depth = self._walk(label, child, child_path, depth + 1)
            count += sub_count
            deepest = max(deepest, sub_depth)
        return count, deepest

    def _step_native_devices(self):
        """Check 5: Track.insert_device by name."""
        results = {}
        for name in NATIVE_DEVICES:
            track = self.new_midi_track("native:" + name, "Probe " + name)
            result = {}
            for label, call in (
                (
                    "insert_device(name, index)",
                    lambda t=track, n=name: t.insert_device(n, 0),
                ),
                ("insert_device(name)", lambda t=track, n=name: t.insert_device(n)),
            ):
                try:
                    returned = call()
                    result["call"] = label
                    result["returned"] = _safe(lambda r=returned: describe_device(r))
                    break
                except Exception as err:
                    result[label] = f"{type(err).__name__}: {err}"
            result["devices"] = self.device_names(track)
            results[name] = result
        self.check(5, results=results)

    def _step_load_core(self):
        """Check 4 (Core Library) and the rack for checks 2 and 3."""
        candidates = self.find_in_index(CORE_PRESET)
        listed = [
            {"root": root, "path": path, "uri": _safe(lambda i=item: i.uri)}
            for root, path, item in candidates
        ]
        loadable = [
            c for c in candidates if _safe(lambda i=c[2]: i.is_loadable) is True
        ]
        track = self.new_midi_track("bass", "Probe Bass")
        result = {"candidates": listed, "devices_before": self.device_names(track)}
        if loadable:
            root, path, item = loadable[0]
            self.load_onto(track, item)
            result["loaded_from"] = root + ": " + path
            result["devices_same_tick"] = self.device_names(track)
        self.check(4, core_library=result)

    def _step_load_pack(self):
        """Check 4 (Packs): walk the file's path below Factory Packs in the browser."""
        segments = PACK_PRESET.split("/")
        result = {"browser_path": PACK_PRESET}
        item, walk = self.walk_path(self.app.browser.packs, segments)
        result.update(walk)
        if item is not None:
            track = self.new_midi_track("pack", "Probe Pack")
            self.load_onto(track, item)
            result["devices_same_tick"] = self.device_names(track)
        self.check(4, packs=result)

    def _step_browser_layout(self):
        """Check 4 (Places): where Live 12.4 keeps Places folders.

        Runs 1-3 found browser.user_folders empty although Library.cfg listed the
        folder, so list every Browser attribute and its first level of children, and
        say where the walk met the Places preset.
        """
        browser = self.app.browser
        layout = {}
        for name in dir(browser):
            if name.startswith("_"):
                continue
            value = _safe(lambda n=name: getattr(browser, n))
            entry = {"type": type(value).__name__}
            children = _safe(lambda v=value: list(v.children))
            if isinstance(children, list):
                entry["children"] = [c.name for c in children]
            else:
                items = _safe(lambda v=value: list(v))
                if isinstance(items, list):
                    entry["items"] = [_safe(lambda i=i: i.name) for i in items]
            layout[name] = entry
        found = [
            {"root": root, "path": path, "uri": _safe(lambda i=item: i.uri)}
            for root, path, item in self.find_in_index(PLACES_PRESET)
        ]
        self.check(4, browser_layout=layout, places_preset_in_walk=found)

    def _step_load_places(self):
        """Check 4 (Places): the test folder added to Places before the run."""
        result = {
            "file_exists": os.path.exists(os.path.join(PLACES_DIR, PLACES_PRESET))
        }
        roots = list(self.app.browser.user_folders)
        result["places"] = [
            {"name": r.name, "uri": _safe(lambda r=r: r.uri)} for r in roots
        ]
        folder = next(
            (
                r
                for r in roots
                if os.path.basename(PLACES_DIR) in str(_safe(lambda r=r: r.uri))
                or r.name == os.path.basename(PLACES_DIR)
            ),
            None,
        )
        if folder is None:
            result["error"] = "the probe-places folder is not in Places"
        else:
            item, walk = self.walk_path(folder, [PLACES_PRESET])
            result.update(walk)
            if item is not None:
                track = self.new_midi_track("places", "Probe Places")
                self.load_onto(track, item)
                result["devices_same_tick"] = self.device_names(track)
        self.check(4, places=result)

    def _step_sustain_track(self):
        """Check 1, part 1: a piano to hear the pedal on."""
        candidates = self.find_in_index(CORE_PIANO)
        loadable = [
            c for c in candidates if _safe(lambda i=c[2]: i.is_loadable) is True
        ]
        track = self.new_midi_track("sustain", "Probe Sustain")
        if not loadable:
            raise LookupError(f"no loadable {CORE_PIANO!r} in the browser")
        self.load_onto(track, loadable[0][2])
        self.check(1, piano=loadable[0][0] + ": " + loadable[0][1])

    def _step_sustain_cc_control(self):
        """Check 1, part 2: CC Control in front of the piano, and all its parameters."""
        track = self._tracks["sustain"]
        self.check(1, devices_before=self.device_names(track))
        try:
            track.insert_device("CC Control", 0)
        except Exception:
            track.insert_device("CC Control")
        devices = list(track.devices)
        cc = next((d for d in devices if "cc control" in d.name.lower()), None)
        if cc is None:
            raise LookupError(f"CC Control did not appear: {self.device_names(track)}")
        self.check(
            1,
            devices_after=[d.name for d in devices],
            cc_control=describe_device(cc),
            cc_control_params=[describe_param(p) for p in cc.parameters],
        )

    def _step_sustain_envelope(self):
        """Check 1, part 3: pedal up for bars 1-2, down for bars 3-4."""
        track = self._tracks["sustain"]
        cc = next(d for d in track.devices if "cc control" in d.name.lower())
        params = [p for p in cc.parameters if "sustain" in p.name.lower()]
        # The first run (6 Nov 2026) found no "Sustain": the only on/off control is
        # Custom A, whose CC number must be checked in Live's interface.
        if not params:
            params = [p for p in cc.parameters if p.name == SUSTAIN_FALLBACK]
        self.check(1, sustain_params=[p.name for p in params])
        if not params:
            raise LookupError("CC Control has neither Sustain nor " + SUSTAIN_FALLBACK)
        param = params[0]
        clip, notes_method = self.make_clip(track)
        clip.name = "Pedal: off bars 1-2, on bars 3-4"
        env, how = self.envelope_for(clip, param)
        if env is None:
            raise RuntimeError(f"no envelope for {param.name!r}")
        half = CLIP_BEATS / 2
        self.write_events(
            env,
            [
                (0.0, param.min, None),
                (half, param.min, None),
                (half, param.max, None),
                (CLIP_BEATS, param.max, None),
            ],
        )
        self.check(
            1,
            notes_method=notes_method,
            envelope_how=how,
            envelope=self.read_events(env, param),
            listen="Session: play 'Pedal: off bars 1-2, on bars 3-4' on Probe Sustain",
        )

    def _step_rack_macros(self):
        """Check 3: macro names and macros_mapped of Electric Bass Soft."""
        track = self._tracks["bass"]
        devices = list(track.devices)
        self.check(4, core_devices_next_tick=[d.name for d in devices])
        rack = next(
            (d for d in devices if _safe(lambda d=d: d.can_have_chains) is True), None
        )
        if rack is None:
            raise LookupError("no rack on Probe Bass: %s" % [d.name for d in devices])
        params = list(rack.parameters)
        mapped = _safe(lambda: list(rack.macros_mapped))
        macros = [describe_param(p) for p in params[1:]]
        names_mapped = (
            [macros[i]["name"] for i, m in enumerate(mapped) if m and i < len(macros)]
            if isinstance(mapped, list)
            else mapped
        )
        self.check(
            3,
            rack=describe_device(rack),
            visible_macro_count=_safe(lambda: rack.visible_macro_count),
            macros_mapped=mapped,
            mapped_names=names_mapped,
            expected=EXPECTED_MACROS,
            matches_expected=names_mapped == EXPECTED_MACROS,
            parameters=[describe_param(p) for p in params],
        )

    def _step_macro_envelope(self):
        """Check 2: a curved envelope on the Release macro."""
        track = self._tracks["bass"]
        rack = next(
            d for d in track.devices if _safe(lambda d=d: d.can_have_chains) is True
        )
        param = next((p for p in rack.parameters if p.name == "Release"), None)
        if param is None:
            raise LookupError("the rack has no parameter named Release")
        clip, _ = self.make_clip(track)
        clip.name = "Release macro: low to high"
        env, how = self.envelope_for(clip, param)
        if env is None:
            raise RuntimeError("no envelope for Release")
        self.write_events(
            env,
            [
                (0.0, param.min, (0.2, 0.8, 0.4, 1.0)),
                (CLIP_BEATS, param.max, None),
            ],
        )
        self.check(
            2,
            envelope_how=how,
            envelope=self.read_events(env, param),
            listen="Session: play clip 'Release macro: low to high' on Probe Bass",
        )

    def _step_mixer_envelopes(self):
        """Check 6: curved volume and send A envelopes in a clip on Probe Operator.

        Not on Probe Bass: a volume fade there would mask the Release macro check.
        """
        song = self.song
        track = self._tracks["native:Operator"]
        if len(song.return_tracks) == 0:
            song.create_return_track()
            self.check(6, created_return=True)
        clip, _ = self.make_clip(track)
        clip.name = "Volume and send A: fade in"
        mixer = track.mixer_device
        results = {}
        for label, param, low, high in (
            ("volume", mixer.volume, 0.0, 0.85),
            ("send A", mixer.sends[0], 0.0, 1.0),
        ):
            env, how = self.envelope_for(clip, param)
            if env is None:
                results[label] = "no envelope"
                continue
            self.write_events(
                env,
                [(0.0, low, (0.1, 0.9, 0.3, 1.0)), (CLIP_BEATS, high, None)],
            )
            results[label] = {"how": how, **self.read_events(env, param)}
        self.check(6, results=results)

    def _step_arrangement(self):
        """Check 9: a MIDI clip made in the Arrangement, a Session clip copied there."""
        track = self._tracks["native:Operator"]
        result = {}
        try:
            track.create_midi_clip(CLIP_BEATS * 2, CLIP_BEATS)
            result["create_midi_clip"] = "ok"
        except Exception as err:
            result["create_midi_clip"] = f"{type(err).__name__}: {err}"
        clip = track.clip_slots[0].clip
        try:
            track.duplicate_clip_to_arrangement(clip, 0.0)
            result["duplicate_clip_to_arrangement"] = "ok"
        except Exception as err:
            result["duplicate_clip_to_arrangement"] = f"{type(err).__name__}: {err}"
        result["arrangement_clips"] = [
            {"name": c.name, "start": c.start_time, "end": c.end_time}
            for c in track.arrangement_clips
        ]
        result["look"] = (
            "Arrangement: Probe Operator should show volume automation in bars 1-4"
        )
        self.check(9, **result)

    def _step_finish(self):
        """Devices again, since browser loads may land after the tick that asked."""
        self.check(
            0,
            devices_at_finish={
                key: self.device_names(track) for key, track in self._tracks.items()
            },
        )
        self.report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.stop("done", "done, report in ~/.tonable/probe-report.json")


def _doc(dotted):
    obj = Live
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj.__doc__
