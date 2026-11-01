"""survival2-1101 (#47): the owner answers of 2026-11-01 21h on survival.

1. 「近づかずに避ける」 (memory owner-answers-9-decisions-20261101, answer 1):
   a never-moving monster whose blows drain a stat is avoided like an
   immobile summoner; firing at it from a distance stays allowed; where
   retreat is impossible it is fought as today (immobile_threat_memory).
   n1-c life-092 (Lv12 Magic-Eater, Angband 14F): the hunt walked to the cell
   beside a レッド・ゼリー (race 131, NEVER_MOVE, TOUCH:LOSE_STR) at (16,86)
   (turn 1065156 '1') and fired beside it, 「ひどく弱くなった気がする。」
   eight times.  n1-b life-287 (Lv23 warrior, Labyrinth 15F): the hunt walked
   beside the sleeping one at (6,43) (turn 929114 '4') and meleed it.
   n1-a life-459 (Lv15 warrior, random quest 49): the control on a quest
   floor, where a 自縛霊 (race 1012, NEVER_MOVE, TOUCH:LOSE_WIS) beside it is
   fought as before.
2. 「近接できない時だけ使う」 (answer 2): while melee is refused (fear or a
   NO_MELEE dungeon) every class fires its bow or throws at the adjacent
   hostile.  c4-a life-014 (Lv40 warrior, 高速度のロング・ボウ and 99 arrows,
   the Anti-melee cave 45F, the recorded death of 2026-10-23;
   tests/fixtures/anti-melee-death-20261023.jsonl.gz): main walked beside its
   attackers ('4' explore, '3' threat:avoid-engagement, '7' approach-descent).

Fixture: tests/fixtures/survival2-1101.json.gz
(tests/extract_survival2_1101_fixtures.py).  Every decision is the public
``choose_key`` and every posted key goes through the production executor port
(test_me_nokey_1031_recorded.PostedKey); the next decision reads the next
recorded board, as in the live driver.
DECLARED RECONSTRUCTED: life-092's staff sequence record is the 12:18
incident capture's ``_me_staff_sequence``, and its floor memory of the
Magic-Eater powers holds the floor's recorded new-floor casts (decision rows
4545-4549, turns 1063321-1063367), which the board window does not reach.
DECLARED CONSTRUCTED: the beside-the-jelly cases start a fresh policy on the
recorded board where the unfixed walk had put the player beside it; the
afraid cases of answer 2 set ``player.status.afraid`` on the Anti-melee
boards and take NO_MELEE out of the loaded dungeon definition (as
test_anti_melee_dungeon_recorded's controls do), the faster-player control
also sets the player's speed to 130.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from tempfile import TemporaryDirectory

from hengbot import immobile_threat_memory, me_powers
from hengbot import me_staff_sequence as sequence
from hengbot.model import Position, parse_snapshot
from hengbot.policy_constants import DIRECTION_KEYS
from tests import test_anti_melee_dungeon_recorded as anti_melee
from tests import test_me_staff_loops_1031_recorded as loops
from tests.test_me_nokey_1031_recorded import PostedKey


with gzip.open(Path(__file__).with_name("fixtures") / "survival2-1101.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASES = json.load(_stream)
CASE_092, CASE_287, CASE_459 = CASES["n1c-092"], CASES["n1b-287"], CASES["n1a-459"]
RED_JELLY, JIBAKU_GHOST = 131, 1012
JELLY_092, JELLY_287, GHOST_459 = Position(16, 86), Position(6, 43), Position(16, 64)
HUNT_TURN_092, HUNT_TURN_287 = 1065156, 929114
STEPS = {key: offset for offset, key in DIRECTION_KEYS.items()}


def new_policy(case, first=None):
    """The recorded policy primed on ``first`` (default: the first board)."""
    boards = case["boards"] if first is None else [raw for raw in case["boards"] if raw["turn"] >= first]
    policy = loops.new_policy(dict(case, boards=boards), case["skill"], monraces=case["monraces"])
    record = case.get("sequence")
    if record is not None:
        sequence.state(policy).absorbed = {
            int(key) if key.isdigit() else key: count for key, count in record["absorbed"].items()}
        board = parse_snapshot(copy.deepcopy(boards[0]), policy._monrace_knowledge)
        me_powers.observe(policy, board)
        memory = getattr(policy, me_powers.MEMORY)
        for turn, effect in case["new_floor_casts"]:
            power = next(row for row in me_powers.POWERS if row.effect == effect)
            memory.uses.append(me_powers.Use(power.ident, power.ident, "new-floor",
                                             board.player.position, turn))
    return policy


def step_of(raw, key):
    """The cell a walk key moves toward, else None."""
    if not key or key[-1] not in STEPS or key[:-1] not in {"", "o"}:
        return None
    dy, dx = STEPS[key[-1]]
    return Position(raw["player"]["y"] + dy, raw["player"]["x"] + dx)


def boards(case, first, last):
    return [copy.deepcopy(raw) for raw in case["boards"] if first <= raw["turn"] <= last]


class StatDrainImmobileRecordedTest(PostedKey):
    """Answer 1: never walk beside a never-moving stat drainer; step out of its ring."""

    def drive_keeping_away(self, case, policy, rows, monster):
        decided = []
        for raw in rows:
            key = loops.decide(policy, raw)
            step = step_of(raw, key)
            decided.append((raw["turn"], key, policy.last_reason))
            if step is not None:
                self.assertGreater(step.distance_to(monster), 1, decided[-1])
            if key:
                self.post(policy, raw, key)
                policy.confirm_key_posted(key)
        return decided

    def test_recorded_rows(self):
        knowledge = CASE_092["monraces"][str(RED_JELLY)]
        self.assertIn("NEVER_MOVE", knowledge["flags"])
        self.assertEqual([blow["effect"] for blow in knowledge["blows"]], ["LOSE_STR"])
        self.assertIn("LOSE_WIS", [blow["effect"] for blow in CASE_459["monraces"][str(JIBAKU_GHOST)]["blows"]])
        rows = {row["turn"]: (row["reason"], row["key"]) for row in CASE_092["decisions"]}
        self.assertEqual(rows[HUNT_TURN_092], ("hunt", "1"))
        self.assertEqual(rows[1065165], ("ranged:magic-eater-device", "mBo1"))
        drained = [raw["turn"] for raw in CASE_092["boards"] if "ひどく弱くなった気がする。" in raw["messages"]]
        self.assertEqual(len(drained), 7, drained)  # the eighth is on board 1065255
        hunt = next(raw for raw in CASE_092["boards"] if raw["turn"] == HUNT_TURN_092)
        self.assertEqual(step_of(hunt, "1").distance_to(JELLY_092), 1)
        self.assertEqual(CASE_287["boards"][12]["player"]["class_id"], 0)  # a warrior
        self.assertTrue(any("ひどく弱くなった気がする。" in raw["messages"] for raw in CASE_287["boards"]))

    def test_magic_eater_hunt_keeps_out_of_the_jelly_ring(self):
        policy = new_policy(CASE_092)
        decided = self.drive_keeping_away(
            CASE_092, policy, boards(CASE_092, 1065063, HUNT_TURN_092), JELLY_092)
        self.assertEqual(decided[-1][0], HUNT_TURN_092)
        self.assertIn(Position(15, 87), immobile_threat_memory.route_cells(policy))

    def test_magic_eater_beside_the_jelly_steps_out(self):
        # DECLARED CONSTRUCTED (module docstring): a fresh policy beside it.
        policy = new_policy(CASE_092, 1065165)
        decided = self.drive_keeping_away(
            CASE_092, policy, boards(CASE_092, 1065165, 1065165), JELLY_092)
        self.assertEqual(decided[0][2], immobile_threat_memory.STEP_OUT_REASON, decided)

    def test_warrior_hunt_keeps_out_of_the_sleeping_jelly_ring(self):
        policy = new_policy(CASE_287)
        decided = self.drive_keeping_away(
            CASE_287, policy, boards(CASE_287, 929001, HUNT_TURN_287), JELLY_287)
        self.assertEqual(decided[-1][0], HUNT_TURN_287)
        self.assertNotEqual(decided[-1][2], "hunt", decided[-1])

    def test_warrior_beside_the_jelly_steps_out_until_it_is_seen_dead(self):
        # DECLARED CONSTRUCTED: a fresh policy on the recorded board beside it.
        policy = new_policy(CASE_287, 929121)
        decided = self.drive_keeping_away(
            CASE_287, policy, boards(CASE_287, 929121, 929144), JELLY_287)
        self.assertEqual({reason for _turn, _key, reason in decided},
                         {immobile_threat_memory.STEP_OUT_REASON}, decided)
        # The recorded board after the kill shows its cell empty: the ring retires.
        loops.decide(policy, boards(CASE_287, 929149, 929149)[0])
        self.assertEqual(immobile_threat_memory.route_cells(policy), frozenset())

    def test_control_quest_floor_keeps_todays_fight(self):
        # Random quest 49 locks the exit: no ring, the warrior fights beside the ghost.
        policy = new_policy(CASE_459)
        decided = []
        for raw in boards(CASE_459, 374062, 374115):
            key = loops.decide(policy, raw)
            decided.append((raw["turn"], key, policy.last_reason))
            self.assertEqual(immobile_threat_memory.route_cells(policy), frozenset())
            if key:
                self.post(policy, raw, key)
                policy.confirm_key_posted(key)
        self.assertEqual(decided[-2], (374106, "2", "melee"))  # the ghost south of it


class MeleeRefusedRangedRecordedTest(PostedKey):
    """Answer 2: while melee is refused, the bow answers the adjacent hostile."""

    _board = anti_melee.AntiMeleeDungeonRecordedTest._board

    @classmethod
    def setUpClass(cls):
        with gzip.open(anti_melee.FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        cls.monrace = anti_melee.load_monrace_knowledge(anti_melee.EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = anti_melee.load_dungeon_knowledge(anti_melee.EDIT / "DungeonDefinitions.jsonc")

    def setUp(self):
        self._directory = TemporaryDirectory()

    def tearDown(self):
        self._directory.cleanup()

    def decide(self, line, *, melee_allowed=False, afraid=False, speed=None):
        raw = json.loads(line)
        raw["player"]["status"]["afraid"] = afraid
        if speed is not None:
            raw["player"]["speed"] = speed
        line = json.dumps(raw, ensure_ascii=False)
        policy, board = self._board(line, melee_allowed=melee_allowed)
        return raw, board, policy, str(policy.choose_key(board)), policy.last_reason

    def assert_fires_at_adjacent(self, raw, board, policy, key, reason):
        here = board.player.position
        adjacent = {DIRECTION_KEYS[(m.position.y - here.y, m.position.x - here.x)]
                    for m in board.visible_monsters if m.position.distance_to(here) == 1}
        arrows = next(item for item in board.inventory if item.tval == 17)
        self.assertEqual(reason, "ranged:fire", (board.turn, key))
        self.assertEqual(key[:2], "f" + arrows.slot, (board.turn, key))
        self.assertIn(key[2:], adjacent, (board.turn, key))
        self.post(policy, raw, key)  # the production executor sends the whole command

    def test_no_melee_dungeon_fires_at_the_adjacent_attacker(self):
        # Unfixed: '4' explore, '3' threat:avoid-engagement, '7' approach-descent.
        for line in self.lines:
            raw, board, policy, key, reason = self.decide(line)
            self.assertEqual(board.player.class_id, 0)  # a warrior
            self.assertIn("NO_MELEE", policy._dungeon_knowledge[anti_melee.ANTI_MELEE_CAVE].flags)
            self.assert_fires_at_adjacent(raw, board, policy, key, reason)

    def test_afraid_beside_a_faster_attacker_fires(self):
        # Unfixed: the flee rung walks away from attackers of speed 115-120.
        for line in self.lines:
            raw, board, policy, key, reason = self.decide(line, melee_allowed=True, afraid=True)
            self.assertTrue(all(m.speed >= board.player.speed for m in board.visible_monsters
                                if m.distance == 1))
            self.assert_fires_at_adjacent(raw, board, policy, key, reason)

    def test_control_an_ordinary_adjacent_fight_stays_melee(self):
        for line, (turn, recorded_key) in zip(self.lines, anti_melee.RECORDED):
            _raw, _board, _policy, key, reason = self.decide(line, melee_allowed=True)
            self.assertEqual((key, reason), (recorded_key, "melee"), turn)

    def test_control_afraid_and_faster_than_the_attackers_flees(self):
        _raw, _board, _policy, key, reason = self.decide(
            self.lines[0], melee_allowed=True, afraid=True, speed=130)
        self.assertEqual(reason, "flee", key)


if __name__ == "__main__":
    unittest.main()
