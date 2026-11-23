"""The kill goes before the leave rules: the lone T2 good-drop unique.

Owner 2026-11-23 (threat_tiers ``kill_before_leave``), the chosen answer, verbatim:

- Decision 1: 「T2 なら物資を使って倒す — 単独で T2 の良い品を落とすユニークは、加速・耐性の薬などの
  物資を使って倒す。即死の見込みや他の強敵がいれば今までどおり *破壊*。T1 なら今までどおり。」

Recorded (tests/extract_kill_before_leave_1123_fixtures.py), n1-b life-416 (Magic-Eater, resist
curse, Angband 95F):

- 4201590-4201633: 光なき闇の大蜘蛛『ウンゴリアント』 (DROP_GOOD, UNIQUE, a summoner), T2 alone with
  nothing else in view, meleed at 4201630; at 4201633 the haste ran out, the 11-09 worsening leave
  read it left and the emergency ladder's escape used *Destruction* ('mA3', the recorded key) on it.

DECLARED RECONSTRUCTED: the Magic-Eater's device lists (the snapshot files carry none): one staff
row of *Destruction*, 22 charges at 95% (as tests/test_amberite_readings_1123_recorded.py).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import destruction_use, me_capability, threat_tiers
from hengbot.model import SV_STAFF_DESTRUCTION, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
UNGOLIANT_FIXTURE = FIXTURES / "kill-before-leave-1123-ungoliant-n1b-416.jsonl.gz"
UNGOLIANT, UNGOLIANT_USE = 808, 4201633


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
                key = policy.choose_key(board)
                return key, policy.last_reason, kept_races, lone, board
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
        cls.key, cls.reason, cls.kept, cls.lone, cls.board = _replay(
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


if __name__ == "__main__":
    unittest.main()
