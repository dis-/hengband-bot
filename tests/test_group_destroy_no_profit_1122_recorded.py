"""A sensed group each T2 or T3 alone and T1 together, that killing yields nothing for, is
destroyed (owner 2026-11-22 「倒して利益のない場合は破壊する」).

The question (verbatim) 「11-13 の決まり『1体ずつは T2 以下でも、まとめて T1 の感知した群れは感知した
T1 と同じに扱う』の『T2 以下』に T3 も含めるか」: the 11-13 group (threat_tiers ``_sensed_strong``)
counted T2 members only, so a pack each T3 alone was no *Destruction* target however strong
together.  Now the members that killing yields nothing for (threat_tiers ``kill_profit``: no
DROP_GOOD / DROP_GREAT, fewer than 3 expected drops a kill) make the group
(``_unprofitable_group``); a member worth killing is left out and fought as before.

Recorded (Angband 80F; extract_group_destroy_no_profit_1122_fixtures.py), each window ending on
the board before the recorded esp-threat Recall:

- n1-c life-219 04:32:05 (tests/fixtures/n1c-219-group-hounds-1122.jsonl.gz, 2532300-2533283):
  a hound pack (エア・ハウンド 8, エナジー・ハウンド 4, 重力ハウンド 2, 魔力・カオス・ハウンド; no
  drops) awake and sensed, each T3 alone, T1 together; 闇の格闘王『ベガ』 (DROP_GOOD),
  太古の大神官『イムホテップ』 (DROP_GOOD) and 冥界レイス (6.9 drops) are worth killing.
- n1-c life-219 05:08:20 (n1c-219-group-moai-1122.jsonl.gz, 2626500-2627460): nine モアイ (DROP_90,
  0.9 a kill), each T3 alone, T1 together.
- n1-b life-413 04:16:00 (n1b-413-group-tindalos-1122.jsonl.gz, 3046700-3047662): three
  ティンダロスの猟犬, each T3 alone and T2 together (supplies win): no T1, the rule does not reach it.
- n1-c life-219 (n1c-219-group-dragons-1122.jsonl.gz, 2620200-2621174): the 万色 dragons (万色ドラゴン
  and 古代万色ドラゴン, 10.5-13.5 drops a kill), shown without グレート・万色ワイアーム (T1 alone): T1
  together, worth killing, not destroyed.

The replays run every board but the last with the new group off (``_unprofitable_group`` patched to
none), so the policy's state is the one the recorded run had; the last board is the decision.  On
main its answer was the esp-threat rest's absorbed heal (the Recall's replacement since
4e1d220173).  DECLARED RECONSTRUCTED: the power lists, the town-arrival checkpoints' (n1-c
05:50:29, tests/fixtures/n1c-219-me-lists-0550-1122.json; n1-b 04:17:07,
n1b-413-me-lists-0417-1122.json), with the absorbed *破壊* at its full charges and the rod of
全感知 (n1-b) shown charging.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
from dataclasses import replace
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import threat_tiers
from hengbot.me_device_attacks import observe_lists
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
N1C_LISTS = FIXTURES / "n1c-219-me-lists-0550-1122.json"
N1B_LISTS = FIXTURES / "n1b-413-me-lists-0417-1122.json"
HOUNDS = FIXTURES / "n1c-219-group-hounds-1122.jsonl.gz"
MOAI = FIXTURES / "n1c-219-group-moai-1122.jsonl.gz"
TINDALOS = FIXTURES / "n1b-413-group-tindalos-1122.jsonl.gz"
DRAGONS = FIXTURES / "n1c-219-group-dragons-1122.jsonl.gz"
DESTRUCTION = ("mA3", "emergency:destruction:absorbed-power")
HEAL = ("mAq", "esp-threat:heal:absorbed-power")
MOAI_RACE = 1160
HOUND_NAMES = {"エア・ハウンド", "エナジー・ハウンド", "重力ハウンド", "魔力ハウンド", "カオス・ハウンド"}
WORTH_KILLING = {"闇の格闘王『ベガ』", "太古の大神官『イムホテップ』", "冥界レイス"}


def _boards(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _lists(path):
    lists = json.loads(path.read_text(encoding="utf-8"))["lists"]
    for row in lists["rod"]:
        if row["name"] == "全感知":
            row["charging"] = row["max"]
    for row in lists["staff"]:
        if row["name"] == "*破壊*":
            row["current"] = row["max"]
    return lists


class GroupDestroyNoProfitRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def drive(self, path, lists, monrace=None):
        monrace = monrace or self.monrace
        boards = _boards(path)
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), monrace)
        first = parse_snapshot(copy.deepcopy(boards[0]), monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        for kind in ("staff", "wand", "rod"):
            listed = dict(copy.deepcopy(boards[0]), turn=boards[0]["turn"] - 1,
                          _magic_eater_power_list={"kind": kind, "rows": lists[kind]})
            observe_lists(policy, parse_snapshot(listed, monrace))
        previous = None
        # The recorded run's state: the new group off on every board but the decision's.
        off = mock.patch.object(threat_tiers, "_unprofitable_group", lambda *_: [], create=True)
        off.start()
        try:
            for raw in boards[:-1]:
                raw = copy.deepcopy(raw)
                if previous is not None:
                    raw["_completed_operation_owner"] = previous
                key = policy.choose_key(policy.with_known_skill_exp(parse_snapshot(raw, monrace)))
                if key:
                    policy.confirm_key_posted(key)
                previous = policy.last_reason if key else None
        finally:
            off.stop()
        raw = copy.deepcopy(boards[-1])
        if previous is not None:
            raw["_completed_operation_owner"] = previous
        board = policy.with_known_skill_exp(parse_snapshot(raw, monrace))
        return policy, board, policy.choose_key(board)

    def test_the_hound_pack_is_destroyed(self):
        policy, board, key = self.drive(HOUNDS, _lists(N1C_LISTS))
        self.assertEqual(board.turn, 2533283)
        # Recorded: esp-threat:leave-recall; main: the absorbed heal in its place.
        self.assertEqual((key, policy.last_reason), DESTRUCTION)
        _, strong = threat_tiers._sensed_strong(policy, board)
        names = {monster.name for monster in strong}
        self.assertTrue(HOUND_NAMES <= names, names)
        # The ones worth killing are no member of the group.
        self.assertFalse(names & WORTH_KILLING, names)

    def test_the_nine_moai_are_destroyed(self):
        policy, board, key = self.drive(MOAI, _lists(N1C_LISTS))
        self.assertEqual(board.turn, 2627460)
        self.assertEqual((board.player.hp, board.player.max_hp), (640, 836))
        # Recorded: esp-threat:leave-recall; main: the absorbed heal in its place.
        self.assertEqual((key, policy.last_reason), DESTRUCTION)
        _, strong = threat_tiers._sensed_strong(policy, board)
        self.assertEqual([monster.race_id for monster in strong], [MOAI_RACE] * 9)

    def test_moai_worth_killing_are_not_destroyed(self):
        # Reconstructed: the モアイ race given DROP_GOOD; every other fact as recorded.
        monrace = dict(self.monrace)
        monrace[MOAI_RACE] = replace(monrace[MOAI_RACE],
                                     flags=monrace[MOAI_RACE].flags | {"DROP_GOOD"})
        policy, board, key = self.drive(MOAI, _lists(N1C_LISTS), monrace)
        self.assertEqual(threat_tiers._sensed_strong(policy, board)[1], [])
        self.assertEqual((key, policy.last_reason), HEAL)

    def test_the_tindalos_hounds_together_t2_are_unchanged(self):
        policy, board, key = self.drive(TINDALOS, _lists(N1B_LISTS))
        self.assertEqual(board.turn, 3047662)
        hostiles, strong = threat_tiers._sensed_strong(policy, board)
        self.assertEqual(strong, [])
        self.assertEqual(threat_tiers.tiered(policy, board, hostiles, contact=True).tier,
                         threat_tiers.T2)
        self.assertEqual((key, policy.last_reason), HEAL)

    def test_the_dragons_worth_killing_are_not_a_group(self):
        raw = copy.deepcopy(_boards(DRAGONS)[-1])
        for field in ("detected_monsters", "visible_monsters"):
            raw[field] = [monster for monster in raw[field] if "万色ドラゴン" in monster["name"]]
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        board = parse_snapshot(raw, self.monrace)
        policy.prime(board)
        hostiles, strong = threat_tiers._sensed_strong(policy, board)
        worth = [monster for monster in hostiles if threat_tiers.kill_profit(policy, board, monster)]
        self.assertEqual(len(worth), 9)
        self.assertTrue(threat_tiers.cannot_win(
            threat_tiers.tiered(policy, board, hostiles, contact=True), board.player.hp))
        self.assertEqual(strong, [])


if __name__ == "__main__":
    unittest.main()
