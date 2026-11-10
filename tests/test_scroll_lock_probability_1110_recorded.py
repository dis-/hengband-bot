"""n1-a life-506's death (2026-11-10 07:59, 鉄獄38階, random quest 45) and the owner's answer.

Analysis: C:/hengband-backups/pdca/captures/n1a-506-death-1110/REPORT.txt.  Boards:
tests/fixtures/scroll-lock-n1a-506-1110.json.xz (tests/extract_scroll_lock_1110_fixture.py), one
board per live decision row (decisions 4044-4105, the whole 38F visit); every decision here is the
public ``choose_key`` of one fresh policy replaying the recorded boards in order
(``confirm_key_posted`` after each key, as the driver does).

Zombie warrior Lv33, HP 681/815, skill_sav 96, resist_conf / resist_chaos, no resist_blind.
Decision 4105: 反逆パラディン (id 497, 1_IN_4, BLIND among eight spells) two cells off and two
monks adjacent.  Live read Teleportation through the scroll-lock escape (any non-zero blind chance
charged one lost turn: 529 + 249 >= 681), landed among unseen casters and died before its next
turn.

Owner 2026-11-10, verbatim (「確率が一定以上の時だけ」): 「次の手番までに盲目・混乱を受ける確率
（魔法防御・耐性を入れて計算）が10%以上の時だけ、1ターン失う分を被害に足して逃げを考える。今回なら
戦い続ける。」  Second answer (speed potion before an emergency teleport): 「今のまま」.

DECLARED RECONSTRUCTION (pin_vacuity): the capture holds no ~f reply, so the skill knowledge is
supplied before each decision (as tests/test_teleport_follower_1109_recorded.py does).

DECLARED CONSTRUCTED (named at its test): 反逆パラディン replaced by 地蔵尊の蛸 (id 1065) on the
last board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path
import unittest
from unittest.mock import patch

from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import SCROLL_LOCK_ESCAPE_PROBABILITY
from tests.support.recorded import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "scroll-lock-n1a-506-1110.json.xz"
PALADIN = 497             # 反逆パラディン
OCTOPUS = 1065            # 地蔵尊の蛸: BR_DARK only, 1_IN_4, speed +0
ARRIVED = 2623782         # decision 4045: the first board decided on 38F
LAST = 2624228            # decision 4105: the scroll-lock teleport
SCROLL_LOCK = "emergency-ranged-status-lock"


def skill(policy, raw):
    policy.consume_skill_knowledge({
        "player": {"level": raw["player"]["level"]},
        "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
    })


def octopus_for_paladin(raw):
    """DECLARED CONSTRUCTED: 地蔵尊の蛸 stands where 反逆パラディン stood."""
    for monster in raw["visible_monsters"]:
        if monster["race_id"] == PALADIN:
            monster["race_id"] = OCTOPUS


class ScrollLockHarness(unittest.TestCase):
    answers = None

    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")
        cls.recorded = {row["turn"]: row for row in cls.payload["decisions"]}

    def replay(self, last_change=None):
        """Every recorded board, one fresh policy (``last_change`` applied to the last board);
        {turn: (raw, key, reason, snapshot)} and the policy."""
        boards = self.payload["boards"]
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), self.races))
        answers = {}
        for raw in boards:
            raw = copy.deepcopy(raw)
            if raw["turn"] == LAST and last_change is not None:
                last_change(raw)
            skill(policy, raw)
            snapshot = parse_snapshot(copy.deepcopy(raw), self.races)
            key = policy.choose_key(snapshot)
            if key:
                policy.confirm_key_posted(key)
            answers[raw["turn"]] = (raw, str(key), policy.last_reason, snapshot)
        return policy, answers

    def recorded_answers(self):
        if type(self).answers is None:
            type(self).answers = self.replay()
        return type(self).answers

    @staticmethod
    def hostiles(snapshot):
        return [monster for monster in snapshot.visible_monsters if monster.hostile]


class ScrollLockRecordedTest(ScrollLockHarness):
    """The recorded boards: the ~0.2% blind chance no longer reads Teleportation."""

    def test_the_replay_matches_the_live_decisions_before_the_last_board(self):
        """Decision 4044 is the descent decided on the previous floor's board (a fresh policy
        explores instead); from 4045 to 4104 the replay decides as live did."""
        _policy, answers = self.recorded_answers()
        for turn, (_raw, key, reason, _snapshot) in answers.items():
            if ARRIVED <= turn < LAST:
                self.assertEqual((key, reason),
                                 (self.recorded[turn]["key"], self.recorded[turn]["reason"]), turn)
        self.assertEqual((self.recorded[LAST]["key"], self.recorded[LAST]["reason"]),
                         ("rg", "emergency:teleport"))

    def test_the_last_board_keeps_fighting(self):
        """Owner 「今回なら戦い続ける」: no teleport read.  The answer is the 10-03 speed dose at
        a strong fight's start (3-turn operational 529 >= half of 681), a fighting action."""
        policy, answers = self.recorded_answers()
        raw, key, reason, snapshot = answers[LAST]
        self.assertEqual((key, reason), ("qa", "item:strong-fight-speed"))
        self.assertNotEqual(getattr(policy, "_last_return_trigger", None), SCROLL_LOCK)
        self.assertFalse(policy._emergency_escape_pending)

    def test_the_blind_chance_is_below_the_owner_line(self):
        """Only 反逆パラディン can lock the scrolls (resist_conf / resist_chaos held).  Per move
        1/4 attempt x BLIND's selected share x (1 - (25 - (33 + 3) / 4) %) x (1 - 96 / 116);
        three moves at speed +10 against 109 before the next turn.  Without the probability the
        old charge was lethal: 529 + 249 >= 681."""
        policy, answers = self.recorded_answers()
        _raw, _key, _reason, snapshot = answers[LAST]
        hostiles = self.hostiles(snapshot)
        self.assertEqual(snapshot.player.saving_skill, 96)
        self.assertNotIn("resist_blind", snapshot.player.abilities)
        self.assertIn("resist_conf", snapshot.player.abilities)
        threats = policy._ranged_scroll_lock_threats(snapshot, hostiles)
        self.assertEqual([monster.race_id for monster, _p in threats], [PALADIN])
        probability = policy._ranged_scroll_lock_probability(snapshot, hostiles)
        self.assertGreater(probability, 0.0)
        self.assertLess(probability, 0.01)
        self.assertLess(probability, SCROLL_LOCK_ESCAPE_PROBABILITY)
        predicted = policy._predicted_damage(snapshot, hostiles, turns=3)
        self.assertLess(predicted, snapshot.player.hp)
        self.assertGreaterEqual(
            predicted + policy._predicted_damage(snapshot, hostiles, turns=1),
            snapshot.player.hp,
        )
        self.assertFalse(policy._ranged_scroll_lock_escape_needed(
            snapshot, hostiles, predicted=predicted))


class ScrollLockConstructedTest(ScrollLockHarness):
    """DECLARED CONSTRUCTED: a dark breather where the paladin stood still escapes."""

    def test_a_dark_breather_at_or_above_ten_percent_still_escapes(self):
        """CONSTRUCTED: 地蔵尊の蛸 (BR_DARK, 1_IN_4) two cells off.  BR_DARK is innate, so only the
        freq_spell * 2 = 50% branch keeps it (mspell-attack-util.cpp:16, mspell-attack.cpp:45-52):
        per move 0.25 x 0.5 = 0.125; blind without resist_blind / resist_dark
        (effect-player-resist-hurt.cpp:447-453); speed 110 against 109 gives two moves:
        1 - 0.875 ** 2 = 0.234 >= 0.10.  The plain 3-turn prediction stays under HP, so the
        teleport comes from the scroll-lock charge."""
        policy, answers = self.replay(last_change=octopus_for_paladin)
        _raw, key, reason, snapshot = answers[LAST]
        hostiles = self.hostiles(snapshot)
        probability = policy._ranged_scroll_lock_probability(snapshot, hostiles)
        self.assertAlmostEqual(probability, 1 - 0.875 ** 2, places=6)
        self.assertGreaterEqual(probability, SCROLL_LOCK_ESCAPE_PROBABILITY)
        self.assertLess(policy._predicted_damage(snapshot, hostiles, turns=3), snapshot.player.hp)
        self.assertEqual((key, reason), ("rg", "emergency:teleport"))
        self.assertEqual(policy._last_return_trigger, SCROLL_LOCK)

    def test_the_owner_line_is_ten_percent_inclusive(self):
        """CONSTRUCTED: the same board with the probability set just under and at 10%."""
        policy, answers = self.replay(last_change=octopus_for_paladin)
        _raw, _key, _reason, snapshot = answers[LAST]
        hostiles = self.hostiles(snapshot)
        predicted = policy._predicted_damage(snapshot, hostiles, turns=3)
        self.assertEqual(SCROLL_LOCK_ESCAPE_PROBABILITY, 0.10)
        for probability, expected in ((0.0999, False), (0.10, True)):
            with self.subTest(probability=probability), patch.object(
                policy, "_ranged_scroll_lock_probability", return_value=probability
            ):
                self.assertIs(policy._ranged_scroll_lock_escape_needed(
                    snapshot, hostiles, predicted=predicted), expected)


if __name__ == "__main__":
    unittest.main()
