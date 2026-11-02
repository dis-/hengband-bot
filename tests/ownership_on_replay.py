"""Replay only causally valid prefixes through the public policy boundary.

The caller supplies an iterator of (recorded decision, board supplier). A
supplier is deliberately lazy: no response/knowledge/effect of the next
historical command is delivered after a divergence. Checkpoint windows are
independent; never splice their states into a continuous trajectory.
"""

from dataclasses import dataclass, field


@dataclass
class ReplayResult:
    window: str
    rows_replayed: int = 0
    matched_rows: int = 0
    town_rows: int = 0
    first_divergence: dict | None = None
    violations: list = field(default_factory=list)


def ownership_violations(policy, key):
    """Include the divergent decision, even when enforcement suppressed its key."""
    reason = policy.last_reason or ""
    violations = []
    if reason.startswith("ownership:"):
        violations.append({"kind": "ownership-terminal", "reason": reason})
    if "item-reserved" in reason:
        violations.append({"kind": "item-reserved", "reason": reason})
    return violations


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
        key = policy.choose_key(board)
        result.rows_replayed += 1
        result.town_rows += bool(board.in_town)
        row = recorded["row"]
        result.violations.extend(
            {"row": row, **violation}
            for violation in ownership_violations(policy, key)
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
