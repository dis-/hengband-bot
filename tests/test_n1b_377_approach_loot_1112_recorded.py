"""n1-b life-377, Angband 80F, 2026-11-12 11:24: the *Destruction* approach and seek-loot loop.

Live (tests/extract_n1b_377_approach_loot_1112_fixture.py): a ヴェノム・ワーム awake 18 cells
off, known only by telepathy, read T1 alone, so the sensed T1 rule went to destroy it
(threat_tiers.approach_key, owner 2026-11-10 「積極的に*破壊*で消しにいく」).  The walk toward its
sure radius stepped west from (31,55) to (31,54), 19 cells off, out of the telepathy's range;
on that board no T1 was sensed, seek-loot stepped back east, the wyrm showed again and the
approach stepped west: 20 alternations, ``loop-detected`` at turn 9031558.

The fix: the approach, once started, goes on toward the targets' last detected cells while they
are not shown (``threat_tiers.remembered_approach_key``).

Replay: every board from the arrival through the public choose_key, each carrying the previous
decision's completed owner as the CLI adds it.
DECLARED CONSTRUCTED: the absorbed power list (*Destruction* and the area map; the live process
had read it) and the skill-exp list (as the other n1-b pins); and, from turn 9031416 on, the
wyrm's detected cell moved from (36,73) to (31,36).  The live process routed west toward
(36,73) through cells its remembered map held (1,281 known cells at the stop) that a replay of
the boards does not rebuild, so the replay finds no route to the recorded cell; at (31,36) the
route is known, starts with the same step west, and the next board (31,54) is the recorded one
without the wyrm: the same alternation, reproduced on main before and after the 2026-11-11
threat-tier change (the wyrm reads T1 on both).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run
from recorded_junk_scope import install_past_destroyed_junk

import copy
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import threat_tiers
from hengbot.me_device_attacks import observe_lists
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy
from tests.test_me_device_attacks import power_list, row
from tests.test_sealed_pocket_quest_1105_recorded import _pin as _sealed_pin

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-377-approach-loot-1112.json.gz"
SHA256 = "e37d4d8b232bf6f0c63527692c1bbbd8d9c45746ac6dc474c1a9cc24db00f6d4"
WYRMS = (1196, 1197)
MOVED_FROM, MOVED_TO = 9031416, (31, 36)
LOST, SHOWN = (31, 54), (31, 55)
_undo_past_junk = None


def setUpModule():
    global _undo_past_junk, CASE, MONRACE
    _undo_past_junk = install_past_destroyed_junk()
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SHA256
    CASE = json.loads(gzip.decompress(raw))
    MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")


def tearDownModule():
    _undo_past_junk()


def moved(raw):
    """DECLARED CONSTRUCTED: the wyrm's detected cell (module docstring)."""
    if raw["turn"] >= MOVED_FROM:
        for monster in raw["detected_monsters"]:
            if monster["race_id"] in WYRMS:
                monster["y"], monster["x"] = MOVED_TO
    return raw


class N1b377ApproachLootRecordedTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def replay(self):
        boards = CASE["boards"]
        policy = _policy(self.root, MONRACE)
        board = parse_snapshot(copy.deepcopy(boards[0]), MONRACE)
        policy.prime(board)
        skill = next(json.loads(line) for line in _sealed_pin()["lines"] if '"skill_exp"' in line)
        policy.consume_skill_knowledge({**skill, "player": {"level": board.player.level}})
        listed = dict(copy.deepcopy(boards[0]), turn=boards[0]["turn"] - 1,
                      _magic_eater_power_list=power_list(
                          "staff", row("*破壊*", 5, current=3, count=3),
                          row("周辺感知", 5, current=3, count=3)))
        observe_lists(policy, parse_snapshot(listed, MONRACE))
        decided, previous = [], None
        for raw in boards:
            raw = moved(copy.deepcopy(raw))
            if previous is not None:
                raw["_completed_operation_owner"] = previous
            board = policy.with_known_skill_exp(parse_snapshot(raw, MONRACE))
            key = str(policy.choose_key(board))
            decided.append((raw["turn"], (board.player.position.y, board.player.position.x),
                            key, policy.last_reason, board))
            policy.confirm_key_posted(key)
            previous = policy.last_reason
        return policy, decided

    def test_the_recording_alternates(self):
        rows = [row for row in CASE["decisions"] if row["turn"] >= MOVED_FROM]
        pairs = {((row["position"]["y"], row["position"]["x"]), row["reason"]) for row in rows[:-1]
                 if row["reason"] in ("seek-loot", threat_tiers.APPROACH_REASON)}
        self.assertIn((SHOWN, threat_tiers.APPROACH_REASON), pairs)
        self.assertIn((LOST, "seek-loot"), pairs)
        self.assertEqual(CASE["decisions"][-1]["reason"], "loop-detected")

    def test_the_approach_goes_on_where_the_wyrm_is_lost(self):
        _policy_, decided = self.replay()
        tail = [entry for entry in decided if entry[0] >= MOVED_FROM]
        shown = [entry for entry in tail if entry[1] == SHOWN]
        lost = [entry for entry in tail if entry[1] == LOST]
        self.assertTrue(shown and lost)
        self.assertTrue(all(any(m.race_id in WYRMS for m in entry[4].detected_monsters)
                            for entry in shown))
        self.assertFalse([entry for entry in lost
                          if any(m.race_id in WYRMS for m in entry[4].detected_monsters)])
        # Where the wyrm shows, the walk toward it steps west (as live).
        self.assertEqual({(entry[2], entry[3]) for entry in shown},
                         {("4", threat_tiers.APPROACH_REASON)})
        # Where it is lost the walk goes on, away from (31,55): never seek-loot back east.  (The
        # recorded boards return the player to (31,55) whatever was sent, so later lost boards
        # may read the walker's own oscillation breaker; none of them is seek-loot.)
        self.assertEqual(lost[0][3], threat_tiers.APPROACH_REASON)
        self.assertNotIn(lost[0][2], ("6", "9", "3"))
        self.assertFalse([entry[:4] for entry in lost if entry[3] == "seek-loot"])
        self.assertGreater(sum(entry[3] == threat_tiers.APPROACH_REASON for entry in lost),
                           len(lost) // 2)

    def test_the_memory_ends_with_the_window(self):
        policy, decided = self.replay()
        board = decided[-1][4]
        self.assertIsNotNone(getattr(policy, threat_tiers.APPROACH_MEMORY))
        from dataclasses import replace
        from hengbot.monster_memory import UNSEEN_GAME_TURNS
        late = replace(board, turn=board.turn + UNSEEN_GAME_TURNS + 100)
        self.assertIsNone(threat_tiers.remembered_approach_key(policy, late))
        self.assertIsNone(getattr(policy, threat_tiers.APPROACH_MEMORY))


if __name__ == "__main__":
    unittest.main()
