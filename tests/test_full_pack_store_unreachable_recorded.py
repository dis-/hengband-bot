"""A full pack and a full Home must not wait on a stale grid index (issue #73).

Recorded inputs:

* ``recall-full-pack-store-unreachable-20261019.jsonl.gz`` (C4-A life-013,
  Level 29, bot 45f0bdc1): line 0 is the last dungeon board (Orc cave 23F,
  recall pending), line 1 the first town board after the recall, the pack
  23/23 at (37,105) beside the Magic shop entrance (38,106).  Live, decisions
  22017-22024 were ``town:blocked:home-full-surplus-store-unreachable`` and
  22025 ``town:blocked:owner-retired-burst``.
* ``home-junk-bones-20261018.jsonl.gz``: the full Home of the same life
  (capture 164159), shared with the #70 pins.

DECLARED CONSTRUCTED: the Home contents are the 10-18 census of the same life
(the 10-19 capture holds only its count, 240/240); the Home capacity
observation (240, 240, town 0); the relief's blocked deposit (the spear, slot
u), since the live relief began before this capture.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import STORE_MAGIC, Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
CAPTURE = FIXTURES / "recall-full-pack-store-unreachable-20261019.jsonl.gz"
BOUNDARIES = FIXTURES / "recall-full-pack-store-unreachable-20261019.boundaries.json"
HOME = FIXTURES / "home-junk-bones-20261018.jsonl.gz"
MAGIC_ENTRANCE = Position(38, 106)


class FullPackStoreUnreachableRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines = gzip.decompress(CAPTURE.read_bytes()).decode("utf-8").splitlines()
        with gzip.open(HOME, "rt", encoding="utf-8") as stream:
            cls.home_lines = stream.read().splitlines()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def _consume(self, policy, line):
        _decoded, snapshots = _consume_response_sequence(
            [line], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        return snapshots

    def _home_census(self, policy):
        # DECLARED CONSTRUCTED: the 10-18 Home census of the same life, with
        # the posted ~9 request whose answer is its line 1 (as in the #70 pin).
        self._consume(policy, self.home_lines[0])
        policy._home_knowledge_scan_inflight = True
        policy._home_knowledge_scan_epoch = None
        self._consume(policy, self.home_lines[1])
        self._consume(policy, self.home_lines[2])

    def _arrival(self):
        policy = _policy(self.directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        self._home_census(policy)
        dungeon = self._consume(policy, self.lines[0])[-1]
        policy._skill_exp_cache = (0, 0, dungeon.player.level, policy._town_visit_epoch)
        policy.choose_key(dungeon)
        self.assertEqual(policy.last_reason, "return:wait-recall")
        board = self._consume(policy, self.lines[1])[-1]
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        # DECLARED CONSTRUCTED: the full-Home fact and the blocked deposit.
        policy._home_capacity_observation = (240, 240, 0)
        spear = next(item for item in board.inventory if item.slot == "u")
        policy._begin_home_full_relief(
            board, ((policy._item_signature(spear), 1, 1),), refused=True)
        return policy, board

    def test_recorded_first_town_board(self):
        data = gzip.decompress(CAPTURE.read_bytes())
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         json.loads(BOUNDARIES.read_text(encoding="utf-8"))["board_sha256"])
        policy, board = self._arrival()
        self.assertTrue(board.in_town)
        self.assertEqual(len(board.inventory), 23)
        self.assertEqual(board.player.position, Position(37, 105))
        self.assertEqual(board.grid_at(MAGIC_ENTRANCE).store_number, STORE_MAGIC)
        self.assertTrue(policy._home_is_full(board))

    def test_full_pack_relief_walks_to_the_adjacent_store(self):
        policy, board = self._arrival()
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "shop:approach")
        self.assertEqual(key, "3")
        self.assertNotEqual(policy._town_blocked_reason,
                            "home-full-surplus-store-unreachable")
        signature, store_type, _before = policy._home_full_relief["sale"]
        self.assertEqual(store_type, STORE_MAGIC)
        self.assertEqual(signature[1:], (55, 5))
        self.assertTrue(policy._home_full_relief["pack_only"])

    def test_control_items_inside_their_targets_are_not_chosen(self):
        policy, board = self._arrival()
        policy.choose_key(board)
        signature = policy._home_full_relief["sale"][0]
        reserved = {policy._item_signature(item) for item in board.inventory
                    if policy._retention_reservation(board, item) > 0}
        self.assertTrue(reserved)
        self.assertNotIn(signature, reserved)
        chosen = next(item for item in board.inventory
                      if policy._item_signature(item) == signature)
        self.assertEqual(policy._retention_reservation(board, chosen), 0)


if __name__ == "__main__":
    unittest.main()
