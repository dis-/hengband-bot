"""The owner's answers to summons on a floor with an engagement plan (2026-11-05).

Owner 「召喚への対応策は事前に決めたはずだがどうなっている？」: quest_find_exit and quest_room_sweep
answered before the shared ladder, so summon_response never ran on their floors.  Recorded: n1-b
life-312's death in Quest 25 (tests/fixtures/q25-summons-n1b-312-1105.json.gz,
tests/extract_q25_summons_1105_fixture.py); one policy decides every board of the floor in
order, and it cannot change the boards after the first key that differs from the recording.
Quest 18 has no recorded summon: its cases are DECLARED CONSTRUCTED on that module's boards.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hengbot import quest_find_exit, quest_force_rows, quest_room_light, quest_room_sweep, summon_response
from hengbot.model import SV_POTION_CURE_CRITICAL, SV_POTION_ENLIGHTENMENT, TVAL_POTION, _parse_items, parse_snapshot
from hengbot.policy import ConservativePolicy
from hengbot.policy_constants import HEAL_POTION_SVALS, REST_MACRO
from tests import test_me_nokey_1031_recorded as nokey
from tests.test_once_quest_recall_recorded import COMMAND_PROMPTS, prompt_screen
from tests import test_q18_water_cave as q18
from tests import test_q25_haunted_house as q25


with gzip.open(Path(__file__).with_name("fixtures") / "q25-summons-n1b-312-1105.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

# 何か has cast twice beside the player at [5,2], HP 1135/1137, 8 monsters in view.
SECOND_UNSEEN_CAST = 11652690
# HP 378, below the plan's line, with the unseen run still open.
BELOW_THE_LINE = 11652737
# レッサー・バルログ first on the row west of [1,18], アラクノトロン beside the player.
CASTER_PAST_THE_ADJACENT = 11653279
# The same row with 撲殺の悪魔 in front of the nearest レッサー・バルログ.
CASTER_BEHIND_A_BODY = 11653273
# メンデスの山羊 named on this board, beside the player with グレイ・レイス, the plan's first.
CASTER_BESIDE = 11653307
# HP 67/1137, nothing in view, no Healing left: 癒しの薬 2 and 致命傷の治癒 3.
QUIET_AT_THE_END = 11653365
SV_POTION_CURING = 61
GOAT, BALROG = "メンデスの山羊", "レッサー・バルログ"
QUYL = 480
# The first cast from the dark of the floor, at [6,1]: the Scroll of Light.
FIRST_UNSEEN_CAST = 11651515
# [1,18], 何か and 撲殺の悪魔 both casting, 啓蒙の薬 picked up 250 ticks before.
POTION_PICKED_UP_IN_THE_DARK = 11653256
POTION_FIRST_QUIET_BOARD = 11653011


def _new_policy():
    policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                quest_strategies=q25.STRATEGIES)
    first = copy.deepcopy(CASE["boards"][0])
    policy.prime(parse_snapshot(first, policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(
        copy.deepcopy(CASE["skill"]), turn=first["turn"],
        player=dict(CASE["skill"]["player"], level=first["player"]["level"])))
    policy.consume_home_knowledge(tuple(_parse_items(CASE["home"]["knowledge"]["items"], protocol=3)))
    return policy


def _replay():
    """turn -> (raw board, key, reason, decision sequence) for every recorded board."""
    policy, answers = _new_policy(), {}
    for raw in CASE["boards"]:
        key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
        answers[raw["turn"]] = (raw, key, policy.last_reason, policy._decision_sequence)
        policy.confirm_key_posted(key)
    return answers


ANSWERS = {}


def answer(turn):
    if not ANSWERS:
        ANSWERS.update(_replay())
    return ANSWERS[turn]


def first_on_the_row_west(raw):
    here = raw["player"]
    return max((m for m in raw["visible_monsters"] if m["y"] == here["y"] and m["x"] < here["x"]),
               key=lambda m: m["x"])


class Q25RecordedTest(nokey.PostedKey):
    def post_recorded(self, turn):
        raw, key, reason, sequence = answer(turn)
        self.post(SimpleNamespace(last_reason=reason, _decision_sequence=sequence), raw, key, screens=[
            prompt_screen(text) for command, text in COMMAND_PROMPTS.items() if key.startswith(command)])

    def test_the_first_cast_from_the_dark_reads_the_light(self):
        raw, key, reason, _ = answer(FIRST_UNSEEN_CAST)
        self.assertEqual(reason, quest_room_light.UNSEEN_LIGHT_REASON)
        slot = next(item["slot"] for item in raw["inventory"]
                    if item["tval"] == q25.TVAL_SCROLL and item["sval"] == q25.SV_LIGHT)
        self.assertEqual(key, "r" + slot)
        self.post_recorded(FIRST_UNSEEN_CAST)

    def test_the_potion_picked_up_on_the_floor_is_drunk_on_the_next_quiet_board(self):
        # Picked up in the melee of 11653002; the recording walked on and carried it to the end.
        raw, key, reason, _ = answer(POTION_FIRST_QUIET_BOARD)
        self.assertEqual(reason, quest_room_light.OPENING_REASON)
        slot = next(item["slot"] for item in raw["inventory"]
                    if item["tval"] == TVAL_POTION and item["sval"] == SV_POTION_ENLIGHTENMENT)
        self.assertEqual(key, "q" + slot)
        self.assertEqual(raw["visible_monsters"], [])
        self.post_recorded(POTION_FIRST_QUIET_BOARD)

    def test_the_potion_still_carried_lights_the_room_at_the_next_cast(self):
        raw, key, reason, _ = answer(POTION_PICKED_UP_IN_THE_DARK)
        self.assertEqual(reason, quest_room_light.UNSEEN_LIGHT_REASON)
        slot = next(item["slot"] for item in raw["inventory"]
                    if item["tval"] == TVAL_POTION and item["sval"] == SV_POTION_ENLIGHTENMENT)
        self.assertEqual(key, "q" + slot)
        self.post_recorded(POTION_PICKED_UP_IN_THE_DARK)

    def test_two_unseen_casts_read_the_teleport_in_the_crowd(self):
        raw, key, reason, _ = answer(SECOND_UNSEEN_CAST)
        self.assertEqual(reason, summon_response.LEAVE_REASON)
        slot = next(item["slot"] for item in raw["inventory"]
                    if item["tval"] == q25.TVAL_SCROLL and item["sval"] == q25.SV_TELEPORT)
        self.assertEqual(key, "r" + slot)
        self.post_recorded(SECOND_UNSEEN_CAST)

    def test_the_plans_survival_rung_goes_first(self):
        _raw, _key, reason, _ = answer(BELOW_THE_LINE)
        self.assertEqual(reason, quest_room_sweep.TELEPORT_REASON)

    def test_the_named_caster_is_shot_past_the_monster_beside_the_player(self):
        raw, key, reason, _ = answer(CASTER_PAST_THE_ADJACENT)
        here = raw["player"]
        self.assertTrue(any(max(abs(m["y"] - here["y"]), abs(m["x"] - here["x"])) <= 1
                            for m in raw["visible_monsters"]))
        self.assertEqual(reason, summon_response.CASTER_SHOT_REASON)
        self.assertTrue(key.startswith("f") and key.endswith("4"), key)
        self.assertEqual(first_on_the_row_west(raw)["name"], BALROG)
        self.post_recorded(CASTER_PAST_THE_ADJACENT)

    def test_a_body_in_the_bolts_way_leaves_the_plans_blow(self):
        raw, _key, reason, _ = answer(CASTER_BEHIND_A_BODY)
        self.assertNotEqual(first_on_the_row_west(raw)["name"], BALROG)
        self.assertEqual(reason, quest_find_exit.MELEE_REASON)

    def test_a_named_caster_beside_the_player_is_struck_before_the_plans_first(self):
        raw, key, reason, _ = answer(CASTER_BESIDE)
        self.assertEqual(reason, quest_find_exit.MELEE_REASON)
        here = raw["player"]
        struck = next(m for m in raw["visible_monsters"]
                      if max(abs(m["y"] - here["y"]), abs(m["x"] - here["x"])) == 1
                      and key == q25.step_key((here["y"], here["x"]), (m["y"], m["x"])))
        self.assertEqual(struck["name"], GOAT)

    def test_no_recall_for_the_summons_on_this_one_time_floor(self):
        for raw in CASE["boards"]:
            self.assertNotEqual(answer(raw["turn"])[2], summon_response.RECALL_REASON, raw["turn"])

    def test_the_last_rest_held_no_hp_recovery(self):
        # 癒しの薬 heals 50 (quaff-effects.cpp, true_healing) and Cure Critical 6d8: the owner's
        # rule counts neither.  The plan's own rest answered, not the hunger gate its row names.
        # An owner question stands on this board (report 2026-11-05); this pins today's answer.
        raw, key, reason, _ = answer(QUIET_AT_THE_END)
        self.assertEqual((key, reason), (REST_MACRO, "rest"))
        carried = {item["sval"] for item in raw["inventory"] if item["tval"] == TVAL_POTION}
        self.assertLessEqual({SV_POTION_CURE_CRITICAL, SV_POTION_CURING}, carried)
        self.assertFalse(carried & (HEAL_POTION_SVALS - {SV_POTION_CURE_CRITICAL}))


class HasteUnderSlownessRecordedTest(unittest.TestCase):
    """n1-b life-312: a shattered Potion of Slowness at 11651908, the four Speed potions of the recording
    from there to 11651925, the slowness over at 11651971 (「動きの遅さがなくなったようだ。」)."""

    def test_slowed_with_the_haste_still_on_no_speed_potion_is_drunk(self):
        for turn in (11651908, 11651913, 11651919, 11651925):
            raw, key, reason, _ = answer(turn)
            self.assertEqual(raw["player"]["speed_display"]["color"], "light_green")
            self.assertNotEqual(reason, quest_find_exit.SPEED_REASON, turn)
            self.assertFalse(key.startswith("q"), (turn, key, reason))

    def test_the_haste_truly_over_the_speed_potion_is_still_drunk(self):
        # 「動きの素早さがなくなったようだ。」 at 11651714: the same field and the same value.
        raw, key, reason, _ = answer(11651714)
        self.assertEqual(raw["player"]["speed_display"]["color"], "light_green")
        self.assertEqual(reason, quest_find_exit.SPEED_REASON)
        self.assertTrue(key.startswith("q"), key)


class HasteReadTest(unittest.TestCase):
    """DECLARED CONSTRUCTED: q25's quiet board with the speed field and the game's lines put on it."""

    YELLOW, GREEN, VIOLET = ("yellow", 13), ("light_green", 3), ("violet", -7)

    def reads(self, *boards):
        """(colour and value, lines) per board through choose_key: the reading after the last."""
        raw = q25.board(speed=0)
        policy = q25.new_policy(raw)
        for (colour, value), lines in boards:
            raw["player"]["speed_display"] = {"color": colour, "riding": False, "text": "", "value": value}
            raw["messages"] = list(lines)
            q25.choose(policy, raw)
        return policy._player_hasted(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))

    def test_yellow_is_on_and_violet_off(self):
        self.assertTrue(self.reads((self.YELLOW, ())))
        self.assertFalse(self.reads((self.VIOLET, ())))

    def test_the_plain_colour_with_no_line_is_off(self):
        self.assertFalse(self.reads((self.GREEN, ())))
        self.assertFalse(self.reads((self.YELLOW, ()), (self.GREEN, ())))

    def test_slowed_while_hasted_stays_on_for_every_later_board(self):
        slowed = (self.GREEN, ("体の動きが遅くなってしまった！",))
        self.assertTrue(self.reads((self.YELLOW, ()), slowed))
        self.assertTrue(self.reads((self.YELLOW, ()), slowed, (self.GREEN, ()), (self.GREEN, ())))
        self.assertTrue(self.reads((self.YELLOW, ()), (self.GREEN, ("You feel yourself moving slower!",))))

    def test_hasted_while_slowed_is_on(self):
        self.assertTrue(self.reads((self.VIOLET, ()), (self.GREEN, ("素早く動けるようになった！",))))

    def test_either_end_is_read(self):
        slowed = (self.GREEN, ("体の動きが遅くなってしまった！",))
        self.assertFalse(self.reads((self.YELLOW, ()), slowed, (self.VIOLET, ("動きの素早さがなくなったようだ。",))))
        self.assertTrue(self.reads((self.YELLOW, ()), slowed, (self.YELLOW, ("動きの遅さがなくなったようだ。",))))
        self.assertFalse(self.reads((self.YELLOW, ()), slowed, (self.VIOLET, ("動きの素早さがなくなったようだ。",)),
                                    (self.GREEN, ("動きの遅さがなくなったようだ。",))))

    def test_the_haste_ending_with_the_slowness_ending_on_one_board_is_off(self):
        slowed = (self.GREEN, ("体の動きが遅くなってしまった！",))
        self.assertFalse(self.reads((self.YELLOW, ()), slowed,
                                    (self.GREEN, ("動きの素早さがなくなったようだ。", "動きの遅さがなくなったようだ。"))))

    def test_the_field_is_the_mounts_while_riding(self):
        raw = q25.board(speed=0)
        snapshot = parse_snapshot(copy.deepcopy(raw), q25.RACES)
        mounted = replace(snapshot, player=replace(snapshot.player, speed_display=(13, "", "yellow", True)))
        self.assertFalse(q25.new_policy(raw)._player_hasted(mounted))

    def test_haste_cancelled_by_slowness_adds_nothing_to_the_measured_speed(self):
        raw = q25.board(speed=0)
        policy = q25.new_policy(raw)
        raw["player"]["speed"] = 123
        raw["player"]["speed_display"] = {"color": "yellow", "riding": False, "text": "", "value": 13}
        q25.choose(policy, raw)
        snapshot = parse_snapshot(copy.deepcopy(raw), q25.RACES)
        self.assertEqual(quest_force_rows._unhasted_speed(policy, snapshot), 113)
        raw["player"]["speed"] = 113
        raw["player"]["speed_display"] = {"color": "light_green", "riding": False, "text": "", "value": 3}
        raw["messages"] = ["体の動きが遅くなってしまった！"]
        q25.choose(policy, raw)
        snapshot = parse_snapshot(copy.deepcopy(raw), q25.RACES)
        self.assertTrue(policy._player_hasted(snapshot))
        self.assertEqual(quest_force_rows._unhasted_speed(policy, snapshot), 113)


class RuleThreeOnAPlanFloorTest(unittest.TestCase):
    def test_a_floor_that_is_not_one_time_reads_recall(self):
        # DECLARED CONSTRUCTED: the recorded fight with the quest's ONCE flag taken away.
        policy = _new_policy()
        with patch.object(ConservativePolicy, "_fixed_quest_is_once", lambda self, quest_id: False):
            for raw in CASE["boards"]:
                key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
                if policy.last_reason == summon_response.RECALL_REASON:
                    self.assertTrue(key.startswith("r"), key)
                    return
                policy.confirm_key_posted(key)
        self.fail("Recall was never read for the summons")


class Q18ConstructedTest(unittest.TestCase):
    """DECLARED CONSTRUCTED: q18's boards with the summon lines put on them."""

    CHOKE = (1, 3)
    EXPOSED = (4, 10)

    @staticmethod
    def cast(raw, name):
        raw["messages"] = [f"{name}が魔法で仲間を召喚した！"]
        return raw

    def test_the_no_teleport_floor_keeps_its_fight(self):
        policy = q18.new_policy()
        answers = []
        for turn in range(3):  # the first board is the arrival: observe() starts the visit after it
            raw = self.cast(q18.board(self.CHOKE, monsters=[q18.monster(q18.SQUID, 1, 4)], speed=0), "何か")
            raw["turn"] += turn * 10
            key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
            answers.append((key, policy.last_reason))
            policy.confirm_key_posted(key)
        self.assertGreaterEqual(policy._summon_response_memory.unseen_run, 2)
        self.assertEqual(answers[-1], (q18.step_key(self.CHOKE, (1, 4)), quest_find_exit.MELEE_REASON))

    def test_on_an_exposed_cell_the_named_caster_is_shot_before_the_walk_out(self):
        beside = q18.monster(q18.SQUID, 5, 9)
        caster = q18.monster(q18.SHARK, 4, 14)
        raw = self.cast(q18.board(self.EXPOSED, monsters=[beside, caster], speed=0), caster["name"])
        key, reason, _ = q18.decide(raw)
        self.assertEqual(reason, summon_response.CASTER_SHOT_REASON)
        self.assertTrue(key.startswith("f"), key)

    def test_on_a_choke_the_named_caster_is_shot_before_the_blow_at_the_plans_first(self):
        beside = q18.monster(q18.SQUID, 1, 4)
        caster = q18.monster(q18.SQUID, 1, 7, index=7)
        caster["name"] = "named-caster"
        raw = self.cast(q18.board(self.CHOKE, monsters=[beside, caster], speed=0), caster["name"])
        with patch.object(ConservativePolicy, "_ranged_target", lambda self, snapshot, targets: targets[0]):
            _key, reason, _ = q18.decide(raw)
        self.assertNotEqual(reason, quest_find_exit.MELEE_REASON)

    def test_a_named_caster_beside_the_player_is_struck_before_the_plans_first(self):
        first = q18.monster(q18.SQUID, 1, 4)
        caster = q18.monster(q18.SHARK, 1, 2)
        raw = self.cast(q18.board(self.CHOKE, monsters=[first, caster], speed=0), caster["name"])
        key, reason, _ = q18.decide(raw)
        self.assertEqual((key, reason), (q18.step_key(self.CHOKE, (1, 2)), quest_find_exit.MELEE_REASON))

    def test_with_nothing_coming_a_named_caster_in_view_is_shot_before_the_rest(self):
        # A never-moving caster that pulls nobody: no engagement on this plan's board.
        caster = q18.monster(QUYL, 1, 6)
        raw = self.cast(q18.board(self.CHOKE, monsters=[caster], speed=0, hp=500), caster["name"])
        key, reason, _ = q18.decide(raw)
        self.assertEqual(reason, summon_response.CASTER_SHOT_REASON)
        self.assertTrue(key.startswith("f"), key)


class Q25DarkRoomTest(unittest.TestCase):
    """Owner 2026-11-05 「光の巻物か啓蒙の薬で適宜照らす」.  DECLARED CONSTRUCTED: q25's boards, every
    cell known and drawn dark as the module's palette has it; ``lit`` draws them lit."""

    IN_THE_HALL = (5, 8)
    CAST = "何かが恐ろしげな幻覚を作り出した。"

    @staticmethod
    def lit(raw):
        for row in raw["grid_map"]["palette"]:
            row[1] = 0
        return raw

    def cast_board(self, position=IN_THE_HALL, *, message=CAST, **kwargs):
        raw = q25.board(position, speed=0, **kwargs)
        raw["messages"] = [message]
        return raw

    @staticmethod
    def with_potion(raw, count=1):
        potion = dict(q25._stack(q25.TVAL_POTION, SV_POTION_ENLIGHTENMENT, count), slot="p")
        raw["inventory"].append(potion)
        return raw

    def test_a_cast_from_the_dark_is_answered_by_the_scroll(self):
        key, reason, _ = q25.decide(self.cast_board(), stage=4)
        self.assertEqual(reason, quest_room_light.UNSEEN_LIGHT_REASON)
        self.assertTrue(key.startswith("r"), key)

    def test_the_absorbed_light_casts_in_its_place(self):
        with patch("hengbot.policy_quest.carry_cast_key", return_value="mAb"):
            key, reason, _ = q25.decide(self.cast_board(light=0), stage=4)
        self.assertEqual(key, "mAb")
        self.assertTrue(reason.startswith(quest_room_light.UNSEEN_LIGHT_REASON), reason)

    def test_the_potion_goes_before_the_scroll(self):
        # A potion not yet seen on this floor is due anyway (Q25OpeningPotionTest); so seen, it is the light's.
        raw = self.with_potion(self.cast_board())
        policy = q25.new_policy(raw)
        q25._set_stage(policy, raw, 4)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        navigator = quest_room_sweep._navigator(policy, snapshot, 25)
        navigator.sweep_potion_carried = 1
        key = q25.choose(policy, raw)
        self.assertEqual(policy.last_reason, quest_room_light.UNSEEN_LIGHT_REASON)
        self.assertTrue(key.startswith("q"), key)

    def test_a_room_drawn_lit_is_not_read(self):
        _key, reason, _ = q25.decide(self.lit(self.cast_board()), stage=4)
        self.assertNotEqual(reason, quest_room_light.UNSEEN_LIGHT_REASON)

    def test_once_a_room_then_the_plan_goes_on(self):
        raw = self.cast_board()
        policy = q25.new_policy(raw)
        q25._set_stage(policy, raw, 4)
        q25.choose(policy, raw)
        self.assertEqual(policy.last_reason, quest_room_light.UNSEEN_LIGHT_REASON)
        q25.choose(policy, raw)
        self.assertNotEqual(policy.last_reason, quest_room_light.UNSEEN_LIGHT_REASON)

    def test_seen_lit_and_dark_again_it_is_read_again(self):
        raw = self.cast_board()
        policy = q25.new_policy(raw)
        q25._set_stage(policy, raw, 4)
        q25.choose(policy, raw)
        q25.choose(policy, self.lit(copy.deepcopy(raw)))
        raw["turn"] += 100
        q25.choose(policy, raw)
        self.assertEqual(policy.last_reason, quest_room_light.UNSEEN_LIGHT_REASON)

    def test_survival_comes_first(self):
        raw = self.cast_board(hp=300, monsters=[q25.monster(q25.SPECTRE, 5, 9)])
        _key, reason, _ = q25.decide(raw, stage=4)
        self.assertEqual(reason, quest_room_sweep.TELEPORT_REASON)

    def test_what_is_no_cast_lights_nothing(self):
        for line in ("何かが足下に転がってきた。", "何かが聞こえた。", "何かはうめいた。"):
            _key, reason, _ = q25.decide(self.cast_board(message=line), stage=4)
            self.assertNotEqual(reason, quest_room_light.UNSEEN_LIGHT_REASON, line)

    def test_a_blind_player_lights_nothing(self):
        raw = self.with_potion(self.cast_board(ccw=0))
        raw["player"]["status"]["blind"] = True
        _key, reason, _ = q25.decide(raw, stage=4)
        self.assertNotEqual(reason, quest_room_light.UNSEEN_LIGHT_REASON)

    def test_a_floor_without_the_field_keeps_its_old_answer(self):
        with patch.dict(q25.PLAN, {"light_dark_room": False}):
            _key, reason, _ = q25.decide(self.cast_board(), stage=4)
        self.assertNotEqual(reason, quest_room_light.UNSEEN_LIGHT_REASON)

    def test_a_lit_cell_is_no_place_for_the_unseen_attacker(self):
        cell = (5, 12)
        raw = self.cast_board()
        snapshot = parse_snapshot(copy.deepcopy(self.lit(raw)), q25.RACES)
        self.assertTrue(quest_room_light.drawn_lit(snapshot, cell))
        policy = q25.new_policy(raw)
        navigator = quest_room_sweep._navigator(policy, snapshot, 25)
        with patch.object(ConservativePolicy, "_recent_reverse_direction", lambda self, position: (0, -1)):
            self.assertEqual(quest_room_sweep._unseen_attacker_cells(policy, snapshot, navigator), set())


class Q25LeaveOnAQuietBoardTest(unittest.TestCase):
    def test_two_unseen_casts_with_only_a_left_alone_quyl_in_view_read_the_teleport(self):
        # DECLARED CONSTRUCTED: q25's board; the quyl is nothing to this plan until its turn.
        policy, answer_reason = None, None
        for turn in range(3):  # the first board is the arrival
            raw = q25.board((5, 8), speed=0, light=0, monsters=[q25.monster(QUYL, 9, 9)])
            raw["messages"] = ["何かが魔法で仲間を召喚した！"]
            raw["turn"] += turn * 10
            if policy is None:
                policy = q25.new_policy(raw)
                q25._set_stage(policy, raw, 4)
            key = str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
            answer_reason = policy.last_reason
            policy.confirm_key_posted(key)
        self.assertEqual(answer_reason, summon_response.LEAVE_REASON)


class Q25OpeningPotionTest(unittest.TestCase):
    """Owner 2026-11-05 「必須にはしないが、啓蒙の薬を持っていれば開幕すぐ飲む」.  DECLARED CONSTRUCTED."""

    with_potion = staticmethod(Q25DarkRoomTest.with_potion)

    def test_held_it_is_drunk_on_the_first_board_and_only_once(self):
        raw = self.with_potion(q25.board(speed=0), count=2)
        policy = q25.new_policy(raw)
        key = q25.choose(policy, raw)
        self.assertEqual(policy.last_reason, quest_room_light.OPENING_REASON)
        self.assertTrue(key.startswith("q"), key)
        q25.choose(policy, raw)
        self.assertNotEqual(policy.last_reason, quest_room_light.OPENING_REASON)

    def test_with_an_enemy_in_view_it_is_still_drunk_after_the_survival_rungs(self):
        raw = self.with_potion(q25.board(speed=0, monsters=[q25.monster(q25.SPECTRE, 13, 5)]))
        _key, reason, _ = q25.decide(raw)
        self.assertEqual(reason, quest_room_light.OPENING_REASON)

    def test_not_held_the_walk_starts(self):
        _key, reason, _ = q25.decide(q25.board(speed=0))
        self.assertEqual(reason, quest_room_sweep.WALK_REASON)

    def picked_up_later(self, *, monsters=()):
        """The walk at its third stop with none, then a board with one in the pack."""
        raw = q25.board(q25.Q25LightTest.MOUTH, speed=0, light=0)
        policy = q25.new_policy(raw)
        q25._set_stage(policy, raw, 2)
        q25.choose(policy, raw)
        self.assertNotEqual(policy.last_reason, quest_room_light.OPENING_REASON)
        raw = self.with_potion(raw)
        raw["visible_monsters"] = [dict(row) for row in monsters]
        return raw, policy

    def test_picked_up_later_it_is_drunk_on_the_next_quiet_board_and_only_once(self):
        # Owner 2026-11-05 「拾ったらすぐ飲む」.
        raw, policy = self.picked_up_later()
        key = q25.choose(policy, raw)
        self.assertEqual(policy.last_reason, quest_room_light.OPENING_REASON)
        self.assertTrue(key.startswith("q"), key)
        q25.choose(policy, raw)
        self.assertNotEqual(policy.last_reason, quest_room_light.OPENING_REASON)

    def test_picked_up_in_a_fight_it_waits_for_the_quiet_board(self):
        raw, policy = self.picked_up_later(monsters=[q25.monster(q25.SPECTRE, 5, 6)])
        q25.choose(policy, raw)
        self.assertNotEqual(policy.last_reason, quest_room_light.OPENING_REASON)
        raw["visible_monsters"] = []
        q25.choose(policy, raw)
        self.assertEqual(policy.last_reason, quest_room_light.OPENING_REASON)

    def test_broken_before_the_quiet_board_nothing_is_due(self):
        raw, policy = self.picked_up_later(monsters=[q25.monster(q25.SPECTRE, 5, 6)])
        q25.choose(policy, raw)
        raw["visible_monsters"] = []
        raw["inventory"] = [item for item in raw["inventory"] if item["sval"] != SV_POTION_ENLIGHTENMENT
                            or item["tval"] != TVAL_POTION]
        q25.choose(policy, raw)
        self.assertFalse(q25.navigator_of(policy).sweep_potion_due)

    def test_a_hall_drawn_lit_by_it_takes_no_read_at_the_mouth(self):
        raw = Q25DarkRoomTest.lit(q25.board(q25.Q25LightTest.MOUTH, speed=0))
        _key, reason, _ = q25.decide(raw, stage=q25.Q25LightTest.STAGE)
        self.assertEqual(reason, quest_room_sweep.WALK_REASON)

    def test_it_is_no_part_of_the_carry(self):
        self.assertNotIn("enlightenment", q25.STRATEGIES[25].required_force.get("required_potions", {}))


if __name__ == "__main__":
    unittest.main()
