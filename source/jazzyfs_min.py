#!/usr/bin/env python3

import os, sys, errno
import time
import csv
from fuse import FUSE, Operations, FuseOSError
from collections import deque


class PassthroughRO(Operations):
    def __init__(self, root):
        # The real directory on disk that JazzyFS exposes
        self.root = os.path.realpath(root)

        # Find the project directory so we can store logs in the right place
        repo_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        self.log_path = os.path.join(repo_root, "logs", "access.csv")

        # Counter to record the order of file reads
        self.seq = 0

        # Make sure the logs folder exists
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

        # If the log file does not exist yet, create it and write column names
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["seq", "timestamp", "path", "offset", "size"])

        # Store recent file read events in memory
        # This will be used later for learning and adaptation
        self.trace = deque(maxlen=1000)

        # Turn basic prefetching on or off
        self.prefetch_enabled = True

        # How many bytes to prefetch ahead (small and safe)
        self.prefetch_size = 4096

        # Placeholders for future AI logic
        self.predictor = None
        self.phase_detector = None
        self.confidence_estimator = None

    def _full(self, path):
        # Convert a virtual filesystem path into a real disk path
        if path.startswith("/"):
            path = path[1:]
        return os.path.join(self.root, path)

    def _log_read(self, path, offset, size):
        # Record a file read in the CSV log
        self.seq += 1
        timestamp = time.time()
        with open(self.log_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([self.seq, timestamp, path, offset, size])

    def _should_prefetch(self, event):
        # For now, always allow prefetching
        # Later, AI logic will decide this
        return True

    def _prefetch_next(self, full_path, next_offset, size):
        # Try to read data ahead of time to warm up the cache
        # This must never cause errors or change behavior
        try:
            with open(full_path, "rb") as f:
                f.seek(next_offset)
                f.read(size)
        except Exception:
            # Ignore any errors during prefetch
            pass

    def _sonify_event(self, event):
        # This will later turn file access into sound
        # Nothing happens here yet
        pass

    def getattr(self, path, fh=None):
        # Return file information (size, permissions, timestamps)
        full = self._full(path)
        try:
            st = os.lstat(full)
        except FileNotFoundError:
            raise FuseOSError(errno.ENOENT)

        return {
            "st_atime": st.st_atime,
            "st_ctime": st.st_ctime,
            "st_gid": st.st_gid,
            "st_mode": st.st_mode,
            "st_mtime": st.st_mtime,
            "st_nlink": st.st_nlink,
            "st_size": st.st_size,
            "st_uid": st.st_uid,
        }

    def readdir(self, path, fh):
        # List files inside a directory
        full = self._full(path)
        try:
            entries = [".", ".."] + os.listdir(full)
        except FileNotFoundError:
            raise FuseOSError(errno.ENOENT)

        for entry in entries:
            yield entry

    def open(self, path, flags):
        # Only allow files to be opened for reading
        if flags & (os.O_WRONLY | os.O_RDWR):
            raise FuseOSError(errno.EACCES)

        full = self._full(path)
        if not os.path.exists(full):
            raise FuseOSError(errno.ENOENT)

        return os.open(full, os.O_RDONLY)

    def read(self, path, size, offset, fh):
        # Move the file pointer to the requested location
        os.lseek(fh, offset, os.SEEK_SET)

        # Confirm the current position
        actual_offset = os.lseek(fh, 0, os.SEEK_CUR)

        # Read data from the file
        data = os.read(fh, size)

        # Log what was actually read
        self._log_read(path, actual_offset, len(data))

        # Save this read in memory for learning later
        event = {
            "t": time.time(),
            "path": path,
            "offset": actual_offset,
            "size": len(data),
        }
        self.trace.append(event)

        # Placeholder for sound generation
        self._sonify_event(event)

        # Perform basic prefetching if enabled
        if self.prefetch_enabled and len(data) > 0 and self._should_prefetch(event):
            full_path = self._full(path)
            next_offset = actual_offset + len(data)
            self._prefetch_next(full_path, next_offset, self.prefetch_size)

        return data

    def release(self, path, fh):
        # Close the file when finished
        os.close(fh)


def main():
    # Require exactly two arguments from the command line
    if len(sys.argv) != 3:
        print("Usage: jazzyfs_min.py <source_dir> <mount_point>")
        sys.exit(1)

    # Get source directory and mount location
    source, mount = sys.argv[1], sys.argv[2]

    # Make sure the mount directory exists
    os.makedirs(mount, exist_ok=True)

    print(f"Mounting {source} at {mount} (read-only)")
    print("Logging file reads to logs/access.csv")

    # Start the filesystem
    FUSE(
        PassthroughRO(source),  # filesystem logic
        mount,                  # where it appears
        foreground=True,        # run in terminal
        ro=True,                # read-only
        nothreads=True,         # simpler execution
        direct_io=True,         # bypass kernel caching
        kernel_cache=False      # always go through JazzyFS
    )


if __name__ == "__main__":
    main()
