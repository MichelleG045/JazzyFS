#!/usr/bin/env bash
set -euo pipefail

# Tar extraction workload: reads archive through JazzyFS mount
# Simulates software installation or backup restore (sequential small files)
mkdir -p /tmp/jazzyfs_tar_extract
trap 'rm -rf /tmp/jazzyfs_tar_extract' EXIT
[[ -f mount/archive.tar ]] || { echo "ERROR: mount/archive.tar not found"; exit 1; }
tar -xf mount/archive.tar -C /tmp/jazzyfs_tar_extract
rm -rf /tmp/jazzyfs_tar_extract
trap - EXIT
