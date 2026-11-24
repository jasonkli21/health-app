# PAS and Health paired synthetic verification

The lane used detached worktrees at PAS `00c7d954f864d001ec7186c5c98528262abbf06d` and Health `dff958671ae637198a90c1091c43228e4808bcb3`. The probes use `pas-dispatch/1`, the Health R5 receipt verifier, Health's verified create/preview and confirmation caller, the existing PAS application plan routes, and the same generic PAS `PrivateDispatch` and `RuntimeDispatch` seam. The receiver runs independently and signs a synthetic response. The fixture never installs a live runtime or uses a live identity.

## Reproduce

Place the Health and PAS detached worktrees at sibling paths named `health` and `pas`. The harness lives in `health/verification-step4`. Use the repositories' reviewed Python environments with dev and native PostgreSQL dependencies. The run used Python 3.12.14 in both processes and PostgreSQL 16.2. The Health and PAS dependency defaults in `run.sh` point to this environment's existing virtualenvs. Override `HEALTH_PYTHON`, `PAS_PYTHON`, and `PG_BIN` as needed.

Run these commands from this directory.

```bash
./setup-postgres.sh
./run-matrix.sh /var/tmp/paired-health-reproduction > evidence.jsonl
```

The database setup requires an unused data directory and Unix socket path. It creates two disposable databases, applies the Health migration through `20261123d102`, and the PAS worker applies PAS migrations in its own database. Set `HEALTH_PAIRED_DSN` and `PAS_PAIRED_DSN` to the corresponding Unix socket URLs if the defaults are unavailable. Use a new absolute fixture directory outside repository trees. The PAS protected store refuses a directory with a `.git` ancestor. This environment has an empty `/tmp/.git` marker, so fixture runtime storage used `/var/tmp`. The network-capable shell invocation was needed for explicit numeric loopback and the PostgreSQL socket. Participant audit hooks rejected external TCP and DNS. The local PostgreSQL server bound only its Unix socket.

## Topology and what it establishes

- The Health worker uses real Health profile reads and consent mutations, R5 reservations and original receipt verification, and native PostgreSQL for the original dispatch intent. A separate per-scenario SQLite fixture checkpoint reserves its original key before the Health SQL insert. In-memory synthetic enrollment and authority witnesses drive live per-operation checks. The delegated Firebase verification and PAS-facing service authentication use local SDK and HMAC witnesses, with fixed audiences and one-use reverse request proofs. The private Health reverse endpoint is a fixture adapter over the Health registered-source callback and source readers.
- The PAS worker serves the real FastAPI routes with a dedicated loopback port. The PAS principal directory, memory and memory lifecycle, and routing roots use a second PostgreSQL database. Its root witness is fsynced outside PostgreSQL. The application source grants, PAS disclosure grants, branch and conversation/message history, and frozen dependency lookup are fixture-process memory. Canonical dispatch status and result use PAS's synthetic SQLite journal. The protected POSIX runtime stores both attempt and original-key send fences. The runtime runs inside the PAS process, and the receiver has its own PID, loopback listener, signing key and arrival ledger.
- The ordinary R5 confirmation path returns 422 for every case. The separate private wire path uses the registered Health original receipt key, preview and terminal key roles, live source/branch/grant checks and exact receiver digest comparison. The harness records digest and presence checks for the selected Health record and PAS memory. The captured evidence contains no raw receipt, Health projection, PAS memory text, provider payload, bearer token or signing key.
- A fixed fixture clock keeps the detached receipt and dispatch checks synchronized. Identity age, PostgreSQL root time, transport timeouts, and the bounded callback duration use real time. The expiry case advances the Health fixture clock at the detail boundary.
- PAS's original-key and attempt fences and Health's native journal were exercised. The interruption cases inject a lost response, a pre-transport interruption after the Health SQL commit, a failed PAS root claim and a failure after PAS and runtime retained fences. Observation after interruption constructs a new Health caller against the same committed state. The lane did not kill and reconstitute PAS or independently restore every authority, conversation, source or runtime store. It has no native mobile, hosted Firebase, production PAS, provider, or billing verdict.

The run summary, row scoring, and counts are recorded in the [paired ledger](LEDGER.md). An independent read-only query cross-checked all 26 original Health selections and any submitted intent and PAS root. The PostgreSQL observations are in [native-topology.json](native-topology.json).
