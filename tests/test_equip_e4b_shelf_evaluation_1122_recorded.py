"""Equipment review E4b: a shelf piece is an upgrade when the whole loadout improves with it.

Owner answers of the equipment review 2026-11-22 (verbatim):

* Q5 「自宅に同じ能力の品があれば取り出して使い店では買わない。店の品が装備の評価で上なら買い替えとして
  買ってよい」;
* on the E4 report's question 1: 「組全体の評価で比べる」 -- the exception runs the gear search with the
  shelf piece added to the owned set, any slot against any slot, and buys only when the chosen
  loadout wears it (policy_equipment ``_shelf_candidate_worn``).  Evaluating a shelf piece decides
  nothing again (equipment review E3): the visit's target and the search memo stay.

Recorded: n1-c life-218's town visit of 2026-11-21 21:00:41
(tests/fixtures/n1c-218-chaos-home-1121), replayed through ``choose_key`` (recorded keys posted)
to the visit's first search (row 5): its target wields the Home's (混沌)ヘヴィ・フレイル for the
Mountain's 49 (its only resist_chaos sets hold a weapon of less than half the ★Pike's melee); the
worn kit still lacks resist_chaos.

DECLARED CONSTRUCTED:

* the shelf rows (no shelf of that visit carried resist_chaos), made as store rows from the Home
  census's flail row: a Ring of Resist Chaos (another slot than the flail: with it the ★Pike's set
  meets band 49), and the flail made ten points of to-hit and to-dam worse (the same kind, worse);
  their price is 1 gold so the survival reserve admits them;
* the row-1 character dump, written again after the posted dump as test_n1c_218_chaos_home_1121
  does (the game writes it; the journal does not hold it).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import fields, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from hengbot import ability_gear, ability_sources, equipment_target
from hengbot.model import StoreItem
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-218-chaos-home-1121"
SEARCH_ROW = 5
TR_RES_CHAOS = 62
TVAL_RING = 45
FLAIL = "(混沌)ヘヴィ・フレイル"


class ShelfEvaluationRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()):
            policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name))
        dump = Path(policy._character_dump_path).read_bytes()
        for recorded, supply in steps[:SEARCH_ROW + 1]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(board)
            posted = recorded["key"]
            if posted:
                policy.confirm_key_posted(posted)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, posted):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": posted})
            if recorded["reason"] == "periodic:character-dump":
                # DECLARED CONSTRUCTED (module docstring): the game writes the dump.
                Path(policy._character_dump_path).write_bytes(dump)
        cls.policy, cls.board = policy, board
        census = next(item for item in policy._home_knowledge_items if item.name.startswith(FLAIL))
        common = {field.name for field in fields(StoreItem)} - {"letter", "price", "exported_fields"}
        shelf = StoreItem(letter="a", price=1, **{name: getattr(census, name) for name in common})
        # DECLARED CONSTRUCTED (module docstring): the two shelf rows.
        cls.ring = replace(shelf, name="耐混沌の指輪", tval=TVAL_RING, sval=1,
                           known_flags=frozenset({TR_RES_CHAOS}), damage_dice_num=0,
                           damage_dice_sides=0, to_h=0, to_d=0, weight=1, count=1,
                           is_ego=False, is_artifact=False, pval=0)
        cls.worse_flail = replace(shelf, letter="b", to_h=shelf.to_h - 10, to_d=shelf.to_d - 10,
                                  count=1)

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def rows(self, *items):
        flags = ability_gear._open_flags(self.policy, self.board)
        return ability_gear._rows(self.policy, self.board, SimpleNamespace(items=list(items)), flags)

    def target(self):
        result = equipment_target.loadout_target_result(self.policy)
        return (sorted(result.best.loadout.item_ids),
                equipment_target.loadout_search_signature(self.policy))

    def test_the_target_wears_the_home_flail_and_the_worn_kit_lacks_resist_chaos(self):
        policy, board = self.policy, self.board
        main_hand = dict(equipment_target.loadout_target_result(policy).best.loadout.slots)["main_hand"]
        self.assertEqual(main_hand.origin, "home")
        self.assertTrue(main_hand.item.name.startswith(FLAIL))
        self.assertIn("resist_chaos", ability_gear._landing_missing(policy, board))
        self.assertIn(TR_RES_CHAOS, ability_gear._open_flags(policy, board))
        self.assertTrue(ability_sources.owned_unworn_sources(policy, "resist_chaos"))

    def test_a_ring_of_another_slot_improving_the_whole_set_is_bought(self):
        before = self.target()
        self.assertTrue(self.policy._shelf_candidate_worn(self.board, self.ring))
        self.assertEqual(self.rows(self.ring), [self.ring])
        # Evaluating it decided nothing again (E3): the visit's target and memo are the same.
        self.assertEqual(self.target(), before)

    def test_a_worse_flail_is_not_bought_while_the_home_flail_gives_it(self):
        self.assertFalse(self.policy._shelf_candidate_worn(self.board, self.worse_flail))
        self.assertEqual(self.rows(self.worse_flail), [])
        # With no owned source the gap is closed by it as before E4.
        with mock.patch.object(ability_sources, "owned_unworn_sources", lambda *_args: []):
            self.assertEqual(self.rows(self.worse_flail), [self.worse_flail])


if __name__ == "__main__":
    unittest.main()
