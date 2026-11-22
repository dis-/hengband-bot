"""n1-b life-414's Q18 death (2026-11-22 10:42, Magic-Eater Lv33, floor (0,35,18)), recorded.

What happened (decisions 22885-22904): after the fights at the chokes (1,3), (1,5) and (1,9) the
walk went on from (1,9), took the shrieks of the siren on (6,14) on (1,16) and (2,18) (「何かが
かん高い金切り声をあげた。」, 「付近で何かが突如興奮したような感じを受けた！」), left the choke (1,19) at once
for the open (3,20), met two seahorses 443 hasted by the shrieks and a giant squid 482 there, and
died on (1,19) in the Recall's countdown with the absorbed wand of Teleport Away at 23 charges
(the dump at death).

1. Owner 2026-11-22 (verbatim) 「叫びを受けた理由を調査すること。受けないように立ち回る指示なので。」:
   the walk was the plan's own (QUEST_18 opening: 「全31歩のうち叫びが届くのは11マス（セイレーン:
   [2,6]、[1,16] [1,17] [2,18]、…）」).  The three corridor cells are beside (2,17), the one cell the
   siren on (6,14) has a direct line to through the gap (3,16); the corridor's other walls are
   permanent (QuestPreferences "X"), so no walk from (1,15) to (1,19) avoids them.  The fix is
   the plan's 「目を覚ました敵がいる間は、叫びの届かない隘路に立って1体ずつ倒す」: a shriek heard
   holds the next unexposed choke as a fought one (quest_find_exit ``_shriek_hold``).
2. Owner 2026-11-22 「使う」 to 「Q18 で即死の見込みがある時と帰還待ちの間に、敵を飛ばすテレポート・
   アウェイを使ってよいか」: the absorbed rod, then the absorbed wand (quest_find_exit
   ``_instant_death_escape``, ``_recall_wait_away``).

Recorded: tests/fixtures/n1b-414-q18-1122.jsonl.gz (tests/extract_n1b_414_q18_1122_fixture.py),
fed in order through the public ``choose_key`` from the walk's start on (1,9); the replay
reproduces every recorded key of 22885-22894 and 22896, 22901, 22902.
DECLARED RECONSTRUCTED: the absorbed power lists are the same life's 08:48 town-arrival
checkpoint's (tests/fixtures/n1b-414-me-lists-0848-1122.json: the wand of Teleport Away at 17,
the rod of it 1 and charged), the 10:41 checkpoint having stayed on the viewing server.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import gzip
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import quest_exposure, quest_find_exit
from hengbot.me_device_attacks import observe_lists
from hengbot.me_device_attacks_input import compile_device
from hengbot.model import (
    Position, SV_POTION_SPEED, SV_ROD_TELEPORT_AWAY, SV_STAFF_SPEED, SV_WAND_TELEPORT_AWAY, parse_snapshot,
)
from hengbot.quest_plan_base import SPEED_REASON
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import WAIT_KEY
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from tests.support.recorded import EDIT, GAME_ROOT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
with gzip.open(FIXTURES / "n1b-414-q18-1122.jsonl.gz", "rt", encoding="utf-8") as _stream:
    BOARDS = {raw["turn"]: raw for raw in map(json.loads, _stream)}
LISTS = json.loads((FIXTURES / "n1b-414-me-lists-0848-1122.json").read_text(encoding="utf-8"))["lists"]
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
QUEST = load_quest_knowledge(find_quest_definitions(GAME_ROOT / "bot-client" / "state.jsonl"))[18]
PLAN = load_quest_strategies(Path(__file__).parents[1] / "strategy" / "quests")[18].engagement_plan["find_exit"]

START = 1769330                 # 22885: exit-walk '6' from the choke (1,9)
SHRIEKS = (1769404, 1769424)    # 22892 on (1,16), 22894 on (2,18)
STIRRED = 1769413               # 22893 on (1,17): 「付近で何かが突如興奮した」 alone
ON_THE_CHOKE = 1769438          # 22895 on (1,19): recorded exit-walk '3'
OPEN = 1769463                  # 22897 on (3,20): recorded emergency:quaff-speed:absorbed-power
COUNTDOWN = 1769526             # 22903 on (1,19), recalling: recorded emergency:cornered-attack '3'
SEAHORSE, SQUID, SIREN = 443, 482, 1272
AWAY = quest_find_exit.AWAY_REASON + ":absorbed-power"
BEFORE_CORRIDOR = 1769390       # 22891 on (1,15), the step onto (1,16): recorded exit-walk '6'
# The absorbed staff of Speed (sval 22, 'w'): the plan's Speed reason with the cast's suffix.
HASTE = ("mA" + chr(ord("a") + SV_STAFF_SPEED), SPEED_REASON + ":absorbed-power")
STEPS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1), "7": (-1, -1),
         "8": (-1, 0), "9": (-1, 1)}
ROD_AWAY = "mC" + chr(ord("a") + SV_ROD_TELEPORT_AWAY)      # 'mCn'
WAND_AWAY = "mB" + chr(ord("a") + SV_WAND_TELEPORT_AWAY)    # 'mBd'


def _lists(*, rod_charging=False):
    lists = copy.deepcopy(LISTS)
    if rod_charging:  # DECLARED CONSTRUCTED: the one absorbed rod of Teleport Away charging
        for row in lists["rod"]:
            if row["name"] == "テレポート・アウェイ":
                row["charging"] = row["max"]
    return lists


def drive(last, *, edit=None, lists=None):
    """[(turn, key, reason)] of the recorded boards from START to ``last``; ``edit(turn, raw)``
    changes a board before it is decided (DECLARED CONSTRUCTED where a test says so)."""
    lists = lists or _lists()
    with TemporaryDirectory() as directory:
        policy = _policy(Path(directory), MONRACE)
        first = parse_snapshot(copy.deepcopy(BOARDS[START]), MONRACE)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        for kind in ("staff", "wand", "rod"):
            listed = dict(copy.deepcopy(BOARDS[START]), turn=START - 1,
                          _magic_eater_power_list={"kind": kind, "rows": lists[kind]})
            observe_lists(policy, parse_snapshot(listed, MONRACE))
        decided, previous = [], None
        for turn in sorted(BOARDS):
            if turn > last:
                break
            raw = copy.deepcopy(BOARDS[turn])
            if edit is not None:
                edit(turn, raw)
            if previous is not None:
                raw["_completed_operation_owner"] = previous
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(policy.with_known_skill_exp(parse_snapshot(raw, MONRACE)))
            decided.append((turn, key, policy.last_reason))
            if key:
                policy.confirm_key_posted(key)
            previous = policy.last_reason if key else None
        return policy, decided


def _no_shrieks(turn, raw):
    """DECLARED CONSTRUCTED: the boards of the corridor without the shriek lines."""
    raw["messages"] = [message for message in raw["messages"]
                       if not any(mark in message for mark in quest_find_exit.SHRIEK_MARKS)]


class ShriekCorridorFactsTest(unittest.TestCase):
    """Why the walk took the shrieks: the map leaves it no other way."""

    @classmethod
    def setUpClass(cls):
        terrain = {**QUEST.battlefield.terrain, **{tuple(cell): "deep_water" for cell in PLAN["dig_cells"]}}
        placements = QUEST.battlefield.monster_placements
        cls.sirens = [cell for cell, race in placements if race == SIREN]
        casters = [cell for cell, race in placements if race in PLAN["exposure_races"]]
        reach = {cell: PLAN["aimed_off_reach"][str(race)] for cell, race in placements
                 if str(race) in PLAN["aimed_off_reach"]}
        cls.terrain = terrain
        cls.exposure = quest_exposure.exposure_map(terrain, casters, pullers=set(cls.sirens),
                                                   aimed_off_reach=reach)

    def test_the_corridor_cells_are_shouted_by_the_siren_on_6_14_through_2_17(self):
        for cell in ((1, 16), (1, 17), (2, 18)):
            self.assertEqual(self.exposure.shout.get(cell), frozenset({(6, 14)}), cell)
            self.assertFalse(quest_exposure.projectable(self.terrain, (6, 14), cell), cell)
        # (2,17), beside all three, is the siren's direct line: a pull cell, never walked.
        self.assertTrue(quest_exposure.projectable(self.terrain, (6, 14), (2, 17)))
        self.assertIn((2, 17), self.exposure.pull)
        self.assertEqual(self.terrain[(1, 18)], "wall")  # QuestPreferences "X": PERMANENT

    def test_no_walk_from_1_15_to_1_19_avoids_them(self):
        path = quest_exposure.least_exposed_path(self.terrain, self.exposure, (1, 15), {(1, 19)},
                                                 forbidden=frozenset(self.exposure.pull))
        self.assertEqual(path, [(1, 15), (1, 16), (1, 17), (2, 18), (1, 19)])
        # The recorded walk is that one, and (1,15) and (1,19) are unexposed chokes.
        walked = [tuple((BOARDS[turn]["player"]["y"], BOARDS[turn]["player"]["x"]))
                  for turn in sorted(BOARDS) if START <= turn <= ON_THE_CHOKE]
        self.assertEqual(walked[6:], path)
        for choke in ((1, 15), (1, 19)):
            self.assertIn(list(choke), PLAN["choke_cells"])
            self.assertFalse(self.exposure.exposed(choke))


class ShriekHoldRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy, cls.decided = drive(ON_THE_CHOKE)

    def test_the_walk_to_the_choke_replays_as_recorded(self):
        """The recorded walk, but each step onto a shouted cell of an unhasted board (the recorded
        boards stay unhasted: the haste ran out at 22855) is the absorbed Speed first (owner
        2026-11-22 「加速してから入る」, ``HasteBeforeShoutedRecordedTest``)."""
        recorded = ["6", "3", "9", "3", "9", "6", "6", "6", "3", "9"]
        onto_shouted = {(1, 10), (2, 11), (1, 16), (1, 17), (2, 18)}
        expected = []
        for turn, key in zip(sorted(BOARDS), recorded):
            here = (BOARDS[turn]["player"]["y"], BOARDS[turn]["player"]["x"])
            step = (here[0] + STEPS[key][0], here[1] + STEPS[key][1])
            expected.append(HASTE if step in onto_shouted else (key, quest_find_exit.WALK_REASON))
        self.assertEqual([(key, reason) for _, key, reason in self.decided[:-1]], expected)
        for turn in SHRIEKS:
            self.assertTrue(any("金切り声をあげた" in message for message in BOARDS[turn]["messages"]))

    def test_after_the_shrieks_the_choke_1_19_holds(self):
        # Recorded: exit-walk '3' to (2,20), then (3,20) and the hasted seahorses.
        self.assertEqual(self.decided[-1], (ON_THE_CHOKE, WAIT_KEY, quest_find_exit.HOLD_REASON))
        navigator = self.policy._quest_navigators[18]
        self.assertEqual(navigator.exit_fought_at, Position(1, 19))
        self.assertFalse(navigator.exit_shrieked)

    def test_control_without_the_shrieks_it_walks_on_as_recorded(self):
        _, decided = drive(ON_THE_CHOKE, edit=lambda turn, raw: _no_shrieks(turn, raw) if turn in (
            *SHRIEKS, STIRRED) else None)
        self.assertEqual(decided[-1], (ON_THE_CHOKE, "3", quest_find_exit.WALK_REASON))

    def test_the_stirring_alone_holds_it_too(self):
        """DECLARED CONSTRUCTED: only 「付近で何かが突如興奮した」 of (1,17) left (aggravate_monsters'
        line, the one a shriek always prints when it hastes a monster in view)."""
        _, decided = drive(ON_THE_CHOKE, edit=lambda turn, raw: _no_shrieks(turn, raw) if turn in SHRIEKS else None)
        self.assertEqual(decided[-1], (ON_THE_CHOKE, WAIT_KEY, quest_find_exit.HOLD_REASON))

    def test_the_hold_ends_after_the_quiet_wait(self):
        """DECLARED CONSTRUCTED: the quiet (1,19) board repeated, five game turns apart."""
        policy, _ = drive(ON_THE_CHOKE)
        quiet = BOARDS[ON_THE_CHOKE]
        decided = []
        for count in range(1, PLAN["choke_hold_turns"] + 2):
            raw = dict(copy.deepcopy(quiet), turn=quiet["turn"] + 5 * count, messages=[])
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(policy.with_known_skill_exp(parse_snapshot(raw, MONRACE)))
            decided.append((key, policy.last_reason))
            if key:
                policy.confirm_key_posted(key)
        self.assertTrue(all(row == (WAIT_KEY, quest_find_exit.HOLD_REASON) for row in decided[:-2]),
                        decided)
        self.assertEqual(decided[-1], ("3", quest_find_exit.WALK_REASON))


class HasteBeforeShoutedRecordedTest(unittest.TestCase):
    """Owner 2026-11-22 「加速してから入る」 to 「叫びの届くマスへ入る前に加速が切れていたら、敵が
    見えていなくても取り込んだスピードか薬で加速するか」.  Recorded: on (1,15) the haste had been off
    since 22855 (「動きの素早さがなくなったようだ。」 on (1,9)), nothing in view, and the walk stepped
    onto (1,16), where the siren's first shriek came (22892)."""

    def test_the_step_onto_1_16_is_the_absorbed_speed_first(self):
        _, decided = drive(BEFORE_CORRIDOR)
        board = BOARDS[BEFORE_CORRIDOR]
        self.assertEqual((board["player"]["y"], board["player"]["x"]), (1, 15))
        self.assertEqual(board["visible_monsters"] + board["detected_monsters"], [])
        self.assertEqual(board["player"]["speed_display"]["color"], "white")  # not hasted
        # Recorded: exit-walk '6' onto (1,16).
        self.assertEqual(decided[-1][1:], HASTE)
        verb, (step,) = compile_device(*decided[-1][1:])
        self.assertEqual((verb, step.kind, step.sval), ("m", "staff", SV_STAFF_SPEED))

    def test_control_hasted_it_steps_on(self):
        """DECLARED CONSTRUCTED: the (1,15) board with the haste of 22902's board (speed 120,
        the yellow (+10))."""
        hasted = BOARDS[1769523]["player"]

        def haste(turn, raw):
            if turn == BEFORE_CORRIDOR:
                raw["player"].update(speed=hasted["speed"], speed_display=copy.deepcopy(hasted["speed_display"]))
        _, decided = drive(BEFORE_CORRIDOR, edit=haste)
        self.assertEqual(decided[-1][1:], ("6", quest_find_exit.WALK_REASON))

    def test_control_the_step_onto_a_free_cell_is_no_dose(self):
        # 22888 on (2,11): the step onto the choke (1,12), which no caster reaches.
        _, decided = drive(1769354)
        self.assertEqual(decided[-1][1:], ("9", quest_find_exit.WALK_REASON))

    def test_without_the_absorbed_speed_a_potion(self):
        """DECLARED CONSTRUCTED: the absorbed Speed emptied, and three Speed potions in slot d
        (賢さ復活の薬's place)."""
        lists = _lists()
        for row in lists["staff"]:
            if row["name"] == "スピード":
                row["current"] = 0

        def potions(turn, raw):
            for item in raw["inventory"]:
                if item["slot"] == "d":
                    item.update(sval=SV_POTION_SPEED, count=3, name="3服の スピードの薬")
        _, decided = drive(BEFORE_CORRIDOR, edit=potions, lists=lists)
        self.assertEqual(decided[-1][1:], ("qd", SPEED_REASON))


class TeleportAwayRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy, decided = drive(COUNTDOWN)
        cls.decided = {turn: (key, reason) for turn, key, reason in decided}

    def test_the_instant_death_board_on_3_20_sends_a_seahorse_away_by_the_rod(self):
        key, reason = self.decided[OPEN]
        self.assertEqual((key, reason), (ROD_AWAY + "1", AWAY))
        board = parse_snapshot(copy.deepcopy(BOARDS[OPEN]), MONRACE)
        self.assertIn((SEAHORSE, Position(4, 19)),
                      [(monster.race_id, monster.position) for monster in board.visible_monsters])
        self.assertTrue(all(monster.fast for monster in board.visible_monsters
                            if monster.race_id == SEAHORSE))  # hasted by the shrieks
        # The production executor port: the absorbed rod of Teleport Away, aimed south-west.
        verb, (step,) = compile_device(key, reason)
        self.assertEqual((verb, step.kind, step.sval, step.keys), ("m", "rod", SV_ROD_TELEPORT_AWAY, "1"))

    def test_the_recall_countdown_on_1_19_sends_the_seahorse_away(self):
        # Recorded: emergency:cornered-attack '3' (HP 101), then death.
        key, reason = self.decided[COUNTDOWN]
        self.assertEqual((key, reason), (ROD_AWAY + "3", AWAY))
        self.assertTrue(BOARDS[COUNTDOWN]["player"]["recalling"])

    def test_with_the_rod_charging_the_wand_is_next(self):
        _, decided = drive(OPEN, lists=_lists(rod_charging=True))
        key, reason = decided[-1][1:]
        self.assertEqual((key, reason), (WAND_AWAY + "1", AWAY))
        verb, (step,) = compile_device(key, reason)
        self.assertEqual((step.kind, step.sval, step.keys), ("wand", SV_WAND_TELEPORT_AWAY, "1"))

    def test_the_countdown_without_the_instant_death_still_sends_it_away(self):
        """DECLARED CONSTRUCTED: the countdown board at full HP (508), so no 即死: the Recall's
        countdown rung, not the 即死 one, answers before the plan's blow."""
        def full(turn, raw):
            if turn == COUNTDOWN:
                raw["player"]["hp"] = raw["player"]["max_hp"]
        _, decided = drive(COUNTDOWN, edit=full)
        self.assertEqual(decided[-1][1:], (ROD_AWAY + "3", AWAY))

    def test_control_not_recalling_at_full_hp_no_teleport_away(self):
        """DECLARED CONSTRUCTED: the same board at full HP and no Recall under way."""
        def quiet(turn, raw):
            if turn == COUNTDOWN:
                raw["player"]["hp"] = raw["player"]["max_hp"]
                raw["player"]["recalling"] = False
        _, decided = drive(COUNTDOWN, edit=quiet)
        self.assertNotEqual(decided[-1][2], AWAY, decided[-1])


if __name__ == "__main__":
    unittest.main()
