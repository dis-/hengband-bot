"""Replay only causally valid prefixes through the public policy boundary.

The caller supplies an iterator of (recorded decision, board supplier). A
supplier is deliberately lazy: no response/knowledge/effect of the next
historical command is delivered after a divergence. Checkpoint windows are
independent; never splice their states into a continuous trajectory.
"""

from dataclasses import dataclass, field
from unittest.mock import patch


@dataclass
class ReplayResult:
    window: str
    rows_replayed: int = 0
    matched_rows: int = 0
    town_rows: int = 0
    shadow_rows: int = 0
    first_divergence: dict | None = None
    violations: list = field(default_factory=list)


def ownership_violations(policy, key, shadow=None):
    """Include the divergent decision, even when enforcement suppressed its key."""
    reason = policy.last_reason or ""
    violations = []
    if reason.startswith("ownership:"):
        violations.append({"kind": "ownership-terminal", "reason": reason})
    if "item-reserved" in reason:
        violations.append({"kind": "item-reserved", "reason": reason})
    claim = policy.decision_claim or {}
    shadow = shadow if shadow is not None else claim.get("s33_shadow") or {}
    if shadow.get("would_stop"):
        violations.append({"kind": "s33_shadow", "would_stop": shadow["would_stop"]})
    return violations


def choose_with_on_shadow(policy, board):
    """Observe S3.3 at its production recording seam without turning ON off.

    Production omits the OFF-only s33_shadow field in ON mode. The seam calls
    _claim_suspended_exit, clears the Home observation marker, then judges the
    shadow before consuming offers or declaring the winner. Wrap those two
    recording methods to insert that same pure observer at that exact point.
    The marker assignment is the immediately following production assignment;
    no producer, gate, declaration, recorded board or command is replaced.
    """
    if not hasattr(policy, "_record_decision_claim"):
        return policy.choose_key(board), (policy.decision_claim or {}).get("s33_shadow")
    original_record = policy._record_decision_claim
    original_suspended = policy._claim_suspended_exit
    observation = {"shadow": None}
    active = {}

    def record(snapshot, key):
        active["key"] = key
        try:
            return original_record(snapshot, key)
        finally:
            active.clear()

    def suspended(snapshot, register):
        original_suspended(snapshot, register)
        if active and (snapshot.in_town or snapshot.store is not None):
            policy._claim_home_knowledge_observed = False
            observation["shadow"] = policy._s33_shadow_verdict(snapshot, active["key"])

    with patch.object(policy, "_record_decision_claim", record), patch.object(policy, "_claim_suspended_exit", suspended):
        key = policy.choose_key(board)
    return key, observation["shadow"]


def replay_window(name, policy, decisions):
    """Choose and acknowledge matching decisions only; stop at first difference.

    Conservatively compare both key and reason. Even a reason-only difference
    ends this window. None and the empty key are distinct; do not stringify a
    terminal result to match a recording.
    """
    from hengbot.policy import staged_prompt_chain_matches

    result = ReplayResult(name)
    for recorded, board_supplier in decisions:
        board = board_supplier()
        key, shadow = choose_with_on_shadow(policy, board)
        result.rows_replayed += 1
        result.town_rows += bool(board.in_town)
        result.shadow_rows += shadow is not None
        row = recorded["row"]
        result.violations.extend(
            {"row": row, **violation}
            for violation in ownership_violations(policy, key, shadow)
        )
        if (key, policy.last_reason) != (recorded["key"], recorded["reason"]):
            result.first_divergence = {
                "row": row,
                "recorded": [recorded["key"], recorded["reason"]],
                "new": [key, policy.last_reason],
            }
            break
        result.matched_rows += 1
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
        if key is None:
            break
    return result
