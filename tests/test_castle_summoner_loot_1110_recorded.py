"""n1-b life-367, the Castle 48F, 2026-11-10 20:43:29: an open summoner on a T3 board.

Owner 2026-11-10 (the deep-dive report's P6, verbatim): 「ドロップに価値がないなら*破壊*、価値
があるT3なら穴熊を試みて地形が悪ければやはり*破壊*する。」 (summoner_loot).

Recorded (tests/extract_castle_summoner_loot_1110_fixture.py): decisions 7302-7305 through the
public choose_key; the last (turn 5245999, 629/629 HP, tier T3, thirteen summoners in view)
was the live emergency:destruction:absorbed-power under emergency-summoner.  Two Ultra-elite
paladins (race 699: DROP_1D2, DROP_60, DROP_90, 3.0 expected drops) stand within the radius:
the use would delete a valuable drop.  The pocket finds no pack there (anaguma), so the
recorded board still reads *Destruction*.
DECLARED CONSTRUCTED: the absorbed power list and the skill-exp list (as the other n1-b pins);
a collaborator wall on ``anaguma.key`` (its own pack and terrain rules are pinned by the
Anaguma tests; walled after the producer under test, summoner_loot, asks it) that answers a
marker key; the board without the paladins.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run
from recorded_junk_scope import install_past_destroyed_junk

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import anaguma
from hengbot.me_device_attacks import observe_lists
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy
from tests.test_me_device_attacks import power_list, row
from tests.test_sealed_pocket_quest_1105_recorded import _pin as _sealed_pin

FIXTURE = Path(__file__).with_name("fixtures") / "castle-summoner-loot-1110.json.xz"
PALADIN = 699
DESTRUCTION = ("mA3", "emergency:destruction:absorbed-power")
POCKET = "ANAGUMA"
_undo_past_junk = None


def setUpModule():
    global _undo_past_junk
    _undo_past_junk = install_past_destroyed_junk()


def tearDownModule():
    _undo_past_junk()


def _without_paladins(raw):
    raw = copy.deepcopy(raw)
    for key in ("visible_monsters", "detected_monsters"):
        raw[key] = [monster for monster in raw[key] if monster.get("race_id") != PALADIN]
    return raw


class CastleSummonerLootRecordedTest(unittest.TestCase):
    def setUp(self):
        rows = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))
        self.boards = [json.loads(line) for line in rows]
        self.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def drive(self, last=None):
        boards = [*self.boards[:-1], last if last is not None else self.boards[-1]]
        policy = _policy(self.root, self.monrace)
        board = parse_snapshot(boards[0], self.monrace)
        policy.prime(board)
        skill = next(json.loads(line) for line in _sealed_pin()["lines"] if '"skill_exp"' in line)
        policy.consume_skill_knowledge({**skill, "player": {"level": board.player.level}})
        listed = dict(copy.deepcopy(boards[0]), turn=boards[0]["turn"] - 1, _magic_eater_power_list=power_list(
            "staff", row("*破壊*", 5, current=3, count=3), row("周辺感知", 5, current=3, count=3)))
        observe_lists(policy, parse_snapshot(listed, self.monrace))
        previous, key = None, None
        for raw in boards:
            raw = copy.deepcopy(raw)
            if previous is not None:
                raw["_completed_operation_owner"] = previous
            key = policy.choose_key(policy.with_known_skill_exp(parse_snapshot(raw, self.monrace)))
            previous = policy.last_reason
        return policy, key

    def pocket(self, policy, snapshot, hostiles):
        policy.last_reason = "anaguma:walk"
        return POCKET

    def test_no_pack_to_dig_for_keeps_the_recorded_destruction(self):
        policy, key = self.drive()
        self.assertEqual((key, policy.last_reason), DESTRUCTION)

    def test_a_valuable_drop_asks_the_pocket_first(self):
        """Live: *Destruction*.  The pocket answers in its place and no escape is latched."""
        with mock.patch.object(anaguma, "key", self.pocket):
            policy, key = self.drive()
        self.assertEqual((key, policy.last_reason), (POCKET, "anaguma:walk"))
        self.assertNotEqual(policy._last_return_trigger, "emergency-summoner")
        self.assertFalse(policy._emergency_escape_pending)

    def test_no_valuable_drop_keeps_the_destruction(self):
        with mock.patch.object(anaguma, "key", self.pocket):
            policy, key = self.drive(_without_paladins(self.boards[-1]))
        self.assertEqual((key, policy.last_reason), DESTRUCTION)


if __name__ == "__main__":
    unittest.main()
