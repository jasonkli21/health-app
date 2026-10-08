"""Status-only boundary for the disabled Personal AI integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PERSONAL_AI_DISABLED_REASON = (
    "Live Assistant messaging is unavailable until the Personal AI Application "
    "Integration Contract is implemented and reviewed."
)


@dataclass(frozen=True, slots=True)
class PersonalAIIntegrationStatus:
    """Facts Health can report while no external integration is configured."""

    configured: Literal[False] = False
    status: Literal["disabled"] = "disabled"
    reason: str = PERSONAL_AI_DISABLED_REASON


def create_personal_ai_adapter() -> PersonalAIIntegrationStatus:
    """Return disabled status only; no message transport is available."""
    return PersonalAIIntegrationStatus()
