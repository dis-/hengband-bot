"""D57 (#47): two owner answers of 2026-11-01 on the n1-c Magic-Eater deaths.

(a) life-079 (Lv12, 151 max HP, 鉄獄12階, build 04ad2c6d2, 04:28):
「その階の間覚えて隣を避ける」.  The absorbed Detect Evil showed a デスソード
(race 107, NEVER_MOVE, speed +20, SLASH 5d5 x2) at (14,63) on the board of
turn 600499; from the next board on the game no longer listed it, the descent
route walked (5,57) -> (12,61) and its '3' at turn 600610 stepped to (13,62)
beside it: HP 151 -> -2 in one step (「デスソードに斬られた。」).

(b) life-083 (Lv14, 171 max HP, 迷宮12階, build c326f0fd6): 「代わりのダンジョン
も数える」.  A dive of the over-extension alternate (the Labyrinth) with seven
emergency escapes and no pickup ended by Word of Recall at turn 1187204.
life-083 had not unlocked Angband's recall, so the Labyrinth was its target
and the dive advanced the streak (recorded row 5357: 1 -> 2).  Once Angband's
recall is unlocked (life-084 and life-085 had it, at the same Labyrinth
depths) the target is Angband and the alternate's dives were judged on the
guardian bounce alone: the same dive left the streak where it was.

Fixtures: tests/fixtures/d57-n1c-079-1101.json.gz, d57-n1c-083-1101.json.gz
(tests/extract_d57_nav_depth_1101_fixtures.py).  Every decision is the public
``choose_key`` and every posted key goes through the production executor port;
the executor's board after a posted key (the next recorded board, with the
completed-operation provenance the executor adds) is the next decision's
board, as in the live driver.
DECLARED RECONSTRUCTED: the over-extension state at the start of the life-083
drive is the first recorded row's ``over_extension`` (alternate 4, streak 1,
last over-extended depth 11) with the switch reason ``over_extended_dives``;
the staff sequence record is the capture's ``_me_staff_sequence``.
DECLARED CONSTRUCTED: the Angband-unlocked drive sets
``progress.angband_recall_unlocked`` on the life-083 boards; the control of
(a) gives the player 400 HP on every board; the third-dive case starts the
streak at 2.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import immobile_threat_memory, me_powers
from hengbot.cli import SendResult, _ExecutorInputPort, _transport_key
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.magic_eater import MISSILE_REASON
from hengbot.me_staff_sequence import POWER_NAMES
from hengbot.model import Position
from hengbot.policy_constants import DIRECTION_KEYS
from tests import test_me_staff_loops_1031_recorded as loops
from tests import test_n1c_deaths_1101_recorded as d57
from tests.support.recorded import FaithfulHookGame, command_screen, prompt_screen
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests.test_me_stage2_powers import TYPE_PROMPT


FIXTURES = Path(__file__).with_name("fixtures")


def _load(name):
    with gzip.open(FIXTURES / f"d57-n1c-{name}-1101.json.gz", "rt", encoding="utf-8") as stream:
        return json.load(stream)


CASE_079, CASE_083 = _load("079"), _load("083")
DEATH_SWORD, SWORD_CELL = 107, Position(14, 63)
DETECTED_TURN, LAST_TURN = 600499, 600610
ARRIVAL_TURN = 1187204
LABYRINTH, ORC_CAVE = 4, 3
# The game's prompts of the two-key commands these drives post.
PROMPTS = {**d57.PROMPTS, "r": "どの巻物を読みますか? ",
           "R": "休憩 (0-9999, '*' で HP/MP全快, '&' で必要なだけ): &"}
STEPS = {key: offset for offset, key in DIRECTION_KEYS.items()}


def new_policy(case, boards=None):
    """d57's recorded Magic-Eater policy with the frozen dungeon definitions."""
    policy = d57.new_policy(case if boards is None else dict(case, boards=boards))
    policy._dungeon_knowledge = {
        int(key): DungeonInfo(**dict(row, flags=frozenset(row["flags"])))
        for key, row in case["dungeons"].items()}
    return policy


class RecordedDrive(d57.PostedDeathKey):
    """Drive recorded boards; each posted key's executor board is the next board."""

    def send(self, policy, raw, key, following, absorbed):
        if policy.last_reason == MISSILE_REASON:
            super().post(policy, raw, key)  # the Magic Missile's own power game
            return following
        screens = []
        if policy.last_reason.startswith(me_powers.REASON + ":"):
            rows = [(me_powers.encode_letter(sval), POWER_NAMES[sval][0], count, 30, 20)
                    for sval, count in sorted(absorbed.items()) if sval in POWER_NAMES]
            screens = [prompt(TYPE_PROMPT), power_screen("staff", rows)]
        elif len(key) > 1 and key[0] in PROMPTS:
            screens = [prompt_screen(PROMPTS[key[0]])]
        final = command_screen(following["turn"])
        if following["messages"]:  # the message line the game shows after the command
            final["lines"][0] = following["messages"][0].split(" <x")[0]
        game = FaithfulHookGame()
        game.capacity = 256
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [*screens, final]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual("".join(game.accepted), _transport_key(key, True))
        return port.last_result.board

    def drive_boards(self, case, boards, policy):
        absorbed = {int(sval): count for sval, count in case["sequence"]["absorbed"].items()}
        rows, raw = [], boards[0]
        for following in [*boards[1:], None]:
            key = loops.decide(policy, raw)
            rows.append((raw, key, policy.last_reason))
            if following is None:
                break
            if key:
                following = self.send(policy, raw, key, following, absorbed)
                policy.confirm_key_posted(key)
            raw = following
        return rows


def step_of(raw, key):
    """The cell a walk (or door-opening) key moves toward, else None."""
    if not key or key[-1] not in STEPS or key[:-1] not in {"", "o"}:
        return None
    dy, dx = STEPS[key[-1]]
    return Position(raw["player"]["y"] + dy, raw["player"]["x"] + dx)


def with_hp(boards, hp):
    for raw in boards:
        raw["player"]["hp"] = raw["player"]["max_hp"] = hp
    return boards


class DetectedDeathSwordRecordedTest(RecordedDrive):
    """life-079: the detected never-moving デスソード is remembered and avoided."""

    def boards(self):
        return copy.deepcopy(CASE_079["boards"])

    def test_recorded_rows(self):
        boards = {raw["turn"]: raw for raw in CASE_079["boards"]}
        self.assertEqual([(m["race_id"], m["y"], m["x"]) for m in boards[DETECTED_TURN]["detected_monsters"]
                          if m["race_id"] == DEATH_SWORD], [(DEATH_SWORD, SWORD_CELL.y, SWORD_CELL.x)])
        self.assertTrue(all(not raw["detected_monsters"] and not raw["visible_monsters"]
                            for turn, raw in boards.items() if turn > DETECTED_TURN))
        self.assertIn("NEVER_MOVE", CASE_079["monraces"][str(DEATH_SWORD)]["flags"])
        rows = d57.recorded(CASE_079)
        self.assertEqual(rows[LAST_TURN], ("approach-descent", "3"))
        step = step_of(boards[LAST_TURN], "3")
        self.assertEqual((step, step.distance_to(SWORD_CELL)), (Position(13, 62), 1))

    def test_descent_route_keeps_off_the_remembered_death_sword(self):
        policy = new_policy(CASE_079)
        rows = self.drive_boards(CASE_079, self.boards(), policy)
        self.assertEqual(rows[-1][0]["turn"], LAST_TURN)
        steps = [(raw["turn"], key, reason, step_of(raw, key)) for raw, key, reason in rows]
        self.assertTrue(any(reason == "approach-descent" for _t, _k, reason, _s in steps), steps)
        for turn, key, reason, step in steps:
            if step is not None:
                self.assertGreater(step.distance_to(SWORD_CELL), 1, (turn, key, reason))
        self.assertNotEqual(rows[-1][1], "3", rows[-1][1:])
        self.assertIn(Position(13, 62), immobile_threat_memory.route_cells(policy))

    def test_control_a_survivable_sword_keeps_the_recorded_route(self):
        # DECLARED CONSTRUCTED: with 400 HP its one-turn prediction is not lethal.
        boards = with_hp(self.boards(), 400)
        policy = new_policy(CASE_079, boards)
        rows = self.drive_boards(CASE_079, boards, policy)
        self.assertEqual(rows[-1][1:], ("3", "approach-descent"))
        self.assertEqual(immobile_threat_memory.route_cells(policy), frozenset())

    def test_a_new_floor_visit_forgets_the_sword(self):
        policy = new_policy(CASE_079)
        self.drive_boards(CASE_079, self.boards()[:7], policy)
        self.assertTrue(immobile_threat_memory.route_cells(policy))
        immobile_threat_memory.forget_floor_visit(policy)
        self.assertEqual(immobile_threat_memory.route_cells(policy), frozenset())


class AlternateDiveOverExtensionRecordedTest(RecordedDrive):
    """life-083: the alternate's emergency-ridden dive advances the streak."""

    def drive(self, *, unlocked, streak=None):
        boards = copy.deepcopy(CASE_083["boards"])
        if unlocked:
            for raw in boards:
                raw["progress"]["angband_recall_unlocked"] = True
        policy = new_policy(CASE_083, boards)
        start = CASE_083["decisions"][0]["over_extension"]
        policy._alternate_dungeon = start["alternate_dungeon_id"]
        policy._alternate_dungeon_reason = "over_extended_dives"
        policy._target_dungeon_id = start["target_dungeon_id"]
        policy._target_empty_dives = start["over_extended_dive_streak"] if streak is None else streak
        policy._last_overextended_depth = start["last_overextended_depth"]
        rows = self.drive_boards(CASE_083, boards, policy)
        self.assertEqual(rows[-1][0]["turn"], ARRIVAL_TURN)
        self.assertTrue(rows[-1][0]["floor"]["in_town"])
        reasons = [reason for _raw, _key, reason in rows]
        self.assertGreaterEqual(reasons.count("emergency:teleport"), 2, reasons)
        return policy

    def test_recorded_rows(self):
        rows = {row["decision_sequence"]: row["over_extension"] for row in CASE_083["decisions"]}
        self.assertEqual((rows[5297]["alternate_dungeon_id"], rows[5297]["over_extended_dive_streak"]),
                         (LABYRINTH, 1))
        self.assertEqual((rows[5356]["dive_emergencies"], rows[5356]["dive_loot"]), (7, 0))
        arrival = [row for row in CASE_083["decisions"] if row["turn"] == ARRIVAL_TURN]
        self.assertEqual(arrival[-1]["over_extension"]["over_extended_dive_streak"], 2)
        self.assertFalse(CASE_083["boards"][0]["progress"]["angband_recall_unlocked"])

    def test_control_recorded_progress_counts_the_dive_as_the_target(self):
        policy = self.drive(unlocked=False)
        self.assertEqual(policy._target_empty_dives, 2)

    def test_angband_unlocked_alternate_dive_advances_the_streak(self):
        policy = self.drive(unlocked=True)
        self.assertEqual((policy._target_empty_dives, policy._alternate_dungeon), (2, LABYRINTH))

    def test_third_alternate_dive_steps_to_a_shallower_dungeon(self):
        policy = self.drive(unlocked=True, streak=2)
        # The Orc cave lands at 11, shallower than the Labyrinth's 12.
        self.assertEqual((policy._alternate_dungeon, policy._target_empty_dives), (ORC_CAVE, 0))
        self.assertEqual(policy._last_overextended_depth, 12)


if __name__ == "__main__":
    unittest.main()
