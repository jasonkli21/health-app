# Configuration

`settings.py` loads server-only settings from the environment or root `.env`.
The configured principal UUID and timezone come from the server; no request
field can set the current owner. Database URLs and other server settings must
never be copied to Expo public variables or routine logs.

`PERSONAL_AI_ENABLED` defaults to `false`. Setting it to `true` is rejected
until the real Personal AI service, authentication, delegation, tool, and
retention contracts are supplied and configured. There is no user-configurable
AI URL: outbound destinations must come from a reviewed server adapter, never
from a request or an unverified local placeholder.
