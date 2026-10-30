"""Replay one recorded bot session (raw state lines + decision rows) on a fresh policy.

Shared by the D34 recorded pins.  The segmentation is the one of
test_supply_shortfall_owner_recorded (``_segments``); the ``~f`` skill list
of the same session is consumed on every board, as the live driver keeps it.
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from test_esp_threat_rest_recorded import _policy
from test_supply_shortfall_owner_recorded import _segments


def replay_session(test, pin, monrace):
    """Yield (policy, board, recorded decision) for every recorded row of ``pin``."""
    directory = TemporaryDirectory()
    test.addCleanup(directory.cleanup)
    root = Path(directory.name)
    policy = _policy(root, monrace)
    policy._crossarea_fundraising_enforced = True  # live argv
    policy._in_store_ops_enabled = True  # live argv (--in-store-shop-ops)
    lines, decisions = pin["lines"], pin["decisions"]
    skill = next(json.loads(line) for line in lines if '"skill_exp"' in line)
    previous = None
    for index, start, end in _segments(lines, decisions):
        recorded = decisions[index]
        segment = lines[start:end]
        if previous is not None and previous["key"]:
            row = json.loads(segment[-1])
            row["_completed_operation_sequence"] = previous["decision_sequence"]
            row["_completed_operation_owner"] = previous["reason"]
            segment = segment[:-1] + [json.dumps(row, ensure_ascii=False) + "\n"]
        _, boards = _consume_response_sequence(
            segment, policy, lambda _key: True, monrace,
            knowledge_ledger_path=root / "knowledge.jsonl")
        board = boards[-1]
        if previous is None:
            policy.prime(board)
        policy.consume_skill_knowledge({**skill, "player": {"level": board.player.level}})
        board = policy.with_known_skill_exp(board)
        yield policy, board, recorded
        previous = recorded
