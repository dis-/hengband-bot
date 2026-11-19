"""Owner 2026-11-18: the Magic-Eater's launcher at 50F+ (me_deep_launcher).

「50F以降の装備優先度について。魔道具術師については射撃威力を評価値から外し、弓枠は追加能力や
耐性のみで評価する。また、射撃威力が100ダメージ/ターンを下回る場合は矢も持たない。」

Recorded: the last town arrivals of the two viewing Magic-Eaters on 2026-11-18, both Lv50 at
80F, both wearing the 高速度のヘヴィ・クロスボウ (x4) (+10,+17) and choosing band 80
(tests/extract_me_deep_launcher_1118_fixtures.py; the loadout reports of the same visits
recorded that crossbow).  n1-b life-411's Home holds ★進化する銃『クリムゾン』 (+4 speed, r
shards and nether), n1-c life-216's ★バック郷のスリング (+3 speed, r blind, confusion, fear).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from hengbot import launcher_upgrade, me_deep_launcher
from hengbot.equipment_optimizer import (
    ABILITY_FLAG,
    EvaluatedLoadout,
    Loadout,
    LoadoutMetrics,
    OwnedEquipment,
    SLOT_BOW,
    _stable_operational_best,
    optimize_loadout,
)
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import InventoryItem
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "me-deep-launcher-1118"
WORN_CROSSBOW = "高速度のヘヴィ・クロスボウ (x4) (1.33turn) (+10,+17)"
CRIMSON = "★進化する銃『クリムゾン』"
BUCKLAND = "★バック郷のスリング"
PLAYER_CLASS_WARRIOR = 0
# Q2's and Q25's required force (strategy/quests/QUEST_2.jsonc, QUEST_25.jsonc).
RANGED_QUEST_FORCES = (
    {"launcher": {"ammo": "equipped", "equipped": True, "min_average_damage": 25},
     "throwing_items": {"launcher_ammo": 99}},
    {"ranged": {"shot_average": 65, "ammo": 40, "turn_average": 180, "device_classes": [16],
                "reference_race": 571},
     "throwing_items": {"launcher_ammo": 40}},
)


def _decide(policy, rows):
    """Decide and post the recorded rows (the n1-b fixture's Home scan)."""
    for row, supply in rows:
        policy.choose_key(supply())
        key = row["key"]
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def at_normal_speed(board):
    """``board`` with the player at +0 and no timed haste or slowness."""
    return replace(board, player=replace(board.player, speed=110, speed_display=None))


class RecordedBoard:
    """The arrival policy and the last kept board, after the earlier rows are decided."""

    def __init__(self, bot):
        self._scratch = TemporaryDirectory(prefix=f"me-deep-launcher-{bot}-")
        self.policy, _journal, rows = load(FIXTURE / bot, Path(self._scratch.name))
        _decide(self.policy, rows[:-1])
        self.board = rows[-1][1]()

    def close(self):
        self._scratch.cleanup()

    def optimize(self):
        self.policy._equipment_optimization_signature = None
        preparation = self.policy._prepare_equipment_optimization(
            self.policy._with_cached_skill_exp(self.board))
        return preparation.result

    def wearing(self, item):
        """The board with ``item`` worn in the bow slot (the optimizer's swap)."""
        worn = [kept for kept in self.board.equipment if kept.slot != SLOT_BOW]
        return replace(self.board, equipment=[*worn, replace(item, slot=SLOT_BOW)])

    def ammo(self, board):
        return [item for item in board.inventory if item.is_ammo]


class RecordedLoadoutTest(unittest.TestCase):
    """Before: both kept the crossbow for its power.  After: the bow slot is chosen by its flags."""

    def check(self, bot, expected):
        recorded = RecordedBoard(bot)
        self.addCleanup(recorded.close)
        result = recorded.optimize()
        self.assertEqual(result.chosen_depth, 80)
        bow = result.best.loadout.item_at(SLOT_BOW)
        self.assertNotEqual(bow.item.name, WORN_CROSSBOW)
        self.assertTrue(bow.item.name.startswith(expected), bow.item.name)
        self.assertEqual(bow.origin, "home")
        return recorded, result

    def test_n1b_wears_the_crimson_for_its_speed_and_resistances(self):
        _, result = self.check("n1-b", CRIMSON)
        # 14 before (the crossbow, recorded speed +14 with the gear): +4 more.
        self.assertEqual(result.best.metrics.speed_bonus, 18)
        # The reported metrics are the evaluated ones: the gun shoots nothing.
        self.assertEqual(result.best.metrics.ranged_dps, 0.0)

    def test_n1c_wears_bucklands_sling(self):
        _, result = self.check("n1-c", BUCKLAND)
        self.assertEqual(result.best.metrics.speed_bonus, 22)

    def test_a_pending_ranged_quest_changes_nothing(self):
        """Owner 2026-11-18 「魔道具術師は矢の威力ではなく魔法道具の攻撃力で評価する。装備優先度の
        例外にはしない。」: with Q25's force pending n1-c still wears Buckland's sling.

        DECLARED CONSTRUCTED: the quest the town prepares for is set to the approved Q25."""
        recorded = RecordedBoard("n1-c")
        self.addCleanup(recorded.close)
        quest = recorded.policy.approved_quest_strategy(25)
        self.assertIn("ranged", quest.required_force)
        with patch.object(type(recorded.policy), "_carry_procurement_strategy",
                          lambda _policy, _board, **_kwargs: quest):
            bow = recorded.optimize().best.loadout.item_at(SLOT_BOW)
        self.assertTrue(bow.item.name.startswith(BUCKLAND), bow.item.name)

    def test_a_warrior_of_the_same_board_keeps_the_crossbow(self):
        """The rule is the Magic-Eater's: as class 0 the same catalog keeps the crossbow."""
        recorded = RecordedBoard("n1-c")
        self.addCleanup(recorded.close)
        original = me_deep_launcher.launcher_power_unscored

        def as_warrior(class_id, depth, **kwargs):
            return original(PLAYER_CLASS_WARRIOR, depth, **kwargs)

        with patch.object(me_deep_launcher, "launcher_power_unscored", as_warrior):
            bow = recorded.optimize().best.loadout.item_at(SLOT_BOW)
        self.assertEqual(bow.item.name, WORN_CROSSBOW)


class RecordedAmmoTest(unittest.TestCase):
    """The carry target every purchase, Home withdrawal and retention reads."""

    def test_the_worn_crossbow_shoots_over_100_and_keeps_its_rounds(self):
        for bot, power in (("n1-b", 141.0), ("n1-c", 192.0)):
            with self.subTest(bot):
                recorded = RecordedBoard(bot)
                self.addCleanup(recorded.close)
                policy, board = recorded.policy, recorded.board
                # The best obtainable stack's figure: a Home stack (141/turn, 192/turn).
                self.assertEqual(me_deep_launcher.shot_power_per_turn(policy, board), power)
                self.assertFalse(me_deep_launcher.ammo_unneeded(policy, board))
                self.assertGreater(policy._ammo_procurement_target(board), 0)
                for item in recorded.ammo(board):
                    self.assertEqual(policy._retention_reservation(board, item), item.count)

    def test_n1c_with_bucklands_sling_carries_no_shots(self):
        """After the swap the sling's plain shot is 42.5 per turn: no shots are bought or kept.

        DECLARED CONSTRUCTED: the arrival board with the chosen sling worn (the swap the
        optimizer plans for this visit); the inventory is the recorded one."""
        recorded = RecordedBoard("n1-c")
        self.addCleanup(recorded.close)
        policy = recorded.policy
        sling = next(owned.item for owned in policy._equipment_catalog.items
                     if owned.item.name.startswith(BUCKLAND))
        worn = recorded.wearing(sling)
        # Owner 2026-11-19 「10ゲームターンあたりのダメージで評価して」: at the board's +19 (energy
        # 29) the 42.5 a turn is 123.25 per 10 game turns, over the floor: the rounds stay.
        self.assertEqual(me_deep_launcher.shot_power_per_10_game_turns(policy, worn), 123.25)
        self.assertFalse(me_deep_launcher.ammo_unneeded(policy, worn))
        # DECLARED CONSTRUCTED: the same at +0 (42.5 per 10 game turns) carries none.
        board = at_normal_speed(worn)
        self.assertEqual(me_deep_launcher.shot_power_per_turn(policy, board), 42.5)
        self.assertTrue(me_deep_launcher.ammo_unneeded(policy, board))
        # Before: 99 shots to buy (and the Weapon Smith reopened for them).
        self.assertEqual(policy._ammo_procurement_target(board), 0)
        policy._new_launcher_ammo = (policy._town_visit_epoch, sling.ammo_tval)
        self.assertIsNone(launcher_upgrade.ammo_work_tval(policy, board))
        # The carried bolts fit no launcher now: the existing rules release them.
        for item in recorded.ammo(board):
            self.assertEqual(policy._retention_reservation(board, item), 0)

    def test_weak_rounds_alone_are_not_carried(self):
        """n1-b with only its plain bolts (75/turn): none kept.

        DECLARED CONSTRUCTED: the recorded board without the (+7,+7) stack and with an
        empty Home ammunition list."""
        recorded = RecordedBoard("n1-b")
        self.addCleanup(recorded.close)
        policy = recorded.policy
        plain = [item for item in recorded.board.inventory
                 if not (item.is_ammo and item.to_d > 0)]
        plain_board = replace(recorded.board, inventory=plain)
        policy._equipment_catalog._home_ammunition = ()
        # Per 10 game turns at its +14 (energy 24): 180, over the floor (owner 2026-11-19).
        self.assertEqual(me_deep_launcher.shot_power_per_10_game_turns(policy, plain_board), 180.0)
        self.assertFalse(me_deep_launcher.ammo_unneeded(policy, plain_board))
        # DECLARED CONSTRUCTED: the same at +0 (75 per 10 game turns) keeps none.
        board = at_normal_speed(plain_board)
        self.assertEqual(me_deep_launcher.shot_power_per_turn(policy, board), 75.0)
        self.assertTrue(me_deep_launcher.ammo_unneeded(policy, board))
        self.assertEqual(policy._ammo_procurement_target(board), 0)
        for item in recorded.ammo(board):
            self.assertEqual(policy._retention_reservation(board, item), 0)


def _bow(item_id, *, to_d, flags=()):
    item = InventoryItem(
        slot=item_id, name=item_id, count=1, tval=19, sval=12, aware=True, known=True,
        fully_known=True, is_equipment=True, to_d=to_d, known_flags=frozenset(flags))
    return OwnedEquipment(item_id, item, "home")


def _entry(bow, *, ranged, survival, margin):
    return EvaluatedLoadout(
        Loadout(((SLOT_BOW, bow),), "empty"),
        LoadoutMetrics(expected_dps=100, survival_turns=survival, combat_margin=margin,
                       ranged_dps=ranged, player_speed=110))


class SelectionTest(unittest.TestCase):
    strong = _bow("strong bow", to_d=30)
    resisting = _bow("resisting bow", to_d=0, flags=(1,))

    def field(self):
        # The same survival: the strong bow wins on its shooting power alone.  The
        # resisting bow's flag is worth a slightly higher ratio (inside the 1% band).
        return (_entry(self.strong, ranged=200, survival=40, margin=10.0),
                _entry(self.resisting, ranged=10, survival=40, margin=10.05))

    def test_with_power_the_strong_bow(self):
        chosen = _stable_operational_best(self.field(), frozenset(), {"strong bow": 60.0})
        self.assertIs(chosen.loadout.item_at(SLOT_BOW), self.strong)

    def test_without_power_the_flags_decide_and_the_entry_is_returned_as_evaluated(self):
        field = self.field()
        chosen = _stable_operational_best(field, frozenset(), {"strong bow": 60.0},
                                          launcher_power=False)
        self.assertIs(chosen, field[1])
        self.assertEqual(chosen.metrics.ranged_dps, 10)

    def test_the_band_decides(self):
        """The descent's 80F band leaves the power out; the depth given as 49 keeps it."""
        metrics = {entry.loadout.item_at(SLOT_BOW).id: entry.metrics for entry in self.field()}

        def run(depth):
            return optimize_loadout(
                (self.strong, self.resisting),
                lambda loadout: metrics[loadout.item_at(SLOT_BOW).id],
                depth=depth,
                intrinsic_abilities=frozenset(ABILITY_FLAG),
                has_destruction=True,
                candidate_loadouts=tuple(Loadout(((SLOT_BOW, bow),), "empty")
                                         for bow in (self.strong, self.resisting)),
                require_light=False, require_body=False, require_armor_slots=frozenset(),
                launcher_power_unscored=lambda band: me_deep_launcher.launcher_power_unscored(
                    PLAYER_CLASS_MAGIC_EATER, band),
            ).best.loadout.item_at(SLOT_BOW)

        self.assertIs(run(None), self.resisting)
        self.assertIs(run(49), self.strong)
        self.assertIs(run(50), self.resisting)


class JudgementTest(unittest.TestCase):
    def test_class_and_depth(self):
        unscored = me_deep_launcher.launcher_power_unscored
        self.assertTrue(unscored(PLAYER_CLASS_MAGIC_EATER, 50))
        self.assertTrue(unscored(PLAYER_CLASS_MAGIC_EATER, 81))
        self.assertFalse(unscored(PLAYER_CLASS_MAGIC_EATER, 49))
        self.assertFalse(unscored(PLAYER_CLASS_MAGIC_EATER, None))
        self.assertFalse(unscored(PLAYER_CLASS_WARRIOR, 80))

    def test_the_floor_is_100_per_turn(self):
        def policy(figure, quest=None):
            ammo = SimpleNamespace(tval=18, count=10, name=f"bolt (1/shot {figure}/turn)")
            launcher = SimpleNamespace(sval=24, ammo_tval=18)
            return SimpleNamespace(
                _equipped_launcher=lambda _board: launcher,
                _obtainable_launcher_ammunition=lambda _board: (ammo,),
                _planned_depth=lambda: 80,
                _carry_procurement_strategy=lambda _board: quest,
                _quest_strategy_for_errand_or_floor=lambda _board: quest)

        # +0 (energy 10): the figure per 10 game turns is the per-turn one.
        board = SimpleNamespace(player=SimpleNamespace(class_id=PLAYER_CLASS_MAGIC_EATER, speed=110,
                                                       speed_display=None))
        self.assertTrue(me_deep_launcher.ammo_unneeded(policy(99), board))
        self.assertFalse(me_deep_launcher.ammo_unneeded(policy(100), board))
        # Owner 2026-11-18 「装備優先度の例外にはしない」: a pending ranged quest changes nothing.
        for force in RANGED_QUEST_FORCES:
            quest = SimpleNamespace(required_force=force)
            self.assertTrue(me_deep_launcher.ammo_unneeded(policy(99, quest), board))
            self.assertFalse(me_deep_launcher.ammo_unneeded(policy(100, quest), board))


if __name__ == "__main__":
    unittest.main()
