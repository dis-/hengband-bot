"""Town rebuild stage 3-3d: a short carried surplus hands the weight back to Home's relief.

n1-c life-205 2026-11-13 18:07 (town:blocked:overweight-home-full-no-legal-relief):
the surplus disposal state was set while the carried surplus cleared the excess;
on a later board it no longer did, and _overweight_surplus_sale_key stopped the
town although the weight relief's route was home-relief (its restart, with no
disposal state, took that relief and recovered).  The departure rescue of
inventory_weight_ready is that same function, so the leaf had no rescue (owner
2026-11-12 「落ちた葉には必ず救済の手」).

Recorded: the incident capture's town-arrival checkpoint, journal rows 0-10 and
sidecar files (tests/extract_n1c_205_overweight_short_1113_fixture.py).  Rows 0-5
replay through the public choose_key; current code leaves the record at row 6
(the item-use-route table changed the Home deposit), so rows 6-9 are supplied
(their recorded inputs consumed) without deciding, and row 10 is the board outside
Home on which the recorded bot stopped.

DECLARED CONSTRUCTED: on that board the carried surplus clears the excess on
current code (item-use-route adds carried surplus), so the first worn slot's
weight is raised by 380 (the excess 140 -> 520 exceeds the carried surplus, not
the Home deposits; the 18:07 hypothesis is an item entering the worn set), and
the disposal state is the one the need router sets
(policy_town._town_need_candidates: {"town": ...}).

The second pin is the Step 1.5b Home-full capture (as its pin 1, through the public
choose_key): there Home's own relief gives up and sets the disposal itself; a
heavier board (DECLARED CONSTRUCTED +60 on the first worn slot) must keep the
named stop rather than hand back to the relief that gave up.
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import tests  # noqa: F401
from hengbot.cli import _consume_response_sequence
from hengbot.model import _parse_items, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from support.town_arrival_fixture import load
from tests.support.recorded import EDIT, _policy
from test_equipment_homefull_step15a import post
from test_overweight_homefull_step15b import CAPTURES

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-205-overweight-short-1113" / "i1807"
REPLAYED_ROWS = 6
STOP_ROW = 10
STOP = "town:blocked:overweight-home-full-no-legal-relief"


def heavier(board, extra):
    return replace(board, equipment=tuple(
        replace(item, weight=item.weight + (extra if index == 0 else 0))
        for index, item in enumerate(board.equipment)))


class N1c205ShortSurplusRecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, self.recorded, self.steps = load(FIXTURE, Path(scratch.name))

    def stop_board(self):
        policy = self.policy
        for row, supply in self.steps[:REPLAYED_ROWS]:
            board = supply()
            key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason), (row["key"], row["reason"]), row["row"])
            if key:
                policy.confirm_key_posted(key)
        for _, supply in self.steps[REPLAYED_ROWS:STOP_ROW]:
            supply()
        return self.steps[STOP_ROW][1]()

    def test_short_surplus_hands_the_weight_back_to_home_relief(self):
        self.assertEqual(self.recorded[STOP_ROW]["reason"], STOP)
        board = self.stop_board()
        policy = self.policy
        self.assertIsNone(board.store)
        self.assertEqual((policy._inventory_weight(board), policy._inventory_weight_limit(board)),
                         (1990, 1850))
        heavy = heavier(board, 380)
        relief = policy._weight_relief_selection(heavy)
        self.assertEqual(relief.route, "home-relief")
        self.assertLess(sum(i.weight * n for _, _, i, n, _ in relief.surplus), relief.excess)
        self.assertTrue(policy._home_knowledge_current)
        policy._overweight_surplus_disposal = {"town": policy._effective_town_id(heavy)}

        key = policy._overweight_surplus_sale_key(heavy)

        self.assertIsNone(key)
        self.assertNotEqual(policy.last_reason, STOP)
        self.assertIsNone(policy._overweight_surplus_disposal)
        self.assertIsNone(policy._town_blocked_reason)


class ExhaustedHomeReliefKeepsTheStopTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / 'MonraceDefinitions.jsonc')

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.env = patch.dict('os.environ', {'HENGBOT_RUNTIME_DIR': str(self.directory)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_a_relief_that_gave_up_is_not_handed_the_weight_again(self):
        rows = CAPTURES['20261008-175411']['bot-state-fixed']['rows']
        board = parse_snapshot(rows[54], self.monrace)
        policy = _policy(self.directory, self.monrace)
        policy.prime(board)
        ledger = self.directory / 'knowledge.jsonl'
        _consume_response_sequence([json.dumps(r) for r in rows[51:55]], policy,
                                   lambda _: True, self.monrace, knowledge_ledger_path=ledger)
        for r in rows[51:55]:
            if r.get('knowledge', {}).get('category') == 'skill_exp':
                policy.consume_skill_knowledge(r)
        post(policy, policy.choose_key(board))
        _consume_response_sequence([json.dumps(r) for r in rows[55:57]], policy,
                                   lambda _: True, self.monrace, knowledge_ledger_path=ledger)
        home = parse_snapshot(rows[56], self.monrace)
        post(policy, policy.choose_key(home))
        # The Home census returned to the relief scan (as Step 1.5b pin 1).
        row = next(r for r in reversed(rows) if r.get('knowledge', {}).get('category') == 'home')
        policy.consume_home_knowledge(tuple(_parse_items(row['knowledge']['items'], protocol=3)))
        policy._home_full_relief_key(home)
        self.assertIsNone(policy._home_full_relief)
        self.assertTrue(policy._overweight_surplus_disposal.get('home_relief_exhausted'))

        heavy = heavier(home, 60)
        self.assertEqual(policy._weight_relief_selection(heavy).route, 'home-relief')
        policy._overweight_surplus_sale_key(heavy)

        self.assertEqual(policy.last_reason, STOP)
        self.assertIsNotNone(policy._overweight_surplus_disposal)


if __name__ == '__main__':
    unittest.main()
