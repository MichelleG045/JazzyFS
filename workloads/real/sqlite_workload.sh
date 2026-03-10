#!/usr/bin/env bash
set -euo pipefail

# SQLite workload: reads DB file through JazzyFS mount (read-only)
# Simulates database application: sequential scans + random lookups
sqlite3 "file:mount/test.db?mode=ro" \
    "SELECT COUNT(*) FROM data;" \
    "SELECT * FROM data WHERE id % 7 = 0 LIMIT 500;" \
    "SELECT AVG(value) FROM data;" \
    "SELECT * FROM data ORDER BY value DESC LIMIT 100;"
