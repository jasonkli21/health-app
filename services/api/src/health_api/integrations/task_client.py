"""Supply Health service identity to the shared bounded task transport."""

from collections.abc import Callable
from typing import cast

import httpx
from google.oauth2 import id_token

from health_api.integrations.personal_ai_context_auth import (
    PersonalAIContextIdentityVerifier,
    _bounded_google_request_type,
)
from health_api.integrations.task_control import (
    SourceTaskControlClient,
    SourceTaskSettings,
    TaskControlUnavailable,
)


def _service_token(audience: str, service_account: str) -> str:
    request = _bounded_google_request_type()()
    try:
        token = str(cast(Callable[..., str], id_token.fetch_id_token)(request, audience))
    finally:
        request.session.close()
    claims = PersonalAIContextIdentityVerifier._google_claims(token, audience)
    if claims.get("email") != service_account or claims.get("email_verified") is not True:
        raise TaskControlUnavailable
    return token


def task_client(settings: SourceTaskSettings) -> SourceTaskControlClient:
    return SourceTaskControlClient(
        application_id="health",
        base_url=settings.base_url,
        audience=settings.audience,
        issuer=settings.issuer,
        key_id=settings.key_id,
        private_key=settings.private_key.get_secret_value(),
        service_account=settings.service_account,
        token_fetcher=_service_token,
        client_type=httpx.Client,
    )
