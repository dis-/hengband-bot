"""Short of 50F the gear that makes an owned *Destruction* staff reliable is weighed, and the staff carried.

n1-a life-525 (Lv40 Warrior) died on ガラスの城 49F on 2026-11-15 21:06:00, its last Teleportation
landing beside the sleeping 『スマウグ』, a storm and 『ウリエル』, all within *Destruction*'s radius
13.  Twelve staves of *Destruction* were in the Home and the 魔力支配の革グローブ (+3) and the
魔法道具支配のアミュレット (+1) make them reliable (device skill 32 -> 64, 85.7%), but the staff
was asked only from 50F (DESTRUCTION_GATE_DEPTH) and the character was held at 49F for want
of telepathy, so the 21:05:39 departure wore neither and carried none.  Owner 2026-11-15,
verbatim: 「深さに関係なく持っていく」; the swap's combat loss is weighed by the loadout
comparison (equipment_utility.destruction_means_bonus, the size of full telepathy, on the
survival side), and the departure carries the staff once the worn loadout makes it reliable
(destruction_use.staff_carry_uses in the *Destruction* requirement).

Recorded: the 21:05:39 town-arrival checkpoint of that fatal departure and its first 7 journal
rows (tests/extract_n1a_525_departure_1115_fixture.py), decided through the public choose_key;
rows 0-5 replay as recorded.

DECLARED CONSTRUCTED:
* The calibration after row 5's character dump: the live dump re-derived it from the drained INT
  the board shows (printed key 69/-18/75/67/138/49) and that file was not captured, so the
  arrival's sidecar is adopted with the board's printed stat key (``visible_stat_key``).  The
  control (the bonus 0) reproduces the live decision log's optimizer exactly: band 49, ratio
  0.6840438277367907, row 6's recorded key.
* ``worn``: row 6's board with the chosen set's device skill, the board the transaction leads to.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import destruction_use, device_skill, equipment_utility
from replay_town_arrival import adopt_calibration
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-525-departure-1115"
GLOVES, AMULET = 24, 8          # their MAGIC_MASTERY skill (8 * pval)
LIVE_RATIO = 0.6840438277367907  # the decision log's chosen_ratio (decisions 23832-23888)


def visit(scratch: Path):
    """(policy, row 6's board, its key, its reason, rows 0-5 as (decided, recorded))."""
    policy, _journal, steps = load(FIXTURE, scratch)
    replayed = []
    for recorded, supply in steps[:6]:
        board = supply()
        key = policy.choose_key(board)
        replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
        policy.confirm_key_posted(recorded["key"])
        if recorded["reason"] == "periodic:character-dump":
            # DECLARED CONSTRUCTED: the dump's calibration with the board's printed stat key.
            sidecar = scratch / "town-arrival" / "sidecars" / "_character_calibration_path"
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            data["observed_turn"] = board.turn
            data["visible_stat_key"] = list(board.player.printed_stat_cur_key)
            dumped = scratch / "dumped-calibration.json"
            dumped.write_text(json.dumps(data), encoding="utf-8")
            adopt_calibration(policy, dumped, scratch / "runtime")
    _recorded, supply = steps[6]
    board = supply()
    key = policy.choose_key(board)
    return policy, board, key, policy.last_reason, replayed


def gate_of(policy, board):
    return policy._optimizer_destruction_means(
        board, policy._equipment_catalog.items, policy._character_calibration)[1]


class N1a525DestructionCarry1115RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        root = Path(cls.scratch.name)
        cls.policy, cls.board, cls.key, cls.reason, cls.replayed = visit(root / "real")
        with mock.patch.object(equipment_utility, "DESTRUCTION_MEANS_BONUS", 0.0):
            cls.control = visit(root / "control")

    @classmethod
    def tearDownClass(cls):
        for policy in (cls.policy, cls.control[0]):
            policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_rows_0_to_5_replay_as_recorded(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)

    def test_control_without_the_bonus_is_the_live_decision(self):
        policy, board, key, reason, _replayed = self.control
        result = policy._equipment_optimization_preparation.result
        self.assertEqual(result.chosen_depth, 49)
        self.assertEqual(result.chosen_decision.ratio, LIVE_RATIO)
        self.assertEqual((key, reason), ("\x1b`n%.", "shop:travel"))
        gate = gate_of(policy, board)
        self.assertEqual(gate.skill(result.best.loadout), board.player.device_skill)
        self.assertFalse(gate.opens(result.best.loadout))

    def test_the_staff_is_owned_and_unreliable_on_the_worn_set(self):
        board = self.board
        self.assertEqual((board.player.class_id, board.player.level, board.player.device_skill),
                         (0, 40, 32))
        self.assertLess(destruction_use.staff_success(board.player, 50), 80)
        self.assertFalse(any(self.policy._is_destruction_staff(item) for item in board.inventory))
        staves = destruction_use.staff_home_items(self.policy, board)
        self.assertEqual(sum(item.count for item in staves), 12)
        # The departure's landing is short of the gate: no *Destruction* was asked.
        self.assertLess(self.policy._intended_dive_depth(board), 50)
        self.assertEqual(self.policy._required_destruction_uses(board), 0)

    def test_the_optimizer_weighs_in_the_gear_and_the_visit_goes_to_wear_it(self):
        result = self.policy._equipment_optimization_preparation.result
        self.assertFalse(result.timed_out)
        self.assertEqual(result.chosen_depth, 49)
        best = result.best.loadout
        gate = gate_of(self.policy, self.board)
        self.assertTrue(gate.opens(best))
        self.assertEqual(gate.skill(best), 64)
        added = {slot: device_skill.item_mastery(item) for slot, item in best.slots
                 if item.origin == "home"}
        self.assertEqual((added.get("arms"), added.get("neck")), (GLOVES, AMULET))
        # The bonus is on the survival side of the comparison, not a forced pick: without it the
        # set's 27.4 turns fall under the selector's 30-turn floor (the control keeps 30.8).
        raw = self.policy._warrior_evaluator_cache.evaluator(best).metrics
        bonus = equipment_utility.DESTRUCTION_MEANS_BONUS
        self.assertAlmostEqual(result.best.metrics.survival_turns, raw.survival_turns * (1 + bonus))
        self.assertAlmostEqual(result.best.metrics.utility_value, raw.utility_value + bonus)
        control = self.control[0]._equipment_optimization_preparation.result.best.metrics
        self.assertLess(raw.survival_turns, 30)
        self.assertGreaterEqual(control.survival_turns, 30)
        self.assertEqual((self.key, self.reason), ("5", "equipment-transaction:travel-home:await-entry"))

    def worn(self):
        """DECLARED CONSTRUCTED: row 6's board wearing the chosen set's device skill."""
        best = self.policy._equipment_optimization_preparation.result.best.loadout
        player = self.board.player
        return replace(self.board, player=replace(
            player, device_skill=gate_of(self.policy, self.board).skill(best)))

    def test_the_departure_carries_the_staff_short_of_the_gate(self):
        policy, worn = self.policy, self.worn()
        self.assertGreaterEqual(destruction_use.staff_success(worn.player, 50), 80)
        self.assertLess(policy._intended_dive_depth(worn), 50)
        self.assertEqual(destruction_use.staff_carry_uses(policy, worn), 5)
        self.assertEqual(policy._required_destruction_uses(worn), 5)
        self.assertEqual(policy._missing_destruction_uses(worn), 5)
        staff = destruction_use.staff_home_items(policy, worn)[0]
        # The Home-first take's shortage, the same one the departure readiness publishes.
        self.assertEqual(policy._procurement_missing_amount(worn, staff), 5)
        self.assertIn({"item": "*Destruction* uses", "current": 0, "target": 5, "missing": 5},
                      policy.procurement_requirements(worn))

    def test_a_berserker_carries_none(self):
        worn = self.worn()
        berserker = replace(worn, player=replace(worn.player, class_id=destruction_use.PLAYER_CLASS_BERSERKER))
        self.assertEqual(destruction_use.staff_carry_uses(self.policy, berserker), 0)


if __name__ == "__main__":
    unittest.main()
