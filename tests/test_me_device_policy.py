"""The Magic-Eater's per-device policy table (owner 2026-10-31).

The owner's form (src/hengbot/me_device_policy.json, 95 staffs, wands and
rods) and the owner's answers of the same night: 「1本目だけ充填する」 (a stage
kind's first copy is recharged before it is absorbed, later copies are
absorbed on the spot), 「食料を先にする」, Stone to Mud 「1本目だけ買う」 and
Identify 「段階1の1本だけ」.

Boards, all recorded n1-c Magic-Eater boards, DECLARED CONSTRUCTED where a
class says so:
* Purchase: the D25 life-033 Outpost Magic-shop page (tests/fixtures/
  n1c-town-stops2-20261030.json.gz), whose shelf sells a Staff of Remove
  Curse (buy_first) at 'm' beside the stage staffs; every stage absorbed,
  no fundraising run in progress and 10,000 gold (constructed, as
  test_me_stage2_staffs does).
* On the spot: the life-016 Yeek-cave board (tests/fixtures/
  me-mining-death-20261030.json.gz) with the D24 pack's recorded Staff of
  Perception row (9 charges) added, the visible yeek removed and full HP.
* Tower: the D24 Tower board with the stage-2 staffs of
  test_me_stage2_staffs and a Staff of Speed (absorb_after_charge, the D24
  staff row f with sval 22 and 3 charges) added.
Replies to posted keys are constructed as in the borrowed harnesses; every
posted key goes through the production executor.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import unittest

from hengbot import me_device_policy as table
from hengbot import me_staff_sequence as sequence
from hengbot.magic_eater import ABSORB_REASON
from hengbot.magic_eater_devices import SV_WAND_MAGIC_MISSILE, SV_WAND_WONDER
from hengbot.me_absorbed_substitutes import STONE_TO_MUD
from hengbot.model import SV_WAND_STONE_TO_MUD, TVAL_STAFF, TVAL_WAND, parse_snapshot
from tests import test_input_executor as harness
from tests import test_me_mining_death_recorded as mining
from tests import test_me_stage2_staffs as stage2
from tests import test_me_tower_recharge_recorded as d24
from tests.test_magic_eater_o3 import prompt

IDENTIFY, SPEED = sequence.SV_STAFF_IDENTIFY, 22
REMOVE_CURSE = 6


def d24_row(tval, sval):
    return copy.deepcopy(next(it for it in d24.MeTowerRechargeRecordedTest.case["approach"]["inventory"]
                              if (it["tval"], it["sval"]) == (tval, sval)))


class TableTest(unittest.TestCase):
    """The rows the hard-coded rules overlap read as those rules decide."""

    def test_every_row_has_exactly_one_absorption_choice(self):
        rows = table.devices()
        self.assertEqual(len(rows), 95)
        for row in rows.values():
            with self.subTest(names=row.names):
                self.assertEqual(sum((row.absorb_now, row.absorb_after_charge, row.never)), 1)
                self.assertFalse(row.never and (row.buy_first or row.buy_more))

    def test_stage_rows_are_the_staff_sequence_staffs(self):
        staged = {(row.tval, row.sval) for row in table.devices().values() if row.stage}
        self.assertEqual(staged, {(TVAL_STAFF, sval) for sval in sequence.SEQUENCE_SVALS})

    def test_overlapping_hard_coded_rules(self):
        rows = table.devices()
        wonder = rows[(TVAL_WAND, SV_WAND_WONDER)]
        self.assertTrue(wonder.never)   # the staple food is eaten, never absorbed
        self.assertTrue(rows[(TVAL_WAND, SV_WAND_MAGIC_MISSILE)].absorb_now)  # O3
        stone = rows[(TVAL_WAND, SV_WAND_STONE_TO_MUD)]
        self.assertEqual((stone.buy_first, stone.buy_more, stone.absorb_after_charge),
                         (True, False, True))  # 「1本目だけ買う」, rule 3
        self.assertEqual(STONE_TO_MUD.names, stone.names)


class PurchaseTest(harness.ProductionHarness):
    """「1本目を見たら買う」 on the recorded life-033 Magic-shop page."""
    shelf_screen = staticmethod(stage2.Stage2ShopTest.shelf_screen)
    post = stage2.Stage2ShopTest.post
    reply = stage2.Stage2ShopTest.reply
    drive = stage2.Stage2ShopTest.drive

    @classmethod
    def setUpClass(cls):
        stage2.Stage2ShopTest.setUpClass.__func__(cls)

    def boundary(self, life, *, kit_bought=False):
        policy, raw = stage2.Stage2ShopTest.boundary(self, life, kit_bought=kit_bought)
        record = sequence.state(policy)
        record.absorbed = {sval: sequence.max_charges(sval) for sval in sequence.SEQUENCE_SVALS}
        # DECLARED CONSTRUCTED: no fundraising run in progress (the recorded
        # run's kit shopping buys only its kit).
        policy._fundraising_mode = None
        policy._supply_stockout_gold_target = None
        # The viewing bots run with --in-store-shop-ops (recorded
        # shop:in-store-buy decisions of n1-c life-065).
        policy._in_store_ops_enabled = True
        return policy, raw

    @staticmethod
    def setup(raw):
        """DECLARED CONSTRUCTED: 10,000 gold; the carried Staff of Object
        Location (absorb_now, absorbed first in town) out of the pack."""
        raw["player"]["gold"] = 10000
        raw["inventory"] = [it for it in raw["inventory"] if (it.get("tval"), it.get("sval")) != (55, 11)]
        for index, item in enumerate(raw["inventory"]):
            item["slot"] = chr(ord("a") + index)

    def test_the_shop_selector_picks_the_buy_first_device_once(self):
        # The production selector on the recorded page (the in-store visit
        # then composes it outside, the atomic shop contract; the borrowed
        # D25 replies cannot follow the Home stop that comes first).
        policy, raw = self.boundary("life-033")
        board = parse_snapshot(raw, policy._monrace_knowledge)
        shelf = next(it for it in board.store.items if (it.tval, it.sval) == (TVAL_STAFF, REMOVE_CURSE))
        self.assertEqual(shelf.letter, "m")
        # Unfixed: None (no rung or selector step buys a Staff of Remove Curse).
        self.assertEqual(policy._next_purchase(board), shelf)
        self.assertEqual([match.rung_id for match in policy._matching_live_purchase_rungs(board, shelf)],
                         ["me-device:policy"])
        # The stage staffs on the same page stay the staff sequence's.
        self.assertFalse(any(table.purchase_wanted(policy, board, it) for it in board.store.items
                             if it.tval == TVAL_STAFF and it.sval in sequence.SEQUENCE_SVALS))
        # Once held, no second copy (buy_more is not set for it).
        bought = dict(copy.deepcopy(raw["store"]["items"][0]), tval=TVAL_STAFF, sval=REMOVE_CURSE,
                      slot="w")
        bought.pop("letter"), bought.pop("price")
        raw["inventory"].append(bought)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertFalse(table.purchase_wanted(policy, board, shelf))

    def test_spare_gold_bounds_the_purchase(self):
        policy, raw = self.boundary("life-033")
        board = parse_snapshot(raw, policy._monrace_knowledge)
        shelf = next(it for it in board.store.items if (it.tval, it.sval) == (TVAL_STAFF, REMOVE_CURSE))
        raw["player"]["gold"] = shelf.price + (raw["player"]["gold"] - sequence.spare_gold(policy, board)) - 1
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertFalse(table.purchase_wanted(policy, board, shelf))


class OnTheSpotTest(harness.ProductionHarness):
    """「拾って鑑定したらその場で取り込む」 and 「1本目だけ充填する」 on a dungeon floor."""
    raw = mining.MagicEaterMiningDeathRecordedTest.raw
    recorded_policy = mining.MagicEaterMiningDeathRecordedTest.policy
    choose = mining.MagicEaterMiningDeathRecordedTest.choose
    post = mining.MagicEaterMiningDeathRecordedTest.post

    @classmethod
    def setUpClass(cls):
        mining.MagicEaterMiningDeathRecordedTest.setUpClass.__func__(cls)
        d24.MeTowerRechargeRecordedTest.setUpClass()

    def board(self):
        raw = self.raw("life-016", 94171)
        raw["visible_monsters"] = []
        raw["player"]["hp"] = raw["player"]["max_hp"]
        staff = d24_row(TVAL_STAFF, IDENTIFY)
        staff["slot"] = chr(ord("a") + len(raw["inventory"]))
        raw["inventory"].append(staff)
        return raw, staff["slot"]

    def test_a_later_copy_of_an_absorbed_kind_is_absorbed_on_the_spot(self):
        raw, slot = self.board()
        policy = self.recorded_policy("life-016", raw)
        sequence.state(policy).absorbed = {IDENTIFY: 21}
        key = self.choose(policy, raw)
        # Unfixed: the Identify power identifies the floor's unknown item.
        self.assertEqual((key, policy.last_reason), ("G" + slot, ABSORB_REASON))
        game, _ = self.post(policy, raw, key, [prompt(
            d24.ABSORB_PROMPT, "item", area="inventory", areas=["inventory", "floor"],
            menu=False, first_label="a", last_label=slot)])
        self.assertEqual(game.accepted, ["G", slot])

    def test_the_first_copy_of_a_stage_kind_is_kept_for_the_tower(self):
        raw, slot = self.board()
        policy = self.recorded_policy("life-016", raw)
        key = self.choose(policy, raw)
        self.assertNotEqual(policy.last_reason, ABSORB_REASON, key)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        staff = next(it for it in board.inventory if it.slot == slot)
        self.assertTrue(table.charge_first(policy, board, table.device(staff)))


class AfterChargeTowerTest(harness.ProductionHarness):
    """「持ち帰ってチャージしてから取り込む」: a Staff of Speed at the Tower."""
    _tower = stage2.Stage2TowerTest
    setUpClass = classmethod(_tower.setUpClass.__func__)
    board = _tower.board
    absorb_screen = _tower.absorb_screen
    policy = _tower.policy
    decide = _tower.decide
    post = _tower.post
    recharge_reply = _tower.recharge_reply
    absorb_reply = staticmethod(_tower.absorb_reply)
    move_reply = staticmethod(_tower.move_reply)

    def test_the_staff_is_recharged_and_absorbed_after_the_stage(self):
        from hengbot.policy_constants import WAIT_KEY
        from tests.test_me_tower_recharge_recorded import DIRECTIONS, recharge_all_screens

        raw = self.board()
        speed = d24_row(TVAL_STAFF, IDENTIFY)
        speed.update(sval=SPEED, name="スピードの杖 (3回分)", charges=3, pval=3)
        raw["inventory"].append(speed)
        raw["inventory"].sort(key=lambda it: (-it["tval"], it["sval"]))
        for index, item in enumerate(raw["inventory"]):
            item["slot"] = chr(ord("a") + index)
        policy = self.policy(raw)
        steps = []
        for _ in range(24):
            key = self.decide(policy, raw)
            reason = policy.last_reason
            if reason == "me-staff:return-outpost":
                break
            if reason == "me-staff:recharge-all":
                total = sequence.recharge_cost(parse_snapshot(copy.deepcopy(raw), self.knowledge))
                following = self.recharge_reply(raw)
                self.post(policy, raw, key, following, recharge_all_screens(total))
                steps.append(reason)
            elif reason == ABSORB_REASON:
                item = next(it for it in raw["inventory"] if it["slot"] == key[1])
                following = self.absorb_reply(raw, key[1])
                self.post(policy, raw, key, following, [self.absorb_screen(raw)])
                steps.append(("absorb", item["tval"], item["sval"], item["charges"]))
            elif key in DIRECTIONS or key == WAIT_KEY:
                following = (self.move_reply(raw, key) if key in DIRECTIONS
                             else dict(copy.deepcopy(raw), turn=raw["turn"] + 10))
                self.post(policy, raw, key, following)
                steps.append(reason)
            else:
                self.fail((key, reason, steps))
            raw = following
        else:
            self.fail(("no return", steps))
        full = sequence.morivant_tower.device_definitions()[(TVAL_STAFF, SPEED)][0]
        # Unfixed: the Speed staff is neither recharged for nor absorbed.
        self.assertEqual(steps[-2:], ["me-staff:stage2-complete", ("absorb", TVAL_STAFF, SPEED, full)])
        self.assertEqual(sequence.state(policy).absorbed[f"staff:{SPEED}"], full)


if __name__ == "__main__":
    unittest.main()
