"""n1-c life-218: the only resist_chaos set was in Home and the town mined for the 49F gate.

Owner 2026-11-21 (verbatim): 「唯一のカオス耐性を自宅に仕舞い込んで勝手に持っていない判定にした経緯を
解析」 (destination_band_floor's docstring has the history).

Recorded: n1-c's town visit of 2026-11-21 21:00:41 (tests/fixtures/n1c-218-chaos-home-1121, 37
journal rows).  Its arrival descent refused band 49 by the half-melee limit (the ★Pike's 238
against the (混沌)ヘヴィ・フレイル set's 92) and adopted band 30; row 24 opened
``fundraising:no-safe-destination:depth-gate:destination-49:missing-resist_chaos``.  The replay
matches the record through row 23; on row 24 the floor engages instead, the descent takes band
49 and the transaction withdraws the flail from Home.

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
from types import SimpleNamespace

from hengbot import destination_band_floor
from hengbot.equipment_optimizer import BandDecision
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-218-chaos-home-1121"
GATE_ROW = 24
MOUNTAIN = 14
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
        for recorded, supply in steps[:GATE_ROW + 1]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            cls.decided.append((recorded, key, policy.last_reason))
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
        self.assertEqual(self.arrival_bands, [
            (81, "no-set"), (80, "no-set"), (49, "melee-ratio"), (39, "melee-ratio"), (30, None)])

    def test_the_visit_replays_to_the_gate(self):
        for recorded, key, reason in self.decided[:GATE_ROW]:
            self.assertEqual((key, reason), (recorded["key"], recorded["reason"]), recorded["row"])
        self.assertEqual(
            self.decided[GATE_ROW][0]["reason"],
            "town:entrance-step-off:fundraising:no-safe-destination:"
            "depth-gate:destination-49:missing-resist_chaos")
        self.assertNotIn("resist_chaos", self.board.player.abilities)

    def test_the_gate_wears_the_home_flail_instead_of_fundraising(self):
        _recorded, _key, reason = self.decided[GATE_ROW]
        self.assertNotIn("fundraising", reason)
        self.assertEqual(self.policy._fundraising_mode, None)
        self.assertEqual(getattr(self.policy, destination_band_floor.STATE), (MOUNTAIN, 49))
        preparation = self.policy._equipment_optimization_preparation
        decision = preparation.result.chosen_decision
        self.assertEqual((decision.band, decision.destination_floor), (49, True))
        self.assertEqual(self.policy._equipment_optimization_last_depth, 49)
        main_hand = dict(preparation.result.best.loadout.slots)["main_hand"]
        self.assertEqual(main_hand.origin, "home")
        self.assertTrue(main_hand.item.name.startswith(FLAIL))
        self.assertIn(("withdraw", main_hand.id), {
            (action.kind, action.item_id) for action in preparation.transaction.actions})


class DestinationBandFloorTest(unittest.TestCase):
    """CONSTRUCTED: policy doubles for the floor's own rules."""

    @staticmethod
    def policy(target, bands):
        result = SimpleNamespace(band_decisions=tuple(
            BandDecision(band, refusal != "no-set", None, 100.0, refusal, None)
            for band, refusal in bands))
        policy = SimpleNamespace(
            _target_dungeon_id=target,
            _equipment_optimization_preparation=SimpleNamespace(result=result),
            _equipment_optimization_signature="cached", searched=0)
        policy._prepare_equipment_optimization = lambda _snapshot: setattr(
            policy, "searched", policy.searched + 1)
        return policy

    def test_band_of_a_depth(self):
        self.assertEqual([destination_band_floor.band_of(depth) for depth in (5, 20, 31, 45, 49, 50, 99)],
                         [19, 20, 39, 49, 49, 80, 81])

    def test_engages_once_for_a_melee_refused_band_and_follows_the_target(self):
        policy = self.policy(MOUNTAIN, [(81, "no-set"), (49, "melee-ratio"), (30, None)])
        self.assertTrue(destination_band_floor.engage(policy, None, 49))
        self.assertEqual((policy.searched, policy._equipment_optimization_signature), (1, None))
        self.assertEqual(destination_band_floor.floor(policy), 49)
        self.assertFalse(destination_band_floor.engage(policy, None, 49))
        policy._target_dungeon_id = 12
        self.assertIsNone(destination_band_floor.floor(policy))

    def test_no_owned_set_engages_nothing(self):
        policy = self.policy(MOUNTAIN, [(81, "no-set"), (49, "no-set"), (30, None)])
        self.assertFalse(destination_band_floor.engage(policy, None, 49))
        self.assertIsNone(destination_band_floor.floor(policy))


if __name__ == "__main__":
    unittest.main()
