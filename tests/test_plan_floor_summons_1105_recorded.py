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
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hengbot import quest_find_exit, quest_room_sweep, summon_response
from hengbot.model import SV_POTION_CURE_CRITICAL, TVAL_POTION, _parse_items, parse_snapshot
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


if __name__ == "__main__":
    unittest.main()
