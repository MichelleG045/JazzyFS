#!/usr/bin/env python3

import os
import sys
import errno
import time
import csv
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

# Total duration of musical playback after workload completes
TOTAL_PLAY_TIME = 8.0

# --------------------------------------------------
# Evaluation Modes
# --------------------------------------------------

MODE_NONE = "none"         # No prefetching (control baseline)
MODE_BASELINE = "baseline" # Always prefetch (fixed heuristic)
MODE_ADAPTIVE = "adaptive" # Confidence-guided prefetching (research contribution)

# --------------------------------------------------
# Musical Frequencies
# --------------------------------------------------

NOTE_FREQ = {
    "C4": 261.63,
    "D4": 293.66,
    "E4": 329.63,
    "F4": 349.23,
    "G4": 392.00,
    "A4": 440.00,
    "B4": 493.88,
    "C5": 523.25,
    "Eb4": 311.13,
    "Ab4": 415.30,
    "Bb4": 466.16,
}

# Scale encodes prefetching strategy (orthogonal to tempo)
# none     = Major     (neutral, no strategy)
# baseline = Natural Minor (always active, can be wasteful)
# adaptive = Harmonic Minor (selective, nuanced)
SCALES = {
    MODE_NONE:     ["C4", "D4", "E4",  "F4", "G4", "A4",  "B4",  "C5"],
    MODE_BASELINE: ["C4", "D4", "Eb4", "F4", "G4", "Ab4", "Bb4", "C5"],
    MODE_ADAPTIVE: ["C4", "D4", "Eb4", "F4", "G4", "Ab4", "B4",  "C5"],
}

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

        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

        write_access_header = not os.path.exists(self.log_path) or os.path.getsize(self.log_path) == 0
        self._log_f = open(self.log_path, "a", newline="")
        self._log_writer = csv.writer(self._log_f)
        if write_access_header:
            self._log_writer.writerow(["seq", "timestamp", "path", "offset", "size"])

        write_decision_header = not os.path.exists(self.decision_log_path) or os.path.getsize(self.decision_log_path) == 0
        self._decision_f = open(self.decision_log_path, "a", newline="")
        self._decision_writer = csv.writer(self._decision_f)
        if write_decision_header:
            self._decision_writer.writerow([
                "timestamp", "mode", "path", "offset", "size",
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
        self.last_read_time = time.time()
        self.melody_playing = False

        print(f"[JazzyFS] Mode           = {self.mode}")
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
        self._log_writer.writerow([self.seq, time.time(), path, offset, size])
        self._log_f.flush()

    def _log_decision(self, path, offset, size, phase, confidence, prefetch, prefetch_offset):
        self._decision_writer.writerow([
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

    def _play_segment(self, duration, tempo):
        # Play a segment of the scale at the given tempo
        scale = SCALES.get(self.mode, SCALES[MODE_ADAPTIVE])
        note_index = 0
        start = time.time()

        while time.time() - start < duration:
            note = scale[note_index % len(scale)]
            freq = NOTE_FREQ[note]

            subprocess.Popen(
                ["play", "-n", "synth", str(tempo * 0.9), "sine", str(freq)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            note_index += 1
            time.sleep(tempo)

    def _analyze_and_play(self):
        pattern = self._compress_phases()
        print(f"[JazzyFS] Phase pattern: {pattern}")

        if not pattern:
            return

        self.melody_playing = True

        # Tempo encodes workload structure (orthogonal to scale/mode)
        FAST = 0.15   # Sequential access = fast notes
        SLOW = 1.2    # Irregular access = slow notes

        segment_duration = TOTAL_PLAY_TIME / len(pattern)

        for phase in pattern:
            if phase == "sequential":
                self._play_segment(segment_duration, FAST)
            else:
                self._play_segment(segment_duration, SLOW)

        # Reset after playback
        self.phase_history.clear()
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