# Configuration

`settings.py` loads server-only settings from the environment or root `.env`.
Phase 1 accepts only local/test environments and local development auth. The
configured principal UUID and timezone come from the server; no request field
can set the current owner. Database URLs and other server settings must never
be copied to Expo public variables or routine logs.
