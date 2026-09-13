"""Quest-travel pins over a minimal retained-incident fixture.

The fixture holds original records 4-11, 13-14, and 16-22 from
``jsonlog/incident-quest-request-retired-20260913.snapshots.jsonl``: the Home
request/response and q22 travel observations at turns 2856171, 2856179,
2856191, 2856202, 2856214, 2856584, 2856596, 2856607, 2856615, 2856625,
2856635, and 2856646.  Repeated turns retain distinct emitted record types.
"""

import copy
import gzip
import json
import os
import tempfile
import unittest
from pathlib import Path

from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.cli import _dispatch_response_lines
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import WAIT_KEY
from hengbot.policy_types import DecisionCandidate
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_strategies import find_quest_strategies, load_quest_strategies
from hengbot.town_maps import parse_town_map


ROOT = Path(__file__).resolve().parents[1]
EDIT = Path("C:/hengband/lib/edit")
SNAPSHOTS = ROOT / "tests/fixtures/quest-request-retired-stage1.jsonl.gz"
PIN_RECORDS = (4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 16, 17, 18, 19, 20, 21, 22)


class QuestTravelProgressPins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.previous_home = os.environ.get("HENGBOT_HOME_HISTORY_DIR")
        os.environ["HENGBOT_HOME_HISTORY_DIR"] = self.temp.name
        self.addCleanup(self._restore_home)

    def _restore_home(self):
        if self.previous_home is None:
            os.environ.pop("HENGBOT_HOME_HISTORY_DIR", None)
        else:
            os.environ["HENGBOT_HOME_HISTORY_DIR"] = self.previous_home

    def _policy(self, *, maps=True):
        town_maps = {}
        if maps:
            names = (
                "01_Outpost_Full.txt", "02_Telmora.txt", "03_Morivant.txt",
                "04_Angwil.txt", "05_Zul.txt",
            )
            town_maps = {
                town_id: parse_town_map(EDIT / "towns" / name)
                for town_id, name in enumerate(names)
            }
        return HengbotPolicy(
            town_maps=town_maps,
            monrace_knowledge=self.monrace,
            dungeon_knowledge=load_dungeon_knowledge(
                EDIT / "DungeonDefinitions.jsonc"
            ),
            quest_knowledge=load_quest_knowledge(EDIT / "quests"),
            quest_strategies=load_quest_strategies(
                find_quest_strategies(ROOT / "jsonlog/bot-state-fixed.jsonl")
            ),
            baseitem_costs=load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc"),
            exploration_ledger_path=Path(self.temp.name) / "exploration.json",
        )

    def _records(self):
        with gzip.open(SNAPSHOTS, mode="rt", encoding="utf-8") as stream:
            lines = list(stream)
        self.assertEqual(len(lines), len(PIN_RECORDS))
        return [
            (number, json.loads(line), line)
            for number, line in zip(PIN_RECORDS, lines)
        ]

    def _dispatch(self, policy, line):
        return _dispatch_response_lines(
            [line], policy, lambda *_a, **_k: None,
            knowledge_ledger_path=Path(self.temp.name) / "knowledge.jsonl",
        )

    def test_pin_p_public_replay_uses_selected_bfs_route(self):
        policy = self._policy()
        expected = {
            2856171: 10, 2856179: 9, 2856191: 8, 2856202: 7,
            2856214: 6, 2856607: 42, 2856615: 41, 2856625: 40,
            2856635: 39, 2856646: 38,
        }
        observed = []
        seen_turns = set()
        for number, raw, line in self._records():
            if raw.get("type") in {"knowledge", "look", "character"}:
                self._dispatch(policy, line)
                continue
            snapshot = parse_snapshot(raw, self.monrace)
            if number == 4:
                policy.prime(snapshot)
            key = policy.choose_key(snapshot)
            policy.confirm_key_posted(key)
            if policy.last_reason == "fixedquest:q22-travel":
                self.assertIsInstance(key, DecisionCandidate)
                declaration = key.route_declaration
                self.assertIsNotNone(declaration)
                if snapshot.turn not in seen_turns:
                    observed.append((snapshot.turn, declaration.bfs_rank))
                    seen_turns.add(snapshot.turn)
                    self.assertEqual(
                    policy._town_turn_arbiter.telemetry[
                        "budget_remaining_estimate"
                    ],
                    3,
                    )
                self.assertNotIn("quest-request", policy._town_turn_arbiter._retired)
        self.assertEqual(observed, list(expected.items()))

    def test_pin_w_equal_key_distinct_candidate_has_no_authority(self):
        policy = self._policy()
        records = self._records()
        priming = parse_snapshot(records[0][1], self.monrace)
        policy.prime(priming)
        initial = policy.choose_key(priming)
        policy.confirm_key_posted(initial)
        self._dispatch(policy, records[1][2])
        snapshot = parse_snapshot(records[2][1], self.monrace)
        key = policy.choose_key(snapshot)
        self.assertIsInstance(key, DecisionCandidate)
        collision = DecisionCandidate(
            str(key), reason=key.reason,
            decision_identity=key.decision_identity,
            route_declaration=key.route_declaration,
        )
        self.assertNotEqual(id(key), id(collision))
        self.assertTrue(policy._valid_q22_travel_declaration(snapshot, key, key.reason))
        self.assertFalse(
            policy._valid_q22_travel_declaration(snapshot, collision, collision.reason)
        )
        self.assertEqual(
            len(policy._town_arbiter_progress_vector(snapshot, collision.reason, collision)),
            8,
        )

    @staticmethod
    def _without_inn_metadata(raw):
        derived = copy.deepcopy(raw)
        grid_map = derived.get("grid_map") or {}
        for cell in grid_map.get("cells", []):
            if cell.get("b") == 4:
                cell.pop("b")
                cell.pop("p", None)
        return derived

    def test_pin_n_real_q22_producer_retires_and_recovers(self):
        policy = self._policy(maps=False)
        records = self._records()
        priming = self._without_inn_metadata(records[0][1])
        priming_snapshot = parse_snapshot(priming, self.monrace)
        policy.prime(priming_snapshot)
        initial = policy.choose_key(priming_snapshot)
        policy.confirm_key_posted(initial)
        response = records[1][1]
        self._dispatch(policy, json.dumps(response))
        board = self._without_inn_metadata(records[2][1])
        vectors = []
        budgets = []
        for offset in range(6):
            current = copy.deepcopy(board)
            current["turn"] += offset * 10
            snapshot = parse_snapshot(current, self.monrace)
            key = policy.choose_key(snapshot)
            policy.confirm_key_posted(key)
            vectors.append(policy._town_turn_arbiter._vector_by_owner.get("quest-request"))
            budgets.append(
                policy._town_turn_arbiter.telemetry["budget_remaining_estimate"]
            )
        self.assertTrue(all(vector == vectors[0] for vector in vectors[:4]))
        self.assertEqual(budgets[:4], [3, 2, 1, 0])
        self.assertEqual(policy.last_reason, "fixedquest:q22-travel:unsatisfiable")
        self.assertEqual(key, WAIT_KEY)
        restored = parse_snapshot(records[2][1], self.monrace)
        restored_key = policy.choose_key(restored)
        self.assertIsInstance(restored_key, DecisionCandidate)
        self.assertEqual(policy.last_reason, "fixedquest:q22-travel")


if __name__ == "__main__":
    unittest.main()
