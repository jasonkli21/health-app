"""Cross-check the captured roots and original Health selections against PostgreSQL."""

import json
import os
from pathlib import Path
from uuid import UUID

import psycopg

SOURCES = [
    "first-run.jsonl",
    "third-run.jsonl",
    "fourth-run.jsonl",
    "second-run.jsonl",
]


def main():
    observations = []
    with (
        psycopg.connect(
            os.environ["HEALTH_PAIRED_DSN"].replace(
                "postgresql+psycopg:", "postgresql:"
            )
        ) as health,
        psycopg.connect(os.environ["PAS_PAIRED_DSN"]) as pas,
    ):
        health_version = health.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
        assert health_version == "20261123d102"
        for filename in SOURCES:
            for line in Path(filename).read_text().splitlines():
                evidence = json.loads(line)
                token = UUID(evidence["original_key"])
                attempt = UUID(evidence["attempt"])
                original = health.execute(
                    "SELECT object_id, object_revision FROM r5_preview_reservations WHERE original_key=%s",
                    (token,),
                ).fetchone()
                submission = health.execute(
                    "SELECT root, attempt, create_receipt_digest, preview_receipt_digest, body_digest, "
                    "quarantined_at IS NOT NULL FROM health_dispatch_intents WHERE original_key=%s",
                    (token,),
                ).fetchone()
                assert original and original[1] == 1
                root = UUID(evidence["pas"]["root"])
                routed = pas.execute(
                    "SELECT state, attempt_id, payload_sha256 FROM inference_route_roots WHERE root_id=%s",
                    (root,),
                ).fetchone()
                expected = evidence["health_journal"]
                if expected is None:
                    assert submission is None
                else:
                    assert submission[:2] == (root, attempt)
                    assert submission[4:] == (
                        expected["body_digest"],
                        expected["quarantined"],
                    )
                assert bool(routed) == evidence["pas"]["native_root"]
                if routed:
                    assert routed == ("fenced", attempt, evidence["payload_digest"])
                observations.append(
                    {
                        "scenario": evidence["scenario"],
                        "source_object_id": str(original[0]),
                        "original_revision": original[1],
                        "original_key": str(token),
                        "health_create_receipt_digest": submission[2]
                        if submission
                        else None,
                        "health_preview_receipt_digest": submission[3]
                        if submission
                        else None,
                        "health_original_intent_present": submission is not None,
                        "pas_root": str(root),
                        "pas_native_root_state": routed[0] if routed else None,
                    }
                )
        doc = {
            "health_database": health.info.dbname,
            "health_migration": health_version,
            "pas_database": pas.info.dbname,
            "postgres_server_version": health.info.server_version,
            "observations": observations,
        }
    Path("native-topology.json").write_text(json.dumps(doc, indent=2) + "\n")


if __name__ == "__main__":
    main()
