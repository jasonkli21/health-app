# Mobile source

Product code belongs under feature-oriented modules such as `features/today`, `features/add`, `features/profile`, `features/assistant`, `features/plans`, `features/goals`, `features/insights`, `features/trackers`, `features/records`, and `features/settings`.

Native-only integrations such as HealthKit must stay behind mobile-specific adapters and must not leak into shared packages.

`features/insights` uses the generated Phase 7 client for explicit metric
trends, bounded same-day associations, evidence-linked insight/recommendation
history, and manual experiment drafts/results. `CurrentInsightCards` adds at
most three current, unexpired insights to Today and links to the full surface.

`features/account-data` uses the generated Phase 9 API client for owner JSON
export and explicit domain deletion. A deletion request ID is kept in secure
storage until the server reports completion; then the app removes the
account-scoped HealthKit consent and indexed checkpoint entries before
signing out. The share sheet is user-directed and may retain its own export
copy. This does not erase Apple Health originals or external service copies.
