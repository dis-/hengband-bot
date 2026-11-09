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
from hengbot.me_absorbed_substitutes import POWERS as SUBSTITUTE_POWERS
from hengbot.model import SV_WAND_STONE_TO_MUD, TVAL_STAFF, TVAL_WAND, parse_snapshot
from tests.support import recorded as harness
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
        self.assertEqual(SUBSTITUTE_POWERS[("wand", SV_WAND_STONE_TO_MUD)].names, stone.names)


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

    def test_absorbing_every_copy_leaves_the_buy_rules(self):
        """Owner 2026-11-07: buying stays 「1本目だけ買う」 for Stone to Mud."""
        policy, raw = self.boundary("life-033")
        shelf_row = next(it for it in raw["store"]["items"]
                         if (it["tval"], it["sval"]) == (TVAL_STAFF, REMOVE_CURSE))
        shelf_row.update(tval=TVAL_WAND, sval=SV_WAND_STONE_TO_MUD, name="岩石溶解の魔法棒 (8回分)",
                         charges=8, pval=8)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        shelf = next(it for it in board.store.items
                     if (it.tval, it.sval) == (TVAL_WAND, SV_WAND_STONE_TO_MUD))
        self.assertTrue(table.purchase_wanted(policy, board, shelf))
        sequence.state(policy).absorbed = {**sequence.state(policy).absorbed,
                                           f"wand:{SV_WAND_STONE_TO_MUD}": 12}
        self.assertFalse(table.purchase_wanted(policy, board, shelf))
        # ... while a carried copy is still absorbed at the Tower.
        self.assertTrue(table.charge_first(policy, board, table.device(shelf)))

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
        policy, _, steps = self.absorb_after_stage(SPEED, "スピードの杖 (3回分)")
        full = sequence.morivant_tower.device_definitions()[(TVAL_STAFF, SPEED)][0]
        # Unfixed: the Speed staff is neither recharged for nor absorbed.
        self.assertEqual(steps[-2:], ["me-staff:stage2-complete", ("absorb", TVAL_STAFF, SPEED, full)])
        self.assertEqual(sequence.state(policy).absorbed[f"staff:{SPEED}"], full)

    @staticmethod
    def wand_rows(sval, name, counts, charges):
        """DECLARED CONSTRUCTED: carried identified stacks of wand ``sval``
        (the D24 Sleep Monster row renamed), one per count, each stack after
        the first inscribed so the game keeps them apart."""
        rows = []
        for index, count in enumerate(counts):
            row = d24_row(TVAL_WAND, 8)
            inscription = f" {{#{index}}}" if index else ""
            row.update(sval=sval, count=count, charges=charges, pval=charges,
                       name=f"{count}本の{name} ({charges}回分){inscription}")
            rows.append(row)
        return rows

    def wand_visit(self, sval, name, counts, recorded, *, check=None):
        key = f"wand:{sval}"
        policy, _, steps = self.absorb_after_stage(
            None, None, rows=self.wand_rows(sval, name, counts, 4),
            absorbed={key: recorded}, check=check)
        return policy, steps

    def test_absorbed_stone_to_mud_copies_are_recharged_and_absorbed(self):
        """Owner 2026-11-07 「2本目以降も充填して取り込み、上限を増やす」: n1-c
        life-159 carried six Stone to Mud wands (buy_more not set) beside an
        absorbed Stone to Mud and the Tower only recharged them every trip."""
        full = sequence.morivant_tower.device_definitions()[(TVAL_WAND, SV_WAND_STONE_TO_MUD)][0] * 6

        def kept_for_the_sequence(policy, raw):
            # 「岩石溶解の全部持つ決まりは、取り込む分だけ外す」: the wand the
            # sequence absorbs is held by the sequence, not by the keep-all rule.
            board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            wand = next(it for it in board.inventory
                        if (it.tval, it.sval) == (TVAL_WAND, SV_WAND_STONE_TO_MUD))
            # Unfixed: (6, "utility:stone-to-mud").
            self.assertEqual(policy._retention_reservation_baseline_detail(board, wand),
                             (6, "me-staff:absorb"))

        policy, steps = self.wand_visit(SV_WAND_STONE_TO_MUD, "岩石溶解の魔法棒", [6], 10,
                                        check=kept_for_the_sequence)
        # Unfixed: the stage ends the visit and the wands ride home unabsorbed.
        self.assertEqual(steps[0], "me-staff:recharge-all")
        self.assertEqual(steps[-2:], ["me-staff:stage2-complete",
                                      ("absorb", TVAL_WAND, SV_WAND_STONE_TO_MUD, full)])
        self.assertEqual(sequence.state(policy).absorbed[f"wand:{SV_WAND_STONE_TO_MUD}"], full)

    def test_every_stack_of_an_absorbed_kind_is_absorbed(self):
        """Four stacks: one 'G' each, none counted as an absorb without progress."""
        policy, steps = self.wand_visit(SV_WAND_STONE_TO_MUD, "岩石溶解の魔法棒", [1, 1, 1, 1], 20)
        absorbs = [step for step in steps if isinstance(step, tuple)
                   and step[1:3] == (TVAL_WAND, SV_WAND_STONE_TO_MUD)]
        # Unfixed (settle by "no copy left"): the fourth 'G' stops the bot as
        # me-staff absorb-no-progress:wand:6.
        self.assertEqual(len(absorbs), 4, steps)
        self.assertIsNone(sequence.state(policy).failure)
        # A copy's 12 charges never lower the count the record already holds
        # (the game only adds to it).
        self.assertEqual(sequence.state(policy).absorbed[f"wand:{SV_WAND_STONE_TO_MUD}"], 20)

    def test_absorbed_teleport_other_copy_is_recharged_and_absorbed(self):
        from hengbot.model import SV_WAND_TELEPORT_AWAY

        full = sequence.morivant_tower.device_definitions()[(TVAL_WAND, SV_WAND_TELEPORT_AWAY)][0]
        policy, steps = self.wand_visit(SV_WAND_TELEPORT_AWAY, "テレポート・アウェイの魔法棒", [1], 10)
        # Unfixed: no absorption of the wand.
        self.assertEqual(steps[-2:], ["me-staff:stage2-complete",
                                      ("absorb", TVAL_WAND, SV_WAND_TELEPORT_AWAY, full)])

    def test_a_power_at_its_count_cap_takes_no_more_copies(self):
        """mind-magic-eater.cpp caps the count at 99: another copy adds nothing."""
        key = f"wand:{SV_WAND_STONE_TO_MUD}"
        policy, steps = self.wand_visit(SV_WAND_STONE_TO_MUD, "岩石溶解の魔法棒", [6],
                                        table.POWER_COUNT_CAP)
        self.assertFalse(any(isinstance(step, tuple) and step[1] == TVAL_WAND for step in steps),
                         steps)
        self.assertEqual(steps[-1], "me-staff:stage2-complete")
        self.assertEqual(sequence.state(policy).absorbed[key], table.POWER_COUNT_CAP)
        # The displayed list's count is the evidence as well.
        stone = table.devices()[(TVAL_WAND, SV_WAND_STONE_TO_MUD)]
        policy._me_device_lists = {"wand": (0, ({"name": stone.names[0], "current": 50, "max": 99},))}
        sequence.state(policy).absorbed = {key: 10}
        board = parse_snapshot(copy.deepcopy(self.board()), self.knowledge)
        self.assertFalse(table.charge_first(policy, board, stone))
        policy._me_device_lists["wand"] = (0, ({"name": stone.names[0], "current": 50, "max": 98},))
        self.assertTrue(table.charge_first(policy, board, stone))

    def absorb_after_stage(self, sval, name, *, rows=None, absorbed=None, check=None):
        """(policy, the board after the return step, steps) of one Tower visit
        that carries the D24 Identify row as staff ``sval`` with 3 charges
        (or the given pack ``rows``), the record holding ``absorbed`` first;
        ``check(policy, raw)`` looks at the first board."""
        from hengbot.policy_constants import WAIT_KEY
        from tests.test_me_tower_recharge_recorded import DIRECTIONS, recharge_all_screens

        raw = self.board()
        if rows is None:
            speed = d24_row(TVAL_STAFF, IDENTIFY)
            speed.update(sval=sval, name=name, charges=3, pval=3)
            rows = [speed]
        raw["inventory"].extend(rows)
        raw["inventory"].sort(key=lambda it: (-it["tval"], it["sval"]))
        for index, item in enumerate(raw["inventory"]):
            item["slot"] = chr(ord("a") + index)
        policy = self.policy(raw)
        if absorbed:
            sequence.state(policy).absorbed = dict(absorbed)
        if check is not None:
            check(policy, raw)
        steps = []
        for _ in range(24):
            key = self.decide(policy, raw)
            reason = policy.last_reason
            if reason == "me-staff:return-outpost":
                return policy, raw, steps
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
        self.fail(("no return", steps))


if __name__ == "__main__":
    unittest.main()
