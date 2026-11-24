"""Render the captured synthetic runs as a stable redacted ledger."""

import json
from pathlib import Path

SOURCES = ["first-run.jsonl", "third-run.jsonl", "fourth-run.jsonl", "second-run.jsonl"]
SUCCESS = {"ok", "concurrent", "lost-ack"}
RECEIVER_FAULTS = {"429", "timeout", "disconnect"}
READ_DENIALS = {"changed-detail", "expired-before-publication", "forged-terminal"}
SCENARIOS = {
    *SUCCESS,
    *RECEIVER_FAULTS,
    *READ_DENIALS,
    "health-ai-consent",
    "health-cross-domain-consent",
    "health-owner",
    "health-firebase-revoked",
    "health-record",
    "health-recipient",
    "health-crossed-recipient",
    "crossed-pas-owner",
    "regrant-higher-epoch",
    "pas-memory",
    "pas-source",
    "pas-owner",
    "pas-release",
    "interrupt-after-health-commit",
    "pas-root-failure",
    "pas-after-fence",
    "health-revoked-after-fence",
}


def main():
    records = [
        json.loads(line)
        for filename in SOURCES
        for line in Path(filename).read_text().splitlines()
    ]
    assert (
        len(records) == len(SCENARIOS)
        and {row["scenario"] for row in records} == SCENARIOS
    )
    output = [
        "# PAS and Health paired verification ledger",
        "",
        "PAS `00c7d954f864d001ec7186c5c98528262abbf06d`",
        "",
        "Health `dff958671ae637198a90c1091c43228e4808bcb3`",
        "",
        "| Row | Paired verdict | Evidence |",
        "|---|---|---|",
        "| H08 | PASS E1 synthetic | Original Health R5 create/preview and private dispatch receipts verified. One synthetic Health profile preference and separately authorized canonical PAS memory were present in exactly one fixture-observed POST with the attested digest. |",
        "| H09 | PASS E1 synthetic | Each crossed authority, consent, epoch, owner, record, and PAS grant case issued and received zero provider POSTs. A Health source revoked at the second send check was blocked after both runtime fences and before the socket write. |",
        "| H10 | PASS E1 synthetic with named native stores | Concurrent same-key Health calls and a lost 202 each produced one POST. Receiver 429, read timeout and EOF each produced one POST and a nonterminal original-key read with no resend. Pre-write interruptions at three layers produced zero POSTs. Full independent process restore remains unverified. |",
        "| H11 | PASS E1 synthetic with named native stores | Current Health and PAS rights gate status and matching detail. Valid recovery verifies the pinned terminal and exact result before disclosure. Crossed keys/owners, Health or PAS revoke, conflicting detail, forged terminal and expiry at publication suppress disclosure. |",
        "| H17 | PASS E1 synthetic topology | Separate Health, PAS and fake receiver processes and loopback ports. Native Health profile/intent and PAS principal/memory/routing root, POSIX send fences, PAS fixture canonical SQLite and synthetic grant/dependency/branch witnesses. Full native/independent restore and hosted tiers remain unverified. |",
        "",
        "| Scenario | Caller continuation POSTs to PAS | PAS POSTs issued | Receiver POSTs | PAS journal | Native root | Runtime fences | Health outward result |",
        "|---|---:|---:|---:|---|---|---:|---|",
    ]
    for row in records:
        name = row["scenario"]
        pas = row["pas"]
        expected_count = int(name in SUCCESS | RECEIVER_FAULTS | READ_DENIALS)
        assert len({row["health_pid"], row["pas_pid"], row["receiver_pid"]}) == 3
        assert len({row["health_port"], row["pas_port"], row["receiver_port"]}) == 3
        assert len(pas["issued"]) == len(row["receiver"]) == expected_count
        assert row["result_disclosed"] is (name in SUCCESS)
        assert row["ordinary_confirmation_status"] == 422
        assert pas["branch"] == row["branch"] and not pas["network_denials"]
        assert row["health_confirmations"] <= 1
        if expected_count:
            assert pas["native_root"] and pas["physical_fences"] == 2
            assert row["health_journal"]["body_digest"] == pas["body_digest"]
        if name in READ_DENIALS:
            assert row["health_journal"]["quarantined"]
        output.append(
            f"| {name} | {row['health_confirmations']} | {len(pas['issued'])} | "
            f"{len(row['receiver'])} | {pas['state']} | {'yes' if pas['native_root'] else 'no'} | "
            f"{pas['physical_fences']} | {'verified result' if row['result_disclosed'] else 'none'} |"
        )
    output.extend(
        [
            "",
            f"Across {len(records)} scenarios, PAS issued {sum(len(row['pas']['issued']) for row in records)} provider POSTs and the independent receivers observed the same count. "
            "Each issued POST matched the corresponding receiver digest and pre-confirmation preview attestation. Distinct original attempts were used across scenarios.",
            "",
            "The JSONL records come from successive runs and four supplemental fault cases. The initial Firebase stub omitted `UserNotFoundError` and the first crossed-owner probe expected the empty read response on a POST. The corrected probes exercised the reviewed verifier and private admission and recorded zero provider POSTs.",
            "",
            "E2 evidence applies only to the named native stores in this fixture. Full independent restore, hosted identity and enrollment, installed/mobile runtime and production activation remain outside this paired verdict. No Step 5 release or activation occurred.",
        ]
    )
    Path("LEDGER.md").write_text("\n".join(output) + "\n")


if __name__ == "__main__":
    main()
