"""n1-b life-419 (2026-11-27 11:03-11:06): Morivant's gold piles walked to on the Outpost's map.

The chain (Zombie Magic-Eater CL50, HP 1128/1128, 55685 gold; build bot-da2924aea; one process):

 * Morivant (town id 2), the staff errand (me-staff:approach-tower) holding the board: gold (tval
   127) seen at (34,79) on turn 11260613 and at (64,180) on turn 11261289.
 * 11262110 me-staff:return-outpost '1ma': the Inn teleport back to the Outpost (town id 0).  Every
   town shares floor_key (0, 0, 0), so the floor change's loot reset did not run, and the loot
   memory kept both Morivant cells.
 * 11262113-11262615: seek-loot for 138 boards on the Outpost, the player moving every board: west to
   (33,80) (the empty (34,79) dropped), then east to (63,179) (the empty (64,180) dropped).
 * 11262618 town:cycle-break, then town:blocked:repetition '5' 24 times, the owner-halt at 11262708.

The fix (loot_memory): a change of town forgets the loot memory, where the routing terrain was
already forgotten (policy_navigation ``_scope_terrain_to_town``).

Recorded: tests/fixtures/n1b-419-town-loot-memory-1127.json.gz
(tests/extract_n1b_419_town_loot_memory_1127_fixture.py).  A fresh policy decides the three recorded
boards in order through the public ``choose_key``, each key confirmed as posted, with the game's
static town maps (as the live CLI loads them).

DECLARED PARTIAL STATE: the fresh policy has the arrival checkpoint's magic-eater device lists and the
halt's staff-sequence counts (absorbed, stage, remaining; the powers read), nothing else of the live
policy.  With the fix reverted the fresh policy decides the Outpost board as the live one did ('7'
seek-loot toward (34,79), the recorded key); with the fix it goes on to its own town work (shop:travel
here: its visit is not the live visit, which had finished its shopping), so the pinned answers are
"not seek-loot" and the loot walk's own (``_normal_loot_key``) None.  The full live state was replayed
from the capture's town-arrival checkpoint (tests/replay_town_arrival.py, not committed: 37 MB).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from collections import Counter
from pathlib import Path

from hengbot.policy import ConservativePolicy
from hengbot.me_staff_sequence import MeStaffSequence
from hengbot.model import TVAL_GOLD, Position, parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.town_maps import find_town_map, parse_town_map
from support.recorded import skill

with gzip.open(Path(__file__).with_name("fixtures") / "n1b-419-town-loot-memory-1127.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

MORIVANT_GOLD = (Position(34, 79), Position(64, 180))
OUTPOST_BOARD = 2


def drive(count=len(CASE["boards"])):
    """The fresh policy after deciding the first ``count`` boards, and their (key, reason)."""
    here = Path(__file__)
    maps = {index - 1: parse_town_map(find_town_map(index, here)) for index in range(1, 6)}
    policy = ConservativePolicy(
        monrace_knowledge=load_monrace_knowledge(find_monrace_definitions(here, None)),
        town_maps=maps)
    boards = CASE["boards"][:count]
    policy.prime(parse_snapshot(copy.deepcopy(boards[0]), policy._monrace_knowledge))
    policy._me_device_lists = {kind: (turn, tuple(rows)) for kind, (turn, rows) in CASE["device_lists"].items()}
    sequence = CASE["staff_sequence"]
    policy._me_staff_sequence = MeStaffSequence(
        absorbed=dict(sequence["absorbed"]), stage=sequence["stage"],
        remaining=tuple(sequence["remaining"]), powers_read=True)
    answers = []
    for raw in boards:
        skill(policy, raw)
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        answers.append((key, policy.last_reason))
        policy.confirm_key_posted(key)
    return policy, answers


class TheRecordingTest(unittest.TestCase):

    def test_morivant_gold_walked_to_on_the_outpost_until_the_stop(self):
        towns = [board["floor"]["town_id"] for board in CASE["boards"]]
        self.assertEqual(towns, [2, 2, 0])
        piles = {(cell["y"], cell["x"]): cell.get("t") for board in CASE["boards"][:2]
                 for cell in board["grid_map"]["cells"] if cell.get("o")}
        self.assertEqual([piles[(cell.y, cell.x)] for cell in MORIVANT_GOLD], [[TVAL_GOLD], [TVAL_GOLD]])
        rows = CASE["recorded"]
        self.assertEqual((rows[0]["turn"], rows[0]["reason"], rows[0]["key"]),
                         (11262110, "me-staff:return-outpost", "1ma"))
        reasons = Counter(row["reason"] for row in rows)
        self.assertEqual((reasons["seek-loot"], reasons["town:cycle-break"],
                          reasons["town:blocked:repetition"]), (138, 1, 24))
        walk = [row for row in rows if row["reason"] == "seek-loot"]
        self.assertEqual((walk[0]["key"], walk[0]["loot"]["target"]), ("7", {"y": 34, "x": 79}))
        # The player moved on every board of the walk; the piles were dropped beside their cells.
        self.assertTrue(all(before["position"] != after["position"] for before, after in zip(walk, walk[1:])))
        dropped = [(row["position"], len(row["loot"]["known"])) for row in rows
                   if row["turn"] in (11262247, 11262618)]
        self.assertEqual(dropped, [([33, 80], 1), ([63, 179], 0)])
        self.assertEqual(rows[-1]["turn"], 11262708)


class TownChangeTest(unittest.TestCase):

    def test_morivant_keeps_its_piles(self):
        policy, answers = drive(OUTPOST_BOARD)
        self.assertEqual(policy._known_loot, set(MORIVANT_GOLD))
        self.assertEqual(answers[-1][1], "me-staff:approach-tower")

    def test_the_outpost_forgets_the_morivant_piles(self):
        policy, answers = drive()
        key, reason = answers[OUTPOST_BOARD]
        self.assertNotEqual(reason, "seek-loot", key)
        self.assertEqual(policy._known_loot, set())
        self.assertIsNone(policy._loot_target)
        board = policy._with_grid_memory(parse_snapshot(
            copy.deepcopy(CASE["boards"][OUTPOST_BOARD]), policy._monrace_knowledge))
        self.assertIsNone(policy._normal_loot_key(board, []))
        self.assertIsNone(policy._loot_target)


if __name__ == "__main__":
    unittest.main()
