"""Recorded idle windows with one policy per window.

The capture has no serialized policy. Seed its recorded prepare mode and the
filed withdrawal identified by its admission row. Public choose_key posts the
scan before the recorded Home knowledge is consumed. Skill-request suppression
matches round 16. These are open-loop boards, not simulated command effects.
"""
import tests  # noqa: F401

import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.home_visit import HomeVisitKind, HomeVisitRequest
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.warrior_optimization import load_character_calibration
from tests.test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"


def replay_idle(stamp):
    with gzip.open(FIXTURES / f"town-idle-20261025-{stamp}.jsonl.gz",
                   "rt", encoding="utf8") as stream:
        capture = json.load(stream)
    monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
    trace = []
    with TemporaryDirectory() as directory, patch.object(
            HengbotPolicy, "_skill_exp_request_key", return_value=None):
        root = Path(directory)
        policy = _policy(root, monrace)
        calibration = root / "recorded-calibration.json"
        calibration.write_text(json.dumps(capture["calibration"]), encoding="utf8")
        policy._character_calibration = load_character_calibration(calibration)
        policy._character_calibration_loaded = True
        policy._calibration_session_id = policy._character_calibration.session_id
        policy._crossarea_fundraising_enforced = True
        policy._in_store_ops_enabled = True

        def consume(row):
            _, boards = _consume_response_sequence(
                [json.dumps(row, ensure_ascii=False)], policy, lambda _key: True,
                monrace, knowledge_ledger_path=root / "knowledge.jsonl")
            return boards[-1] if boards else None

        consume(capture["skill"])
        board = consume(capture["boards"][1])
        policy._fundraising_mode = "prepare"
        target = tuple(capture["original"][-1]["admissions"][-1]["terminal"][1][0])
        policy._home_visit.file(HomeVisitRequest(
            HomeVisitKind.WITHDRAW, "legacy-withdrawal", target, address=target))
        scan = policy.choose_key(board)
        policy.confirm_key_posted(scan)
        consume(capture["home"])
        # Timer requests belong to the live CLI and were already serviced.
        policy._periodic_dump_requested = False
        policy._periodic_save_requested = False
        for row in capture["boards"][1:]:
            board = consume(row)
            key = policy.choose_key(board)
            plan = policy._town_errand_plan
            trace.append({
                "sequence": policy._decision_sequence,
                "turn": board.turn, "key": None if key is None else str(key),
                "reason": policy.last_reason,
                "admissions": list(policy._decision_terminal_admissions),
                "plan": repr(plan), "request": repr(policy._home_visit.request),
            })
            if key is not None:
                policy.confirm_key_posted(key)
    return {"scan": str(scan), "trace": trace}
