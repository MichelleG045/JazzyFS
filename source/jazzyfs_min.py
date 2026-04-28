#!/usr/bin/env python3

# JazzyFS — read-only FUSE filesystem for studying adaptive prefetching.
#
# This file is the entire implementation. It does three things:
#   1. Acts as a FUSE filesystem: intercepts read() calls from the OS and
#      forwards them to the real underlying directory.
#   2. Runs phase detection + confidence scoring on every read to classify
#      the current workload as sequential or irregular.
#   3. Optionally plays music that reflects the workload behavior in real time
#      (sonification), using scale, tempo, and melody direction as signals.

import os
import sys
import errno
import time
import csv
import random
import subprocess
import threading
from fuse import FUSE, Operations, FuseOSError  # FUSE Python bindings (fusepy)
from collections import deque                   # Fixed-size sliding window for the trace

# --------------------------------------------------
# Phase Detection Config
# --------------------------------------------------

# How many of the most recent reads to examine when deciding the current phase.
# A window of 5 means we look at the last 5 read() calls to determine if the
# workload is currently behaving sequentially or randomly.
PHASE_WINDOW = 5

# The minimum confidence score (0.0 – 1.0) required before adaptive mode will
# issue a prefetch. At 0.7, at least 3 out of 4 recent transitions must be
# sequential before we consider the pattern predictable enough to prefetch.
CONFIDENCE_THRESHOLD = 0.7

# How many extra blocks to read ahead when a prefetch is triggered.
# 1 = only the immediately next block; 4 = four blocks ahead, etc.
# Controlled at runtime via the JAZZYFS_PREFETCH_DEPTH environment variable.
PREFETCH_DEPTH = int(os.environ.get("JAZZYFS_PREFETCH_DEPTH", "1"))

# --------------------------------------------------
# Evaluation Modes
# --------------------------------------------------

# Control baseline: never prefetch. Used to measure the cost of FUSE alone,
# with no read-ahead activity at all.
MODE_NONE = "none"

# Fixed heuristic: always prefetch after every read, regardless of the access
# pattern. Represents the traditional "always read ahead" strategy.
MODE_BASELINE = "baseline"

# Confidence-guided prefetching: only prefetch when the recent access pattern
# is measurably sequential AND our confidence score meets the threshold.
# This is the research contribution of JazzyFS.
MODE_ADAPTIVE = "adaptive"

# --------------------------------------------------
# Musical Frequencies
# --------------------------------------------------

# Each prefetching mode is mapped to a different musical scale.
# The scale gives each mode a distinct "sound personality":
#   none     → Major scale      (bright, resolved)
#   baseline → Natural Minor    (darker, melancholic)
#   adaptive → Harmonic Minor   (exotic tension/resolution — reflects the
#                                 system's decision-making complexity)
# Values are semitone offsets from the root note (0 = root, 12 = octave above).
SCALE_INTERVALS = {
    MODE_NONE:     [0, 2, 4, 5, 7, 9, 11],  # Major
    MODE_BASELINE: [0, 2, 3, 5, 7, 8, 10],  # Natural Minor
    MODE_ADAPTIVE: [0, 2, 3, 5, 7, 8, 11],  # Harmonic Minor
}

# Chord progressions — one triad per cycle, 4 cycles total.
# Each entry is [root_semitone, third_semitone, fifth_semitone] relative to
# the scale root. Chords are voiced one octave above the melody so they don't
# clash with the lower melody notes.
#
# Progressions follow standard tonal motion for each scale type:
#   Major:         I  → IV → V  → I   (tonic → subdominant → dominant → resolution)
#   Natural Minor: i  → iv → v  → i
#   Harmonic Minor: i → iv → V  → i   (raised 7th in V gives the "harmonic" flavour)
CHORD_PROGRESSIONS = {
    MODE_NONE: [           # Major: I → IV → V → I
        # IV placed on notes 4-6 so scale degree 4 (F in C) is the chord root — no tritone clash
        [0,  4,  7],       # I   major   (tonic)
        [5,  9, 12],       # IV  major   (subdominant — root matches scale deg 4)
        [7, 11, 14],       # V   major   (dominant — scale deg 7 is chord 3rd)
        [0,  4,  7],       # I   major   (tonic resolution)
    ],
    MODE_BASELINE: [       # Natural Minor: i → iv → v → i
        # iv placed on notes 4-6 so scale degree 4 matches chord root — no clash
        [0,  3,  7],       # i   minor   (tonic)
        [5,  8, 12],       # iv  minor   (subdominant — root matches scale deg 4)
        [7, 10, 14],       # v   minor   (dominant)
        [0,  3,  7],       # i   minor   (tonic resolution)
    ],
    MODE_ADAPTIVE: [       # Harmonic Minor: i → iv → V → i  (textbook cadence)
        # Same alignment — iv catches scale deg 4, major V catches raised 7th
        [0,  3,  7],       # i   minor   (tonic)
        [5,  8, 12],       # iv  minor   (subdominant — root matches scale deg 4)
        [7, 11, 14],       # V   major   (dominant — raised 7th is chord 3rd)
        [0,  3,  7],       # i   minor   (tonic resolution — lands on last note)
    ],
}

# All 25 chromatic pitches from C3 to C5 in Hz.
# At playback time we randomly pick one of the 7 natural notes (C D E F G A B)
# as the root, so the key changes each session.
_CHROMATIC_ROOTS_HZ = [
    130.81,  # C3
    138.59,  # C#3
    146.83,  # D3
    155.56,  # Eb3
    164.81,  # E3
    174.61,  # F3
    185.00,  # F#3
    196.00,  # G3
    207.65,  # Ab3
    220.00,  # A3
    233.08,  # Bb3
    246.94,  # B3
    261.63,  # C4
    277.18,  # C#4
    293.66,  # D4
    311.13,  # Eb4
    329.63,  # E4
    349.23,  # F4
    369.99,  # F#4
    392.00,  # G4
    415.30,  # Ab4
    440.00,  # A4
    466.16,  # Bb4
    493.88,  # B4
    523.25,  # C5
]

def _build_scale_hz(root_hz, intervals):
    """
    Convert a root frequency and a list of semitone intervals into actual Hz values.

    Uses the standard equal-temperament formula: each semitone is a factor of
    2^(1/12) ≈ 1.0595. An interval of 12 semitones = one octave = double the frequency.

    Example: root=261.63 Hz (C4), intervals=[0,4,7] → C major triad frequencies.
    """
    return [root_hz * (2 ** (i / 12)) for i in intervals]

# --------------------------------------------------
# Filesystem
# --------------------------------------------------

class PassthroughRO(Operations):
    """
    Read-only FUSE filesystem that passes every operation through to a real
    underlying directory, while intercepting read() calls to:
      - Log the raw access event to access.csv
      - Run phase detection and confidence scoring
      - Decide whether to prefetch the next block(s)
      - Log the prefetch decision to decisions.csv
      - Update the sonification history for the background audio thread
    """

    def __init__(self, root):
        # The real directory on disk that this FUSE mount exposes.
        # All file paths received from FUSE are relative; _full() converts them.
        self.root = os.path.realpath(root)

        # --------------------------------------------------
        # CSV Logging Setup (Evaluation)
        # --------------------------------------------------
        # Logs are written to <repo_root>/logs/ so they are always in a
        # predictable location regardless of where the script is invoked from.
        repo_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        self.log_path = os.path.join(repo_root, "logs", "access.csv")
        self.decision_log_path = os.path.join(repo_root, "logs", "decisions.csv")

        # Monotonically increasing counter used as a sequence number in the log.
        self.seq = 0

        # Experiment metadata injected via environment variables by the harness.
        # These appear as columns in the CSV so results from many runs can be
        # aggregated without ambiguity.
        self.run_index = os.environ.get("JAZZYFS_RUN_INDEX", "")
        self.run_label = os.environ.get("JAZZYFS_RUN_LABEL", "")
        self.workload_name = os.environ.get("JAZZYFS_WORKLOAD", "")

        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

        # Open both CSV files in append mode so multiple runs accumulate in the
        # same file. Write the header row only if the file is new/empty.
        write_access_header = not os.path.exists(self.log_path) or os.path.getsize(self.log_path) == 0
        self._log_f = open(self.log_path, "a", newline="")
        self._log_writer = csv.writer(self._log_f)
        if write_access_header:
            self._log_writer.writerow([
                "run_index", "run_label", "mode", "workload",
                "seq", "timestamp", "path", "offset", "size"
            ])

        write_decision_header = not os.path.exists(self.decision_log_path) or os.path.getsize(self.decision_log_path) == 0
        self._decision_f = open(self.decision_log_path, "a", newline="")
        self._decision_writer = csv.writer(self._decision_f)
        if write_decision_header:
            self._decision_writer.writerow([
                "run_index", "run_label", "mode", "workload",
                "timestamp", "path", "offset", "size",
                "phase", "confidence", "decay_rate", "prefetch", "prefetch_offset", "prefetch_size", "prefetch_depth"
            ])

        # --------------------------------------------------
        # Shared State
        # --------------------------------------------------

        # The trace is a sliding window of the last 1000 read events.
        # Each entry is {"t": timestamp, "path": path, "offset": int, "size": int}.
        # Using a deque with maxlen automatically discards the oldest entry when
        # the window is full, bounding memory usage regardless of run length.
        self.trace = deque(maxlen=1000)

        # Default block size for prefetch reads (4 KB = one OS page).
        self.prefetch_size = 4096

        # How many blocks ahead to read during a prefetch (configurable at mount time).
        self.prefetch_depth = PREFETCH_DEPTH

        # Master switch — always True in current code; allows disabling prefetch
        # globally without touching mode logic (useful for debugging).
        self.prefetch_enabled = True

        # Confidence decay tracking for real-time abrupt phase change detection.
        # prev_confidence stores the confidence from the previous read so the
        # decay rate (drop per read) can be computed on every call.
        # JAZZYFS_DECAY_THRESHOLD sets how large a single-read confidence drop
        # must be to trigger an immediate prefetch stop regardless of the current
        # confidence value. Default 0.25 = one window transition changed.
        self.prev_confidence = 0.0
        self.decay_threshold = float(os.environ.get("JAZZYFS_DECAY_THRESHOLD", "0.25"))

        # --------------------------------------------------
        # Mode + Sound Config
        # --------------------------------------------------

        # The prefetching algorithm to use. Defaults to adaptive if not set.
        self.mode = os.environ.get("JAZZYFS_MODE", MODE_ADAPTIVE)

        # Whether to play audio after each workload completes.
        self.sound_enabled = os.environ.get("JAZZYFS_SOUND", "0") == "1"

        # --------------------------------------------------
        # Sonification State
        # --------------------------------------------------

        # Accumulated per-read history used by the audio thread.
        # These lists grow during a workload and are cleared after playback.
        self.phase_history = []       # "sequential" or "irregular" per read
        self.confidence_history = []  # float [0.0, 1.0] per read
        self.prefetch_history = []    # bool per read (did we prefetch?)

        # Timestamp of the most recent read() call. The monitor thread uses this
        # to detect when a workload has finished (idle for > 1 second).
        self.last_read_time = time.time()

        # Current position in the scale for melody generation.
        # Reset to 0 (root note) at the start of each playback session.
        self.note_index = 0

        # True while audio is playing. Prevents overlapping playback sessions.
        self.melody_playing = False

        # Protects all shared mutable state above from the background audio thread.
        # The FUSE read() path and the monitor thread both touch these fields.
        self._state_lock = threading.Lock()

        print(f"[JazzyFS] Mode           = {self.mode}")
        if self.run_label:
            print(f"[JazzyFS] Run Label      = {self.run_label}")
        if self.workload_name:
            print(f"[JazzyFS] Workload       = {self.workload_name}")
        print(f"[JazzyFS] Prefetch Depth = {self.prefetch_depth}")
        print(f"[JazzyFS] Sound          = {self.sound_enabled}")
        print(f"[JazzyFS] Logging        = {self.log_path}")

        # Start the background thread that listens for workload completion and
        # triggers audio playback. Only launched when sound is enabled.
        if self.sound_enabled:
            threading.Thread(target=self._monitor_completion, daemon=True).start()

    # --------------------------------------------------
    # Logging Helpers (Evaluation)
    # --------------------------------------------------

    def _log_read(self, path, offset, size):
        """
        Write one row to access.csv capturing the raw read event.
        Called on every read() before any analysis happens.
        flush() is called immediately so the file is usable even if the
        process is killed mid-run.
        """
        self.seq += 1
        self._log_writer.writerow([
            self.run_index, self.run_label, self.mode, self.workload_name,
            self.seq, time.time(), path, offset, size
        ])
        self._log_f.flush()

    def _log_decision(self, path, offset, size, phase, confidence, decay_rate, prefetch, prefetch_offset):
        """
        Write one row to decisions.csv capturing the phase detection result,
        confidence score, decay rate, and the prefetch decision made for this read.
        This is the primary data source for the experiment analysis scripts.
        decay_rate is the drop in confidence since the previous read — positive
        values indicate falling confidence, zero indicates stable or rising.
        """
        self._decision_writer.writerow([
                self.run_index, self.run_label, self.mode, self.workload_name,
                time.time(), path, offset, size,
                phase, f"{confidence:.4f}", f"{decay_rate:.4f}", int(prefetch),
                prefetch_offset if prefetch else "",
                self.prefetch_size if prefetch else "",
                self.prefetch_depth
            ])
        self._decision_f.flush()

    # --------------------------------------------------
    # Adaptive Logic
    # --------------------------------------------------

    def _detect_phase(self):
        """
        Classify the current access pattern as 'sequential', 'irregular', or
        'unknown' by examining the last PHASE_WINDOW (5) reads in the trace.

        A transition between two consecutive reads is 'sequential' if the next
        read starts exactly where the previous one ended:
            prev.offset + prev.size == curr.offset

        Classification rule:
            - 'sequential' if nearly all transitions in the window are sequential
              (allows one miss to handle occasional out-of-order reads)
            - 'irregular'  otherwise
            - 'unknown'    if fewer than 2 reads have been seen yet

        This runs in O(1) time since the window size is fixed.
        """
        if len(self.trace) < 2:
            return "unknown"

        # Take only the most recent PHASE_WINDOW events from the trace.
        recent = list(self.trace)[-PHASE_WINDOW:]
        sequential = 0

        for i in range(1, len(recent)):
            prev = recent[i - 1]
            curr = recent[i]
            # Byte-exact contiguity check: end of previous read == start of current read.
            if prev["offset"] + prev["size"] == curr["offset"]:
                sequential += 1

        # Lenient threshold: all-but-one transitions must be sequential.
        # This prevents a single stray read from flipping the label to 'irregular'.
        if sequential >= len(recent) - 1:
            return "sequential"

        return "irregular"

    def _prediction_confidence(self):
        """
        Return a continuous confidence score in [0.0, 1.0] representing how
        sequential the recent access window is.

        Uses the same window and contiguity check as _detect_phase(), but
        returns the raw ratio instead of a binary label:
            confidence = sequential_transitions / total_possible_transitions

        Examples:
            4/4 sequential → 1.00  (fully sequential stream)
            3/4 sequential → 0.75  (mostly sequential)
            0/4 sequential → 0.00  (fully random)

        The adaptive prefetch decision uses this score against CONFIDENCE_THRESHOLD
        (0.7) to gate read-ahead. This is what makes the adaptive algorithm
        "confidence-guided" rather than purely phase-based.
        """
        if len(self.trace) < 2:
            return 0.0

        recent = list(self.trace)[-PHASE_WINDOW:]
        matches = 0

        for i in range(1, len(recent)):
            prev = recent[i - 1]
            curr = recent[i]
            if prev["offset"] + prev["size"] == curr["offset"]:
                matches += 1

        # Divide by (window - 1) since that is the number of possible transitions.
        # max(1, ...) guards against the edge case of a single-element window.
        return matches / max(1, len(recent) - 1)

    def _prefetch_next(self, full_path, next_offset, size):
        """
        Warm the OS page cache by speculatively reading ahead of the current
        position. The data read here is immediately discarded — the only goal
        is to load the pages into the kernel's buffer cache so the application's
        next read() hits warm cache instead of cold storage.

        Reads PREFETCH_DEPTH blocks starting at next_offset, each of size
        `prefetch_size` bytes (default 4 KB per block).

        Any exception (e.g., reading past end-of-file) is silently swallowed
        because prefetch failures are harmless — they simply mean no warm-up
        happened for that block.
        """
        try:
            with open(full_path, "rb") as f:
                for i in range(self.prefetch_depth):
                    f.seek(next_offset + i * self.prefetch_size)
                    f.read(size)
        except Exception:
            pass

    # --------------------------------------------------
    # Sonification Engine
    # --------------------------------------------------

    def _compress_phases(self):
        """
        Reduce the per-read phase_history list to a compact sequence of
        distinct phase transitions (run-length encoding, keeping only labels).

        Example:
            Input:  ["sequential","sequential","sequential","irregular","sequential"]
            Output: ["sequential","irregular","sequential"]

        This compressed sequence directly drives audio playback: each element
        maps to one call to _play_segment() with a tempo derived from the phase.
        Consecutive duplicates are collapsed so the music reflects structural
        transitions, not repeated identical segments.
        """
        if not self.phase_history:
            return []

        compressed = [self.phase_history[0]]
        for phase in self.phase_history[1:]:
            if phase != compressed[-1]:
                compressed.append(phase)

        return compressed

    def _play_segment(self, tempo, vol, avg_confidence, root_idx=0):
        """
        Render and play one audio segment corresponding to a single phase.

        Structure: 4 cycles × 8 notes = 32 notes total.
        Each cycle pairs a sustained background chord with a 8-note melody pass.

        Parameters:
            tempo          — seconds per note (0.15 = fast/sequential, 1.2 = slow/irregular)
            vol            — melody volume (0.0 – 1.0)
            avg_confidence — session-average confidence; controls melody direction
            root_idx       — index into _CHROMATIC_ROOTS_HZ for the key root

        Melody direction (set once per session, not per segment):
            confidence >= 0.5 → ascending  (root → octave above)
            confidence <  0.5 → descending (octave above → root)

        Two scheduling paths based on tempo:
            Fast (sequential): one chord per cycle, fires at the start of each cycle.
            Slow (irregular):  four chord changes per cycle, one every 3-3-1-1 notes,
                               giving denser harmonic motion to compensate for the
                               sparse, slow melody.
        """
        intervals = SCALE_INTERVALS.get(self.mode, SCALE_INTERVALS[MODE_ADAPTIVE])
        root_hz = _CHROMATIC_ROOTS_HZ[root_idx]
        scale_hz = _build_scale_hz(root_hz, intervals)
        n = len(scale_hz)  # 7 notes in the scale
        ascending = avg_confidence >= 0.5
        n_notes = n + 1    # 8 notes per cycle — last note always resolves to root octave

        progression = CHORD_PROGRESSIONS.get(self.mode, CHORD_PROGRESSIONS[MODE_ADAPTIVE])
        n_cycles    = len(progression)  # 4 cycles
        slow        = tempo >= 0.5      # True for irregular phase (1.2 s/note)

        def _melody_note(i):
            """Return the Hz value for the i-th note in the current direction."""
            if ascending:
                # Ascending: scale[0], scale[1], ..., scale[6], scale[0]*2 (octave)
                return scale_hz[0] * 2 if i == n else scale_hz[i]
            else:
                # Descending: scale[0]*2, scale[6], ..., scale[1], scale[0]
                return scale_hz[0] * 2 if i == 0 else scale_hz[n - i]

        def _play_chord(semitones, duration, chord_vol=0.30, fade_in=0.05, fade_out_dur=None):
            """
            Fire a background chord using SoX (`play` command).
            Chord tones are voiced one octave above the root so they sit above
            the melody range and don't muddy the lower notes.
            Popen is used (non-blocking) so the chord rings while the melody plays.
            """
            if fade_out_dur is None:
                fade_out_dur = round(min(duration * 0.4, tempo * 1.5), 3)
            # Raise chords one octave — keeps voicing bright and above the low melody range
            tones = [root_hz * 2 * (2 ** (s / 12)) for s in semitones]
            cmd = ["play", "-q", "-n", "synth", str(duration)]
            for f in tones:
                cmd += ["sine", str(round(f, 2))]
            cmd += ["vol", f"{chord_vol:.2f}", "fade", "t", str(fade_in), str(duration), str(fade_out_dur)]
            subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def _play_note(i):
            """
            Play the i-th melody note using a triangle wave (SoX `play`).
            Duration is slightly shorter than one tempo period (85%) with a
            short fade-out (15%) to prevent clicks between notes.
            sleep(tempo) blocks until it is time for the next note.
            """
            dur      = tempo * 0.85
            fade_out = tempo * 0.15
            subprocess.Popen(
                ["play", "-q", "-n", "synth", str(dur), "triangle", str(_melody_note(i)),
                 "vol", f"{vol:.2f}", "fade", "t", "0", str(dur), str(fade_out)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            time.sleep(tempo)

        if not slow:
            # ── FAST path (sequential phase, tempo = 0.15 s/note) ──────────────
            # One chord per cycle. The chord fires at the start of each cycle and
            # rings for the full duration of that cycle (8 notes × tempo).
            for cycle_idx in range(n_cycles):
                chord_dur = round(tempo * n_notes, 3)
                _play_chord(progression[cycle_idx], chord_dur)
                for i in range(n_notes):
                    _play_note(i)

        else:
            # ── SLOW path (irregular phase, tempo = 1.2 s/note) ────────────────
            # Four chord changes within each cycle, at note boundaries 1, 4, 7, 8.
            # This gives the slow, sparse melody harmonic support so it doesn't
            # sound bare. The final chord of the final cycle gets a longer decay
            # to produce a clear cadential resolution.
            SLOW_GROUPS = [3, 3, 1, 1]  # notes per chord group within a cycle

            for cycle_idx in range(n_cycles):
                note_i = 0
                for group_idx, group_size in enumerate(SLOW_GROUPS):
                    # Rotate through all 4 chords across the combined cycle×group space.
                    chord_idx  = (cycle_idx * len(SLOW_GROUPS) + group_idx) % n_cycles
                    is_cadence = (cycle_idx == n_cycles - 1 and group_idx == len(SLOW_GROUPS) - 1)

                    if is_cadence:
                        # Final chord: fires simultaneously with the last note,
                        # rings twice as long, and decays slowly for resolution.
                        _play_chord(progression[chord_idx],
                                    duration=round(tempo * 2.0, 3),
                                    chord_vol=0.35,
                                    fade_in=0.0,
                                    fade_out_dur=round(tempo * 1.0, 3))
                    else:
                        _play_chord(progression[chord_idx], round(tempo * group_size, 3))

                    for j in range(group_size):
                        _play_note(note_i + j)

                    note_i += group_size

        # Wait for the last note's sustain to finish before returning,
        # so the caller knows this segment is fully done.
        time.sleep(tempo * 0.85)

    def _analyze_and_play(self):
        """
        Called by the monitor thread after a workload has been idle for 1 second.

        Steps:
          1. Grab the accumulated phase and confidence history under the lock,
             then immediately clear it (so the next workload starts fresh).
          2. Compress the phase history to a sequence of distinct transitions.
          3. Pick a random root note (one of the 7 natural notes in C3 octave).
          4. Wait 5 seconds to let any in-flight I/O finish.
          5. For each phase segment, play one audio segment at the matching tempo.
          6. Clear the melody_playing flag when done.
        """
        with self._state_lock:
            pattern = self._compress_phases()
            if not pattern:
                return
            self.melody_playing = True
            # Reset to root note at the start of each new playback session.
            self.note_index = 0
            avg_confidence = sum(self.confidence_history) / max(1, len(self.confidence_history))
            prefetch_rate = sum(self.prefetch_history) / max(1, len(self.prefetch_history))
            # Clear histories now so the next workload's data starts accumulating fresh.
            self.phase_history.clear()
            self.confidence_history.clear()
            self.prefetch_history.clear()

        print(f"[JazzyFS] Phase pattern: {pattern}")

        vol = 0.7  # Two triangle waves can sum above 1.0 — stay below to avoid clipping

        direction = "ASCENDING" if avg_confidence >= 0.5 else "DESCENDING"
        print(f"[JazzyFS] avg_confidence={avg_confidence:.2f} → {direction}")
        print(f"[JazzyFS] prefetch_rate={prefetch_rate:.2f}")

        # Randomly choose a root note from the 7 natural pitches (C D E F G A B)
        # so each playback session sounds different even for the same workload.
        _NATURAL_INDICES = [0, 2, 4, 5, 7, 9, 11]   # positions in _CHROMATIC_ROOTS_HZ
        _NATURAL_NAMES   = ["C3","D3","E3","F3","G3","A3","B3"]
        root_bucket = random.randrange(7)
        root_idx  = _NATURAL_INDICES[root_bucket]
        root_name = _NATURAL_NAMES[root_bucket]
        scale_name = {MODE_NONE: "Major", MODE_BASELINE: "Natural Minor", MODE_ADAPTIVE: "Harmonic Minor"}.get(self.mode, "")
        print(f"[JazzyFS] Root: {root_name}  Scale: {scale_name}  Mode: {self.mode}")
        print("[JazzyFS] Starting in 5 seconds...")

        # Brief pause before playback so any last I/O events finish logging.
        time.sleep(5)

        # Tempo encodes the workload's access structure — orthogonal to scale/mode.
        FAST = 0.15   # Sequential access → fast notes (data arrives in a steady stream)
        SLOW = 1.2    # Irregular access  → slow notes (seeks are sparse and unpredictable)

        # Play one audio segment per distinct phase in the compressed history.
        for phase in pattern:
            tempo = FAST if phase == "sequential" else SLOW
            print(f"[JazzyFS] ▶ phase={phase}  tempo={tempo}s/note  {direction}")
            self._play_segment(tempo, vol, avg_confidence, root_idx)

        print("[JazzyFS] Playback complete")

        with self._state_lock:
            self.melody_playing = False

    def _monitor_completion(self):
        """
        Background daemon thread that polls every 0.2 seconds to detect when
        a workload has finished, then triggers audio playback.

        Trigger conditions (all must be true):
          - No read() has arrived in the last 1.0 second   (workload finished)
          - phase_history is non-empty                      (something to play)
          - melody_playing is False                         (no overlap)

        The 0.2 s poll interval is fine enough to catch the idle boundary
        promptly while cheap enough not to burn CPU.
        """
        while True:
            time.sleep(0.2)

            with self._state_lock:
                should_play = (
                    time.time() - self.last_read_time > 1.0 and
                    self.phase_history and
                    not self.melody_playing
                )

            if should_play:
                self._analyze_and_play()

    # --------------------------------------------------
    # Filesystem Operations
    # --------------------------------------------------

    def _full(self, path):
        """
        Convert a FUSE-relative path (e.g., "/big.txt") to the real absolute
        path on disk under self.root. Strips the leading slash before joining
        so os.path.join behaves correctly.
        """
        return os.path.join(self.root, path.lstrip("/"))

    def getattr(self, path, fh=None):
        """
        Return file/directory metadata for `path`.
        Called by the OS for every stat(), open(), ls -l, etc.

        Delegates entirely to os.lstat() on the real path and returns a dict
        of the standard stat fields. No JazzyFS logic here — pure passthrough.
        Raises ENOENT if the path doesn't exist on the real filesystem.
        """
        try:
            st = os.lstat(self._full(path))
        except FileNotFoundError:
            raise FuseOSError(errno.ENOENT)

        return {
            "st_atime": st.st_atime,
            "st_ctime": st.st_ctime,
            "st_gid":   st.st_gid,
            "st_mode":  st.st_mode,
            "st_mtime": st.st_mtime,
            "st_nlink": st.st_nlink,
            "st_size":  st.st_size,
            "st_uid":   st.st_uid,
        }

    def readdir(self, path, fh):
        """
        Yield directory entries for `path`.
        Called by the OS for opendir()/readdir() (e.g., ls, find).

        Always includes "." and ".." then all real directory entries.
        Pure passthrough — no JazzyFS logic.
        """
        try:
            entries = [".", ".."] + os.listdir(self._full(path))
        except FileNotFoundError:
            raise FuseOSError(errno.ENOENT)
        for e in entries:
            yield e

    def open(self, path, flags):
        """
        Open a file and return a file descriptor.
        Called by the OS when an application calls open().

        Enforces read-only access: rejects any open that requests write (O_WRONLY)
        or read-write (O_RDWR) with EACCES. This is the enforcement mechanism
        for JazzyFS's read-only contract.

        Returns the OS-level file descriptor, which FUSE passes back to read()
        and release() as `fh`.
        """
        # Reject any write-access attempt — JazzyFS is strictly read-only.
        if flags & (os.O_WRONLY | os.O_RDWR):
            raise FuseOSError(errno.EACCES)

        full = self._full(path)
        if not os.path.exists(full):
            raise FuseOSError(errno.ENOENT)

        return os.open(full, os.O_RDONLY)

    def read(self, path, size, offset, fh):
        """
        Read `size` bytes starting at `offset` from the open file `fh`.
        This is the central method where all JazzyFS research logic runs.

        Execution order:
          1. Perform the actual read from the real filesystem.
          2. Log the raw access event to access.csv.
          3. Under the state lock:
             a. Reset trace if > 2 s have passed since the last read
                (separates workload runs without requiring an explicit reset).
             b. Append this event to the sliding-window trace.
             c. Run phase detection and update phase_history.
             d. Update last_read_time for the idle detector.
          4. Run confidence scoring (reads the same trace, no lock needed here
             since we're in the single-threaded FUSE dispatcher).
          5. Make the prefetch decision based on mode + phase + confidence.
          6. Execute prefetch if decided (fire-and-forget, result discarded).
          7. Update confidence and prefetch histories for sonification.
          8. Log the decision to decisions.csv.
          9. Return the data to the calling application.
        """
        # Step 1: perform the real read.
        # lseek to the requested offset, then read the requested bytes.
        # actual_offset captures the confirmed position after seeking
        # (should equal offset, but we use the confirmed value for accuracy).
        os.lseek(fh, offset, os.SEEK_SET)
        actual_offset = os.lseek(fh, 0, os.SEEK_CUR)
        data = os.read(fh, size)

        # Step 2: log the raw access before any analysis.
        self._log_read(path, actual_offset, len(data))

        with self._state_lock:
            # Step 3a: reset trace if this read arrives more than 2 seconds after
            # the previous one. This handles the boundary between successive
            # workload runs without requiring an explicit signal from the harness.
            if time.time() - self.last_read_time > 2.0:
                self.trace.clear()
                self.phase_history.clear()
                self.confidence_history.clear()
                self.prefetch_history.clear()
                self.prev_confidence = 0.0

            # Step 3b: record this read event in the sliding-window trace.
            event = {"t": time.time(), "path": path, "offset": actual_offset, "size": len(data)}
            self.trace.append(event)

            # Step 3c: detect phase and append to history for sonification.
            # "unknown" is excluded from history since it carries no signal.
            sonification_phase = self._detect_phase()
            if sonification_phase != "unknown":
                self.phase_history.append(sonification_phase)

            # Step 3d: record the timestamp so the idle detector can fire after 1 s.
            self.last_read_time = time.time()

        # Steps 4–6: prefetch decision.
        # confidence_scoring reads the trace without modifying it, so no lock needed.
        phase = sonification_phase
        confidence = self._prediction_confidence()

        # Compute single-read confidence drop; a large drop signals an abrupt phase change.
        decay_rate = max(0.0, self.prev_confidence - confidence)
        self.prev_confidence = confidence

        prefetch = False
        prefetch_offset = None

        if self.prefetch_enabled and len(data) > 0:

            # No Prefetching — control baseline: never issue read-ahead.
            if self.mode == MODE_NONE:
                prefetch = False

            # Fixed Heuristic Prefetching — always prefetch, regardless of pattern.
            elif self.mode == MODE_BASELINE:
                prefetch = True

            # Confidence-Guided Prefetching — the research contribution:
            # only prefetch when the pattern is measurably sequential AND
            # our confidence in that classification meets the threshold.
            # If confidence drops abruptly (decay_rate >= threshold), stop immediately
            # rather than waiting for confidence to fall read by read.
            elif self.mode == MODE_ADAPTIVE:
                if decay_rate >= self.decay_threshold:
                    prefetch = False
                else:
                    prefetch = (phase == "sequential" and confidence >= CONFIDENCE_THRESHOLD)

            if prefetch:
                # The next block to prefetch starts immediately after the current read.
                prefetch_offset = actual_offset + len(data)
                self._prefetch_next(self._full(path), prefetch_offset, self.prefetch_size)

        # Step 7: record this read's confidence and prefetch decision for sonification.
        with self._state_lock:
            self.confidence_history.append(confidence)
            self.prefetch_history.append(prefetch)

        # Step 8: log the full decision record (phase, confidence, decay_rate, prefetch) to CSV.
        self._log_decision(path, actual_offset, len(data), phase, confidence, decay_rate, prefetch, prefetch_offset)

        # Step 9: return the data to the application that made the read() call.
        return data

    def release(self, path, fh):
        """
        Close the file descriptor when the application is done with a file.
        Called by the OS on close(). Pure passthrough — no JazzyFS logic.
        """
        os.close(fh)


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    """
    Entry point. Expects exactly two arguments:
        source_dir   — the real directory to expose through the FUSE mount
        mount_point  — where to mount the JazzyFS filesystem

    FUSE options used:
        foreground=True   — stay in the foreground (don't daemonize); makes it
                            easy to terminate with Ctrl-C and see log output.
        ro=True           — tell the FUSE layer to enforce read-only at the
                            kernel level in addition to our open() check.
        nothreads=True    — disable FUSE's multi-threaded dispatcher. All FUSE
                            callbacks run sequentially in one thread, so the only
                            concurrency to manage is the background audio thread.
        direct_io=True    — bypass the kernel page cache for reads through this
                            mount. Ensures every read() call reaches JazzyFS
                            so we observe the true access pattern rather than
                            cache-satisfied reads that never reach FUSE.
        kernel_cache=False — disables kernel-side caching of file data, keeping
                             the observation layer accurate.
    """
    if len(sys.argv) != 3:
        print("Usage: jazzyfs.py <source_dir> <mount_point>")
        sys.exit(1)

    source, mount = sys.argv[1], sys.argv[2]
    os.makedirs(mount, exist_ok=True)

    print(f"[JazzyFS] Mounting {source} at {mount} (read-only)")
    print("[JazzyFS] Set JAZZYFS_MODE to: none | baseline | adaptive")
    print("[JazzyFS] Set JAZZYFS_SOUND=1 to enable sonification")

    FUSE(
        PassthroughRO(source),
        mount,
        foreground=True,
        ro=True,
        nothreads=True,
        direct_io=True,
        kernel_cache=False
    )


if __name__ == "__main__":
    main()
