"""The Recall wait's pickup does not walk back onto the cell the sensed T1 leave left (1119).

n1-b life-411 (Magic-Eater Lv50, Angband 99F, 2026-11-19 00:55:21, loop-detected, build
bot-febdf2f35).  Word of Recall was running; アンバーの王『オベロン』 (race 860, awake, vision 100)
was known by telepathy only (no hostile in view) with the player inside its sensing radius.  The
sensed T1 leave (threat_tiers ``sensed_t1_leave_key``, owner 2026-11-08 「その敵の感知範囲内なら
早急に離脱する」; during the wait its scroll is withheld, owner 2026-11-15) walked '7' from the item
cell (15,17) into the dead end (14,16); there no cell is farther from the T1, so the leave
answered nothing, and the wait's pickup (owner 2026-11-18 「見える敵がいなければ拾う」, which left
every other reader of a sensed monster unchanged, so the leave keeps its rung above it) walked
'3' straight back onto (15,17): the left cell was the pocket's only exit, so left_cells did not
record it (``seals``) or did not read it (``_encloses``).  15 leaves and 14 pickups in the last
200 decisions; the ping-pong guard skips a round whose loser is a survival reason (by design).

Now a running Recall in the dungeon is the way on (engagement_avoid_seal ``_way_on``): the left
cell stays refused and the pickup waits in the pocket for the Recall.

Recorded: the capture's state.jsonl (hengband.net
~/hengbot-soak/n1-b/life-411/captures/20261119-005521-loop-detected/), its 92 player-turn boards
(the one ``power_list`` reply left out), turns 7814114-7814337.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import left_cells
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-recall-loot-t1-1119.jsonl.gz"
ITEM_CELL = Position(15, 17)
POCKET = Position(14, 16)
LEAVE_BOARD = 7814331   # at the item cell: the leave walks '7' into the pocket
POCKET_BOARD = 7814333  # in the pocket: live walked '3' back (return:seek-loot)
OBERON = 860


class N1b411RecallLootT1RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, until):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            boards = [json.loads(line) for line in stream if line.strip()]
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = parse_snapshot(copy.deepcopy(boards[0]), self.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        for raw in boards:
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
            if board.turn == until:
                return policy, board
            key = policy.choose_key(board)
            if key:
                policy.confirm_key_posted(key)
        raise AssertionError(f"turn {until} not in {FIXTURE.name}")

    def test_the_leave_still_steps_off_the_item_cell(self):
        policy, board = self.replay(LEAVE_BOARD)
        self.assertTrue(board.player.recalling)
        self.assertEqual(board.player.position, ITEM_CELL)
        self.assertEqual([m for m in board.visible_monsters if m.hostile], [])
        self.assertEqual([(m.race_id, m.asleep) for m in board.detected_monsters], [(OBERON, False)])

        key = policy.choose_key(board)

        self.assertEqual((policy.last_reason, key), ("sensed-t1:walk", "7"))

    def test_the_pickup_waits_in_the_pocket_instead_of_walking_back(self):
        policy, board = self.replay(POCKET_BOARD)
        self.assertTrue(board.player.recalling)
        self.assertEqual(board.player.position, POCKET)
        # The pocket's only exit is the cell the leave left.
        self.assertEqual(policy._walkable_neighbors(board, POCKET), [ITEM_CELL])
        self.assertIn(ITEM_CELL, left_cells.refused(policy, board))

        key = policy.choose_key(board)

        self.assertEqual((policy.last_reason, key), ("return:wait-recall", "5"))


if __name__ == "__main__":
    unittest.main()
