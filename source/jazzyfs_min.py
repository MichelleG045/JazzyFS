#!/usr/bin/env python3

import os
import sys
import errno
import time
import csv
import random
import subprocess
import threading
from fuse import FUSE, Operations, FuseOSError
from collections import deque

# --------------------------------------------------
# Phase Detection Config
# --------------------------------------------------

# Number of recent reads to examine when detecting access behavior
PHASE_WINDOW = 5

# Minimum confidence required before enabling adaptive prefetching
CONFIDENCE_THRESHOLD = 0.7

# Number of blocks to prefetch ahead (1 = next block only, 2 = next two blocks, etc.)
PREFETCH_DEPTH = int(os.environ.get("JAZZYFS_PREFETCH_DEPTH", "1"))

# --------------------------------------------------
# Evaluation Modes
# --------------------------------------------------

MODE_NONE = "none"         # No prefetching (control baseline)
MODE_BASELINE = "baseline" # Always prefetch (fixed heuristic)
MODE_ADAPTIVE = "adaptive" # Confidence-guided prefetching (research contribution)

# --------------------------------------------------
# Musical Frequencies
# --------------------------------------------------

# Scale intervals (semitone steps) per mode
# none     = Major
# baseline = Natural Minor
# adaptive = Harmonic Minor
SCALE_INTERVALS = {
    MODE_NONE:     [0, 2, 4, 5, 7, 9, 11],  # Major
    MODE_BASELINE: [0, 2, 3, 5, 7, 8, 10],  # Natural Minor
    MODE_ADAPTIVE: [0, 2, 3, 5, 7, 8, 11],  # Harmonic Minor
}

# Background chord progressions — one triad per cycle (4 cycles total)
# Semitone offsets from the scale root for each chord tone [root, third, fifth]
CHORD_PROGRESSIONS = {
    MODE_NONE: [           # Major: I → IV → V → I
        # Scale degrees per group: [1,2,3] [4,5,6] [7] [8=root octave]
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

# Chromatic root notes starting at C3, one semitone apart
# Used to select the current key as the melody climbs
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
    """Return list of frequencies for a scale given a root frequency and semitone intervals."""
    return [root_hz * (2 ** (i / 12)) for i in intervals]

# --------------------------------------------------
# Filesystem
# --------------------------------------------------

class PassthroughRO(Operations):

    def __init__(self, root):
        self.root = os.path.realpath(root)

        # --------------------------------------------------
        # CSV Logging Setup (Evaluation)
        # --------------------------------------------------
        repo_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        self.log_path = os.path.join(repo_root, "logs", "access.csv")
        self.decision_log_path = os.path.join(repo_root, "logs", "decisions.csv")
        self.seq = 0
        self.run_index = os.environ.get("JAZZYFS_RUN_INDEX", "")
        self.run_label = os.environ.get("JAZZYFS_RUN_LABEL", "")
        self.workload_name = os.environ.get("JAZZYFS_WORKLOAD", "")

        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

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
                "timestamp", "fs_mode", "path", "offset", "size",
                "phase", "confidence", "prefetch", "prefetch_offset", "prefetch_size", "prefetch_depth"
            ])

        # --------------------------------------------------
        # Shared State
        # --------------------------------------------------
        self.trace = deque(maxlen=1000)
        self.prefetch_size = 4096
        self.prefetch_depth = PREFETCH_DEPTH
        self.prefetch_enabled = True

        # --------------------------------------------------
        # Mode + Sound Config
        # --------------------------------------------------
        self.mode = os.environ.get("JAZZYFS_MODE", MODE_ADAPTIVE)
        self.sound_enabled = os.environ.get("JAZZYFS_SOUND", "0") == "1"

        # --------------------------------------------------
        # Sonification State
        # --------------------------------------------------
        self.phase_history = []
        self.confidence_history = []
        self.prefetch_history = []
        self.last_read_time = time.time()
        # Persistent note position — moves up or down based on confidence across sessions
        self.note_index = 0  # start at root of scale
        self.melody_playing = False

        print(f"[JazzyFS] Mode           = {self.mode}")
        if self.run_label:
            print(f"[JazzyFS] Run Label      = {self.run_label}")
        if self.workload_name:
            print(f"[JazzyFS] Workload       = {self.workload_name}")
        print(f"[JazzyFS] Prefetch Depth = {self.prefetch_depth}")
        print(f"[JazzyFS] Sound          = {self.sound_enabled}")
        print(f"[JazzyFS] Logging        = {self.log_path}")

        if self.sound_enabled:
            threading.Thread(target=self._monitor_completion, daemon=True).start()

    # --------------------------------------------------
    # Logging Helpers (Evaluation)
    # --------------------------------------------------

    def _log_read(self, path, offset, size):
        self.seq += 1
        self._log_writer.writerow([
            self.run_index, self.run_label, self.mode, self.workload_name,
            self.seq, time.time(), path, offset, size
        ])
        self._log_f.flush()

    def _log_decision(self, path, offset, size, phase, confidence, prefetch, prefetch_offset):
        self._decision_writer.writerow([
                self.run_index, self.run_label, self.mode, self.workload_name,
                time.time(), self.mode, path, offset, size,
                phase, f"{confidence:.4f}", int(prefetch),
                prefetch_offset if prefetch else "",
                self.prefetch_size if prefetch else "",
                self.prefetch_depth
            ])
        self._decision_f.flush()

    # --------------------------------------------------
    # Adaptive Logic
    # --------------------------------------------------

    def _detect_phase(self):
        if len(self.trace) < 2:
            return "unknown"

        recent = list(self.trace)[-PHASE_WINDOW:]
        sequential = 0

        for i in range(1, len(recent)):
            prev = recent[i - 1]
            curr = recent[i]
            if prev["offset"] + prev["size"] == curr["offset"]:
                sequential += 1

        if sequential >= len(recent) - 1:
            return "sequential"

        return "irregular"

    def _prediction_confidence(self):
        if len(self.trace) < 2:
            return 0.0

        recent = list(self.trace)[-PHASE_WINDOW:]
        matches = 0

        for i in range(1, len(recent)):
            prev = recent[i - 1]
            curr = recent[i]
            if prev["offset"] + prev["size"] == curr["offset"]:
                matches += 1

        return matches / max(1, len(recent) - 1)

    def _prefetch_next(self, full_path, next_offset, size):
        # Read-ahead to warm the OS cache — never affects correctness
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
        # Remove consecutive duplicates to preserve structural transitions
        if not self.phase_history:
            return []

        compressed = [self.phase_history[0]]
        for phase in self.phase_history[1:]:
            if phase != compressed[-1]:
                compressed.append(phase)

        return compressed

    def _play_segment(self, tempo, vol, avg_confidence, root_idx=0):
        # 3 cycles × 7 (or 8) notes each.
        # Each cycle launches a sustained background chord, then runs the melody over it.
        # Chord progression per mode: Major=I→IV→V, NatMinor=i→iv→v, HarmMinor=i→III+→V
        intervals = SCALE_INTERVALS.get(self.mode, SCALE_INTERVALS[MODE_ADAPTIVE])
        root_hz = _CHROMATIC_ROOTS_HZ[root_idx]
        scale_hz = _build_scale_hz(root_hz, intervals)
        n = len(scale_hz)  # 7
        ascending = avg_confidence >= 0.5
        n_notes = n + 1  # 8 notes either direction — last note always lands on root octave

        progression = CHORD_PROGRESSIONS.get(self.mode, CHORD_PROGRESSIONS[MODE_ADAPTIVE])
        n_cycles    = len(progression)  # 4
        slow        = tempo >= 0.5

        def _melody_note(i):
            if ascending:
                return scale_hz[0] * 2 if i == n else scale_hz[i]
            else:
                return scale_hz[0] * 2 if i == 0 else scale_hz[n - i]

        def _play_chord(semitones, duration, chord_vol=0.30, fade_in=0.05, fade_out_dur=None):
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
            dur      = tempo * 0.85
            fade_out = tempo * 0.15
            subprocess.Popen(
                ["play", "-q", "-n", "synth", str(dur), "triangle", str(_melody_note(i)),
                 "vol", f"{vol:.2f}", "fade", "t", "0", str(dur), str(fade_out)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            time.sleep(tempo)

        if not slow:
            # ── FAST ──────────────────────────────────────────────────────────────
            # Chord N fires on note 1 of cycle N (cycle 1→chord 1, ..., cycle 4→chord 4).
            for cycle_idx in range(n_cycles):
                chord_dur = round(tempo * n_notes, 3)
                _play_chord(progression[cycle_idx], chord_dur)
                for i in range(n_notes):
                    _play_note(i)

        else:
            # ── SLOW ──────────────────────────────────────────────────────────────
            # Within each cycle: chord 1@note1, chord 2@note4, chord 3@note7, chord 4@note8.
            # Groups: notes [0-2]=chord A, [3-5]=chord B, [6]=chord C, [7]=chord D (resolution).
            SLOW_GROUPS = [3, 3, 1, 1]  # note boundaries: 1, 4, 7, 8

            for cycle_idx in range(n_cycles):
                note_i = 0
                for group_idx, group_size in enumerate(SLOW_GROUPS):
                    chord_idx  = (cycle_idx * len(SLOW_GROUPS) + group_idx) % n_cycles
                    is_cadence = (cycle_idx == n_cycles - 1 and group_idx == len(SLOW_GROUPS) - 1)

                    if is_cadence:
                        # Resolution chord fires simultaneously with the last note, rings longer
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

        # Wait for the last note to finish before returning
        time.sleep(tempo * 0.85)

    def _analyze_and_play(self):
        pattern = self._compress_phases()
        print(f"[JazzyFS] Phase pattern: {pattern}")

        if not pattern:
            return

        self.melody_playing = True
        self.note_index = 0  # reset to root for each new playback session

        vol = 0.7  # two triangle waves sum — keep below 1.0 to avoid clipping

        avg_confidence = sum(self.confidence_history) / max(1, len(self.confidence_history))
        prefetch_rate = sum(self.prefetch_history) / max(1, len(self.prefetch_history))

        direction = "ASCENDING" if avg_confidence >= 0.5 else "DESCENDING"
        print(f"[JazzyFS] avg_confidence={avg_confidence:.2f} → {direction}")
        print(f"[JazzyFS] prefetch_rate={prefetch_rate:.2f}")

        # Root note randomly chosen from the 7 natural notes (C D E F G A B)
        _NATURAL_INDICES = [0, 2, 4, 5, 7, 9, 11]   # chromatic indices in _CHROMATIC_ROOTS_HZ
        _NATURAL_NAMES   = ["C3","D3","E3","F3","G3","A3","B3"]
        root_bucket = random.randrange(7)
        root_idx  = _NATURAL_INDICES[root_bucket]
        root_name = _NATURAL_NAMES[root_bucket]
        scale_name = {MODE_NONE: "Major", MODE_BASELINE: "Natural Minor", MODE_ADAPTIVE: "Harmonic Minor"}.get(self.mode, "")
        print(f"[JazzyFS] Root: {root_name}  Scale: {scale_name}  Mode: {self.mode}")
        print(f"[JazzyFS] Starting in 5 seconds...")

        time.sleep(5)

        # Tempo encodes workload structure (orthogonal to scale/mode)
        FAST = 0.15   # Sequential access = fast notes
        SLOW = 1.2    # Irregular access = slow notes

        for phase in pattern:
            tempo = FAST if phase == "sequential" else SLOW
            print(f"[JazzyFS] ▶ phase={phase}  tempo={tempo}s/note  {direction}")
            self._play_segment(tempo, vol, avg_confidence, root_idx)

        print("[JazzyFS] Playback complete")

        # Reset after playback
        self.phase_history.clear()
        self.confidence_history.clear()
        self.prefetch_history.clear()
        self.melody_playing = False

    def _monitor_completion(self):
        # Background thread: trigger playback when reads stop for 1 second
        while True:
            time.sleep(0.2)

            if (time.time() - self.last_read_time > 1.0 and
                    self.phase_history and
                    not self.melody_playing):

                self._analyze_and_play()

    # --------------------------------------------------
    # Filesystem Operations
    # --------------------------------------------------

    def _full(self, path):
        return os.path.join(self.root, path.lstrip("/"))

    def getattr(self, path, fh=None):
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
        try:
            entries = [".", ".."] + os.listdir(self._full(path))
        except FileNotFoundError:
            raise FuseOSError(errno.ENOENT)
        for e in entries:
            yield e

    def open(self, path, flags):
        if flags & (os.O_WRONLY | os.O_RDWR):
            raise FuseOSError(errno.EACCES)

        full = self._full(path)
        if not os.path.exists(full):
            raise FuseOSError(errno.ENOENT)

        return os.open(full, os.O_RDONLY)

    def read(self, path, size, offset, fh):
        # Reset trace if more than 2 seconds since last read
        # This handles workload boundaries without clearing on every open()
        # Keeps trace intact across rapid dd calls within the same workload
        if time.time() - self.last_read_time > 2.0:
            self.trace.clear()
            self.phase_history.clear()
            self.confidence_history.clear()
            self.prefetch_history.clear()

        os.lseek(fh, offset, os.SEEK_SET)
        actual_offset = os.lseek(fh, 0, os.SEEK_CUR)
        data = os.read(fh, size)

        # Log raw access
        self._log_read(path, actual_offset, len(data))

        # Update shared trace
        event = {"t": time.time(), "path": path, "offset": actual_offset, "size": len(data)}
        self.trace.append(event)

        # Update sonification state
        sonification_phase = self._detect_phase()
        if sonification_phase != "unknown":
            self.phase_history.append(sonification_phase)

        self.last_read_time = time.time()

        # Prefetch decision uses the same phase and confidence
        phase = sonification_phase
        confidence = self._prediction_confidence()

        prefetch = False
        prefetch_offset = None

        if self.prefetch_enabled and len(data) > 0:
            if self.mode == MODE_NONE:
                prefetch = False

            elif self.mode == MODE_BASELINE:
                prefetch = True

            elif self.mode == MODE_ADAPTIVE:
                prefetch = (phase == "sequential" and confidence >= CONFIDENCE_THRESHOLD)

            if prefetch:
                prefetch_offset = actual_offset + len(data)
                self._prefetch_next(self._full(path), prefetch_offset, self.prefetch_size)

        # Track sonification history
        self.confidence_history.append(confidence)
        self.prefetch_history.append(prefetch)

        # Log decision for evaluation and reproducibility
        self._log_decision(path, actual_offset, len(data), phase, confidence, prefetch, prefetch_offset)

        return data

    def release(self, path, fh):
        os.close(fh)


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    if len(sys.argv) != 3:
        print("Usage: jazzyfs.py <source_dir> <mount_point>")
        sys.exit(1)

    source, mount = sys.argv[1], sys.argv[2]
    os.makedirs(mount, exist_ok=True)

    print(f"[JazzyFS] Mounting {source} at {mount} (read-only)")
    print(f"[JazzyFS] Set JAZZYFS_MODE to: none | baseline | adaptive")
    print(f"[JazzyFS] Set JAZZYFS_SOUND=1 to enable sonification")

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
