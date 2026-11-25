"""n1-c life-220 2026-11-22 19:35:52-19:36:01 (Quest 33): held to death under sensed fire.

Recorded: the death capture C:/hengband-backups/pdca/n1c-220-q33-death/ (bot main 30e054b0c),
reduced by tests/extract_n1c_220_q33_sensed_1122_fixture.py (tests/fixtures/n1c-220-q33-sensed-1122):
the decisions 10884-10959 and the last 62 boards.  After the summon answer's disengage the plan was
in its steps after it (quest_summon_answer.after_key).  Two 船幽霊 (race 1389, AQUATIC, BO_WATE
10d10+25) in the deep water at [4,41] and [5,41] were known by telepathy only (the board's
``detected_monsters``, esp; ``visible_monsters`` empty: the player's view, bot-json-output.cpp
make_visible_monsters_json) and cast water bolts at the player on [1,27].  The plan's board read no
enemy (quest_plan_base.Board.enemy: in view, or the unseen's hit, which the named casts never were),
so its quiet branch ran, which has no 即死, withdrawal, heal or haste rung; after_key read the
casters as coming (a caster with a line stays and casts, quest_wait_placement) and held '5' 23 times
in a row, HP 811 to death, with the haste run out at 19:35:56 and !Healing 3, ?Teleportation 6,
absorbed Teleportation 20 and absorbed Speed 38 left.

Pinned, through the public choose_key:

* A (owner: Q33 strategy's survival lines -- 即死 is the teleport, the withdrawal line 40%, the heal
  line 50%; the Magic-Eater's haste in fights 2026-11-04): the casters are the board's enemy
  (``Board.firing``), and the plan's survival rungs answer them: the absorbed Speed once the haste
  has run out, the Healing potion below 50%, the absorbed Teleportation below 40% and on 即死.
* B: above those lines the casters, telepathy-seen with a line from the player, are shot
  (quest_summon_answer ``_strike_around``), not held for.
* C (owner 2026-11-19 「地形と敵の位置、敵のアルゴリズムを確認して有効な場所で待つ」): with no shot at
  them, the player closes on the dry cells beside them a blow reaches (they never leave the water;
  ``attack_cells``, n1-a life-537 2026-11-25), and with neither a shot nor a blow he leaves their
  line (``fire_answer_key``); he never holds in it.

DECLARED CONSTRUCTED (the choose_key replay): the policy is n1-c life-217's town arrival
(tests/test_quest33_alignment_split ``recorded``), not life-220's; the Q33 navigator is put in the
disengaged state the capture's plan was in; the board's skill-list values are filled (that policy
never read life-220's ~f list); the policy's displayed power lists are life-217's, re-dated to before
the boards (their own turn is later than these boards', which reads as a new life,
me_device_attacks.observe_lists), and its absorption record is given life-220's Teleportation (20)
and Speed (38) counts.  The recorded boards never show a teleport's landing, so the plan's
heal-after-teleport latch (navigator ``sweep_heal_next``) is cleared before the 即死 board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import me_absorbed_substitutes, me_capability, quest_plan_base, quest_room_sweep, quest_summon_answer
from hengbot.model import SV_STAFF_SPEED, SV_STAFF_TELEPORTATION, Position, parse_snapshot
from hengbot.policy_constants import REST_MACRO, WAIT_KEY
from hengbot.quest_plan_base import _navigator
from tests.test_quest33_alignment_split import QUEST, quest_dir, recorded

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-220-q33-sensed-1122"
HOLD_CELL = Position(1, 27)
# On the 船幽霊's line of fire (the cells it crosses toward [1,27]) and 8 grids from [5,41]: within the
# bot's reach for a shot (RANGED_MAX_DISTANCE 10), as [1,27] (14 grids) is not.
SHOT_CELL = Position(3, 33)
SHIP_CELLS = {"@4,41", "@5,41"}
# Within the 船幽霊's vision (20) and with no line of fire from them: they act on the player there
# (quest_summon_answer.acting_around) and never come (AQUATIC, in deep water).
ACTED_ON_CELL = Position(1, 22)
LIST_READ_REASON = "periodic:magic-eater-powers"
HASTED_BOARDS = 13  # the boards before the haste ran out at 19:35:56 (HP 682 to 634)
PHANTOM_SHIP = 1389
INSTANT_DEATH_TURN = 3211903  # HP 119, the capture's 即死 (p95 164)
ABSORBED = {me_capability.record_key("staff", SV_STAFF_TELEPORTATION): 20,
            me_capability.record_key("staff", SV_STAFF_SPEED): 38}


def load(name):
    return json.loads(lzma.decompress((FIXTURE / name).read_bytes()))


class N1c220SensedRecordTest(unittest.TestCase):
    def test_the_record_is_the_death(self):
        rows = load("decisions.json.xz")
        holds = [row for row in rows if (row["position"]["y"], row["position"]["x"]) == (1, 27)]
        self.assertEqual({(row["reason"], row["key"]) for row in holds}, {(quest_room_sweep.HOLD_REASON, WAIT_KEY)})
        self.assertEqual(len(holds), len(rows))
        self.assertEqual((rows[0]["hp"], rows[-1]["hp"]), (811, 8))
        self.assertTrue(rows[-1]["instant_death"])
        for raw in load("boards.json.xz"):
            self.assertEqual(raw["visible_monsters"], [])
            self.assertEqual({(m["race_id"], m["esp"], m["asleep"]) for m in raw["detected_monsters"]},
                             {(PHANTOM_SHIP, True, False)})


class N1c220SensedChooseKeyTest(unittest.TestCase):
    def setUp(self):
        if quest_dir() is None:
            self.skipTest("the Hengband quest data is not available")
        self.scratch, self.policy, _town = recorded("n1c-217")
        self.addCleanup(self.scratch.cleanup)
        self.lists = {kind: (0, *rest) for kind, (_turn, *rest) in self.policy._me_device_lists.items()}

    def snapshot(self, raw):
        snapshot = parse_snapshot(raw, self.policy._monrace_knowledge)
        return replace(snapshot, player=replace(snapshot.player, two_weapon_skill=0, shield_skill=0))

    def answers(self, *, at=None, boards=None, disengaged=True, full_hp=False, kinds=None):
        """choose_key over the recorded boards (the first ``boards``), the player on ``at`` if given;
        ``disengaged``: the plan in the summon answer's steps after a disengage (else its own fight);
        ``full_hp``: the HP at its maximum; ``kinds``: the displayed power lists kept (None: all)."""
        out = []
        lists = {kind: rows for kind, rows in self.lists.items() if kinds is None or kind in kinds}
        for raw in load("boards.json.xz")[:boards]:
            if at is not None:
                raw = {**raw, "player": {**raw["player"], "y": at.y, "x": at.x}}
            if full_hp:
                raw = {**raw, "player": {**raw["player"], "hp": raw["player"]["max_hp"]}}
            snapshot = self.snapshot(raw)
            navigator = _navigator(self.policy, snapshot, QUEST)
            if not disengaged:
                navigator.summon_state = None
            elif navigator.summon_state is None:
                navigator.summon_state = quest_summon_answer.DISENGAGED
            if snapshot.turn == INSTANT_DEATH_TURN:
                navigator.sweep_heal_next = False
            self.policy._me_device_lists = dict(lists)
            self.policy._me_staff_sequence.absorbed.update(ABSORBED)
            key = str(self.policy.choose_key(snapshot))
            out.append((snapshot, self.policy.last_reason, key))
            self.policy.confirm_key_posted(key)
        return out

    def test_the_casters_are_the_boards_enemy(self):
        profile = self.policy.approved_quest_strategy(QUEST)
        plan = profile.engagement_plan["room_sweep"]
        for raw in load("boards.json.xz"):
            snapshot = self.snapshot(raw)
            navigator = _navigator(self.policy, snapshot, QUEST)
            board = quest_room_sweep._Board(self.policy, snapshot, profile, navigator, plan)
            self.assertEqual(board.in_view, [])
            self.assertTrue(board.firing, snapshot.turn)
            self.assertEqual({monster.race_id for monster in board.firing}, {PHANTOM_SHIP})
            self.assertTrue(board.enemy)

    def test_survival_lines_answer_the_sensed_fire(self):
        answers = self.answers()
        speed = me_absorbed_substitutes.POWERS[("staff", SV_STAFF_SPEED)]
        teleport = me_absorbed_substitutes.POWERS[me_absorbed_substitutes.TELEPORTATION]
        unhasted = next(answer for answer in answers if not self.policy._player_hasted(answer[0])
                        and answer[0].player.hp_ratio >= 0.5)
        self.assertEqual(unhasted[1:], (quest_plan_base.SPEED_REASON + me_absorbed_substitutes.CAST_SUFFIX,
                                        speed.key))
        below_heal = next(answer for answer in answers if answer[0].player.hp_ratio < 0.5)
        self.assertEqual(below_heal[1], quest_plan_base.HEAL_REASON)
        self.assertTrue(below_heal[2].startswith("q"), below_heal[2])
        below_line = next(answer for answer in answers if answer[0].player.hp_ratio <= 0.4)
        self.assertEqual(below_line[1:], (quest_plan_base.TELEPORT_REASON + me_absorbed_substitutes.CAST_SUFFIX,
                                          teleport.key))
        instant = next(answer for answer in answers if answer[0].turn == INSTANT_DEATH_TURN)
        self.assertEqual(instant[0].player.hp, 119)
        self.assertEqual(instant[1:], (quest_plan_base.TELEPORT_REASON + me_absorbed_substitutes.CAST_SUFFIX,
                                       teleport.key))
        for snapshot, reason, key in answers:
            self.assertEqual(snapshot.player.position, HOLD_CELL)
            if snapshot.player.hp_ratio < 0.5:
                self.assertNotEqual((reason, key), (quest_room_sweep.HOLD_REASON, WAIT_KEY), snapshot.turn)

    def test_a_sensed_caster_in_reach_is_shot(self):
        # DECLARED CONSTRUCTED: the recorded boards with the player on SHOT_CELL (the boards while the
        # haste lasted and the HP stood above the heal line).
        # After the disengage (quest_summon_answer ``_strike_around``) and in the plan's own fight
        # (quest_room_sweep ``_fight``).
        for disengaged in (True, False):
            with self.subTest(disengaged=disengaged):
                for snapshot, reason, key in self.answers(at=SHOT_CELL, boards=6, disengaged=disengaged):
                    self.assertEqual(snapshot.player.position, SHOT_CELL)
                    self.assertEqual(reason, "ranged:magic-eater-device", snapshot.turn)
                    self.assertIn(key[key.index("@"):], SHIP_CELLS)

    def assert_no_hold(self, answers):
        for snapshot, reason, key in answers:
            self.assertNotEqual((reason, key), (quest_room_sweep.HOLD_REASON, WAIT_KEY), snapshot.turn)

    def test_casters_out_of_reach_are_closed_on(self):
        # The recorded boards while the haste lasted: 14 grids off, beyond the bot's shot, the player
        # walks toward a cell the shot is taken from instead of holding in their line.
        for disengaged in (True, False):
            with self.subTest(disengaged=disengaged):
                answers = self.answers(boards=HASTED_BOARDS, disengaged=disengaged)
                self.assert_no_hold(answers)
                self.assertEqual({reason for _snapshot, reason, _key in answers},
                                 {quest_summon_answer.FIRE_APPROACH_REASON})

    def test_without_a_shot_the_shore_is_closed_on(self):
        # DECLARED CONSTRUCTED: only the staff list displayed (no absorbed attack power; life-220
        # carried no rounds for its launcher): no shot reaches the casters from anywhere.  The
        # 船幽霊 never leave the water (AQUATIC) and a blow reaches them from the dry cells beside it
        # (quest_summon_answer ``attack_cells``, n1-a life-537 2026-11-25): the player closes on
        # them there, not waits in their line nor walks out of it for the lure to walk back.
        for disengaged in (True, False):
            with self.subTest(disengaged=disengaged):
                answers = self.answers(boards=HASTED_BOARDS, disengaged=disengaged, kinds={"staff"})
                self.assert_no_hold(answers)
                # Between the walks the policy asks for the power lists it does not hold
                # (me_powers_refresh), as the rest-loop replay of this life does.
                reasons = [reason for _snapshot, reason, _key in answers]
                self.assertLessEqual(set(reasons), {quest_summon_answer.FIRE_APPROACH_REASON, LIST_READ_REASON})
                self.assertIn(quest_summon_answer.FIRE_APPROACH_REASON, reasons)

    def test_without_a_shot_nor_a_blow_the_line_is_left(self):
        # DECLARED CONSTRUCTED: as above, and no blow reaches the casters either (the melee expectation
        # read as 0): no cell kills them, so the player leaves their line.
        from unittest.mock import patch

        with patch.object(quest_summon_answer.attack_expectation, "melee", return_value=0.0):
            answers = self.answers(boards=HASTED_BOARDS, kinds={"staff"})
        self.assert_no_hold(answers)
        reasons = [reason for _snapshot, reason, _key in answers]
        self.assertLessEqual(set(reasons), {quest_summon_answer.FIRE_WALK_REASON, LIST_READ_REASON})
        self.assertIn(quest_summon_answer.FIRE_WALK_REASON, reasons)

    def test_a_caster_that_never_comes_is_not_waited_for(self):
        # DECLARED CONSTRUCTED: the player on ACTED_ON_CELL at full HP.  The AQUATIC casters act on
        # him there and never come: the plan closes on them (the lure's walk to a cell they would be
        # seen from), not holds for the plan's 200-hold wait.
        answers = self.answers(at=ACTED_ON_CELL, boards=8, full_hp=True)
        self.assert_no_hold(answers)
        self.assertIn(quest_summon_answer.LURE_WALK_REASON, {reason for _snapshot, reason, _key in answers})


class Q18SensedFireTest(unittest.TestCase):
    """The same reading on Quest 18's own board (quest_find_exit ``_Board.engaged``): a hostile known
    by telepathy only that fires at the player is no quiet floor to rest on.

    DECLARED CONSTRUCTED: test_q18_water_cave's board (the recorded n1-c Q31 board on the real
    018_WaterCave map) on its choke (1,12) at half HP, a 巨大イカ (482, AQUATIC, BR_ELEC/ACID/POIS)
    in the deep water at (5,8), shown by telepathy, with a line to the choke."""

    def test_hurt_under_sensed_fire_is_answered_not_rested(self):
        from tests.test_q18_water_cave import FULL_HP, HEAL_REASON, Q18ClearBeforeAdvancingTest, board, monster

        quiet = board(Q18ClearBeforeAdvancingTest.CHOKE, hp=FULL_HP // 2)
        fired_at = board(Q18ClearBeforeAdvancingTest.CHOKE, hp=FULL_HP // 2)
        fired_at["detected_monsters"] = [dict(monster(482, 5, 8), esp=True, detected=False)]
        runner = Q18ClearBeforeAdvancingTest()
        self.assertEqual(runner.run_boards([quiet]), [(REST_MACRO, "rest")])
        (key, reason), = runner.run_boards([fired_at])
        self.assertEqual(reason, HEAL_REASON)
        self.assertTrue(key.startswith("q"), key)


if __name__ == "__main__":
    unittest.main()
