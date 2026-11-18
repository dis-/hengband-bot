"""n1-a life-530's death (Lv50 warrior, 古城 51F, 2026-11-18 12:50): no Speed dose when the dragon came.

Analysis: C:/hengband-backups/pdca/n1a-530-death-1118.  Boards:
tests/fixtures/n1a-530-flee-haste-1118.json.xz (tests/extract_n1a_530_flee_haste_1118_fixture.py),
one board per live decision row of the floor's stay; every decision here is the public
``choose_key`` of one fresh policy replaying the recorded boards in order (``confirm_key_posted``
after each key, as the driver does).

The arrival read Word of Recall at once (decision 4648, the *Destruction* means spent rule), and
the countdown's first wait (4649, ``return:wait-recall``, turn 13142083) began the escape episode
on a board with no hostile.  At 4668 (turn 13142169) a dragon appeared 19 cells away (speed 190
against the player's 120, a 507-point blow); the episode was then neither at its start nor at a
haste run out, so the escape's Speed rule never asked: ten Potions of Speed stayed in the pack
while the breaths took the HP from 1278 to 471.

Owner 2026-09-18 (the escape's Speed dose: a melee pursuer at least as fast, unhasted) and
2026-11-10 (n1-c life-190) 「接敵してしまったらまず加速。」: the first board of an episode with a
hostile in view or sensed is its start for the haste decision.

DECLARED RECONSTRUCTION (pin_vacuity): the captures hold no ~f reply, so the skill knowledge is
supplied before each decision (as tests/test_n1a_525_flee_haste_1115_recorded.py does).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path
import unittest

from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import SV_POTION_SPEED, TVAL_POTION, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests.support.recorded import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-530-flee-haste-1118.json.xz"
ARRIVAL = 13142081         # decision 4648, return:recall (means spent)
EPISODE_START = 13142083   # decision 4649, return:wait-recall, no hostile
FIRST_SIGHT = 13142169     # decision 4668, flee:wait, the dragon 19 cells away
DEATH = 13142245           # decision 4683
SPEED_REASON = "emergency:quaff-speed"


def skill(policy, raw):
    policy.consume_skill_knowledge({
        "player": {"level": raw["player"]["level"]},
        "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
    })


def speed_key(raw):
    return "q" + next(item["slot"] for item in raw["inventory"]
                      if item["tval"] == TVAL_POTION and item["sval"] == SV_POTION_SPEED)


class N1a530FleeHaste1118RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")
        cls.recorded = {row["turn"]: row for row in cls.payload["decisions"]}
        cls.policy, cls.answers = cls.replay(DEATH)

    @classmethod
    def replay(cls, until):
        """Every recorded board up to game turn ``until``, one fresh policy;
        {turn: (board, key, reason, physical hostiles)}."""
        boards = cls.payload["boards"]
        policy = HengbotPolicy(monrace_knowledge=dict(cls.races),
                               dungeon_knowledge=dict(cls.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), cls.races))
        answers = {}
        for raw in boards:
            if raw["turn"] > until:
                break
            skill(policy, raw)
            board = parse_snapshot(copy.deepcopy(raw), cls.races)
            key = policy.choose_key(board)
            if key:
                policy.confirm_key_posted(key)
            answers[raw["turn"]] = (raw, str(key), policy.last_reason,
                                    policy._physical_hostiles(board))
        return policy, answers

    def test_the_recorded_boards(self):
        self.assertEqual(self.recorded[ARRIVAL]["reason"], "return:recall")
        self.assertEqual(self.recorded[EPISODE_START]["reason"], "return:wait-recall")
        self.assertEqual(self.recorded[FIRST_SIGHT]["reason"], "flee:wait")
        self.assertNotIn(SPEED_REASON, [row["reason"] for row in self.payload["decisions"]])
        raw = self.answers[FIRST_SIGHT][0]
        self.assertEqual(raw["player"]["speed"], 120)
        self.assertEqual(sum(item["count"] for item in raw["inventory"]
                             if item["tval"] == TVAL_POTION and item["sval"] == SV_POTION_SPEED), 10)

    def test_the_episode_began_with_no_hostile(self):
        for turn, (_raw, _key, reason, hostiles) in self.answers.items():
            if EPISODE_START <= turn < FIRST_SIGHT:
                self.assertEqual(reason, "return:wait-recall", turn)
                self.assertEqual(hostiles, [], turn)
        _raw, _key, _reason, hostiles = self.answers[FIRST_SIGHT]
        self.assertEqual(len(hostiles), 1)
        self.assertGreaterEqual(hostiles[0].speed, 120)
        self.assertGreater(hostiles[0].max_melee_damage, 0)

    def test_the_first_board_with_the_dragon_quaffs_speed(self):
        raw, key, reason, _hostiles = self.answers[FIRST_SIGHT]
        self.assertEqual(reason, SPEED_REASON)
        self.assertEqual(key, speed_key(raw))
        # The recorded boards after it never show that dose's haste: no second dose.
        for turn in sorted(self.answers):
            if turn > FIRST_SIGHT:
                self.assertNotEqual(self.answers[turn][2], SPEED_REASON, turn)

    def test_the_other_boards_replay_as_recorded(self):
        for turn, (_raw, key, reason, _hostiles) in self.answers.items():
            if turn == FIRST_SIGHT:
                continue
            row = self.recorded[turn]
            self.assertEqual((key, reason), (row["key"], row["reason"]), turn)


if __name__ == "__main__":
    unittest.main()
