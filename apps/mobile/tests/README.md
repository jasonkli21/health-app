# Mobile tests

- `api-client.test.ts` checks generated route serialization, errors, and compile-time contract cases.
- `profile-model.test.ts` checks Profile draft serialization, unknown/false/zero distinctions, timezone validity, and edit-draft preservation.
- `profile-form.render.test.tsx` uses test-only native element stubs and React DOM server rendering to verify the initial accessible form labels and permissions-off defaults. It does not simulate native events or replace device accessibility checks.
- Assistant, Planning, and Insights state tests exercise extracted feature transitions, request staleness, revision/retry identity, and typed draft serialization without mounting native screens.
- `assistant-proposal-editor.render.test.tsx` uses the existing server-render/native-stub approach to verify that visible and accessible proposal-editor labels identify the correct fields in order.

Keep tests in this directory or clearly separated test subdirectories. Do not mix test files into production source directories by default. Expo export in CI verifies Metro can bundle the complete native route tree; an equipped host must still perform the manual interaction and accessibility walkthrough documented in the local development guide.
