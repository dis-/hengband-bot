"""2026-10-30 20:34-21:20 n1-c: the Magic-Eater town stops D25.

Lives 033, 035, 036 and 037 each came back from the staff sequence's
explicit-target mining run with the target gold, then spent it in the Magic
shop on wands and staffs bought as zombie "food" (a Light staff and two
empty Magic Missile wands; two Sleep Monster wands).  A Magic-Eater's
identified device is absorption stock that the food count never credits
(magic_eater_devices, 2026-10-28), so the food requirement stayed open, the
next visit bought again, and the sequence started run after run until
quest:blocked:me-staff.

Each case starts on the recorded Magic-shop page of that first buy, with the
recorded shelves.  Only the replies to newly posted keys are constructed
(tests/test_me_town_stops_recorded.py); every decision goes through the
public chooser and the production executor.
"""
import tests  # noqa: F401

import gzip
import json
from pathlib import Path

from hengbot import me_staff_sequence
from hengbot.magic_eater_devices import is_absorption_device
from hengbot.model import TVAL_STAFF, TVAL_WAND, parse_snapshot
from hengbot.policy_constants import (
    RUMOR_COST, RUMOR_GOLD_RESERVE, RUMOR_READS_PER_VISIT, TOWN_TELEPORT_COST,
)
from tests import test_lv7_town_stop_recorded as lv7
from tests import test_me_town_stops_recorded as me
import tests.test_input_executor as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-town-stops2-20261030.json.gz"


class MagicEaterTownStops2RecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post
    reply = me.MagicEaterTownStopsRecordedTest.reply
    drive = me.MagicEaterTownStopsRecordedTest.drive

    @classmethod
    def setUpClass(cls):
        lv7.Lv7TownStopRecordedTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = {case["id"].split("/")[0]: case for case in json.load(stream)}

    def boundary(self, life, *, kit_bought=False):
        case = self.cases[life]
        policy, raw = lv7.Lv7TownStopRecordedTest().boundary(dict(
            monraces=case["monraces"], snapshot=case["board"], knowledge=case["knowledge"],
            state={"modes_and_latches": case["state"]}), kit_bought=kit_bought)
        # DECLARED CONSTRUCTED: this process already read the game's staff
        # power list (me_staff_sequence.read_powers, #47).
        me_staff_sequence.state(policy).powers_read = True
        policy._fundraising_mode = case["fundraising_mode"]
        if life == "life-036":
            # DECLARED RECONSTRUCTED: the capture keeps neither the staff
            # sequence's record nor the run's target.  The run returning here
            # is its sixth (policy-state _fundraising_runs_started 6), begun
            # by me-staff:fundraise:rumor-travel-recharge:2220 (seq 1635).
            policy._supply_stockout_gold_target = 2220
            # Its ascent (fundraise:ascend, seq 2059) completed the one run.
            policy._planned_mining_runs, policy._mining_runs_completed = 1, 1
            record = me_staff_sequence.state(policy)
            record.fundraise_target, record.fundraise_runs = 2220, me_staff_sequence.FUNDRAISE_RUN_LIMIT
            record.bought = frozenset(me_staff_sequence.SEQUENCE_SVALS)
        return policy, raw

    def devices_bought(self):
        return [name for name, _ in self.bought if "杖" in name or "魔法棒" in name]

    def test_recorded_visits_bought_devices_that_never_counted_as_food(self):
        for life, gold in (("life-033", 502), ("life-036", 344)):
            with self.subTest(life=life):
                visit = self.cases[life]["recorded"]["visit"]
                bought = [row for row in visit if row[0] == "shop:in-store-buy"]
                self.assertGreaterEqual(len(bought), 2)
                self.assertTrue(all(row[3]["category"] == "device" for row in bought))
                self.assertEqual(visit[-1][2], gold)
                # The food requirement was as open after the buys as before.
                food = [next(r for r in row[4] if r["item"] == "Device charges for food")
                        for row in visit]
                self.assertEqual({(r["current"], r["target"]) for r in food}, {(14, 15)})
                self.assertEqual(self.cases[life]["recorded"]["reason"], "quest:blocked:me-staff")

    def test_magic_eater_shelf_devices_are_absorption_stock(self):
        policy, raw = self.boundary("life-033")
        board = parse_snapshot(raw, policy._monrace_knowledge)
        devices = [it for it in board.store.items if it.tval in {TVAL_WAND, TVAL_STAFF}]
        self.assertTrue(devices)
        self.assertTrue(all(is_absorption_device(16, it) for it in devices))

    def test_life_033_keeps_the_staff_gold(self):
        # Phase buy: the Detect Treasure staff is not on the shelf, so the
        # sequence starts its next restock run instead of spending the gold.
        policy, raw, reasons = self.drive("life-033", limit=20, done=lambda policy, raw, key: (
            not raw.get("store") and policy.last_reason.startswith("me-staff:")))
        self.assertEqual(self.devices_bought(), [])
        self.assertEqual(raw["player"]["gold"], 1180)
        self.assertTrue(policy.last_reason.startswith("me-staff:fundraise:staff-stockout"),
                        reasons[-6:])

    def test_life_036_buys_survival_supplies_and_funds_the_sequence_on(self):
        # Phase rumor, the sixth run back: the recorded visit spent 2279 of
        # 2623 gold on two Sleep Monster wands and the sequence stopped on
        # its run limit.  Owner 2026-10-30 counts the carried Sleep Monster
        # wand, Detect Objects staff and Staff of Nothing as food (15 of 15),
        # so no device is bought.  The departure plan's Word of Recall is a
        # survival supply and is bought first (supervisor 2026-10-30,
        # 「生存処理を優先しなければキャラクタは死亡する。」); the run that met
        # its 2220 target is no failure, and the sequence starts its next run
        # with a target covering the still-unmet supplies and its own cost.
        policy, raw, reasons = self.drive("life-036", limit=80, done=lambda policy, raw, key: (
            policy.last_reason.startswith("me-staff:fundraise:")))
        self.assertEqual(self.devices_bought(), [])
        self.assertEqual([quantity for name, quantity in self.bought], [3])
        self.assertTrue(all("帰還" in name for name, _ in self.bought), self.bought)
        self.assertEqual(raw["player"]["gold"], 2623 - 3 * 237)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertEqual(me_staff_sequence._phase(policy, board), "rumor")
        self.assertIsNone(me_staff_sequence.state(policy).failure)
        supplies = me_staff_sequence.supply_cost(policy, board)
        # Four Teleportation (63) and four Cure Critical Wounds (158) remain.
        self.assertEqual(supplies, 4 * 63 + 4 * 158)
        target = (2 * TOWN_TELEPORT_COST + me_staff_sequence.recharge_cost(board) + supplies
                  + RUMOR_GOLD_RESERVE + RUMOR_COST * RUMOR_READS_PER_VISIT)
        self.assertEqual(policy.last_reason, f"me-staff:fundraise:rumor-travel-recharge:{target}")
        self.assertEqual(policy._supply_stockout_gold_target, target)

if __name__ == "__main__":
    import unittest
    unittest.main()
