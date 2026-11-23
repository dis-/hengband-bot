"""The kill goes before the leave rules: the lone T2 good-drop unique and the prepared Amberite.

Owner 2026-11-23 (threat_tiers ``kill_before_leave``), two chosen answers, verbatim:

- Decision 1: 「T2 なら物資を使って倒す — 単独で T2 の良い品を落とすユニークは、加速・耐性の薬などの
  物資を使って倒す。即死の見込みや他の強敵がいれば今までどおり *破壊*。T1 なら今までどおり。」
- Decision 2: 「倒すことを先にする — 倒す準備（加速と耐性の薬）が済んだ王族には、離れる決まりより
  倒すことを先にする。即死の見込みや HP の線を割った時は今までどおり逃げる。」

Recorded (tests/extract_kill_before_leave_1123_fixtures.py), n1-b life-416 (Magic-Eater, resist
curse, Angband 95F):

- 4201590-4201633: 光なき闇の大蜘蛛『ウンゴリアント』 (DROP_GOOD, UNIQUE, a summoner), T2 alone with
  nothing else in view, meleed at 4201630; at 4201633 the haste ran out, the 11-09 worsening leave
  read it left and the emergency ladder's escape used *Destruction* ('mA3', the recorded key) on it.
- 4077000-4077044: 陰謀家『ケイン』 approached while the Recall counted down; the absorbed Speed and a
  Potion of Resistance were taken for his kill (amberite_curse rule 3) and on the next board, at
  4077044, the worsening leave held him left and the summoner escape's *Destruction* ('mA3', the
  recorded key) erased him.

DECLARED RECONSTRUCTED: the Magic-Eater's device lists (the snapshot files carry none): one staff
row of *Destruction*, 22 charges at 95% (as tests/test_amberite_readings_1123_recorded.py).  The
Rocket of the recorded kill attempt is not in it, so the replayed kill is the launcher's shot.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import amberite_curse, destruction_use, me_capability, threat_tiers
from hengbot.model import SV_STAFF_DESTRUCTION, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
UNGOLIANT_FIXTURE = FIXTURES / "kill-before-leave-1123-ungoliant-n1b-416.jsonl.gz"
CAINE_FIXTURE = FIXTURES / "kill-before-leave-1123-caine-n1b-416.jsonl.gz"
UNGOLIANT, UNGOLIANT_USE = 808, 4201633
CAINE, CAINE_USE = 799, 4077044


def _replay(fixture, last):
    """The key, its reason and readings on the board at turn ``last``."""
    monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
    with gzip.open(fixture, "rt", encoding="utf-8") as stream:
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
            if board.turn == last:
                engagement = threat_tiers.engagement(policy, board)
                kept = threat_tiers.kill_before_leave(policy, board, engagement)
                kept_races = {monster.race_id for monster in engagement if monster.index in kept}
                lone = threat_tiers.lone_good_drop_t2(policy, board, engagement)
                prepared = [monster.race_id for monster in engagement
                            if amberite_curse.prepared(policy, board, monster)]
                key = policy.choose_key(board)
                return key, policy.last_reason, kept_races, lone, prepared, board
            key = policy.choose_key(board)
            if key:
                policy.confirm_key_posted(key)
    finally:
        directory.cleanup()
    raise AssertionError(f"no board at turn {last}")


class LoneGoodDropT2RecordedTest(unittest.TestCase):
    """Decision 1: ウンゴリアント is fought, not erased."""

    @classmethod
    def setUpClass(cls):
        cls.key, cls.reason, cls.kept, cls.lone, _prepared, cls.board = _replay(
            UNGOLIANT_FIXTURE, UNGOLIANT_USE)

    def test_the_lone_t2_good_drop_unique_is_read(self):
        self.assertIsNotNone(self.lone)
        self.assertEqual(self.lone.race_id, UNGOLIANT)
        self.assertEqual(self.kept, {UNGOLIANT})

    def test_no_destruction_erases_it(self):
        # Recorded: emergency:destruction:before-teleport-away:absorbed-power 'mA3'.
        self.assertNotEqual(self.key, "mA3")
        self.assertFalse((self.reason or "").startswith(destruction_use.REASON), self.reason)

    def test_it_is_fought(self):
        # Beside the player, the supply plan's free attack (its doses are Healing at the plan's HP).
        self.assertEqual(self.reason, "melee")


class PreparedAmberiteRecordedTest(unittest.TestCase):
    """Decision 2: ケイン, hasted and covered by Resistance, is shot at, not erased."""

    @classmethod
    def setUpClass(cls):
        cls.key, cls.reason, cls.kept, cls.lone, cls.prepared, cls.board = _replay(
            CAINE_FIXTURE, CAINE_USE)

    def test_the_kill_is_prepared(self):
        self.assertEqual(self.prepared, [CAINE])
        self.assertEqual(self.kept, {CAINE})
        self.assertIsNone(self.lone)  # an Amberite keeps its own rule, not Decision 1

    def test_no_destruction_erases_him(self):
        # Recorded: emergency:destruction:absorbed-power 'mA3'.
        self.assertNotEqual(self.key, "mA3")
        self.assertFalse((self.reason or "").startswith(destruction_use.REASON), self.reason)

    def test_he_is_struck(self):
        self.assertEqual(self.reason, "ranged:fire")


if __name__ == "__main__":
    unittest.main()
