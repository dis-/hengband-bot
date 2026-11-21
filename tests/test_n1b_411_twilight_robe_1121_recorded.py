"""No loadout search takes a NO_AC piece; a worn 宵闇のローブ is swapped out in town.

Owner 2026-11-21 (verbatim): 「99F 100Fでも宵闇のローブは禁止」 and 「AC0では打撃を受けると即死抽選が
ある。優先対処。」.  n1-b life-411 wore 宵闇のローブ [0,+10] (EgoDefinitions.jsonc TWILIGHT: every
resistance, NO_AC) on Angband 95F: the ordinary search had chosen it at 05:51 (band 81); only the
99F/100F search left NO_AC out.

Recorded: n1-b's town arrival of 2026-11-21 11:26:08 (tests/fixtures/n1b-411-twilight-robe-1121),
the robe worn; its first three decisions replayed (the skill list and the Home census read), then
the worn loadout's search run on the board the policy decided (``_map_predicate_snapshot``: the
visit's own equipment work runs it later, after a character dump the replay cannot answer).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.equipment_rules import TR_NO_AC
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-twilight-robe-1121"


class N1b411TwilightRobeRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, self.steps = load(FIXTURE, Path(self.scratch.name))

    def tearDown(self):
        self.policy._home_disposal.history_path.unlink(missing_ok=True)
        self.scratch.cleanup()

    def test_the_worn_robe_is_taken_off(self):
        policy = self.policy
        for recorded, supply in self.steps[:3]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
            policy.confirm_key_posted(key)
        robe = next(owned for owned in policy._equipment_catalog.items
                    if owned.origin == "equipped" and TR_NO_AC in owned.flags)
        with contextlib.redirect_stdout(io.StringIO()):
            preparation = policy._prepare_equipment_optimization(policy._map_predicate_snapshot)
        best = preparation.result.best
        self.assertEqual([item.id for _slot, item in best.loadout.slots if TR_NO_AC in item.flags], [])
        self.assertNotEqual(best.loadout.item_at("body").id, robe.id)
        # The swap takes the robe off (it is not kept for being worn).
        self.assertIn(robe.id, [action.item_id for action in preparation.transaction.actions
                                if action.kind in ("takeoff", "deposit")])


class TwilightRobeOrdinarySearchTest(unittest.TestCase):
    """The ordinary (not the 99F/100F) search leaves a NO_AC piece out too.

    Recorded: n1-c life-217's town visit of 2026-11-21 05:55:10 (tests/fixtures/n1c-finale-prep-1121),
    its first 30 decisions replayed.  DECLARED CONSTRUCTED: a robe of twilight carried, the worn body
    armour's row with AC 0, every resistance, resist curse, NO_AC and +10 blows (so that without the
    rule the ordinary search takes it); the 99F/100F phase stopped (the ordinary rank)."""

    def test_the_ordinary_search_leaves_the_robe(self):
        from dataclasses import replace

        from hengbot import finale_prep
        from hengbot.equipment_optimizer import ABILITY_FLAG
        TR_BLOWS = 13  # object/tr-types.h
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, _journal, steps = load(Path(__file__).with_name("fixtures") / "n1c-finale-prep-1121",
                                       Path(scratch.name))
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        held = finale_prep.phase(policy)
        robe = None
        for recorded, supply in steps[:30]:
            board = supply()
            if robe is None:
                worn = next(item for item in board.equipment if item.slot == "body")
                flags = frozenset(flag for name, flag in ABILITY_FLAG.items()
                                  if name.startswith("resist_")) | {TR_NO_AC, 148, TR_BLOWS}
                robe = replace(worn, slot=chr(ord("a") + len(board.inventory)), name="宵闇のローブ",
                               ac=0, to_a=0, pval=10, known_flags=frozenset(worn.known_flags) | flags)
            board = replace(board, inventory=(*board.inventory, robe))
            held.in_town, held.step, held.stopped = True, finale_prep.STOPPED, "declared"
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(board)
            policy.confirm_key_posted(recorded["key"])
        with contextlib.redirect_stdout(io.StringIO()):
            preparation = policy._prepare_equipment_optimization(policy._map_predicate_snapshot)
        self.assertFalse(finale_prep.dedicated_order(policy))
        best = preparation.result.best
        self.assertEqual([item.item.name for _slot, item in best.loadout.slots
                          if TR_NO_AC in item.flags], [])


if __name__ == "__main__":
    unittest.main()
