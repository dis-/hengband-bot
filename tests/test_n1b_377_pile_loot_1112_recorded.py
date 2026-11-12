"""n1-b life-377's town:blocked:owner-retired-burst (2026-11-12 11:13, Outpost Home).

Recorded: the capture's town-arrival checkpoint, journal rows 0-283 and
sidecar files (tests/extract_n1b_377_pile_loot_1112_fixture.py).

life-377 resumed the Lv45 Magic-Eater of life-370 in the Home pocket whose
three exits carried the chest's piles.  Row 268's seek-loot walked onto the
armour pile (46,124) (best distance 0) while the Home scan took that board,
and the town errands then walked the loot goal's stall budget out across
the town.  From row 281 on, each Home exit (home:leave-for-pending-withdraw)
let seek-loot step onto the pile again ('3'); the arrival counted as one
more stalled decision, the navigation ledger deferred the pile on the cell
itself, the pickup refused it, the Home approach stepped back ('7'), and the
fifth round stopped the bot (owner-retired-burst).

The rows replay the recorded keys up to row 283, the first arrival on the
pile in the loop.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import base64
import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.model import Position
from hengbot.policy import staged_prompt_chain_matches
from hengbot.quest_navigator import PICKUP_KEY
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)
from replay_town_arrival import adopt_calibration, decisions, journal, restore


FIXTURE = Path(__file__).with_name("fixtures") / "n1b-377-pile-loot-1112"
ARRIVAL_ROW = 283
ARMOUR_PILE = Position(46, 124)


class N1b377PileLoot1112RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self):
        visit = self.scratch / "town-arrival"
        (visit / SIDECAR_DIRECTORY).mkdir(parents=True)
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((FIXTURE / "journal.jsonl.xz").read_bytes())))
        sidecars = json.loads(lzma.decompress((FIXTURE / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(
            json.dumps(sidecars["manifest"], ensure_ascii=False), encoding="utf-8")
        for role, data in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(base64.b64decode(data))
        runtime = self.scratch / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path",
                          runtime)
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def test_arrival_on_the_committed_pile_picks_it_up(self):
        """Row 283: live ``7`` shop:approach back to the entrance; now the pickup."""
        policy, recorded, steps = self.load()
        for row, supply in steps[:ARRIVAL_ROW]:
            policy.choose_key(supply())
            key = recorded[row["row"]]["key"]
            if key:
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
        self.assertEqual([(recorded[row]["key"], recorded[row]["reason"]) for row in (281, 282, 283)],
                         [("\x1b", "home:leave-for-pending-withdraw"), ("3", "seek-loot"),
                          ("7", "shop:approach")])
        board = steps[ARRIVAL_ROW][1]()
        self.assertEqual(board.player.position, ARMOUR_PILE)
        self.assertEqual(board.grids[ARMOUR_PILE].object_count, 1)
        self.assertEqual(len(board.inventory), 13)
        self.assertEqual(policy._loot_target, ARMOUR_PILE)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), (PICKUP_KEY, "pickup"))
        self.assertNotIn(ARMOUR_PILE, policy._deferred_loot)
        self.assertFalse(policy._nav_ledger.is_expired("loot", ARMOUR_PILE))


if __name__ == "__main__":
    unittest.main()
