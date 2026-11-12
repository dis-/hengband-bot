"""The Potion of Resistance through the public choose_key (owner 2026-11-05).

Owner: 「危ない敵と戦う時に飲む」, 「資金に余裕があるとき闇市で購入する」, 「耐性の薬を飲んでも勝ち目がないなら
飲まずに逃走や破壊を優先する」.  Recorded: n1-b life-312's Quest 25 boards, two potions held
(tests/fixtures/q25-summons-n1b-312-1105.json.gz).  The edits on a board and the two boards moved
to a plain floor are DECLARED CONSTRUCTED; so are the Black Market towns, on the
OptionalBlackMarketPotionTest fixtures.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace
from unittest.mock import patch

from hengbot import consumable_policy, destruction_use, quest25_battle, quest_room_sweep, resist_potion, threat_tiers
from hengbot.model import (
    STORE_BLACK, SV_POTION_RESISTANCE, SV_POTION_SPEED, TVAL_POTION, StoreState, parse_snapshot,
)
from hengbot.monrace_knowledge import MonsterBlow
from hengbot.policy_constants import BUY_KEY, HEAL_POTION_SVALS, PACK_CAPACITY
from hengbot.policy import HengbotPolicy
from tests import test_plan_floor_summons_1105_recorded as q25_boards
from tests import test_q18_water_cave as q18
from tests import test_policy_shop as shop

# 幽体ティラノサウルス (BR_POIS) alone in view, HP 872/1137: the three-turn prediction 522 (375 after
# the drink), six turns to clear at 625.
TYRANNOSAUR = 11651719
TYRANNOSAUR_RACE_NAME = "幽体ティラノサウルス"
# The same monster beside the player, HP 879.
BESIDE_IT = 11651725
# Eight in view, レッサー・バルログ (BR_FIRE) among them, HP 1137: 1811 over the twelve turns to
# clear, 882 after the drink: only the drink makes this fight winnable.
WON_ONLY_WITH_THE_DRINK = 11653246
# Thirteen in view, HP 1137: 4204 over the 21 turns to clear even after the drink.
NO_CHANCE = 11653263
# Twenty in view, HP 846: the prediction 1242 lies above the HP, the ladder's own emergency.
CROWD = 11651625


def _letter(raw, tval, sval):
    return next(chr(ord("a") + index) for index, item in enumerate(raw["inventory"])
                if item["tval"] == tval and item["sval"] == sval)


def _is_drink(raw, key):
    return key == "q" + _letter(raw, TVAL_POTION, SV_POTION_RESISTANCE)


def _on_a_plain_floor(raw):
    raw["floor"]["quest_id"] = 0
    raw["quests"] = {}


def _alone(turn, change=None):
    """One decision of a fresh policy on the board of ``turn``, moved to a plain floor."""
    raw = copy.deepcopy(next(board for board in q25_boards.CASE["boards"] if board["turn"] == turn))
    _on_a_plain_floor(raw)
    if change is not None:
        change(raw)
    policy = q25_boards._new_policy()
    key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
    return policy, raw, key


def _with_hp(hp, max_hp=None):
    def change(raw):
        raw["player"]["hp"] = hp
        if max_hp is not None:
            raw["player"]["max_hp"] = max_hp
    return change


def _bar(*keys):
    def change(raw):
        raw["player"]["status_bar"] = [{"id": 0, "key": key, "label": key} for key in keys]
    return change


TOWN = shop.OptionalBlackMarketPotionTest()  # the town fixtures


def _below_half_the_hp(test, policy, raw):
    """The rule does not apply: such an enemy is in view, but the 3-turn prediction is below
    half the HP (``_is_material_threat``)."""
    board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    test.assertTrue(resist_potion._such_enemy_in_view(policy, board))
    test.assertFalse(policy._is_material_threat(board, policy._physical_hostiles(board)))
    test.assertIsNone(resist_potion._verdict(policy, board))


class PlanFloorTest(unittest.TestCase):
    """The Q25 board, where quest_find_exit answers before the shared ladder.

    Re-driven 2026-11-12 (t3-survival-1112 D, the game's spell odds: the innate breath only in
    the 2 x freq share): the tyrannosaur's poison breath comes on fewer moves and the 3-turn prediction falls below half the HP (272 against 872, 408
    against 1137), so 「3ターンの予想が今の HP の半分以上の時に飲みます」 does not hold on these
    boards and the plan's own step answers."""

    def test_such_an_enemy_at_half_the_hp_is_drunk_for(self):
        policy, raw, key = q25_boards.replay_until(TYRANNOSAUR)
        _below_half_the_hp(self, policy, raw)
        self.assertEqual(policy.last_reason, "quest25:trap-disarm")
        self.assertFalse(_is_drink(raw, key), key)

    def test_the_drink_that_makes_the_fight_winnable_is_taken(self):
        policy, raw, key = q25_boards.replay_until(WON_ONLY_WITH_THE_DRINK)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertFalse(policy._engagement_is_winnable(snapshot, policy._physical_hostiles(snapshot)))
        _below_half_the_hp(self, policy, raw)
        self.assertEqual(policy.last_reason, "quest-strategy:hold")
        self.assertFalse(_is_drink(raw, key), key)

    def test_no_chance_even_with_the_drink_the_leave_stands_below_the_q25_phase(self):
        # Owner 2026-11-07 「Q25内部でのテレポートの優先度を下げる」: on the Q25 floor the phase's own
        # step (the ambush's hold) answers before the leave; with no step, the leave still reads it.
        policy, raw, key = q25_boards.replay_until(NO_CHANCE)
        self.assertNotEqual(policy.last_reason, resist_potion.LEAVE_REASON, key)
        self.assertFalse(_is_drink(raw, key))
        with patch.object(quest25_battle, "_phase_key", lambda policy, snapshot: None):
            policy, raw, key = q25_boards.replay_until(NO_CHANCE)
        self.assertEqual(policy.last_reason, resist_potion.LEAVE_REASON, key)
        self.assertTrue(key.startswith("r"), key)
        self.assertFalse(_is_drink(raw, key))

    def test_not_while_its_elements_are_on_the_status_bar(self):
        policy, raw, key = q25_boards.replay_until(TYRANNOSAUR, _bar("resist_pois"))
        self.assertNotEqual(policy.last_reason, resist_potion.QUAFF_REASON)
        self.assertFalse(_is_drink(raw, key))

    def test_another_element_on_the_bar_does_not_stop_it(self):
        # Fire on the bar leaves poison uncovered (the prediction is below half the HP, above).
        policy, raw, key = q25_boards.replay_until(TYRANNOSAUR, _bar("resist_fire"))
        _below_half_the_hp(self, policy, raw)
        self.assertFalse(_is_drink(raw, key), key)

    def test_no_such_enemy_awake(self):
        def asleep(raw):
            for monster in raw["visible_monsters"]:
                monster["sleeping"] = True
                monster["asleep"] = True
        policy, raw, key = q25_boards.replay_until(TYRANNOSAUR, asleep)
        self.assertFalse(policy.last_reason.startswith("resist-potion"), policy.last_reason)

    def test_below_half_the_hp_it_is_not_drunk(self):
        # 522 against half of 1137.
        policy, raw, key = q25_boards.replay_until(TYRANNOSAUR, _with_hp(1137))
        self.assertFalse(policy.last_reason.startswith("resist-potion"), policy.last_reason)

    def test_the_plans_survival_rung_goes_first(self):
        # The plan's order beneath its 1-turn 即死 rung (owner 2026-11-07 「作戦が先・即死だけ例外」):
        # at HP 300 the tyrannosaur's next action reaches the HP, so the rung answers first now,
        # with the plan's own escape: the same Teleportation.
        with patch.object(threat_tiers, "instant_death_key", lambda *args: None):
            policy, raw, key = q25_boards.replay_until(TYRANNOSAUR, _with_hp(300))
        self.assertEqual(policy.last_reason, "quest-strategy:sweep-teleport")
        policy, raw, key = q25_boards.replay_until(TYRANNOSAUR, _with_hp(300))
        self.assertEqual(policy.last_reason, "quest-strategy:sweep-teleport")  # the plan's escape

    def test_a_race_with_no_such_breath_and_an_immune_player(self):
        race = next(monster["race_id"] for board in q25_boards.CASE["boards"] if board["turn"] == TYRANNOSAUR
                    for monster in board["visible_monsters"] if monster["name"] == TYRANNOSAUR_RACE_NAME)
        knowledge = q25_boards.q25.RACES[race]

        def immune_to(*names):
            def change(raw):
                raw["player"]["immunities"] = {name: {"equipment": True} for name in names}
            return change

        # The drinks of the last two: none since 2026-11-12 (D: on this board the prediction is
        # below half the HP, PlanFloorTest); ElementalBlowsTest keeps a drink.
        for abilities, change, drinks in ((frozenset({"BR_NETH"}), None, False),
                                          (frozenset({"BR_FIRE"}), immune_to("fire"), False),
                                          (frozenset({"BR_FIRE"}), None, False),
                                          # A ball, at half of an HP its prediction 420 reaches.
                                          (frozenset({"BA_ACID", "BR_NETH"}), _with_hp(800), False)):
            with self.subTest(abilities=abilities, immune=change is not None), patch.dict(
                    q25_boards.q25.RACES, {race: replace(knowledge, abilities=abilities)}):
                policy, raw, key = q25_boards.replay_until(TYRANNOSAUR, change)
                self.assertEqual(policy.last_reason == resist_potion.QUAFF_REASON, drinks, policy.last_reason)


class ElementalBlowsTest(unittest.TestCase):
    def test_the_drink_counts_for_elemental_blows_on_top_of_the_resistance(self):
        # The board beside the monster, with its breath all but silent and fire blows of 40d40:
        # the fight after the drink is winnable only by the second layer on those blows.
        race = next(monster["race_id"] for board in q25_boards.CASE["boards"] if board["turn"] == BESIDE_IT
                    for monster in board["visible_monsters"] if monster["name"] == TYRANNOSAUR_RACE_NAME)
        fire = replace(q25_boards.q25.RACES[race], abilities=frozenset({"BR_FIRE"}), spell_frequency=1,
                       blows=(MonsterBlow("BITE", "FIRE", 40, 40),))
        with patch.dict(q25_boards.q25.RACES, {race: fire}):
            policy, raw, key = q25_boards.replay_until(BESIDE_IT)
        self.assertEqual(policy.last_reason, resist_potion.QUAFF_REASON)


class PlacementOnThePlansBranchesTest(unittest.TestCase):
    """DECLARED CONSTRUCTED: where each plan asks; the judgement itself is patched to hold."""

    CHOKE = (1, 3)
    EXPOSED = (4, 10)

    def _q18(self, cell, *, kind=q18.SHARK, flags=frozenset(), across=3):
        race = replace(q18.RACES[kind], abilities=frozenset({"BR_FIRE"}), flags=flags or q18.RACES[kind].flags)
        raw = q18.board(cell, monsters=[q18.monster(kind, cell[0], cell[1] + across)], speed=0)
        raw["inventory"].append(q18.potion(SV_POTION_RESISTANCE, 1))
        with patch.dict(q18.RACES, {kind: race}), \
                patch.object(HengbotPolicy, "_is_material_threat", return_value=True), \
                patch.object(HengbotPolicy, "_engagement_is_winnable", return_value=True):
            return q18.decide(raw)[1]

    def test_find_exit_at_the_line(self):
        # What comes for the player, beside it (Q18ConstructedTest's squid).
        self.assertEqual(self._q18(self.CHOKE, kind=q18.SQUID, across=1), resist_potion.QUAFF_REASON)

    def test_find_exit_on_a_cell_the_casters_reach(self):
        self.assertEqual(self._q18(self.EXPOSED), resist_potion.QUAFF_REASON)

    def test_find_exit_with_nothing_that_comes(self):
        self.assertEqual(self._q18(self.CHOKE, flags=frozenset({"NEVER_MOVE"})), resist_potion.QUAFF_REASON)

    def test_room_sweep_with_only_what_it_leaves_alone_in_view(self):
        race = next(monster["race_id"] for board in q25_boards.CASE["boards"] if board["turn"] == TYRANNOSAUR
                    for monster in board["visible_monsters"])
        # A quiet rung of the plan with an answer: the drink stands before it.
        # The judgement itself patched to hold (the class's construction; since 2026-11-12 the
        # board's own prediction is below half the HP, PlanFloorTest).
        with patch.object(quest_room_sweep, "_left_alone_races", return_value={race}), \
                patch.object(quest_room_sweep, "_out_of_line", return_value="X"), \
                patch.object(HengbotPolicy, "_is_material_threat", return_value=True),                 patch.object(resist_potion, "_winnable_after_the_drink", return_value=True):
            policy, raw, key = q25_boards.replay_until(TYRANNOSAUR, lambda board: board.update(messages=[]))
        self.assertEqual(policy.last_reason, resist_potion.QUAFF_REASON)


class SharedLadderTest(unittest.TestCase):
    """The same boards on a floor with no plan (DECLARED CONSTRUCTED)."""

    def test_a_t3_fight_is_fought_without_the_drink(self):
        # Threat tiers step 6 (owner OQ-9, C-1): outside the plans the potion is drunk only in a
        # selected supply fight.  Alone, the tyrannosaur falls to the free attacks (T3: 750 over
        # the six turns to clear against HP 872), so it is shot, not drunk for (11-05 drank).
        policy, raw, key = _alone(TYRANNOSAUR)
        self.assertEqual(policy.last_reason, "ranged:fire")
        self.assertFalse(_is_drink(raw, key), key)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(threat_tiers.assess(policy, board, policy._physical_hostiles(board)).tier,
                         threat_tiers.T3)

    def test_no_chance_reads_the_teleport_where_the_prediction_is_below_the_hp(self):
        # 1242 below the HP: the emergency ladder lets it pass, and no attack comes first.  The
        # crowd is T1 (threat tiers step 6), so the flee rung above this rule reads the same
        # Teleportation first (before step 6 the rule's own no-chance leave read it).
        policy, raw, key = _alone(CROWD, _with_hp(1300, 1300))
        self.assertEqual(policy.last_reason, "flee:scroll")
        self.assertTrue(key.startswith("r"), key)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(threat_tiers.assess(policy, board, policy._physical_hostiles(board)).tier,
                         threat_tiers.T1)

    def test_no_chance_uses_destruction_before_the_scroll(self):
        with patch.object(destruction_use, "_carried_key", return_value="uX"):
            policy, raw, key = _alone(CROWD, _with_hp(1300, 1300))
        self.assertEqual((key, policy.last_reason), ("uX", destruction_use.REASON))

    def test_the_emergency_ladder_goes_first(self):
        # The prediction 1242 at HP 846: the ladder's lethal escape, whatever the potion would do.
        policy, raw, key = _alone(CROWD)
        self.assertFalse(policy.last_reason.startswith("resist-potion"), policy.last_reason)
        self.assertFalse(_is_drink(raw, key))

    def test_the_heal_of_the_emergency_ladder_goes_first(self):
        # Re-driven 2026-11-12 (t3-survival-1112 C, owner 「離れるのを先にする」): at HP 450,
        # below the low-HP line, beside the faster tyrannosaur the escape goes before the heal.
        policy, raw, key = _alone(TYRANNOSAUR, _with_hp(450))
        self.assertEqual(policy.last_reason, "emergency:teleport")
        self.assertFalse(_is_drink(raw, key))

    def test_the_flee_rung_goes_first(self):
        # Below the flee ratio, the prediction 522 below the HP (no emergency), the fight
        # unwinnable at 625 and nothing to heal with.
        def no_heal(raw):
            _with_hp(600, 2000)(raw)
            raw["inventory"] = [item for item in raw["inventory"]
                                if not (item["tval"] == TVAL_POTION and item["sval"] in HEAL_POTION_SVALS)]
        policy, raw, key = _alone(TYRANNOSAUR, no_heal)
        # Re-driven 2026-11-12 (t3-survival-1112 D, the game's spell odds): alone the
        # tyrannosaur's innate breath comes on fewer moves; the free attacks win (T3), so it is shot, not fled, and the drink is not reached either.
        self.assertEqual(policy.last_reason, "ranged:fire")
        self.assertFalse(_is_drink(raw, key))

    def test_no_potion_no_rule(self):
        def drunk(raw):
            raw["inventory"] = [item for item in raw["inventory"]
                                if not (item["tval"] == TVAL_POTION and item["sval"] == SV_POTION_RESISTANCE)]
        policy, raw, key = _alone(CROWD, lambda r: (_with_hp(1300, 1300)(r), drunk(r)))
        self.assertFalse(policy.last_reason.startswith("resist-potion"), policy.last_reason)


class TableTest(unittest.TestCase):
    def test_the_rule_owns_the_use_so_it_is_not_drunk_on_sight(self):
        potion = shop.item("p", TVAL_POTION, SV_POTION_RESISTANCE)
        entry = consumable_policy.row(potion)
        self.assertTrue(entry.use and entry.buy and entry.carry)
        self.assertFalse(consumable_policy.quaffed_on_sight(potion))


class BlackMarketTest(unittest.TestCase):
    """Bought by the buy-out's own line: 10-08's departure resupply stays in hand."""

    def _shelf(self, *wares, gold, inventory=None):
        policy = shop.HengbotPolicy()
        TOWN._declare_constructed_departure_prices(policy)
        town = TOWN._town(inventory=inventory, store=StoreState(STORE_BLACK, list(wares)), gold=gold)
        return policy, town

    def test_with_spare_money_the_shelf_is_bought(self):
        ware = shop.store_item("a", TVAL_POTION, SV_POTION_RESISTANCE, price=500, count=3)
        policy, town = self._shelf(ware, gold=10000)
        key = str(shop._public_shop_inner(self, policy, town))
        self.assertTrue(key.startswith(BUY_KEY + "a"), key)
        self.assertEqual(policy._purchase_quantity(town, ware), 3)

    def test_the_reserve_bounds_the_quantity(self):
        ware = shop.store_item("a", TVAL_POTION, SV_POTION_RESISTANCE, price=500, count=3)
        policy, town = self._shelf(ware, gold=1000)
        reserve = policy._full_departure_resupply_reserve(town)
        self.assertEqual(policy._purchase_quantity(town, ware), (1000 - reserve) // 500)

    def test_without_spare_money_it_is_not_bought(self):
        ware = shop.store_item("a", TVAL_POTION, SV_POTION_RESISTANCE, price=500, count=3)
        policy, town = self._shelf(ware, gold=400)
        self.assertIsNone(policy._next_purchase(town))
        self.assertFalse(str(shop._public_shop_inner(self, policy, town)).startswith(BUY_KEY))

    def test_the_kinds_that_save_a_life_come_first(self):
        resist = shop.store_item("a", TVAL_POTION, SV_POTION_RESISTANCE, price=500, count=3)
        speed = shop.store_item("b", TVAL_POTION, SV_POTION_SPEED, price=500, count=3)
        # Twenty carried and none of the other: the fewer held does not decide it.
        held = [*TOWN._supplies(), shop.item("s", TVAL_POTION, SV_POTION_SPEED, count=20)]
        policy, town = self._shelf(resist, speed, gold=10000, inventory=held)
        self.assertEqual(policy._next_purchase(town), speed)

    def test_a_full_pack_with_no_stack_to_join_buys_none(self):
        ware = shop.store_item("a", TVAL_POTION, SV_POTION_RESISTANCE, price=500, count=3)
        filler = [shop.item(f"x{index}", 70, 100 + index) for index in range(PACK_CAPACITY - len(TOWN._supplies()))]
        policy, town = self._shelf(ware, gold=10000, inventory=[*TOWN._supplies(), *filler])
        self.assertIsNone(policy._next_purchase(town))

    def test_elsewhere_it_is_not_bought(self):
        ware = shop.store_item("a", TVAL_POTION, SV_POTION_RESISTANCE, price=500, count=3)
        policy, town = self._shelf(ware, gold=10000)
        alchemist = replace(town, store=StoreState(shop.STORE_ALCHEMIST, [ware]))
        self.assertIsNone(policy._next_purchase(alchemist))

    def test_the_carried_stack_is_no_surplus_up_to_the_carry_cap(self):
        policy, town = self._shelf(gold=10000)
        carried = shop.item("p", TVAL_POTION, SV_POTION_RESISTANCE, count=12)
        self.assertEqual(policy._retention_surplus(town, carried), 2)


if __name__ == "__main__":
    unittest.main()
