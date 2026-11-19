"""Owner 2026-11-18: the Magic-Eater meets Q2's, Q22's and Q31's launcher with its devices.

Owner (the chosen option, verbatim): 「魔道具術師は魔法道具の力で読む」 -- 「Q2・Q22・Q31 も Q25 と
同じく、取り込んだ攻撃の力（と攻撃の魔法棒・ロッド）の成功率込みの期待値と回数で条件を満たせば受ける。
足りない分だけ弓と矢で補う。」; earlier the same day 「魔道具術師は矢の威力ではなく魔法道具の攻撃力で
評価する。」.  quest_ranged_force reads the three quests' worn launcher (Q2's average 25 over the
carried rounds, owner 2026-11-02/11-03; Q22's 18; Q31's none) and their 99 rounds as Q25's
ranged requirement: a device counts when its success-weighted expected damage meets the per-shot
figure against every reference race, each charge one shot, and only the rounds the charges leave
are asked of the launcher.

Recorded boards:

- n1-b life-411 and n1-c life-216, the Lv50 Magic-Eaters' last town arrivals at 80F on
  2026-11-18 (tests/fixtures/me-deep-launcher-1118, the 50F+ launcher rule's boards).
  DECLARED CONSTRUCTED: both lives finished Q2, Q22 and Q31 long ago; the readiness of each
  quest's force is read on their boards (the force does not read the quest's status).
- n1-b life-398, the Lv19 Magic-Eater at Angwil before it took Q22 on 2026-11-15
  (tests/fixtures/n1b-398-q22-hold-1115, its first town-arrival row; Q22 and Q31 untaken),
  absorbed Magic Missile 17 charges at 90%, and its quest-floor boards in Q22.

The recorded policies were pickled with the strategies of their day: the tests read the
repository's strategy/quests (``_strategies``), which name ``launcher_devices``.  "Before" is the
same force without ``launcher_devices`` (the reading before this change).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot import me_deep_launcher, quest_ranged_force
from hengbot.model import parse_snapshot
from hengbot.quest_strategies import load_quest_strategies
from support.town_arrival_fixture import load
from tests.test_me_deep_launcher_1118 import BUCKLAND, RecordedBoard, at_normal_speed
from tests import test_n1b_398_q22_hold_1115_recorded as n1b398

STRATEGIES = Path(__file__).resolve().parents[1] / "strategy" / "quests"
N1B_398 = Path(__file__).with_name("fixtures") / "n1b-398-q22-hold-1115"
LAUNCHER_CARRIES = ("launcher", "launcher.average_damage", "throwing_items.launcher_ammo")
TVAL_BOW = 19


def _strategies(policy):
    """The repository's strategies (the pickled policy holds the recording day's)."""
    policy._quest_strategies = load_quest_strategies(STRATEGIES)


def _before(force):
    """The force as read before this change: no ``launcher_devices``."""
    return {name: value for name, value in force.items()
            if name != quest_ranged_force.LAUNCHER_DEVICES}


def _readiness(policy, board, quest_id):
    ready = policy._approved_strategy_force_ready(board, policy.approved_quest_strategy(quest_id))
    return ready, policy._fixed_quest_readiness["strategy_force"]


def _carries(policy, board, force):
    return {name: (status["measured"], status["required"])
            for name, status in policy._quest_carry_status(board, force).items()
            if name in LAUNCHER_CARRIES}


class DeepMagicEaterTest(unittest.TestCase):
    """Lv50: the absorbed bolts and balls cover every round of the three quests."""

    # (quest, the device shots counted, the best counted use) per bot.
    COVER = {"n1-b": ((2, 267, 268.0), (22, 411, 268.0), (31, 494, 384.0)),
             "n1-c": ((2, 313, 340.0), (22, 532, 340.0), (31, 562, 392.0))}

    def recorded(self, bot):
        recorded = RecordedBoard(bot)
        self.addCleanup(recorded.close)
        _strategies(recorded.policy)
        return recorded.policy, recorded.board

    def test_before_the_launcher_and_its_99_rounds_were_asked(self):
        policy, board = self.recorded("n1-b")
        force = _before(policy.approved_quest_strategy(2).required_force)
        carries = _carries(policy, board, force)
        self.assertEqual(carries["launcher"], (1, 1))
        self.assertEqual(carries["throwing_items.launcher_ammo"], (95, 99))
        self.assertEqual(carries["launcher.average_damage"][1], 25.0)

    def test_after_the_devices_meet_the_three_quests(self):
        for bot, quests in self.COVER.items():
            policy, board = self.recorded(bot)
            for quest_id, shots, best in quests:
                with self.subTest(bot=bot, quest=quest_id):
                    force = policy.approved_quest_strategy(quest_id).required_force
                    ranged = quest_ranged_force.ranged_requirement(force)
                    self.assertEqual(quest_ranged_force._devices(
                        policy, board, ranged, ranged["shot_average"]), (best, shots))
                    _ready, details = _readiness(policy, board, quest_id)
                    # No launcher, no average, no rounds: nothing to buy, withdraw or keep.
                    self.assertFalse(set(details["carries"]) & set(LAUNCHER_CARRIES))
                    found = details["ranged"]["shots"]
                    self.assertEqual((found["device"], found["required"]), (shots, 99))
                    self.assertGreaterEqual(found["measured"], 99)
                    self.assertNotIn("ranged", details["failed"])
                    self.assertFalse(details["ranged"]["short"])

    def test_the_carried_bolts_are_no_quest_carry(self):
        policy, board = self.recorded("n1-b")
        force = policy.approved_quest_strategy(2).required_force
        bolts = [item for item in board.inventory if item.is_ammo]
        self.assertTrue(bolts)
        for item in bolts:
            self.assertEqual(policy._quest_carry_target_for_item(board, item, _before(force))[0::2],
                             ("launcher_ammo", 99))
            self.assertIsNone(policy._quest_carry_target_for_item(board, item, force))
        # The optimizer keeps no quest launcher family (policy_equipment required_launcher_ammo).
        self.assertIsNone(policy._quest_launcher_ammo(
            board, quest_ranged_force.settled_force(policy, board, force)))
        self.assertEqual(policy._quest_launcher_ammo(board, _before(force)), 18)

    def test_the_50f_rule_and_the_quest_agree_on_no_rounds(self):
        """n1-c with Buckland's sling worn (the swap its 80F selection plans): the 50F+ rule
        carries no shots, and Q2 asks none either, so no purchase or Home trip opposes the
        deposit (owner 2026-11-18 「射撃威力が100ダメージ/ターンを下回る場合は矢も持たない」).

        DECLARED CONSTRUCTED: the arrival board with the chosen sling worn, at +0 (owner 2026-11-19
        「10ゲームターンあたりのダメージで評価して」: at the board's +19 the sling's 42.5 a turn is
        123.25 per 10 game turns and the rounds stay, test_me_deep_launcher_1118)."""
        recorded = RecordedBoard("n1-c")
        self.addCleanup(recorded.close)
        policy = recorded.policy
        _strategies(policy)
        sling = next(owned.item for owned in policy._equipment_catalog.items
                     if owned.item.name.startswith(BUCKLAND))
        board = at_normal_speed(recorded.wearing(sling))
        self.assertTrue(me_deep_launcher.ammo_unneeded(policy, board))
        self.assertEqual(policy._ammo_procurement_target(board), 0)
        for quest_id in (2, 22, 31):
            with self.subTest(quest=quest_id):
                force = quest_ranged_force.settled_force(
                    policy, board, policy.approved_quest_strategy(quest_id).required_force)
                self.assertNotIn("launcher", force)
                self.assertNotIn("launcher_ammo", force["throwing_items"])
                self.assertFalse(force.get(quest_ranged_force.SHORT))


class Lv19MagicEaterTest(unittest.TestCase):
    """n1-b life-398 at Angwil: Magic Missile (10.5 x 90%) is below Q22's 18, not below Q31's none."""

    def setUp(self):
        scratch = TemporaryDirectory(prefix="me-quest-device-n1b398-")
        self.addCleanup(scratch.cleanup)
        self.policy, _journal, rows = load(N1B_398, Path(scratch.name))
        _strategies(self.policy)
        self.board = rows[0][1]()
        self.assertEqual((self.board.player.level, self.board.player.class_id), (19, 16))
        self.assertTrue(self.board.in_town)

    def test_q22_keeps_the_launcher_and_its_99_rounds(self):
        force = self.policy.approved_quest_strategy(22).required_force
        self.assertEqual(_carries(self.policy, self.board, force),
                         _carries(self.policy, self.board, _before(force)))
        self.assertEqual(_carries(self.policy, self.board, force)["throwing_items.launcher_ammo"],
                         (62, 99))

    def test_q31_counts_the_17_missiles_and_asks_82_rounds(self):
        force = self.policy.approved_quest_strategy(31).required_force
        self.assertEqual(_carries(self.policy, self.board, _before(force))[
            "throwing_items.launcher_ammo"], (62, 99))
        self.assertEqual(_carries(self.policy, self.board, force)["throwing_items.launcher_ammo"],
                         (62, 82))
        _ready, details = _readiness(self.policy, self.board, 31)
        self.assertEqual(details["ranged"]["shots"]["device"], 17)

    def test_a_50f_plan_closes_the_remainder_instead_of_buying_it(self):
        """The 50F+ rule carries no rounds below 100 per turn (this crossbow: 60): Q31's 82 are
        not asked (no purchase or Home trip against the deposit) and the quest is refused.

        DECLARED CONSTRUCTED: the departure planned for 80F (``_planned_depth``)."""
        with patch.object(type(self.policy), "_planned_depth", lambda _policy: 80):
            self.assertTrue(me_deep_launcher.ammo_unneeded(self.policy, self.board))
            self.assertEqual(self.policy._ammo_procurement_target(self.board), 0)
            force = self.policy.approved_quest_strategy(31).required_force
            self.assertEqual(_carries(self.policy, self.board, force), {})
            for item in self.board.inventory:
                if item.is_ammo:
                    self.assertIsNone(self.policy._quest_carry_target_for_item(
                        self.board, item, force))
            settled = quest_ranged_force.settled_force(self.policy, self.board, force)
            self.assertFalse(quest_ranged_force.ready(self.policy, self.board, settled))
            ready, details = _readiness(self.policy, self.board, 31)
            self.assertFalse(ready)
            self.assertTrue(details["ranged"]["short"])


class QuestFloorFireTest(n1b398.N1b398Q22Hold1115RecordedTest):
    """In Q22 the ranged plan shoots the devices when no launcher is worn.

    DECLARED CONSTRUCTED: the recorded quest-floor board (an orc two cells north) with the
    crossbow taken off; the recorded board keeps it and fires it (60/turn over the missile's 9.45).
    """
    test_the_visit_and_the_opening_decide_as_recorded = None
    test_the_emergency_landing_walks_to_the_hold_nearest_it = None
    test_a_landing_six_steps_from_the_east_hold_walks_east = None

    def test_the_missile_answers_without_the_crossbow(self):
        _strategies(self.policy)
        profile = self.policy.approved_quest_strategy(22)
        board = self.policy.with_known_skill_exp(
            parse_snapshot(self.raw(self.boards[14]), self.policy._monrace_knowledge))
        hostiles = list(board.visible_monsters)
        self.assertEqual([(monster.race_id, monster.distance) for monster in hostiles], [(244, 2)])
        self.assertEqual(self.policy._q2_ranged_core_key(board, profile, hostiles), "fi8")
        bare = replace(board, equipment=[item for item in copy.copy(board.equipment)
                                         if item.tval != TVAL_BOW])
        self.assertEqual(self.policy._q2_ranged_core_key(bare, profile, hostiles), "mBp8")
        self.assertEqual(self.policy.last_reason, "quest-strategy:ranged-fire:magic-eater")


if __name__ == "__main__":
    unittest.main()
