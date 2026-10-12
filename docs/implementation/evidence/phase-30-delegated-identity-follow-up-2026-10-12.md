# Phase 30 delegated identity follow-up evidence

**Date:** 2026-10-12

**Base revision:** `9aa72fe5825ca1df17764e43c3760d4d4f9d35d6`
**Verification basis:** uncommitted working-tree changes; no commit created.

## Implemented boundary

The narrow `health-federation-export-v1` route accepts a Personal AI service identity plus a short-lived Ed25519-signed delegated Google identity assertion. The assertion is checked for issuer/key, Health audience, recent authentication, request-body hash, purpose, destination, and validity interval. Health maps the verified Google subject through an existing linked provider to an existing Firebase owner; it does not accept an owner ID as authentication or create an account. The existing Health admission path then rechecks the active object, local AI permission, cross-domain consent, exact selected purpose/field/destination, current revision, and sensitivity.

The broad Phase 29 Firebase-token read route remains unavailable to Personal AI's Google OIDC adapter. Federation export remains disabled by default. The assertion is request-bound and is not persisted with grants, context snapshots, logs, or proposal metadata.

## Local verification

- `tests/test_personal_ai_context_contract.py` and `tests/test_personal_ai_federation_export.py`: **20 passed**.
- Changed Health API source and test files: Ruff **passed**.

These tests establish local contract behavior only. They do not establish PostgreSQL-backed grant races, a live Firebase/Google linked account, deployed Cloud Run identity, IAM, provider behavior, or end-to-end product/browser acceptance. Those gates remain open.

See [current state](../../current-state.md), the [Personal AI integration contract](../../ai/personal-ai-integration.md), and the cross-repository [Phase 30/31 follow-up evidence](../../../../personal-ai-system/docs/personal-ai-chapter-2/phase-30-31-follow-up-review-implementation-evidence-2026-10-12.md).
