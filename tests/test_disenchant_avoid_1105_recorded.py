"""disenchant-1105: what disenchants an unresisting player is destroyed or avoided.

Owner 2026-11-05: 「劣化耐性がないときに劣化属性攻撃をするモンスターとの戦闘は可能であれば
回避する。クエスト中でなければ*破壊*対象とする。」, 「ランダムクエストの階であってもターゲット
でなければ*破壊*してよい」 (disenchant_avoid, destruction_use.sight_trigger_key).

Recorded boards (tests/extract_disenchant_fixture.py), every decision through the public
choose_key, the posted key through the production executor:
 * MOBILE: n1-b life-306 鉄獄19階, an awake race 913 (BR_DISE) two cells away, recorded
   ``hunt`` ``4`` and then ``melee`` ``1``; the resist_disen control answers the same.
 * MOLD: n1-c life-140 オークの洞窟23階, a sleeping 劣化モルド (race 192), recorded
   ``ranged:fire-offset``, which woke it; the control answers the same.
 * QUEST: test_rq_teleport_reserve's random quest board, and Q31's fixed quest board.

DECLARED CONSTRUCTED: no capture holds such a monster with a *Destruction* means, so the
staff (with_staff), the resist_disen source and full HP, the monster moved or re-raced,
the board's other monsters removed, and the quest target given the breath.  The executor's reply is
the same board ten turns later.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import dataclasses
import gzip
import json
from pathlib import Path

from hengbot import disenchant_avoid
from hengbot.model import _decode_grid_map, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests.support import recorded as executor_pins
from tests import test_n1c_death_1102_recorded as q31
from tests import test_rq_teleport_reserve_recorded as rq
from tests.test_destruction_use_1104_recorded import (
    HELD_TURN, TARGET, USE_PROMPT, move, own_tests_only, with_staff,
)
from tests.support import recorded as _recorded
from tests.support.recorded import decide
from tests.test_town_decision_speed_caches import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "disenchant-1105.json.gz"
SIGHT = ("us", "emergency:destruction:disenchanter")
AVOID = "threat:avoid-engagement"
BREATHER = 913
TOUCHER = 399        # 劣化ビースト: mobile, four UN_BONUS blows
ORDINARY = 338       # the air hounds of the random quest board
NEVER_MOVING_BREATHER = 1264


def resisting(raw):
    raw["player"]["ability_sources"]["resist_disen"]["equipment"] = True
    return raw


def alone(raw, race, distance):
    """The one monster of the board: awake, unhurt, ``race``, ``distance`` cells east; the
    player unresisting and at full HP (the quest boards' characters resist and are hurt)."""
    raw["player"]["ability_sources"]["resist_disen"] = dict.fromkeys(
        raw["player"]["ability_sources"]["resist_disen"], False)
    raw["player"]["hp"] = raw["player"]["max_hp"]
    monster = copy.deepcopy(raw["visible_monsters"][0])
    raw["visible_monsters"] = [monster]
    raw["detected_monsters"] = []
    monster["race_id"] = race
    monster["asleep"] = False
    monster["health"] = "unhurt"
    move(raw, monster, raw["player"]["y"], raw["player"]["x"] + distance)
    return raw


class Boards(_recorded.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = json.load(stream)
        cls.monraces = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def answer(self, raw, *, first=None, knowledge=None):
        policy = HengbotPolicy(monrace_knowledge={**self.monraces, **(knowledge or {})})
        policy.prime(parse_snapshot(copy.deepcopy(first or raw), policy._monrace_knowledge))
        key = decide(policy, copy.deepcopy(raw))
        return (key, policy.last_reason), policy

    def post_staff(self, policy, raw, key):
        accepted = self.post(policy, raw, key, [executor_pins.prompt_screen(USE_PROMPT)],
                             self.later(raw))
        self.assertEqual(accepted, ["u", key[1:]])


class SightTriggerTest(Boards):
    def setUp(self):
        self.raw = self.boards("mobile")[0]

    def test_awake_in_view_is_used_on_through_the_executor(self):
        raw = with_staff(self.raw)
        answer, policy = self.answer(raw)
        self.assertEqual(answer, SIGHT)
        self.post_staff(policy, raw, answer[0])

    def test_with_resistance_there_is_no_use(self):
        answer, _ = self.answer(resisting(with_staff(self.raw)))
        self.assertEqual(answer, ("4", "hunt"))     # the recorded row

    def test_staff_below_eighty_percent_is_no_means(self):
        answer, _ = self.answer(with_staff(self.raw, skill=59))
        self.assertFalse(answer[1].startswith("emergency:destruction"))

    def test_asleep_is_left_asleep(self):
        raw = with_staff(self.raw)
        raw["visible_monsters"][0]["asleep"] = True
        self.assertFalse(self.answer(raw)[0][1].startswith("emergency:destruction"))

    def test_beyond_the_radius_is_no_use_and_at_it_is(self):
        far = alone(with_staff(copy.deepcopy(self.raw)), BREATHER, 14)
        self.assertFalse(self.answer(far)[0][1].startswith("emergency:destruction"))
        near = alone(with_staff(copy.deepcopy(self.raw)), BREATHER, 13)
        self.assertEqual(self.answer(near)[0], SIGHT)

    def test_an_ordinary_monster_is_no_trigger(self):
        raw = alone(with_staff(self.raw), ORDINARY, 2)
        self.assertFalse(self.answer(raw)[0][1].startswith("emergency:destruction"))


@own_tests_only
class QuestFloorTest(rq.RandomQuestTeleportReserveRecordedTest, Boards):
    @classmethod
    def setUpClass(cls):
        rq.RandomQuestTeleportReserveRecordedTest.setUpClass()

    def setUp(self):
        boards = self.boards("reserve-held")
        self.first = boards[0]
        self.raw = next(raw for raw in boards if raw["turn"] == HELD_TURN)

    def quest_answer(self, raw, knowledge=None):
        return self.answer(raw, first=self.first, knowledge=knowledge)

    def test_random_quest_non_target_is_used_on(self):
        answer, policy = self.quest_answer(alone(with_staff(self.raw), BREATHER, 5))
        self.assertEqual(answer, SIGHT)
        self.assertEqual(parse_snapshot(self.raw, self.monraces).floor_key[2], rq.QUEST_ID)
        self.assertTrue(policy._floor_navigation_exit_locked(
            parse_snapshot(copy.deepcopy(self.raw), self.monraces)))

    def test_random_quest_target_is_not_used_on(self):
        knowledge = {TARGET: dataclasses.replace(
            self.monraces[TARGET],
            abilities=self.monraces[TARGET].abilities | disenchant_avoid.ABILITIES)}
        answer, _ = self.quest_answer(alone(with_staff(self.raw), TARGET, 5), knowledge)
        self.assertFalse(answer[1].startswith("emergency:destruction"))

    def test_random_quest_wounded_target_in_the_circle_bars_the_use(self):
        raw = alone(with_staff(self.raw), BREATHER, 5)
        target = copy.deepcopy(raw["visible_monsters"][0])
        target.update(race_id=TARGET, index=target["index"] + 1, health="wounded",
                      x=raw["player"]["x"] + 16)
        raw["visible_monsters"].append(target)
        self.assertFalse(self.quest_answer(raw)[0][1].startswith("emergency:destruction"))

    def test_fixed_quest_floor_is_not_used_on(self):
        policy = q31.new_policy()
        policy._monrace_knowledge[BREATHER] = self.monraces[BREATHER]
        board = next(raw for raw in q31.CASE["boards"] if raw["visible_monsters"])
        raw = alone(with_staff(copy.deepcopy(board)), BREATHER, 3)
        q31.d57.loops.decide(policy, raw)
        self.assertFalse(policy.last_reason.startswith("emergency:destruction"))
        self.assertEqual(policy._floor_navigation_exit_locked(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)), True)

    def test_locked_quest_floor_without_the_means_is_not_walked_away_from(self):
        answer, _ = self.quest_answer(alone(self.raw, TOUCHER, 2))
        self.assertNotEqual(answer[1], AVOID)


def corridor(raw, *, beyond_open=True, side_branch=False):
    """DECLARED CONSTRUCTED on the recorded mold board: the recorded map's own cell rows,
    all walls but a corridor on row 8 (x 21 to 35), the player at its east end, the
    sleeping mold at x 28.  West of it the corridor ends in unknown ground, or in walls
    (``beyond_open=False``); ``side_branch`` opens unknown ground on the player's side."""
    records = _decode_grid_map(raw["grid_map"], raw["protocol_version"])
    wall = next(row for row in records if row.get("known") and row["terrain"].get("wall"))
    floor = next(row for row in records if row.get("known") and row["terrain"].get("move")
                 and not row.get("monster_index") and not row.get("object_count")
                 and not row["terrain"].get("trap") and not row["terrain"].get("door"))
    unknown = {*(((y, 20)) for y in (7, 8, 9))} if beyond_open else set()
    floors = {(8, x) for x in range(21, 36)}
    if side_branch:
        floors |= {(9, 33), (10, 33)}
        unknown |= {(11, y) for y in (32, 33, 34)}
    rows = []
    for y in range(raw["grid_map"]["h"]):
        for x in range(raw["grid_map"]["w"]):
            if (y, x) in unknown:
                continue
            template = floor if (y, x) in floors else wall
            row = dict(copy.deepcopy(template), y=y, x=x, monster_index=0, object_count=0)
            row["flags"]["mark"] = True      # seen ground: only the left-out cells are unknown
            rows.append(row)
    index = raw["visible_monsters"][0]["index"]
    next(row for row in rows if (row["y"], row["x"]) == (8, 28))["monster_index"] = index
    del raw["grid_map"]
    raw["nearby_grids"] = rows
    raw["visible_monsters"][0].update(y=8, x=28)
    raw["player"].update(y=8, x=35)
    return raw


class WayOnTest(Boards):
    """Owner 2026-11-05 「通路をふさぐ時だけ撃つ」."""

    def setUp(self):
        self.raw = self.boards("mold")[0]
        self.assertTrue(self.raw["visible_monsters"][0]["asleep"])

    def test_a_ring_that_closes_the_way_is_shot_through_the_executor(self):
        raw = corridor(self.raw)
        (key, reason), policy = self.answer(raw)
        self.assertTrue(reason.startswith("ranged:"), reason)
        self.assertEqual(key, "fr4")         # the bolts, west along the corridor
        self.assertEqual(self.post(policy, raw, key, [], self.later(raw)), [key])

    def test_a_way_on_this_side_leaves_it_asleep(self):
        key, reason = self.answer(corridor(self.raw, side_branch=True))[0]
        self.assertFalse(reason.startswith("ranged:"), reason)
        self.assertFalse(key.startswith("f"), key)

    def test_nothing_beyond_it_leaves_it_asleep(self):
        key, reason = self.answer(corridor(self.raw, beyond_open=False))[0]
        self.assertFalse(reason.startswith("ranged:"), reason)
        self.assertFalse(key.startswith("f"), key)

    def test_a_breather_closing_the_way_is_not_shot(self):
        raw = corridor(self.raw)
        raw["visible_monsters"][0]["race_id"] = NEVER_MOVING_BREATHER
        key, reason = self.answer(raw)[0]
        self.assertFalse(reason.startswith("ranged:"), reason)
        self.assertFalse(key.startswith("f"), key)


class AvoidanceTest(Boards):
    def test_recorded_rows(self):
        self.assertEqual([row["reason"] for row in self.cases["mobile"]["decisions"]],
                         ["hunt", "melee", "melee", "melee"])
        self.assertEqual(self.cases["mold"]["decisions"][0]["reason"], "ranged:fire-offset")

    def test_recorded_hunt_becomes_the_retreat_through_the_executor(self):
        raw = self.boards("mobile")[0]
        (key, reason), policy = self.answer(raw)
        # From (48,56), away from the monster at (49,54); the recorded hunt was 4, toward it.
        self.assertEqual((key, reason), ("9", AVOID))
        self.assertEqual(self.post(policy, raw, key, [], self.later(raw)), [key])

    def test_resistance_keeps_the_recorded_hunt_and_melee(self):
        boards = [resisting(raw) for raw in self.boards("mobile")]
        rows = self.cases["mobile"]["decisions"]
        self.assertEqual(self.answer(boards[0])[0], (rows[0]["key"], rows[0]["reason"]))
        self.assertEqual(self.answer(boards[1])[0], (rows[1]["key"], rows[1]["reason"]))

    def test_an_adjacent_breather_with_no_blow_is_walked_away_from(self):
        # Race 913 has no melee; nothing strikes from beside the player yet.
        self.assertEqual(self.answer(self.boards("mobile")[1])[0][1], AVOID)

    def test_a_striker_beside_the_player_is_fought(self):
        raw = alone(self.boards("mobile")[1], TOUCHER, 1)
        self.assertEqual(self.answer(raw)[0][1], "melee")

    def test_with_no_step_away_an_awake_one_is_fought_as_today(self):
        raw = self.boards("mobile")[0]
        board_policy = self.answer(raw)[1]
        board = parse_snapshot(copy.deepcopy(raw), self.monraces)
        monster = board.visible_monsters[0]
        self.assertTrue(disenchant_avoid.avoided(board_policy, board, monster))
        self.assertEqual(disenchant_avoid.fought(board_policy, board, [monster]), [monster])
        asleep = dataclasses.replace(monster, asleep=True)
        self.assertEqual(disenchant_avoid.fought(board_policy, board, [asleep]), [])

    def test_sleeping_mold_is_not_shot_or_approached(self):
        raw = self.boards("mold")[0]
        self.assertTrue(raw["visible_monsters"][0]["asleep"])
        key, reason = self.answer(raw)[0]
        self.assertNotIn(reason, ("ranged:fire-offset", "immobile-threat:approach-to-shoot"))
        self.assertFalse(key.startswith("f"))

    def test_resisting_keeps_the_recorded_shot_at_the_mold(self):
        rows = self.cases["mold"]["decisions"]
        raw = resisting(self.boards("mold")[0])
        self.assertEqual(self.answer(raw)[0], (rows[0]["key"], rows[0]["reason"]))

    def test_awake_touching_mold_stays_the_safe_ranged_kill(self):
        raw = self.boards("mold")[1]
        self.assertFalse(raw["visible_monsters"][0]["asleep"])
        self.assertEqual(self.answer(raw)[0][1], "immobile-threat:approach-to-shoot")
