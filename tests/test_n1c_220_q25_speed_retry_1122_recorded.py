"""Quest 25 on n1-c life-220 (2026-11-22 12:59-13:00): one failed Speed cast, the floor without haste, recorded.

Owner 2026-11-01 「スピードの薬を使用する場面では代わりに取り込んだ杖を試みる」 (a reliable absorbed Staff of
Speed: no potion bought or carried), 2026-11-04 「魔道具術師は取り込んだスピードが残り10回以上なら戦闘時に
加速する」, 2026-11-06 Q25 phase 2 「事前に加速して(6,1)(5,1)と移動」 and the Q25 ``speed_potion_use_when``
(the 3-turn expected damage at least half the HP).

n1-c life-220 (Magic-Eater Lv36, Zombie, build bot-57ba99c2c, no Potion of Speed carried):

 * Decision 2071 (turn 2080298, [7,1], a shadow demon in view): ``quest-strategy:quaff-speed:absorbed-power``
   ``mAw``.  The cast failed (「呪文をうまく唱えられなかった！」 on the next board; cmd-magiceat.cpp returns
   before the charge is spent: the turn is lost, the charge kept).  speed_dose remembered the floor
   (``failed_floor``) and, with no potion to drink instead, gave no dose for the rest of the floor.
 * Decisions 2196 and 2220 (turns 2083231 / 2084475, phase 2 on [7,1]): ``quest25:walk`` '8', the
   pre-haste skipped; 2205-2206 the summons fight (3-turn operational damage 513 of HP 670/675) went on
   unhasted, the Emperor Wight beside the player took two more Potions of Healing, the
   HEALING_FLOOR restock recall was read and the quest failed.

The fix: the failed-floor memory skips the cast only while a Potion of Speed above the scene's reserve
is carried (it is drunk as designed); without one the absorbed Speed is cast again.

Recorded: tests/fixtures/n1c-220-q25-speed-retry-1122.json.gz
(tests/extract_n1c_220_q25_speed_retry_1122_fixture.py): the boards of decisions 2071, 2072, 2196,
2205, 2206 and 2220 and their decision rows.  Every decision is the public ``choose_key`` of a fresh
policy restoring the battle record through the real path.

DECLARED RECONSTRUCTED: the battle record of each phase (the kills the floor's earlier boards show:
the hound, the skeletal and spectral tyrannosaurs, the vampire lord, the spectres and shadow demons;
``ready``; ranged style), the remembered magic-eater lists (the rows of
test_n1c_208_q25_patrol_1115_recorded.lists, n1-c's earlier Speed staff at 93%).  The failed cast's
receipt (``failed:magic-eater`` under the cast's owner) is the executor's (me_menu.USE_FAILED) on
decision 2072's board, observed through speed_dose after decision 2071's dose.
DECLARED CONSTRUCTED: one Potion of Speed added to a recorded board (the control: a carried potion
above the reserve is drunk after the failure, as before).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import dataclasses
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_battle_record, quest25_geometry as geo
from hengbot import quest_plan_base, speed_dose
from hengbot.me_absorbed_substitutes import CAST_SUFFIX
from hengbot.me_menu import USE_FAILED
from hengbot.model import SV_POTION_SPEED, TVAL_POTION, parse_snapshot
from tests.support import q25_house as q25
from tests.test_n1c_208_q25_patrol_1115_recorded import lists

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-220-q25-speed-retry-1122.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

ROWS = {row["decision_sequence"]: row for row in CASE["decisions"]}
CAST = "mAw"                         # m + staff + I2A(SV_STAFF_SPEED)
FAILED_MESSAGE = "呪文をうまく唱えられなかった！"
STAGE1_CAST, STAGE1_FAILED = 2071, 2072
PRE_HASTE = (2196, 2220)             # phase 2 on [7,1]: 「事前に加速して(6,1)(5,1)と移動」
SUMMONS_FIGHT = (2205, 2206)
STAGE1_REASON = quest_plan_base.SPEED_REASON + CAST_SUFFIX
WALL_PASSER_KILLS = {geo.HOUND: 1, geo.SKELETAL_T: 1, geo.VAMPIRE: 1, geo.SPECTRAL_T: 1}


def board(sequence):
    turn = ROWS[sequence]["turn"]
    return copy.deepcopy(next(raw for raw in CASE["boards"] if raw["turn"] == turn))


def speed_potions(raw):
    return sum(item["count"] for item in raw["inventory"]
               if (item["tval"], item["sval"]) == (TVAL_POTION, SV_POTION_SPEED))


def with_speed_potion(raw):
    """DECLARED CONSTRUCTED: one Potion of Speed carried (the inventory's first potion as its row)."""
    potion = copy.deepcopy(next(item for item in raw["inventory"] if item["tval"] == TVAL_POTION))
    potion.update(sval=SV_POTION_SPEED, count=1, name="スピードの薬", inscription="")
    raw["inventory"].insert(0, potion)
    return raw


def _record(raw, phase, kills):
    """DECLARED RECONSTRUCTED (module note): the battle record the restart path restores."""
    held = battle.Battle(phase=battle.PHASE_NAMES.index(phase), ready=True, style="ranged",
                         enlightened=True, kills=dict(kills))
    snapshot = parse_snapshot(copy.deepcopy(raw), q25.RACES)
    return {"version": quest25_battle_record.VERSION, "floor": list(snapshot.floor_key),
            "turn": raw["turn"], "board": None,
            "battle": {field.name: quest25_battle_record._encode(getattr(held, field.name))
                       for field in dataclasses.fields(held) if field.name != "observed"}}


class _Replay(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def policy(self, raw, phase, kills):
        path = self.directory / "q25-battle.json"
        path.write_text(json.dumps(_record(raw, phase, kills), ensure_ascii=False), encoding="utf-8")
        policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                    quest_strategies=q25.STRATEGIES)
        policy._q25_battle_record_path = path
        policy._warning_cell_record_path = self.directory / "warning-cells.json"
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy.prime(snapshot)
        policy._skill_exp_cache = (0, 0, snapshot.player.level, policy._town_visit_epoch)
        policy._me_device_lists = lists()
        return policy

    @staticmethod
    def snapshot(policy, raw):
        return parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)

    def decide(self, policy, raw):
        key = str(policy.choose_key(self.snapshot(policy, raw)))
        return key, policy.last_reason

    def fail_stage1_cast(self, policy, failed_board=None):
        """Decision 2071's dose and decision 2072's receipt, through speed_dose (module note)."""
        cast = speed_dose.key(policy, self.snapshot(policy, board(STAGE1_CAST)), quest_plan_base.SPEED_REASON)
        self.assertEqual((cast, policy.last_reason), (CAST, STAGE1_REASON))
        raw = failed_receipt(board(STAGE1_FAILED) if failed_board is None else failed_board)
        speed_dose.observe(policy, self.snapshot(policy, raw))
        self.assertEqual(getattr(policy, speed_dose.MEMORY).failed_floor, self.snapshot(policy, raw).floor_key)


def failed_receipt(raw):
    """The executor's receipt of the failed cast on the board that shows its message."""
    raw["_completed_operation_owner"] = STAGE1_REASON
    raw["_completed_operation_receipt"] = {"refusal": USE_FAILED}
    return raw


class TheRecordingTest(unittest.TestCase):
    def test_the_failed_cast_and_the_unhasted_floor(self):
        self.assertEqual((ROWS[STAGE1_CAST]["reason"], ROWS[STAGE1_CAST]["key"]), (STAGE1_REASON, CAST))
        self.assertIn(FAILED_MESSAGE, board(STAGE1_FAILED)["messages"])
        self.assertEqual(USE_FAILED, "failed:magic-eater")
        for sequence in PRE_HASTE:
            raw = board(sequence)
            self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (7, 1))
            self.assertEqual((ROWS[sequence]["reason"], ROWS[sequence]["key"]), (battle.WALK_REASON, "8"))
        for sequence in SUMMONS_FIGHT:
            self.assertGreaterEqual(ROWS[sequence]["operational_total"], ROWS[sequence]["hp"] / 2)
            self.assertNotIn(CAST, ROWS[sequence]["key"])
        for sequence in ROWS:
            self.assertEqual(speed_potions(board(sequence)), 0)


class ThePreHasteTest(_Replay):
    """Phase 2 on [7,1]: 「事前に加速して(6,1)(5,1)と移動」."""

    def phase2(self, sequence):
        raw = board(sequence)
        return raw, self.policy(raw, "ipsissimus", {**WALL_PASSER_KILLS, geo.SPECTRE: 2, geo.SHADOW: 4})

    def test_control_no_failure_the_pre_haste_casts(self):
        for sequence in PRE_HASTE:
            raw, policy = self.phase2(sequence)
            self.assertEqual(self.decide(policy, raw), (CAST, battle.HASTE_REASON + CAST_SUFFIX), sequence)

    def test_after_the_failed_cast_with_no_potion_the_pre_haste_casts_again(self):
        for sequence in PRE_HASTE:
            raw, policy = self.phase2(sequence)
            self.fail_stage1_cast(policy)
            self.assertEqual(self.decide(policy, raw), (CAST, battle.HASTE_REASON + CAST_SUFFIX), sequence)

    def test_after_the_failed_cast_a_carried_potion_is_drunk(self):
        for sequence in PRE_HASTE:
            raw, policy = self.phase2(sequence)
            raw = with_speed_potion(raw)
            self.fail_stage1_cast(policy, with_speed_potion(board(STAGE1_FAILED)))
            key, reason = self.decide(policy, raw)
            self.assertEqual((key[:1], reason), ("q", battle.HASTE_REASON), sequence)


class TheSummonsFightTest(_Replay):
    """Decision 2206: 3-turn operational damage 513 of HP 675, the plan's ``speed_potion_use_when``
    condition 1 (half the HP) asks for haste."""

    def test_after_the_failed_cast_the_fight_is_hasted(self):
        raw = board(SUMMONS_FIGHT[1])
        policy = self.policy(raw, "ipsissimus", {**WALL_PASSER_KILLS, geo.SPECTRE: 2, geo.SHADOW: 4})
        self.fail_stage1_cast(policy)
        self.assertEqual(self.decide(policy, raw), (CAST, STAGE1_REASON))


class TheStage1RetryTest(_Replay):
    """Decision 2072: the failure kept the charge; the plan's haste (half the HP in 3 turns) asks again."""

    def test_the_next_board_casts_again(self):
        raw = board(STAGE1_CAST)
        policy = self.policy(raw, "wall-passers", WALL_PASSER_KILLS)
        self.assertEqual(self.decide(policy, raw), (CAST, STAGE1_REASON))
        policy.confirm_key_posted(CAST)
        failed = failed_receipt(board(STAGE1_FAILED))
        self.assertEqual(self.decide(policy, failed), (CAST, STAGE1_REASON))


if __name__ == "__main__":
    unittest.main()
