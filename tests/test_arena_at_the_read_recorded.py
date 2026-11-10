"""The arena's judgement at the recall read (owner 2026-11-05).

Owner: 「ダンジョンに出発する前に闘技場に挑むかの判定を行う。」  Recorded: the first town board of
tests/fixtures/calib-recall-20261031, the Outpost board of a recorded Word of Recall read
(town:recall-to-alt-dungeon).  CONSTRUCTED: the sheet's arena line in a temporary file, the
gold.  DECLARED: a fresh process has not scanned Home or priced its equipment, so the two
departure leaves it lacks are declared held (replays that reach a read from a visit's start,
test_armor_smith_recorded and test_burst_1104_recorded, are red on main before this owner).

The board's target is the Labyrinth, whose recall landing (18F) is its last floor; its guardian,
the Minotaur (race 1034, speed +15, 330 HP), reads T1 for this Lv24 character (the threat tiers
at contact: 557 incoming over the 4 turns to kill it against 473 HP, no supply plan wins).
Owner 2026-11-10 (the n1-b life-367 deep-dive report's P3): 「守護者が T1 の最下層は、*破壊* の
有無に関係なく帰還先にしない。」 (guardian_landing).  So the read the arena gives way to comes
in two decisions: the guardian refusal's switch (``SWITCH``, the 2026-09-25 guardian valve's
choice, here the Orc cave), then, on the next board, the recall to it (``READ``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from dataclasses import replace
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import arena
from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import SKILL_KNOWLEDGE_MACRO, TOWN_TELEPORT_COST

from extraction_calibration import install_extraction_calibration
from tests.support.recorded import EDIT, _policy

CASE = Path(__file__).parent / "fixtures" / "calib-recall-20261031.json.gz"
READ = "town:recall-to-alt-dungeon"
SWITCH = "town:unsafe-recall-fallback"  # the guardian refusal's switch (work town:guardian-recall-fallback)
LABYRINTH, ORC_CAVE = 4, 3


class ArenaAtTheRead(unittest.TestCase):
    def assert_reads_the_recall(self, policy, board):
        """After the arena's verdict on ``board``: the switch off the Labyrinth's T1 last floor,
        then the recall read on the next board (the module docstring)."""
        self.assertEqual(policy.last_reason, SWITCH)
        self.assertEqual(policy._alternate_dungeon, ORC_CAVE)
        following = replace(board, turn=board.turn + 1)
        policy._observe(following)
        key = policy._town_special_key(following)
        self.assertEqual(policy.last_reason, READ, key)
        self.assertEqual(policy._town_recall_destination(following), ("alt-dungeon", ORC_CAVE))

    @classmethod
    def setUpClass(cls):
        cls.case = json.loads(gzip.decompress(CASE.read_bytes()).decode("utf-8"))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def at_the_read(self, sheet_line):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        directory = Path(folder.name)
        policy = _policy(directory, self.monrace)
        policy._character_calibration_path.write_text(json.dumps(self.case["record"]), encoding="utf-8")
        policy._calibration_session_id = install_extraction_calibration(policy).session_id
        policy.confirm_key_posted(SKILL_KNOWLEDGE_MACRO)

        def boards(lines):
            return _consume_response_sequence(
                lines, policy, lambda _key: True, self.monrace,
                knowledge_ledger_path=directory / "knowledge.jsonl")[1]
        boards([self.case["skill"]])
        board = boards(self.case["town"])[0]
        policy._character_dump_path = directory / "bot-test.txt"
        policy._character_dump_path.write_text(f" {sheet_line}\n", encoding="cp932")
        policy._char_dump_done_this_visit = True
        policy._observe(board)
        policy._build_grid_index(board)
        leaves = policy._town_departure_conjuncts(board)
        policy._town_departure_conjuncts = lambda *_args, **_kwargs: dict.fromkeys(leaves, True)
        policy._town_departure_ready = lambda *_args, **_kwargs: True
        policy._equipment_departure_ready = lambda *_args, **_kwargs: True
        return policy, board

    def test_a_winnable_opponent_starts_the_trip_before_the_read(self):
        policy, board = self.at_the_read("闘技場:  0勝")
        key = policy._town_special_key(board)
        record = arena.state(policy)
        self.assertEqual(policy.last_reason, arena.TRAVEL_REASON, key)
        self.assertEqual((record.origin, record.expected, record.holding), (0, arena.OPPONENTS[0], True))
        self.assertEqual(record.last_verdict["fare"], 2 * TOWN_TELEPORT_COST)
        self.assertGreaterEqual(record.last_verdict["chance"], 0.9)

    def test_the_labyrinths_last_floor_is_no_destination(self):
        policy, board = self.at_the_read("闘技場: 40勝")
        self.assertEqual(policy._target_dungeon_id, LABYRINTH)
        self.assertFalse(policy._recall_destination_safe(board, LABYRINTH))
        self.assertTrue(policy._recall_refused_only_for_guardian(board, LABYRINTH))

    def test_a_hopeless_opponent_reads_the_recall(self):
        policy, board = self.at_the_read("闘技場: 40勝")
        policy._town_special_key(board)
        self.assertFalse(arena.state(policy).last_verdict["go"])
        self.assert_reads_the_recall(policy, board)

    def test_without_the_round_trip_it_reads_the_recall(self):
        policy, board = self.at_the_read("闘技場:  0勝")
        short = replace(board, player=replace(board.player, gold=2 * TOWN_TELEPORT_COST - 1))
        policy._town_special_key(short)
        self.assertEqual(arena.state(policy).last_verdict["why"], "fare")
        self.assert_reads_the_recall(policy, short)

    def test_a_defeat_on_the_sheet_reads_the_recall(self):
        policy, board = self.at_the_read("闘技場: 3回戦でX の前に敗北")
        policy._town_special_key(board)
        self.assertEqual(arena.state(policy).last_verdict["why"], "defeated")
        self.assert_reads_the_recall(policy, board)
        self.assertTrue(arena.over_for_good(policy))

    def test_no_sheet_this_visit_reads_the_recall(self):
        policy, board = self.at_the_read("闘技場:  0勝")
        policy._char_dump_done_this_visit = False
        arena.state(policy).last_verdict = None
        self.assertIsNone(arena.standing(policy))
        verdict = arena.judge(policy, board, arena.state(policy), 0)
        self.assertEqual(verdict["why"], "standing-unknown")


if __name__ == "__main__":
    unittest.main()
