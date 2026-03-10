#!/usr/bin/env bash
set -euo pipefail

# Tar extraction workload: reads archive through JazzyFS mount
# Simulates software installation or backup restore (sequential small files)
mkdir -p /tmp/jazzyfs_tar_extract
tar -xf mount/archive.tar -C /tmp/jazzyfs_tar_extract --overwrite
rm -rf /tmp/jazzyfs_tar_extract
