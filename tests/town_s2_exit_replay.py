"""Round-16 n1-a windows, retaining one policy throughout each window.

Declared walls match the S1 measurement: the already held skill list suppresses
its request, and the live identification-flow departure verdict is supplied.
Only 183351 seeds the recorded Morivant expedition. Recorded boards are an
open-loop input; they cannot simulate the movement of newly selected commands.
"""
import tests  # noqa: F401

import gzip
import json
import time
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import MorivantFullIdentifyExpedition
from tests.test_esp_threat_rest_recorded import EDIT, _policy
from hengbot.monrace_knowledge import load_monrace_knowledge

FIXTURES = Path(__file__).parent / 'fixtures'


def live_entry_refusal(self, snapshot, *, destination_depth=None, commit=True, codes=None):
    if codes is not None:
        codes.append('identification-flow')
    return False


def replay_four_boards():
    monrace = load_monrace_knowledge(EDIT / 'MonraceDefinitions.jsonc')
    trace = []
    with gzip.open(FIXTURES / 'n1a-townalt-20261023.jsonl.gz', 'rt', encoding='utf8') as stream:
        lines = list(stream)
    with TemporaryDirectory() as directory, \
            patch.object(HengbotPolicy, '_equipment_departure_ready', live_entry_refusal), \
            patch.object(HengbotPolicy, '_skill_exp_request_key', return_value=None):
        root = Path(directory)
        for line in lines:
            policy = _policy(root, monrace)
            _, boards = _consume_response_sequence(
                [line], policy, lambda _key: True, monrace,
                knowledge_ledger_path=root / 'knowledge.jsonl')
            board = boards[-1]
            policy._home_knowledge_scan_epoch = 0
            policy._morivant_full_identify = MorivantFullIdentifyExpedition(
                origin_town_id=1, target_signatures=tuple(sorted(
                    policy._item_signature(item) for item in policy._carried_full_identify_targets(board))))
            start = time.perf_counter()
            key = policy.choose_key(board)
            trace.append(dict(turn=board.turn, key=None if key is None else str(key),
                              reason=policy.last_reason, seconds=time.perf_counter()-start,
                              admissions=list(getattr(policy, '_decision_terminal_admissions', ()))))
    return trace


def replay_n1(name):
    metadata = json.loads((FIXTURES / 'town-s2-n1-windows.json').read_text(encoding='utf8'))[name]
    monrace = load_monrace_knowledge(EDIT / 'MonraceDefinitions.jsonc')
    trace = []
    entry_wall = (patch.object(HengbotPolicy, '_equipment_departure_ready', live_entry_refusal)
                  if metadata['entry_wall'] else nullcontext())
    with TemporaryDirectory() as directory, entry_wall, \
            patch.object(HengbotPolicy, '_skill_exp_request_key', return_value=None):
        root = Path(directory)
        policy = _policy(root, monrace)
        if not metadata['entry_wall']:
            policy._crossarea_fundraising_enforced = True
            policy._in_store_ops_enabled = True
        seeded = False
        decide_at = set(metadata['decide_at'])
        with gzip.open(FIXTURES / metadata['fixture'], 'rt', encoding='utf8') as stream:
            for index, line in enumerate(stream):
                _, boards = _consume_response_sequence(
                    [line], policy, lambda _key: True, monrace,
                    knowledge_ledger_path=root / 'knowledge.jsonl')
                if index not in decide_at:
                    continue
                board = boards[-1]
                if metadata['seed'] and not seeded:
                    targets = policy._carried_full_identify_targets(board)
                    policy._morivant_full_identify = MorivantFullIdentifyExpedition(
                        origin_town_id=1, target_signatures=tuple(sorted(
                            policy._item_signature(item) for item in targets)))
                    seeded = True
                start = time.perf_counter()
                key = policy.choose_key(board)
                elapsed = time.perf_counter() - start
                claim = getattr(policy, 'decision_claim', None) or {}
                trace.append(dict(turn=board.turn, key=None if key is None else str(key),
                                  reason=policy.last_reason, seconds=elapsed,
                                  admissions=list(getattr(policy, '_decision_terminal_admissions', ())),
                                  preempted='preempted-by:quest-request' in json.dumps(claim)))
                policy.confirm_key_posted(key)
    return trace
