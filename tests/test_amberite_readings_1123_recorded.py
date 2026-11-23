"""The decision log names the rule that erased an Amberite with *Destruction* (1123, record only).

The loot yield study C:/hengband-backups/pdca/loot-yield-1123: n1-b life-416 (Magic-Eater with
resist curse) erased アンバーの狂気の夢想家『ブランド』 21 times, 『ハルコン』 13, 『ジェラード』 13 and
killed none, while the owner's 2026-11-17 rule kills them with resist curse once its conditions
hold (amberite_curse: 「倒すときは視界とその回りに起きた敵が他にいなくてHPが十分のとき、加速して
耐性の薬を使用して倒す」; until then 2026-11-18 「条件がそろうまで *破壊* で消す」).  The log said
neither which rung sent the use nor which condition read the Amberite T1.  Now it says both:
``destruction`` (destruction_use ``use_report``: the reason, the asking rung, the hostiles left)
and ``amberite_readings`` (amberite_curse ``readings_report``: every kill-condition reading of
the decision, with the awake hostiles an ``other-awake`` verdict counted).

Recorded (tests/extract_loot_yield_1123_fixtures.py): n1-b life-416, Angband 95F, turns
4054730-4054751: the sensed T1 approach toward the awake Brand (not in view), then the use at
(18,59), Brand 13 cells off.  The reading: ``other-awake`` for the スペース・モンスター sensed 16
cells off, out of view -- what kept the kill's conditions unmet (an owner question of the study,
not changed here).

DECLARED RECONSTRUCTED: the Magic-Eater's device lists (the snapshot files carry none): one staff
row of *Destruction*, 22 charges at 95% (as tests/test_destruction_loot_livelock_1123_recorded.py).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import amberite_curse, destruction_use, me_capability
from hengbot.model import SV_STAFF_DESTRUCTION, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "loot-yield-1123-amberite-n1b-416.jsonl.gz"
USE = 4054751
BRAND = 773
SPACE_MONSTER = 144


class AmberiteReadingsRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            boards = [json.loads(line) for line in stream if line.strip()]
        directory = TemporaryDirectory()
        try:
            policy = _policy(Path(directory.name), monrace)
            first = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(boards[0]), monrace))
            policy.prime(first)
            policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
            for index, raw in enumerate(boards):
                board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), monrace))
                policy._me_device_lists = {"staff": (board.turn, ({
                    "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
                    "max": 22, "fail": 5, "success": 95},))}
                policy._decision_sequence = index + 1
                key = policy.choose_key(board)
                if board.turn == USE:
                    cls.key, cls.reason = key, policy.last_reason
                    cls.destruction = destruction_use.use_report(policy)
                    cls.readings = amberite_curse.readings_report(policy)
                    cls.resists = amberite_curse.resists_curse(board)
                    break
                if key:
                    policy.confirm_key_posted(key)
        finally:
            directory.cleanup()

    def test_the_recorded_use_is_made(self):
        # Recorded: emergency:destruction:absorbed-power 'mA3'.
        self.assertTrue(self.resists)
        self.assertEqual(self.key, "mA3")
        self.assertTrue(self.reason.startswith(destruction_use.REASON), self.reason)

    def test_the_log_names_the_rung_and_the_amberite_left(self):
        self.assertEqual(self.destruction["rung"], "threat_tiers.sensed_t1_destruction_key")
        self.assertEqual([row[1] for row in self.destruction["leaving"]], [BRAND])

    def test_the_log_names_the_condition_that_read_it_t1(self):
        brand = [reading for reading in self.readings
                 if [row[1] for row in reading["amberites"]] == [BRAND]]
        self.assertTrue(brand, self.readings)
        reading = brand[0]
        self.assertEqual(reading["verdict"], amberite_curse.OTHER_AWAKE)
        self.assertEqual(reading["others_awake"][0][1], SPACE_MONSTER)
        self.assertEqual(reading["others_awake"][0][3:], [16, False])  # 16 cells off, not in view


if __name__ == "__main__":
    unittest.main()
