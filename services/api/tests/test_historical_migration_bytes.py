from __future__ import annotations

import hashlib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_historical_migration_files_match_frozen_digests() -> None:
    manifest = REPOSITORY_ROOT / "migrations" / "historical-sha256.txt"
    entries = [line.split(maxsplit=1) for line in manifest.read_text().splitlines()]

    assert entries
    for expected_digest, relative_path in entries:
        migration = REPOSITORY_ROOT / relative_path
        assert migration.is_file(), f"Frozen migration is missing: {relative_path}"
        actual_digest = hashlib.sha256(migration.read_bytes()).hexdigest()
        assert actual_digest == expected_digest, f"Historical migration changed: {relative_path}"
