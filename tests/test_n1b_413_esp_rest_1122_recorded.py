"""Where the ESP threat refuses the rest: a sensed T1 is gone to, the absorbed heal in the Recall's
place (n1-b life-413, 1122).

Recorded (Angband 80F, the Magic-Eater Lv39; extract_n1b_413_esp_rest_1122_fixtures.py).  On both
boards the HP wanted a rest (below REST_TARGET_HP_RATIO) and awake monsters known only by telepathy
made the ESP-threat tier strong without a feasible fight (policy_combat ``_esp_threat_rest_key``):
recorded ``esp-threat:leave-recall``.

- tests/fixtures/n1b-413-esp-rest-heal-1122.jsonl.gz (2609000-2610137, 02:50:56): HP 628/723, two
  魔力ハウンド (each T3 alone; 7 and 17 off).  Owner 2026-11-22 (verbatim)
  「休息が難しいときに取り込んだ回復の力を使うことは許可する」: the absorbed Cure Light Wounds (18
  charges at 96%, 2d8 a cast) restores the 23 HP short of the rest's target, so it is cast in the
  Recall's place (status_cure ``absorbed_heal_key``); with too few charges the Recall stays.
- tests/fixtures/n1b-413-esp-rest-sensed-t1-1122.jsonl.gz (2620300-2621415, 02:56:03): HP 480/748,
  『サウロンの口』 (T1 alone, awake) sensed 28 off, the sensed approach owning it with no known way
  (threat_tiers ``approach_owns``; its walk had no step, so the rungs below answer).  Owner
  2026-11-10 「積極的に*破壊*で消しにいく」: it is gone to, not left; the 194 HP short of the rest's
  target are more than the 18 Cure Light Wounds restore, so no heal, and the rungs below explore.

The replays settle each power cast as the executor does (the previous decision's reason as the
completed operation's owner).  DECLARED RECONSTRUCTED: the power lists, the town-arrival checkpoint's
of 04:17:07 (tests/fixtures/n1b-413-me-lists-0417-1122.json; 軽傷の治癒 18 of 19 charges), shown
unstunned before the first board; the rod of 全感知 shown charging.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
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
LISTS = FIXTURES / "n1b-413-me-lists-0417-1122.json"
HEAL = FIXTURES / "n1b-413-esp-rest-heal-1122.jsonl.gz"
SENSED_T1 = FIXTURES / "n1b-413-esp-rest-sensed-t1-1122.jsonl.gz"
HEAL_TURN = 2610137
SENSED_T1_TURN = 2621415
RECALL = ("rh", "esp-threat:leave-recall")
CURE_LIGHT_CAST = ("mAq", "esp-threat:heal:absorbed-power")


def _boards(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


class EspRestRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.heal_boards = _boards(HEAL)
        cls.sensed_boards = _boards(SENSED_T1)

    # The window's hound packs (each T3 alone, no drops, T1 together) are destroyed by the 11-22
    # group (threat_tiers ``_unprofitable_group``, test_group_destroy_no_profit_1122_recorded),
    # which the recorded boards do not show; here it is off, so the run is the recorded one.
    def setUp(self):
        group = mock.patch.object(threat_tiers, "_unprofitable_group", lambda *_: [])
        group.start()
        self.addCleanup(group.stop)

    def lists(self, cure_light=None):
        lists = json.loads(LISTS.read_text(encoding="utf-8"))["lists"]
        for row in lists["rod"]:
            if row["name"] == "全感知":
                row["charging"] = row["max"]
        for row in lists["staff"]:
            if row["name"] == "軽傷の治癒" and cure_light is not None:
                row["current"] = cure_light
        return lists

    def drive(self, boards, lists):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = parse_snapshot(copy.deepcopy(boards[0]), self.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        for kind in ("staff", "wand", "rod"):
            listed = dict(copy.deepcopy(boards[0]), turn=boards[0]["turn"] - 1,
                          _magic_eater_power_list={"kind": kind, "rows": lists[kind]})
            observe_lists(policy, parse_snapshot(listed, self.monrace))
        previous = key = board = None
        for raw in boards:
            raw = copy.deepcopy(raw)
            if previous is not None:
                raw["_completed_operation_owner"] = previous
            board = policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))
            key = policy.choose_key(board)
            if board.turn == boards[-1]["turn"]:
                break
            if key:
                policy.confirm_key_posted(key)
            previous = policy.last_reason if key else None
        return policy, board, key

    def test_the_absorbed_cure_light_wounds_in_place_of_the_recall(self):
        policy, board, key = self.drive(self.heal_boards, self.lists())
        self.assertEqual(board.turn, HEAL_TURN)
        self.assertEqual((board.player.hp, board.player.max_hp), (628, 723))
        # Recorded: esp-threat:leave-recall.
        self.assertEqual((key, policy.last_reason), CURE_LIGHT_CAST)
        self.assertEqual(policy._esp_threat_assessment["action"], "leave:heal")

    def test_too_few_charges_keep_the_recall(self):
        # Two casts (2d8 each, 9 on average) do not restore the 23 HP short of the target.
        policy, _, key = self.drive(self.heal_boards, self.lists(cure_light=2))
        self.assertEqual((key, policy.last_reason), RECALL)

    def test_a_sensed_t1_the_approach_owns_is_not_left(self):
        policy, board, key = self.drive(self.sensed_boards, self.lists())
        self.assertEqual(board.turn, SENSED_T1_TURN)
        # Recorded: esp-threat:leave-recall.
        self.assertNotEqual((key, policy.last_reason), RECALL)
        self.assertFalse(policy.last_reason.startswith("esp-threat:leave-"), policy.last_reason)
        self.assertEqual(policy._esp_threat_assessment["action"], "approach-pending")
        self.assertEqual(policy.last_reason, "explore")
        self.assertTrue(threat_tiers.approach_pending(policy, board))


if __name__ == "__main__":
    unittest.main()
