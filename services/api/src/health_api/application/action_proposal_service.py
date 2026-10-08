"""Stable application façade for proposal lifecycle and confirmed execution.

Lifecycle/revision, validation/preview, and apply/replay use cases live in
separate modules. Confirmation, owner locks, execution, receipts, and replay
remain one transaction-owned path in ``proposal_apply``.
"""

from health_api.application.proposal_apply import (
    ApplyProposalOutcome,
    _find_receipt,
    _target_results,
    apply_action_proposal,
)
from health_api.application.proposal_lifecycle import (
    action_proposal_history,
    action_proposal_state,
    action_proposal_summaries,
    create_action_proposal,
    edit_action_proposal,
    get_action_proposal,
    list_action_proposals,
    reject_action_proposal,
)
from health_api.application.proposal_support import (
    ProposalStatus,
    _append_event,
    _append_revision,
    _content_hash,
    _draft_snapshot,
    _json_canonical,
    _parse_snapshot,
    _proposal_changes,
    _reference_revisions,
    _state_from_row,
)
from health_api.application.proposal_validation import (
    _bounded_review_snapshot,
    _changed_reference_hints,
    _validate_commands,
    _validate_evidence,
)

__all__ = [
    "ApplyProposalOutcome",
    "ProposalStatus",
    "_append_event",
    "_append_revision",
    "_bounded_review_snapshot",
    "_changed_reference_hints",
    "_content_hash",
    "_draft_snapshot",
    "_find_receipt",
    "_json_canonical",
    "_parse_snapshot",
    "_proposal_changes",
    "_reference_revisions",
    "_state_from_row",
    "_target_results",
    "_validate_commands",
    "_validate_evidence",
    "action_proposal_history",
    "action_proposal_state",
    "action_proposal_summaries",
    "apply_action_proposal",
    "create_action_proposal",
    "edit_action_proposal",
    "get_action_proposal",
    "list_action_proposals",
    "reject_action_proposal",
]
