"""Worthless remains must not fill the Home (issue #70).

Recorded inputs:

* ``lantern-lost-20261018.jsonl.gz`` line 0 (C4-A life-013, Yeek cave level 1,
  turn 656632): the return-start board.  The pack carries seven recorded junk
  stacks (slots q-w: three corpses, a broken stick, three skeletons) and the
  floor shows recorded corpse (tval 10) and bolt (tval 18) piles.
* ``home-junk-bones-20261018.jsonl.gz``: the full Home of capture 164159.
* ``fundraise-junk-pile-20261018.jsonl.gz``: capture 234158 (loop-detected),
  the fundraising board beside a pottery-shard (tval 3) pile.

DECLARED CONSTRUCTED: the worn lantern fuel above the refill threshold (as in
the existing lantern control), one floor pile shown as a skeleton (tval 1)
instead of its recorded bolts, the pack without its junk for the loot pins,
bounty flags in the bounty control, the ~9 flag and blocked deposit of the
full-Home pin, and the fundraising mode of the fundraising pin.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import LANTERN_REFILL_FUEL
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
DUNGEON = FIXTURES / "lantern-lost-20261018.jsonl.gz"
HOME = FIXTURES / "home-junk-bones-20261018.jsonl.gz"
HOME_BOUNDARIES = FIXTURES / "home-junk-bones-20261018.boundaries.json"
BOLT_PILE = Position(11, 59)
RECORDED_CORPSE_PILE = Position(10, 62)
FUNDRAISE = FIXTURES / "fundraise-junk-pile-20261018.jsonl.gz"
JUNK_PILE = Position(16, 48)


class HomeJunkBonesRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(DUNGEON, "rt", encoding="utf-8") as stream:
            cls.dungeon_lines = stream.read().splitlines()
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

    def _dungeon(self):
        policy = _policy(self.directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        board = self._consume(policy, self.dungeon_lines[0])[-1]
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        # DECLARED CONSTRUCTED: lantern fuel above the refill threshold, so the
        # recorded empty-lantern refill does not take this decision.
        board = replace(board, equipment=type(board.equipment)(
            replace(item, fuel=LANTERN_REFILL_FUEL + 1) if item.is_light else item
            for item in board.equipment))
        return policy, board

    def _without_carried_junk(self, board):
        # DECLARED CONSTRUCTED: the pack without its recorded junk stacks.
        return replace(board, inventory=type(board.inventory)(
            item for item in board.inventory if item.tval not in {1, 3, 10}))

    def test_recorded_board_carries_junk_at_return_start(self):
        policy, board = self._dungeon()
        carried = {item.slot: item.tval for item in board.inventory
                   if item.tval in {1, 3, 10}}
        self.assertEqual(carried, {"q": 10, "r": 10, "s": 10, "t": 3,
                                   "u": 1, "v": 1, "w": 1})
        self.assertEqual(board.grids[BOLT_PILE].object_tvals, (18,))
        self.assertEqual(board.grids[RECORDED_CORPSE_PILE].object_tvals, (10,))
        self.assertTrue(policy._should_start_town_return(board))

    def test_return_start_destroys_carried_remains_first(self):
        policy, board = self._dungeon()
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "inventory:destroy-worthless-junk")
        self.assertTrue(key.endswith("kq"), key)

    def test_control_bounty_remains_are_kept(self):
        policy, board = self._dungeon()
        board = replace(board, inventory=type(board.inventory)(
            replace(item, is_bounty=True) if item.tval in {1, 3, 10} else item
            for item in board.inventory))
        policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "inventory:destroy-worthless-junk")

    def test_floor_skeleton_pile_is_not_sought_or_picked_up(self):
        policy, board = self._dungeon()
        board = self._without_carried_junk(board)
        # DECLARED CONSTRUCTED: the adjacent recorded bolt pile shows a skeleton.
        skeleton = replace(board.grids[BOLT_PILE], object_tvals=(1,))
        junk_board = replace(board, grids={**board.grids, BOLT_PILE: skeleton})
        policy.choose_key(junk_board)
        policy._loot_target = None
        policy._loot_step(junk_board)
        self.assertNotEqual(policy._loot_target, BOLT_PILE)
        self.assertNotIn(BOLT_PILE, policy._known_loot)
        underfoot = replace(junk_board, grids={
            **junk_board.grids,
            board.player.position: replace(skeleton, position=board.player.position)})
        policy._position_changed = True
        self.assertIsNone(policy._current_floor_item_key(
            underfoot, pickup_reason="pickup", trigger_reason="trigger-autodestroy"))

    def test_fundraising_loot_does_not_target_the_recorded_junk_pile(self):
        # Soak 2026-10-18 23:41 (loop-detected): fundraise:seek-loot walked
        # onto the pottery-shard pile (16,48), the pickup refused it and
        # seek-treasure walked back, until the loop detector stopped the run.
        with gzip.open(FUNDRAISE, "rt", encoding="utf-8") as stream:
            line = stream.read().splitlines()[0]
        policy = _policy(self.directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        board = self._consume(policy, line)[-1]
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        self.assertEqual(board.player.position, Position(15, 47))
        self.assertEqual(board.grids[JUNK_PILE].object_tvals, (3,))
        # DECLARED CONSTRUCTED: the recorded fundraising mode (telemetry "mine").
        policy._fundraising_mode = "mine"
        policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "fundraise:seek-loot")
        # The fundraising loot selector (the live fundraise:seek-loot step).
        policy._loot_target = None
        policy._loot_step(board, include_unsafe=True)
        self.assertNotEqual(policy._loot_target, JUNK_PILE)

    def test_control_recorded_bolt_pile_is_still_sought_and_picked_up(self):
        policy, board = self._dungeon()
        board = self._without_carried_junk(board)
        policy.choose_key(board)
        policy._loot_target = None
        policy._loot_step(board)
        self.assertEqual(policy._loot_target, BOLT_PILE)
        underfoot = replace(board, grids={
            **board.grids,
            board.player.position: replace(board.grids[BOLT_PILE],
                                           position=board.player.position)})
        policy._position_changed = True
        self.assertEqual(policy._current_floor_item_key(
            underfoot, pickup_reason="pickup", trigger_reason="trigger-autodestroy"), "g")


    def test_full_home_destroys_remains_before_any_sale(self):
        with gzip.open(HOME, "rt", encoding="utf-8") as stream:
            home_lines = stream.read().splitlines()
        self.assertEqual(hashlib.sha256(gzip.decompress(HOME.read_bytes())).hexdigest(),
                         json.loads(HOME_BOUNDARIES.read_text(encoding="utf-8"))["board_sha256"])
        policy = _policy(self.directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        board = self._consume(policy, home_lines[0])[-1]
        # DECLARED CONSTRUCTED: the posted ~9 request whose answer is line 1.
        policy._home_knowledge_scan_inflight = True
        policy._home_knowledge_scan_epoch = None
        self._consume(policy, home_lines[1])
        board = self._consume(policy, home_lines[2])[-1]
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        self.assertEqual((board.store.stock_num, board.store.capacity), (240, 240))
        self.assertEqual(sum(item.tval == 10 for item in policy._home_knowledge_items), 100)
        self.assertTrue(policy._home_is_full(board))
        # DECLARED CONSTRUCTED: the relief's blocked deposit (the bolt stack).
        bolts = board.inventory[-1]
        policy._begin_home_full_relief(board, (
            (policy._item_signature(bolts), bolts.count, bolts.count),), refused=True)
        policy._home_full_relief_key(board)
        relief = policy._home_full_relief
        self.assertEqual(relief["mode"], "destroy")
        signature, store_type, _before = relief["sale"]
        self.assertIn(signature[1], {1, 3, 10})
        self.assertEqual(policy._home_errand.request.purpose, "full-home-discard")


if __name__ == "__main__":
    unittest.main()
