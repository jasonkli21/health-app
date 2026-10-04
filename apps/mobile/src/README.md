# Mobile source

Product code belongs under feature-oriented modules such as `features/today`, `features/add`, `features/profile`, `features/assistant`, `features/plans`, `features/goals`, `features/insights`, `features/trackers`, `features/records`, and `features/settings`.

Native-only integrations such as HealthKit must stay behind mobile-specific adapters and must not leak into shared packages.
