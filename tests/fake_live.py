"""A small stand-in for Live's Python API, shaped like what stage 0 saw in Live 12.4.16.

Only the attributes the Remote Script reads exist. Names and ranges of the Electric
Bass Soft rack are the real ones from ~/.tonable/probe-report-4.json.
"""

from types import SimpleNamespace


class Param:
    def __init__(self, name, value=0.0, lo=0.0, hi=1.0, items=None, show=None):
        self.name = name
        self.value = value
        self.min = lo
        self.max = hi
        self.is_quantized = items is not None
        self.value_items = items or []
        self.is_enabled = True
        self.automation_state = 0
        self._show = show

    def str_for_value(self, value):
        if self.is_quantized:
            return self.value_items[int(value)]
        if self._show is not None:
            return self._show
        return f"{value:g}"


def device_on(on=True):
    return Param("Device On", 1.0 if on else 0.0, items=["Off", "On"])


class Device:
    def __init__(self, name, class_name, kind, params=(), on=True):
        self.name = name
        self.class_name = class_name
        self.type = kind
        self.parameters = [device_on(on), *params]
        self.can_have_chains = False
        self.can_have_drum_pads = False


class Rack(Device):
    def __init__(self, name, class_name, kind, macros, chains, mapped, visible=8):
        names = list(macros) + [f"Macro {i}" for i in range(len(macros) + 1, 17)]
        params = [Param(n, 0.0, 0.0, 127.0) for n in names]
        super().__init__(name, class_name, kind, params)
        self.can_have_chains = True
        self.chains = chains
        self.macros_mapped = mapped
        self.visible_macro_count = visible


class DrumRack(Rack):
    def __init__(self, name, pads):
        super().__init__(name, "DrumGroupDevice", 1, [], [], [False] * 16)
        self.can_have_drum_pads = True
        self.drum_pads = [
            pads.get(note, SimpleNamespace(note=note, name="", chains=[]))
            for note in range(128)
        ]


def chain(name, *devices):
    return SimpleNamespace(name=name, devices=list(devices), mute=False, solo=False)


def pad(note, name, *devices):
    return SimpleNamespace(note=note, name=name, chains=[chain(name, *devices)])


def clip(name, length=16.0, midi=True, playing=False):
    return SimpleNamespace(
        name=name, length=length, is_midi_clip=midi, looping=True, is_playing=playing
    )


def slot(c=None):
    return SimpleNamespace(has_clip=c is not None, clip=c)


def mixer(volume="0.0 dB", pan="C", sends=()):
    return SimpleNamespace(
        volume=Param("Track Volume", 0.85, show=volume),
        panning=Param("Track Panning", 0.0, -1.0, 1.0, show=pan),
        sends=[Param(f"Send {i}", 0.0, show=level) for i, level in enumerate(sends)],
    )


class Track:
    def __init__(self, name, devices=(), clips=(), kind="midi", **flags):
        self.name = name
        self.devices = list(devices)
        self.clip_slots = [slot(c) for c in clips]
        self.has_midi_input = kind == "midi"
        self.has_audio_input = kind == "audio"
        self.is_foldable = kind == "group"
        self.mute = flags.get("mute", False)
        self.solo = False
        self.arm = flags.get("arm", False)
        self.is_grouped = "group" in flags
        self.group_track = flags.get("group")
        self.mixer_device = mixer(sends=flags.get("sends", ("-inf dB", "-12 dB")))
        self.input_routing_type = SimpleNamespace(display_name="All Ins")
        self.output_routing_type = SimpleNamespace(display_name="Master")
        self.arrangement_clips = flags.get("arrangement", [])


def electric_bass_soft():
    simpler = Device(
        "Simpler", "OriginalSimpler", 1, [Param("Volume", 0.5, show="-6.0 dB")]
    )
    saturator = Device("Saturator", "Saturator", 2, [Param("Drive", 0.3, 0, 36)])
    return Rack(
        "Electric Bass Soft",
        "InstrumentGroupDevice",
        1,
        [
            "Filter Cutoff",
            "Filter Reso",
            "LFO Rate",
            "Volume LFO",
            "Decay",
            "Release",
            "Chorus",
            "Saturate",
        ],
        [chain("Electric Bass Soft", simpler, saturator)],
        [True] * 8 + [False] * 8,
    )


def song():
    """A synthetic Set: bass, drums, a pad in a group, two returns."""
    group = Track("Keys", kind="group")
    pad_track = Track(
        "Pad",
        [Device("Operator", "Operator", 1, [Param("Osc-A Level", 1.0, show="0.0 dB")])],
        [clip("Pad Verse"), None, clip("Pad Chorus")],
        group=group,
    )
    drums = DrumRack(
        "Kit",
        {
            36: pad(36, "Kick", Device("Simpler", "OriginalSimpler", 1)),
            38: pad(38, "Snare", Device("Simpler", "OriginalSimpler", 1)),
        },
    )
    tracks = [
        Track(
            "Bass",
            [electric_bass_soft()],
            [clip("Bass A", playing=True), clip("Bass B")],
        ),
        Track("Drums", [drums], [clip("Beat"), clip("Beat")], arm=True),
        group,
        pad_track,
        Track("Vox", [], [], kind="audio", mute=True),
    ]
    returns = [
        Track(
            "A-Reverb",
            [Device("Reverb", "Reverb", 2, [Param("Decay Time", 0.5, show="2.00 s")])],
            kind="return",
        ),
        Track("B-Delay", [Device("Delay", "Delay", 2, [], on=False)], kind="return"),
    ]
    for r in returns:
        r.clip_slots = []
        r.mixer_device = mixer(sends=())
    master = Track("Master", [], kind="return")
    master.clip_slots = []
    master.mixer_device = mixer(sends=())
    return SimpleNamespace(
        tempo=92.0,
        signature_numerator=4,
        signature_denominator=4,
        is_playing=False,
        loop=False,
        loop_start=0.0,
        loop_length=16.0,
        tracks=tracks,
        return_tracks=returns,
        master_track=master,
        scenes=[
            SimpleNamespace(name="Verse", tempo=92.0, tempo_enabled=False),
            SimpleNamespace(name="Break", tempo=92.0, tempo_enabled=False),
            SimpleNamespace(name="Chorus", tempo=96.0, tempo_enabled=True),
        ],
        cue_points=[SimpleNamespace(name="Intro", time=0.0)],
    )


# --- clips with notes (for write_clip) ---------------------------------------


class Note:
    def __init__(self, note_id, spec):
        self.note_id = note_id
        self.pitch = spec.pitch
        self.start_time = spec.start_time
        self.duration = spec.duration
        self.velocity = spec.velocity
        self.mute = spec.mute


class MidiClip:
    def __init__(self, length):
        self.name = ""
        self.is_midi_clip = True
        self.looping = True
        self.loop_start = 0.0
        self.loop_end = length
        self.end_marker = length
        self.is_playing = False
        self._notes = {}
        self._next_id = 1

    @property
    def length(self):
        return self.loop_end - self.loop_start

    def get_all_notes_extended(self):
        return list(self._notes.values())

    def add_new_notes(self, specs):
        for spec in specs:
            self._notes[self._next_id] = Note(self._next_id, spec)
            self._next_id += 1

    def remove_notes_by_id(self, ids):
        for note_id in ids:
            del self._notes[note_id]


class ClipSlot:
    def __init__(self):
        self.clip = None

    @property
    def has_clip(self):
        return self.clip is not None

    def create_clip(self, length):
        if self.clip is not None:
            raise RuntimeError("slot not empty")
        self.clip = MidiClip(length)


class UndoSong(SimpleNamespace):
    """A song that records undo steps."""

    def begin_undo_step(self):
        self.undo_depth = getattr(self, "undo_depth", 0) + 1
        self.undo_steps = getattr(self, "undo_steps", 0) + 1

    def end_undo_step(self):
        self.undo_depth -= 1


def writable_song():
    """Two MIDI tracks and an audio track with four empty slots each."""

    def track(name, kind="midi"):
        t = Track(name, kind=kind)
        t.clip_slots = [ClipSlot() for _ in range(4)]
        return t

    return UndoSong(
        signature_numerator=4,
        signature_denominator=4,
        tracks=[track("1-MIDI"), track("2-MIDI"), track("3-Audio", "audio")],
        return_tracks=[],
        master_track=Track("Master", kind="return"),
    )


class NoteSpec(SimpleNamespace):
    """Stand-in for Live.Clip.MidiNoteSpecification."""


FAKE_LIVE_MODULE = SimpleNamespace(Clip=SimpleNamespace(MidiNoteSpecification=NoteSpec))


def _apply_note_modifications(self, notes):
    for note in notes:
        self._notes[note.note_id] = note


MidiClip.apply_note_modifications = _apply_note_modifications
