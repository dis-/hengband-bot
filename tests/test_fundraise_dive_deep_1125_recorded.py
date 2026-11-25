"""The one fundraising gate: from a recall depth of 50F the gold comes from a dive (owner 2026-11-25).

Owner 2026-11-25, the answer to 「決戦以外の資金集めでも、深いキャラは1F採掘をやめて潜って稼ぎますか？」
(verbatim): 「帰還の深さ50F以上なら潜る」 (fundraising_route ``dives`` / ``open_set``).  A character
whose recall depth is 50F or deeper opens no Yeek cave 1F mining set for an errand's gold (the
Magic-Eater's staffs, the Q2 Tower recharge, the Zul trip, the plain poverty of a town board):
the errand yields its board, the ordinary departure dives.  A shallower character mines as
before.  What the departure itself lacks (``DEPARTURE_CAUSES``) keeps the set: no dive can leave.

Recorded:
- deep: n1-c life-222 (Magic-Eater Lv49, recall depths Angband 95 / Castle 64), the board of
  2026-11-25 20:10:50 (tests/fixtures/n1c-222-finale-funds-dive-1125.json.gz, the precedent's
  fixture, tests/extract_n1c_222_finale_funds_dive_1125_fixture.py) and the same life's absorbed
  power lists;
- shallow: the 2026-10-02 character that mined the Yeek cave 1F five times and started the next
  poverty set at 1,264 gold (tests/fixtures/fundraising-set-end-counter-20261002.jsonl.gz, row 5,
  test_fundraising_set_end_counter_recorded).

DECLARED CONSTRUCTED: the deep board's gold lowered to 1,000 for the poverty set (it held 42,504);
the deep board's recall depths lowered to 49 and the shallow one's raised to 50 at the boundary
(``test_the_boundary_is_50f``); the errands' owners are asked at their gold step (the private
``_fundraise`` of me_staff_sequence, q2_tower_recharge and zul_trip, the one place each opens its
run) with a fresh record.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import gzip
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import fundraising_route, me_staff_sequence, q2_tower_recharge, zul_trip
from hengbot.cli import _consume_response_sequence
from hengbot.me_device_attacks import observe_lists
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
with gzip.open(FIXTURES / "n1c-222-finale-funds-dive-1125.json.gz", "rt", encoding="utf-8") as _stream:
    DEEP = json.load(_stream)
LISTS = json.loads((FIXTURES / "n1c-222-me-lists-1125.json").read_text(encoding="utf-8"))["lists"]
with gzip.open(FIXTURES / "fundraising-set-end-counter-20261002.jsonl.gz", "rt",
               encoding="utf-8") as _stream:
    SHALLOW_ROWS = [json.loads(line) for line in _stream]
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")


class FundraiseDiveDeep1125RecordedTest(unittest.TestCase):
    def deep(self, *, gold=None, depth=None):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        raw = copy.deepcopy(DEEP)
        if gold is not None:
            raw["player"]["gold"] = gold  # DECLARED CONSTRUCTED (module docstring)
        if depth is not None:
            raw["progress"]["dungeon_recall_depths"] = {
                key: min(int(value), depth)
                for key, value in raw["progress"]["dungeon_recall_depths"].items()}
            raw["progress"]["recall_depth"] = min(int(raw["progress"]["recall_depth"]), depth)
        policy = _policy(Path(scratch.name), MONRACE)
        board = parse_snapshot(copy.deepcopy(raw), MONRACE)
        policy.prime(board)
        for kind in ("staff", "wand", "rod"):
            listed = dict(copy.deepcopy(raw), turn=raw["turn"] - 1,
                          _magic_eater_power_list={"kind": kind, "rows": LISTS[kind]})
            observe_lists(policy, parse_snapshot(listed, MONRACE))
        with contextlib.redirect_stdout(io.StringIO()):
            policy.choose_key(board)
        return policy, board

    def shallow(self, *, depth=None):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy = _policy(Path(scratch.name), MONRACE)
        line = SHALLOW_ROWS[5]["line"]
        if depth is not None:
            raw = json.loads(line)
            # DECLARED CONSTRUCTED (module docstring): the boundary's recall depth.
            raw["progress"]["dungeon_recall_depths"] = {"1": depth}
            line = json.dumps(raw)
        _decoded, boards = _consume_response_sequence(
            [line], policy, lambda _key: True, MONRACE,
            knowledge_ledger_path=Path(scratch.name) / "knowledge.jsonl")
        return policy, boards[-1]

    def test_the_recorded_depths(self):
        _policy_deep, deep = self.deep()
        self.assertEqual(fundraising_route.recall_depth(deep), 95)
        _policy_shallow, shallow = self.shallow()
        self.assertEqual(shallow.player.gold, 1264)
        self.assertLess(fundraising_route.recall_depth(shallow), fundraising_route.DIVE_RECALL_DEPTH)

    def test_a_deep_poverty_set_is_the_dive(self):
        policy, board = self.deep(gold=1000)
        self.assertIsNone(policy._fundraising_mode)

        self.assertFalse(policy._start_fundraising(board, fundraising_route.POVERTY))

        # Before: the poverty set opened (fundraising mode 'prepare', the Yeek cave 1F).
        self.assertIsNone(policy._fundraising_mode)
        self.assertIsNone(policy._planned_mining_runs)

    def test_a_shallow_poverty_set_still_mines(self):
        policy, board = self.shallow()

        self.assertTrue(policy._start_fundraising(board, fundraising_route.POVERTY))

        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_the_departure_s_own_lack_keeps_the_set(self):
        # No dive leaves town while the departure itself is short (an open question to the owner).
        policy, board = self.deep(gold=1000)

        self.assertTrue(policy._start_fundraising(board, fundraising_route.DEPARTURE_SHORTAGE))

        self.assertEqual(policy._fundraising_mode, "prepare")

    def test_deep_errands_yield_to_the_dive(self):
        policy, board = self.deep()
        target = board.player.gold + 1

        staff = me_staff_sequence._fundraise(policy, board, target, "staffs")
        tower = q2_tower_recharge._fundraise(policy, board, target, "travel-recharge")
        zul = zul_trip._fundraise(policy, board, zul_trip.ZulTrip(), target)

        # Before: each opened one fundraising run to ``target`` (WAIT, mode 'prepare').
        self.assertEqual((staff, tower, zul), (None, None, None))
        self.assertIsNone(policy._fundraising_mode)
        self.assertIsNone(getattr(policy, "_supply_stockout_gold_target", None))
        self.assertEqual(me_staff_sequence.state(policy).fundraise_runs, 0)
        self.assertEqual(q2_tower_recharge.state(policy).fundraise_runs, 0)

    def test_a_shallow_errand_still_opens_its_run(self):
        policy, board = self.shallow()
        record = zul_trip.ZulTrip()
        target = board.player.gold + 1

        key = zul_trip._fundraise(policy, board, record, target)

        self.assertTrue(key)
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(policy._supply_stockout_gold_target, target)
        self.assertEqual(record.fundraise_runs, 1)

    def test_the_boundary_is_50f(self):
        _policy_deep, at_49 = self.deep(depth=49)
        self.assertFalse(fundraising_route.dives(_policy_deep, at_49, fundraising_route.ZUL_TRIP))
        policy, at_50 = self.shallow(depth=50)
        self.assertTrue(fundraising_route.dives(policy, at_50, fundraising_route.ZUL_TRIP))
        self.assertFalse(fundraising_route.dives(policy, at_50, fundraising_route.RECALL_STOCKOUT))


if __name__ == "__main__":
    unittest.main()
