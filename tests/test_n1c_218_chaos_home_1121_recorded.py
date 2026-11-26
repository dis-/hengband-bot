"""n1-c life-218: the only resist_chaos set was in Home and the town mined for the 49F gate.

Owner 2026-11-21 (verbatim): 「唯一のカオス耐性を自宅に仕舞い込んで勝手に持っていない判定にした経緯を
解析」 (destination_band_floor's docstring has the history).  Equipment review 2026-11-22, stage E4
(owner answers, verbatim choices):

* Q4 「深さの条件を満たす組があれば打撃が半分を下回っても着て行く。打撃の半分の決まりは条件を満たす組が
  複数ある時の選び方だけ」: the town's search knows the destination; its band is the descent's floor;
* Q3 「自宅・荷物にあれば持っている物として数え、行き先に要るなら着けて行く」: the town's destination
  gates count a Home piece the visit's target wears (ability_sources ``OWNED``); the worn kit's
  readers (the departure on the worn loadout) still read what is worn.

Recorded: n1-c's town visit of 2026-11-21 21:00:41 (tests/fixtures/n1c-218-chaos-home-1121, 37
journal rows).  Its arrival descent refused band 49 by the half-melee limit (the ★Pike's 238
against the (混沌)ヘヴィ・フレイル set's 92) and adopted band 30; row 24 opened
``fundraising:no-safe-destination:depth-gate:destination-49:missing-resist_chaos``.  Replayed
through ``choose_key`` with the recorded keys posted: the visit's first search (row 5) takes band
49 as the destination's band, its target wields the Home flail and its transaction withdraws it;
no row opens the fundraising; the destination gate counts the flail while the worn kit lacks
resist_chaos, so the departure on the worn loadout is refused until it is worn.

DECLARED CONSTRUCTED: the game wrote the row-1 character dump to the dump file, which the journal
does not hold; the sidecar copy of the dump (the same character, taken at the arrival) is written
again after the posted dump (as test_n1b_397_50f_gate_1114_recorded).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import destination_band_floor, equipment_target
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-218-chaos-home-1121"
SEARCH_ROW = 5
GATE_ROW = 24
DESTINATION = 49
FLAIL = "(混沌)ヘヴィ・フレイル"


class ChaosHomeRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name))
        dump = Path(policy._character_dump_path).read_bytes()
        cls.arrival_bands = [
            (decision.band, decision.refusal_reason)
            for decision in policy._equipment_optimization_preparation.result.band_decisions]
        cls.decided = []
        cls.search = None
        for recorded, supply in steps[:GATE_ROW + 1]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            cls.decided.append((recorded, key, policy.last_reason))
            if int(recorded["row"]) == SEARCH_ROW:
                cls.search = equipment_target.loadout_target(policy)
            posted = recorded["key"]
            if posted:
                policy.confirm_key_posted(posted)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, posted):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": posted})
            if recorded["reason"] == "periodic:character-dump":
                # DECLARED CONSTRUCTED (module docstring): the game writes the dump.
                Path(policy._character_dump_path).write_bytes(dump)
        cls.policy = policy
        cls.board = board

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_arrival_descent_refused_band_49_by_melee_alone(self):
        # The pickled arrival state: the search of the record, before E4.
        self.assertEqual(self.arrival_bands, [
            (81, "no-set"), (80, "no-set"), (49, "melee-ratio"), (39, "melee-ratio"), (30, None)])
        self.assertEqual(
            self.decided[GATE_ROW][0]["reason"],
            "town:entrance-step-off:fundraising:no-safe-destination:"
            "depth-gate:destination-49:missing-resist_chaos")

    def test_the_visit_search_takes_the_destination_band_and_the_home_flail(self):
        self.assertEqual(destination_band_floor.floor(self.policy, self.board), DESTINATION)
        decision = self.search.result.chosen_decision
        self.assertEqual((decision.band, decision.destination_floor), (DESTINATION, True))
        main_hand = dict(self.search.result.best.loadout.slots)["main_hand"]
        self.assertEqual(main_hand.origin, "home")
        self.assertTrue(main_hand.item.name.startswith(FLAIL))
        self.assertIn(("withdraw", main_hand.id), {
            (action.kind, action.item_id) for action in self.search.transaction.actions})

    def test_no_row_opens_the_fundraising(self):
        for recorded, _key, reason in self.decided:
            self.assertNotIn("fundraising", reason, recorded["row"])
        self.assertIsNone(self.policy._fundraising_mode)

    def test_the_destination_gate_counts_the_target_flail_and_the_worn_kit_does_not(self):
        board = self.board
        self.assertNotIn("resist_chaos", board.player.abilities)
        self.assertEqual(self.policy._missing_required_abilities(board, DESTINATION, owned=True),
                         frozenset())
        self.assertIn("resist_chaos", self.policy._missing_required_abilities(board, DESTINATION))
        # The departure on the worn loadout waits for the flail to be worn.
        self.assertFalse(self.policy._equipment_departure_ready(
            board, destination_depth=DESTINATION, commit=False))


class DestinationBandTest(unittest.TestCase):
    def test_band_of_a_depth(self):
        # 50-69 and 70-80 are two bands since the 70-80F speed +10 (2026-11-26).
        self.assertEqual([destination_band_floor.band_of(depth)
                          for depth in (5, 20, 31, 45, 49, 50, 69, 70, 99)],
                         [19, 20, 39, 49, 49, 69, 69, 80, 81])


if __name__ == "__main__":
    unittest.main()
