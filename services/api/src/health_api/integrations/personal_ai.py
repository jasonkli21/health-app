"""Typed integration boundary for the optional Personal AI service."""

from __future__ import annotations

from typing import Literal, Protocol

from health_api.domain.ai import AIContextPack, AssistantMessageRequest, AssistantMessageResponse

READ_CAPABILITIES: tuple[
    Literal[
        "health.context",
        "health.search",
        "health.today",
        "health.profile",
        "health.goals",
        "health.plans",
        "health.trends",
    ],
    ...,
] = (
    "health.context",
    "health.search",
    "health.today",
    "health.profile",
    "health.goals",
    "health.plans",
    "health.trends",
)


class PersonalAIAdapterError(Exception):
    """A sanitized adapter failure that is safe to expose as unavailable."""


class PersonalAIUnavailable(PersonalAIAdapterError):
    """Raised when no reviewed Personal AI adapter is available."""


class PersonalAIAdapter(Protocol):
    @property
    def enabled(self) -> bool: ...

    async def send_message(
        self, request: AssistantMessageRequest, context: AIContextPack
    ) -> AssistantMessageResponse: ...


class DisabledPersonalAIAdapter:
    """Fail-closed adapter used until the real service contract is available."""

    @property
    def enabled(self) -> bool:
        return False

    async def send_message(
        self, request: AssistantMessageRequest, context: AIContextPack
    ) -> AssistantMessageResponse:
        del request, context
        raise PersonalAIUnavailable


def create_personal_ai_adapter() -> PersonalAIAdapter:
    """Return the only supported adapter until external protocol review is complete."""
    return DisabledPersonalAIAdapter()
