"""n1-a life-539 (2026-11-26 12:24:19, loop-detected): a 1% wand aimed at a 1-HP shrieker.

The chain (Zombie warrior Lv25, HP 471/471, device skill 23, Angband 17F, one process):

 * turn 683577-683922: 絶叫おばけキノコ (race 40, SHRIEK, never moves, 1d1 HP) two cells away
   at (24,39); the worsens-with-time rung (``worsens_kill``, design 4.4 / 10a) killed it 被害無く
   and spent the supply its schedule spends first: ``supply-fight:aim-wand`` 'ao9', the Wand of
   Hypodynamia (base level 50).  zapwand-execution.cpp: chance 23 - 50 < USE_DEVICE (3), so a use
   works only through one_in_(31) and then randint1(3) >= 3: one in 93.  「魔法棒をうまく使えなかっ
   た。」 x14, three loop stops in 30 s, the life retired.
 * The success rate was read right (``device_use_success`` is the game's 1/93).  The charge was
   scored at that rate times the full 105 damage (1.13), while the free attack it must beat, the
   plain crossbow bolt (36/shot), was paced to the target's 1 HP (``kill_paced``: 1).  So the wand
   "out-damaged" the bolt.  Owner 2026-11-12 (me-ranged-vs-device): devices and shots are compared
   by their expected values with the success rate; read the same way (both paced over the HP),
   the wand is 1/93 against the bolt's ~1.

Recorded: tests/fixtures/n1a-539-wand-fail-loop-1126.json.gz
(tests/extract_n1a_539_wand_fail_loop_1126_fixture.py): the boards of the first (683577) and the
last (683911) aim-wand decisions as the snapshot ring kept them, and their recorded rows.
Nothing constructed: a fresh policy reads each board.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import attack_expectation, threat_projection, worsens_kill
from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-539-wand-fail-loop-1126.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
SHRIEKER = 40
TVAL_WAND, SV_WAND_HYPODYNAMIA = 65, 12


class WandFailLoopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _board(self, index: int):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        _decoded, boards = _consume_response_sequence(
            [CASE["boards"][index]], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=Path(directory.name) / "knowledge.jsonl",
        )
        board = boards[-1]
        return board, policy, policy._strategic_hostiles(board)

    def test_recorded_rows_are_the_incident(self):
        for row in CASE["recorded"]:
            self.assertEqual((row["key"], row["reason"], row["position"]),
                             ("ao9", "supply-fight:aim-wand", {"y": 26, "x": 37}))
            self.assertEqual((row["floor"]["dungeon_id"], row["floor"]["level"]), (1, 17))
        board, _policy_, hostiles = self._board(0)
        self.assertEqual(board.player.device_skill, 23)
        (target,) = hostiles
        self.assertEqual((target.race_id, target.hp, target.distance), (SHRIEKER, 1, 2))
        wand = next(item for item in board.inventory
                    if (item.tval, item.sval) == (TVAL_WAND, SV_WAND_HYPODYNAMIA))
        self.assertEqual(wand.slot, "o")
        # zapwand-execution.cpp: one use in 93 works at skill 23 against base level 50.
        self.assertAlmostEqual(attack_expectation.device_use_success(23, 50), 1 / 93)

    def test_one_percent_wand_does_not_outscore_the_bolt_on_a_one_hp_target(self):
        for index, recorded in enumerate(CASE["recorded"]):
            with self.subTest(turn=recorded["turn"]):
                board, policy, hostiles = self._board(index)
                (target,) = hostiles
                free = worsens_kill._free(policy, board, target)
                self.assertGreater(free, 0.5)  # the plain bolt
                charges = threat_projection._charge_supplies(policy, board, target)
                self.assertTrue(charges)
                self.assertTrue(all(damage < free for damage, _count in charges), charges)
                key = worsens_kill.key(policy, board, hostiles)
                self.assertIsNotNone(key)
                self.assertNotEqual(policy.last_reason, "supply-fight:aim-wand")
                self.assertFalse(key.startswith("a"), key)
                self.assertEqual(policy.last_reason, "ranged:fire")


if __name__ == "__main__":
    unittest.main()
