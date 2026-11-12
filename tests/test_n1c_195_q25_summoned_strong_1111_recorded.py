"""Quest 25 phase 2 on n1-c life-195 (2026-11-11, game 05:33-05:40): the summoned dracolich, recorded.

On [5,1] the first Ipsissimus summons brought a dracolich (701) beside the player, and the phase read
Teleportation as planned (phase2 「それ以外の場合はテレポートで仕切り直す」).  Then the defect: the rally
(``quest25_battle._rally``) ended on the choke [1,18] as soon as no enemy was in view, and the phase's
walk back to the stand [7,1] went west along row 1 toward the dracolich.  Met on the way, it read
Teleportation again at full HP (5:34 on [1,9] at 541 of 542; 5:35 on [1,23] at 542 and, landed
beside it, on [1,8]), and where the way was open it walked on with the dracolich beside it (cold breath
529 -> 309, nether 402 -> 226).  On [2,2] (5:37) the dracolich had just stepped out of the light, the
board showed no enemy, and the plan's 「敵がいない時に下がっていれば飲む」 drank the Restore Life Levels;
the dracolich was beside the player on the next board.  The scrolls ran short, Recall was read, and the
quest failed.

Owner 2026-11-11 「隘路で待って倒す」: 「仕切り直しの隘路（召喚を受けないマス）で、最後に見えた強敵が来るのを
待って迎え撃つ。倒してから立ち位置へ戻る。HP の線を切ったら今の決まりで立て直す。」

The boards (fixture from tests/extract_n1c_195_q25_summoned_strong_1111_fixture.py) are the ring's,
one per decision; the decision log of that window was gone, so no key or reason was recorded: what the
process did is read from the next board (the scroll and potion counts, the landing cell).  Each test
replays the boards from ``START`` ([7,1], 05:33, full HP, the phase about to haste) by one policy
through the public ``choose_key``; the boards after a decision are the recorded ones whatever the
replay decided (each check names the board it reads).

DECLARED CONSTRUCTED: the phase battle the process held is not in the ring.  It is restored by the real
producer (quest25_battle_record, the restart path) from a record written here: the Ipsissimus phase,
ready, with the ambush's four kills and the wall-passers' kills the ring's earlier boards show (a
spectre and two shadow demons; more may have died before the ring).  The process's magic-eater lists and
absorption record are not in the ring either: the replayed character knows no absorbed power, so
its attacks are the crossbow and melee (the walk is the unseen pen's 「見えるマスへ移って撃つ」 walk).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import dataclasses
import gzip
import json
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_battle_record, quest25_geometry as geo, quest_exposure
from hengbot import quest_no_teleport
from hengbot.model import (
    SV_POTION_RESTORE_EXP, SV_SCROLL_TELEPORT, TVAL_POTION, TVAL_SCROLL, parse_snapshot,
)
from hengbot.policy_constants import SKILL_KNOWLEDGE_MACRO
from hengbot.quest_plan_base import HOLD_REASON, RESTORE_REASON
from hengbot.quest_room_sweep import TELEPORT_REASON as ESCAPE_REASON
from tests.support import q25_house as q25

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-195-q25-summoned-strong-1111.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

DRACOLICH = 701
START = 173                  # [7,1] 05:33, full HP
SUMMONED = 180               # [5,1]: the dracolich beside the player, the planned Teleportation
CHOKE = (188, 189)           # [1,18] 05:34: the rally's choke, nothing in view
MET = (197, 198)             # [1,10] / [1,9] 05:34: the dracolich in view on the walk west
WALK_WEST = (205, 206, 207)  # [1,25]-[1,23] 05:35: the dracolich in view on row 1
RESTORED = 232               # [2,2] 05:37: no enemy shown, the Restore Life Levels drunk
BACK = (259, 260, 261)       # [9,1]-[7,1] 05:39: after the fifth Teleportation, the walk back on
ESCAPES = (236, 254, 277, 279)  # the plan's escape (the 1-turn instant death / the HP line)


def _record(first):
    """DECLARED CONSTRUCTED: the battle record the restart path restores (see the module note)."""
    held = battle.Battle(
        phase=battle.PHASE_NAMES.index("ipsissimus"), ready=True,
        kills={geo.HOUND: 1, geo.SKELETAL_T: 1, geo.VAMPIRE: 1, geo.SPECTRAL_T: 1,
               geo.SPECTRE: 1, geo.SHADOW: 2})
    snapshot = parse_snapshot(copy.deepcopy(first), q25.RACES)
    return {"version": quest25_battle_record.VERSION, "floor": list(snapshot.floor_key),
            "turn": first["turn"], "board": None,
            "battle": {field.name: quest25_battle_record._encode(getattr(held, field.name))
                       for field in dataclasses.fields(held) if field.name != "observed"}}


def replay(*, probe=None):
    """{board index: (key, reason)} of the boards from ``START``, by one policy."""
    answers = {}
    boards = CASE["boards"]
    with TemporaryDirectory() as directory:
        policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                    quest_strategies=q25.STRATEGIES)
        first = copy.deepcopy(boards[START])
        policy.prime(parse_snapshot(first, policy._monrace_knowledge))
        policy.consume_skill_knowledge(dict(
            copy.deepcopy(CASE["skill"]), turn=first["turn"],
            player=dict(CASE["skill"]["player"], level=first["player"]["level"])))
        path = Path(directory) / "q25-battle.json"
        path.write_text(json.dumps(_record(first), ensure_ascii=False), encoding="utf-8")
        policy._q25_battle_record_path = path
        asked = False
        for index in range(START, len(boards)):
            raw = copy.deepcopy(boards[index])
            if asked:
                # The ~f list the policy asked for arrives as the CLI delivers it (cli.py).
                policy.consume_skill_knowledge(dict(
                    copy.deepcopy(CASE["skill"]), turn=raw["turn"],
                    player=dict(CASE["skill"]["player"], level=raw["player"]["level"])))
            snapshot = parse_snapshot(raw, policy._monrace_knowledge)
            key = str(policy.choose_key(snapshot))
            answers[index] = (key, policy.last_reason)
            if probe is not None:
                probe(policy, snapshot, index)
            asked = key == SKILL_KNOWLEDGE_MACRO
            policy.confirm_key_posted(key)
    return answers


def cell(index):
    player = CASE["boards"][index]["player"]
    return player["y"], player["x"]


def count(index, tval, sval):
    return sum(item["count"] for item in CASE["boards"][index]["inventory"]
               if (item["tval"], item["sval"]) == (tval, sval))


def dracolich(index):
    return next(((monster["y"], monster["x"]) for monster in CASE["boards"][index]["visible_monsters"]
                 if monster["race_id"] == DRACOLICH), None)


def scrolls(index):
    return count(index, TVAL_SCROLL, SV_SCROLL_TELEPORT)


class RecordingTest(unittest.TestCase):

    def test_the_planned_teleport_then_three_more_at_full_hp(self):
        self.assertEqual((cell(SUMMONED), dracolich(SUMMONED)), ((5, 1), (6, 2)))
        self.assertEqual((scrolls(SUMMONED), scrolls(SUMMONED + 1), cell(SUMMONED + 1)), (15, 14, (1, 22)))
        # 05:34 on [1,9] (541 of 542), the dracolich on [1,3]: read, landed on [6,29].
        self.assertEqual((cell(198), dracolich(198), CASE["boards"][198]["player"]["hp"]), ((1, 9), (1, 3), 541))
        self.assertEqual((scrolls(198), scrolls(199), cell(199)), (14, 13, (6, 29)))
        # 05:35 on [1,23] (542), the dracolich on [1,7]: landed on [1,8] beside it, and read again.
        self.assertEqual((cell(207), dracolich(207), CASE["boards"][207]["player"]["hp"]), ((1, 23), (1, 7), 542))
        self.assertEqual((scrolls(207), scrolls(208), scrolls(209)), (13, 12, 11))

    def test_the_rally_ended_on_the_choke_and_the_walk_went_west(self):
        for index in CHOKE:
            self.assertEqual((cell(index), dracolich(index)), ((1, 18), None))
        self.assertEqual([cell(index) for index in range(190, 199)],
                         [(1, 17), (1, 16), (1, 15), (1, 14), (1, 13), (1, 12), (1, 11), (1, 10), (1, 9)])

    def test_the_restore_was_drunk_with_the_dracolich_a_step_off(self):
        self.assertEqual((cell(RESTORED - 1), dracolich(RESTORED - 1)), ((1, 3), (1, 5)))
        self.assertEqual((cell(RESTORED), dracolich(RESTORED)), ((2, 2), None))
        self.assertTrue(CASE["boards"][RESTORED]["player"]["exp_drained"])
        self.assertEqual((count(RESTORED, TVAL_POTION, SV_POTION_RESTORE_EXP),
                          count(RESTORED + 1, TVAL_POTION, SV_POTION_RESTORE_EXP)), (1, 0))
        self.assertEqual(dracolich(RESTORED + 1), (1, 3))


class SummonedStrongTest(unittest.TestCase):
    """Owner 2026-11-11 「隘路で待って倒す」, replayed."""

    @classmethod
    def setUpClass(cls):
        cls.memory = {}

        def probe(policy, snapshot, index):
            cls.memory[index] = getattr(battle._ctx(policy, snapshot).battle, "strong", None)

        # DECLARED: the 11-11 replay under its own rules.  The owner's 2026-11-12 rule 「大広間が危険な段階3
        # まではテレポートが危険なので禁止」 forbids the phase-2 Teleportation the recording made
        # (``ElevenTwelveTest`` below); with it the boards after 180 are no longer the policy's.
        with patch.object(quest_no_teleport, "q25_hall_forbids", lambda *_args: False):
            cls.answers = replay(probe=probe)

    def test_the_planned_teleport_remembers_the_dracolich(self):
        key, reason = self.answers[SUMMONED]
        self.assertEqual(reason, battle.TELEPORT_REASON)
        self.assertTrue(key.startswith("r"), key)
        self.assertEqual(self.memory[SUMMONED], ((DRACOLICH, (6, 2)),))

    def test_the_choke_holds_with_nothing_in_view(self):
        for index in CHOKE:
            self.assertEqual(self.answers[index], ("5", HOLD_REASON), index)

    def test_no_teleport_at_full_hp_and_no_step_toward_it(self):
        teleports = [index for index, (_, reason) in self.answers.items() if reason == battle.TELEPORT_REASON]
        self.assertEqual(teleports, [SUMMONED])
        for index in (*MET, *WALK_WEST):
            key, reason = self.answers[index]
            self.assertEqual(reason, battle.WALK_REASON, index)
            here, there = cell(index), dracolich(index)
            goal = (here[0] + {"7": -1, "8": -1, "9": -1, "1": 1, "2": 1, "3": 1}.get(key, 0),
                    here[1] + {"7": -1, "4": -1, "1": -1, "9": 1, "6": 1, "3": 1}.get(key, 0))
            self.assertGreaterEqual(quest_exposure.game_distance(goal, there),
                                    quest_exposure.game_distance(here, there), (index, key))

    def test_no_restore_while_it_is_remembered(self):
        self.assertEqual(self.memory[RESTORED], ((DRACOLICH, (1, 5)),))
        self.assertNotEqual(self.answers[RESTORED][1], RESTORE_REASON)

    def test_after_the_fifth_teleport_the_choke_holds_not_the_walk_on(self):
        self.assertEqual(cell(BACK[0]), (9, 1))
        self.assertEqual(self.answers[BACK[0]], ("5", HOLD_REASON))
        for index in BACK:
            self.assertNotEqual(self.answers[index][1], battle.SIGHT_REASON, index)

    def test_control_the_plans_escape_is_unchanged(self):
        # 「HP の線を切ったら今の決まりで立て直す」: the survival rungs above the plan still read it.
        for index in ESCAPES:
            key, reason = self.answers[index]
            if index == 254:
                # Since 2026-11-12 (t3-survival-1112 D, the game's spell odds: the innate breath only in the 2 x freq share) the board's next action no longer reaches the HP: the plan's blow.
                self.assertEqual((key, reason), ("4", "quest-strategy:melee"))
                continue
            self.assertEqual(reason, ESCAPE_REASON, index)
            self.assertTrue(key.startswith("r"), (index, key))



class ElevenTwelveTest(unittest.TestCase):
    """Owner 2026-11-12: on phase 2 no Teleportation; the dracolich beside the player is fought."""

    def test_the_summoned_board_fights_instead_of_teleporting(self):
        answers = replay()
        key, reason = answers[SUMMONED]
        self.assertNotEqual(reason, battle.TELEPORT_REASON)
        self.assertFalse(key.startswith("r"), key)


if __name__ == "__main__":
    unittest.main()
