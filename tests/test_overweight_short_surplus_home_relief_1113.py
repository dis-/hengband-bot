"""Town rebuild stage 3-3d: a short carried surplus hands the weight back to Home's relief.

n1-c life-205 2026-11-13 18:07 (town:blocked:overweight-home-full-no-legal-relief):
the surplus disposal state was set while the carried surplus cleared the excess;
on a later board it no longer did, and _overweight_surplus_sale_key stopped the
town although the weight relief's route was home-relief (its restart took that
relief and recovered).  The departure rescue of inventory_weight_ready is that
same function, so the leaf had no rescue (owner 2026-11-12 「落ちた葉には必ず
救済の手」).  The 18:07 board no longer reproduces on main (the item-use-route
table adds carried surplus), so these pins use the Step 1.5b Home-full capture.

DECLARED CONSTRUCTED: the recorded 2026-10-08 17:54 Home-full flow (the same
rows and census as test_overweight_homefull_step15b pin 1) runs through the
public choose_key until the disposal state is set; then the first equipment
slot's weight is raised (+60: the excess 29 -> 89 exceeds the carried surplus 77
but not the Home deposits; +5000: nothing clears it).  The weight change stands
for an item entering the worn set (the 18:07 hypothesis, the 250-weight axe of an
equipment transaction); no selector, retention or departure gate is replaced.
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
from tests.support.recorded import EDIT, _policy
from test_equipment_homefull_step15a import post
from test_overweight_homefull_step15b import CAPTURES

STOP = "town:blocked:overweight-home-full-no-legal-relief"


class ShortSurplusHomeReliefTest(unittest.TestCase):
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

    def disposal_after_recorded_relief(self):
        """The recorded rows up to the Home-full relief that sets the disposal."""
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
        self.assertIsNotNone(policy._overweight_surplus_disposal)
        self.assertEqual(policy._weight_relief_selection(home).route, 'sell-or-destroy')
        return policy, home

    @staticmethod
    def heavier(board, extra):
        return replace(board, equipment=tuple(
            replace(item, weight=item.weight + (extra if index == 0 else 0))
            for index, item in enumerate(board.equipment)))

    def test_short_surplus_with_home_relief_open_does_not_stop(self):
        policy, home = self.disposal_after_recorded_relief()
        heavy = self.heavier(home, 60)
        relief = policy._weight_relief_selection(heavy)
        self.assertEqual(relief.route, 'home-relief')
        self.assertLess(sum(i.weight * n for _, _, i, n, _ in relief.surplus), relief.excess)
        key = policy.choose_key(heavy)
        self.assertNotEqual(policy.last_reason, STOP)
        self.assertFalse(policy.last_reason.startswith('town:blocked:'), (key, policy.last_reason))
        self.assertIsNone(policy._overweight_surplus_disposal)
        self.assertIsNone(policy._town_blocked_reason)

    def test_excess_nothing_clears_keeps_the_named_stop(self):
        policy, home = self.disposal_after_recorded_relief()
        heavy = self.heavier(home, 5000)
        self.assertEqual(policy._weight_relief_selection(heavy).route, 'home-relief')
        policy._overweight_surplus_sale_key(heavy)
        self.assertEqual(policy.last_reason, STOP)
        self.assertIsNotNone(policy._overweight_surplus_disposal)


if __name__ == '__main__':
    unittest.main()
