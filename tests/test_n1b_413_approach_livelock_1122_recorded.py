"""The sensed-T1 approach makes one decision across the boards it alternated on (n1-b life-413, 1122).

Recorded (Angband 80F, the Magic-Eater Lv39; extract_n1b_413_approach_livelock_1122_fixtures.py):

- tests/fixtures/n1b-413-approach-unreached-subject-1122.jsonl.gz (player turns 2937400-2938160):
  at (21,69) two T1s were sensed, 理想の戦士『ベネディクト』 (index 21, the most dangerous from
  contact, the use's subject) and アイス・ワイアーム (index 5).  No known cell had Benedict within the
  sure radius, so the approach's walk had no step and the explore stepped '9' to (20,70); there
  Benedict was out of the telepathy's range, the wyrm alone was the subject and the approach
  stepped '1' back.  The ping-pong guard escalated and the livelock's Recall was read on 2938158
  (04:03:43, recorded ``livelock:recall-escape``).  Now a subject with no known way is passed over
  for the next most dangerous one with a way (threat_tiers ``approach_subject``): the walk goes on
  toward the wyrm on both cells.
- tests/fixtures/n1b-413-approach-lost-memory-1122.jsonl.gz (player turns 3000600-3001860): at
  (22,47) カオス・ワイアーム (index 58) was sensed with no known cell in reach, the explore stepped
  '6' to (22,48), out of the telepathy's range, where the remembered approach (its targets lost
  from detection, threat_tiers ``remembered_approach_key``) stepped '4' back; the livelock's Recall
  on 3001855 (04:07:10).  Now the sensed approach without a step asks the remembered approach on
  the same board: '4' on both cells.

The replays settle each power cast as the executor does, naming the previous decision's reason as
the completed operation's owner (as tests/test_castle_summoner_loot_1110_recorded.py does).
DECLARED RECONSTRUCTED: the power lists (the snapshot files carry none) are the town-arrival
checkpoint's of 04:17:07 (tests/fixtures/n1b-413-me-lists-0417-1122.json), shown unstunned before the
first board; the rod of 全感知 shown charging (the replay posts no key, so its recharge is never
seen).
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
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
LISTS = FIXTURES / "n1b-413-me-lists-0417-1122.json"
UNREACHED = FIXTURES / "n1b-413-approach-unreached-subject-1122.jsonl.gz"
LOST = FIXTURES / "n1b-413-approach-lost-memory-1122.jsonl.gz"
APPROACH = threat_tiers.APPROACH_REASON
ESCAPE = "livelock:recall-escape"


def _boards(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


class ApproachLivelockRecordedTest(unittest.TestCase):
    # The window's hound packs (each T3 alone, no drops, T1 together) are destroyed by the 11-22
    # group (threat_tiers ``_unprofitable_group``, test_group_destroy_no_profit_1122_recorded),
    # which the recorded boards do not show; here it is off, so the run is the recorded one.
    @classmethod
    def setUpClass(cls):
        cls.group = mock.patch.object(threat_tiers, "_unprofitable_group", lambda *_: [])
        cls.group.start()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        lists = json.loads(LISTS.read_text(encoding="utf-8"))["lists"]
        for row in lists["rod"]:
            if row["name"] == "全感知":
                row["charging"] = row["max"]
        cls.lists = lists
        cls.decided = {}
        for name, path in (("unreached", UNREACHED), ("lost", LOST)):
            cls.decided[name] = cls.drive(_boards(path))

    @classmethod
    def tearDownClass(cls):
        cls.group.stop()

    @classmethod
    def drive(cls, boards):
        directory = TemporaryDirectory()
        try:
            policy = _policy(Path(directory.name), cls.monrace)
            first = parse_snapshot(copy.deepcopy(boards[0]), cls.monrace)
            policy.prime(first)
            policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
            for kind in ("staff", "wand", "rod"):
                listed = dict(copy.deepcopy(boards[0]), turn=boards[0]["turn"] - 1,
                              _magic_eater_power_list={"kind": kind, "rows": cls.lists[kind]})
                observe_lists(policy, parse_snapshot(listed, cls.monrace))
            decided, previous = [], None
            for raw in boards:
                raw = copy.deepcopy(raw)
                if previous is not None:
                    raw["_completed_operation_owner"] = previous
                board = policy.with_known_skill_exp(parse_snapshot(raw, cls.monrace))
                key = policy.choose_key(board)
                decided.append((board.turn, board.player.position, key, policy.last_reason))
                if key:
                    policy.confirm_key_posted(key)
                previous = policy.last_reason if key else None
            return decided
        finally:
            directory.cleanup()

    def at(self, name, turn):
        return next(row for row in self.decided[name] if row[0] == turn)

    def test_unreached_subject_the_walk_goes_on_toward_the_wyrm(self):
        # Recorded: explore '9' at (21,69), approach '1' at (20,70), alternating.
        for turn in (2938077, 2938093, 2938117, 2938134):
            _, position, key, reason = self.at("unreached", turn)
            self.assertEqual(position, Position(21, 69))
            self.assertEqual((key, reason), ("2", APPROACH), turn)
        for turn in (2938085, 2938103, 2938124, 2938145):
            _, position, key, reason = self.at("unreached", turn)
            self.assertEqual(position, Position(20, 70))
            self.assertEqual((key, reason), ("1", APPROACH), turn)

    def test_unreached_subject_no_livelock_recall(self):
        # Recorded: livelock:recall-escape on 2938158.
        self.assertNotIn(ESCAPE, [row[3] for row in self.decided["unreached"]])

    def test_lost_from_detection_the_remembered_approach_answers_both_cells(self):
        # Recorded: explore '6' at (22,47), approach '4' at (22,48), alternating.
        for turn in (3001774, 3001798, 3001817, 3001831):
            _, position, key, reason = self.at("lost", turn)
            self.assertEqual(position, Position(22, 47))
            self.assertEqual((key, reason), ("4", APPROACH), turn)
        for turn in (3001785, 3001808, 3001821, 3001844):
            _, position, key, reason = self.at("lost", turn)
            self.assertEqual(position, Position(22, 48))
            self.assertEqual((key, reason), ("4", APPROACH), turn)

    def test_lost_from_detection_no_livelock_recall(self):
        # Recorded: livelock:recall-escape on 3001855.
        self.assertNotIn(ESCAPE, [row[3] for row in self.decided["lost"]])


if __name__ == "__main__":
    unittest.main()
