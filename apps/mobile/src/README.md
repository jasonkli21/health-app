# Mobile source

Product code belongs under feature-oriented modules such as `features/today`, `features/add`, `features/profile`, `features/assistant`, `features/plans`, `features/goals`, `features/insights`, `features/trackers`, `features/records`, and `features/settings`.

Native-only integrations such as HealthKit must stay behind mobile-specific adapters and must not leak into shared packages.

`features/insights` uses the generated Phase 7 client for explicit metric
trends, bounded same-day associations, evidence-linked insight/recommendation
history, and manual experiment drafts/results. `CurrentInsightCards` adds at
most three current, unexpired insights to Today and links to the full surface.
