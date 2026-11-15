"""n1-a life-525's death (Lv49 warrior, ガラスの城 49F, 2026-11-15 21:05): the haste ran out mid-escape.

Analysis: C:/hengband-backups/pdca/captures/n1a-525-death-1115.  Boards:
tests/fixtures/n1a-525-flee-haste-1115.json.xz (tests/extract_n1a_525_flee_haste_1115_fixture.py),
one board per live decision row of the floor's stay; every decision here is the public
``choose_key`` of one fresh policy replaying the recorded boards in order (``confirm_key_posted``
after each key, as the driver does).

The escape episode began at decision 23988 (return:recall, turn 12041157) with the haste of the
dose of 23981 still on (+10).  The haste ran out at 24016 (turn 12041302); the episode went on
(seek-upstairs, cornered-attack, four emergency heals, the last six boards read 即死) at +0
beside +10..+30 enemies, nine Potions of Speed in the pack, and the escape's Speed rule never
asked again: it asked only on the episode's first board.

Owner 2026-09-18 (the escape's Speed dose: a melee pursuer at least as fast, unhasted) and
2026-11-10 (n1-c life-190) 「接敵してしまったらまず加速。治療薬を連打して離脱チャンスを狙う。」

DECLARED RECONSTRUCTION (pin_vacuity): the captures hold no ~f reply, so the skill knowledge is
supplied before each decision (as tests/test_deaths_1109_recorded.py does).

DECLARED CONSTRUCTED (named at its test): the Potions of Speed out of the pack on the boards of
24016 and 24017, so the dose falls to the first 即死 board, 24018.
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

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-525-flee-haste-1115.json.xz"
FIRST_DOSE = 12041117      # decision 23981, emergency:quaff-speed
EPISODE_START = 12041157   # decision 23988, return:recall, hasted
HASTE_OUT = 12041302       # decision 24016, the first board at +0
NEXT = 12041315            # decision 24017
FIRST_INSTANT_DEATH = 12041322  # decision 24018
DEATH = 12041369           # decision 24023
SPEED_REASON = "emergency:quaff-speed"


def skill(policy, raw):
    policy.consume_skill_knowledge({
        "player": {"level": raw["player"]["level"]},
        "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
    })


def speed_key(raw):
    return "q" + next(item["slot"] for item in raw["inventory"]
                      if item["tval"] == TVAL_POTION and item["sval"] == SV_POTION_SPEED)


def no_speed_potion(raw):
    """DECLARED CONSTRUCTED: the Potions of Speed out of the pack, letters re-given."""
    inventory = raw["inventory"]
    inventory[:] = [item for item in inventory
                    if not (item["tval"] == TVAL_POTION and item["sval"] == SV_POTION_SPEED)]
    for index, item in enumerate(inventory):
        item["slot"] = chr(ord("a") + index)


class FleeHasteRanOutRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")
        cls.recorded = {row["turn"]: row for row in cls.payload["decisions"]}

    def replay(self, until, change=None):
        """Every recorded board up to game turn ``until`` (``change`` applied to each), one
        fresh policy; {turn: (board, key, reason)}."""
        boards = self.payload["boards"]
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), self.races))
        answers = {}
        for raw in boards:
            if raw["turn"] > until:
                break
            raw = copy.deepcopy(raw)
            if change is not None:
                change(raw)
            skill(policy, raw)
            key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.races))
            if key:
                policy.confirm_key_posted(key)
            answers[raw["turn"]] = (raw, str(key), policy.last_reason)
        return policy, answers

    def test_the_recorded_boards(self):
        speeds = {raw["turn"]: raw["player"]["speed"] for raw in self.payload["boards"]}
        self.assertEqual(self.recorded[FIRST_DOSE]["reason"], SPEED_REASON)
        self.assertEqual(self.recorded[EPISODE_START]["reason"], "return:recall")
        self.assertEqual((speeds[EPISODE_START], speeds[HASTE_OUT - 8], speeds[HASTE_OUT]),
                         (120, 120, 110))
        self.assertEqual(self.recorded[HASTE_OUT]["reason"], "emergency:seek-upstairs")
        self.assertEqual([self.recorded[turn]["instant_death"]
                          for turn in sorted(self.recorded) if turn >= FIRST_INSTANT_DEATH],
                         [True] * 6)
        self.assertTrue(all(speeds[turn] == 110 for turn in speeds if turn >= HASTE_OUT))
        self.assertNotIn(SPEED_REASON, [row["reason"] for row in self.payload["decisions"]
                                        if row["turn"] > FIRST_DOSE])

    def test_the_haste_running_out_mid_escape_quaffs_speed(self):
        policy, answers = self.replay(DEATH)
        # As recorded: the first dose, then the escape episode started hasted.
        self.assertEqual(answers[FIRST_DOSE][2], SPEED_REASON)
        self.assertEqual(answers[EPISODE_START][2], "return:recall")
        self.assertEqual(answers[HASTE_OUT - 8][2], "no-wait:least-visited")
        # The first board at +0 inside the same episode: the Speed dose.
        raw, key, reason = answers[HASTE_OUT]
        self.assertEqual(reason, SPEED_REASON)
        self.assertEqual(key, speed_key(raw))
        # The recorded boards after it never show that dose's haste: no second one.
        for turn in sorted(answers):
            if turn > HASTE_OUT:
                self.assertNotEqual(answers[turn][2], SPEED_REASON, turn)
        self.assertEqual(answers[NEXT][2], "emergency:seek-upstairs")
        self.assertEqual(answers[DEATH][2], "emergency:heal")

    def test_the_first_instant_death_board_quaffs_speed(self):
        """DECLARED CONSTRUCTED: no Potion of Speed on the boards of 24016 and 24017; the pack
        holds them again on 24018, the first 即死 board, and the dose is taken there."""
        def change(raw):
            if raw["turn"] in (HASTE_OUT, NEXT):
                no_speed_potion(raw)
        _policy, answers = self.replay(FIRST_INSTANT_DEATH, change)
        self.assertEqual(answers[HASTE_OUT][2], "emergency:seek-upstairs")
        self.assertEqual(answers[NEXT][2], "emergency:seek-upstairs")
        raw, key, reason = answers[FIRST_INSTANT_DEATH]
        self.assertTrue(self.recorded[FIRST_INSTANT_DEATH]["instant_death"])
        self.assertEqual(reason, SPEED_REASON)
        self.assertEqual(key, speed_key(raw))


if __name__ == "__main__":
    unittest.main()
