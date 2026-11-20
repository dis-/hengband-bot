"""A remembered item no walk reaches no longer holds an explored dead-end floor (n1-c life-217, 1120).

n1-c life-217 (Magic-Eater Lv50, Angband 95F: the Angband cap, owner 2026-11-19 「準備ができるまで
鉄獄95Fで探索」) was stopped by the floor-dwell watcher at 2026-11-20 19:34:04
(``stall:floor-dwell:explore``).  Its last 224 decisions were 213 explore steps across the cave
floor -- (54,31) to (60,97), back to (1,11) -- that grew the known map by 2 cells (7,311 to 7,313).
Every row's loot record is the same: one remembered item, a helm at (8,69) inside a block of grids
the map does not know (rows 2-11, x 68-74, walled by known granite), no loot target, no blocker.

explored_floor's Word of Recall (owner 2026-11-17 「探索が済んだら帰還する」) fires on the explore
decision once WINDOW explore decisions grew the map by less than GROWTH_RATIO, but it was held while
any loot candidate was left ("a remembered item it may yet open a way to holds the floor").  The
helm had no route, the explore was opening nothing toward it (loot_frontier steered the explore to
frontier after frontier nearest it, three tries each, over a floor with 253 open frontiers), and
sealed_loot -- the owner's ways into walled loot (11-13 melt, 11-18 map) -- is asked only once the
explore finds nothing at all, which this cave never gave.  So the floor was never left.

Now only a candidate the walk reaches holds the floor; with the window stalled and the remembered
loot beyond every walk, sealed_loot is asked first (its melt or its one mapping), and without a way
in Word of Recall is read, as on the "nothing left to explore" end.

Recorded: tests/fixtures/n1c-217-explore-dwell-1120.jsonl.xz
(tests/extract_n1c_217_explore_dwell_1120_fixture.py): the capture's 43 boards and 224 decision rows.

DECLARED RECONSTRUCTED: the absorbed *Destruction* (a staff row, 22 charges at 95%; the boards keep
no device list), without which the 50F+ means-spent return reads Recall on the first board.  The
explore window at the last board: the capture holds 213 of its 300 explore decisions (2 cells of
growth); its earlier 87 and the count before them are filled with the capture's first known count (the map did not grow
across the capture, and the watcher had seen no floor change for 30 minutes).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import explored_floor, me_capability, sealed_loot
from hengbot.model import SV_STAFF_DESTRUCTION, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-explore-dwell-1120.jsonl.xz"
HELM = Position(8, 69)

with lzma.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    ROWS = [json.loads(line) for line in _stream if line.strip()]
BOARDS = [row["board"] for row in ROWS if row["role"] == "board"]
DECISIONS = [row for row in ROWS if row["role"] == "decision"]
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")


def replay(test_case):
    """The capture's boards replayed up to the last one, the live window set (DECLARED
    RECONSTRUCTED above): (policy, last board)."""
    directory = TemporaryDirectory()
    test_case.addClassCleanup(directory.cleanup)
    policy = _policy(Path(directory.name), MONRACE)
    first = parse_snapshot(copy.deepcopy(BOARDS[0]), MONRACE)
    policy.prime(first)
    policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
    policy._me_device_lists = {"staff": (first.turn, ({
        "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
        "max": 22, "fail": 5, "success": 95},))}
    for raw in BOARDS[:-1]:
        snapshot = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), MONRACE))
        key = policy.choose_key(snapshot)
        if key:
            policy.confirm_key_posted(key)
    last = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(BOARDS[-1]), MONRACE))
    # The capture's explore decisions' known counts, the window's earlier part filled with the
    # first of them; the last board's explore decision adds the window's last count.
    known = [row["known"] for row in DECISIONS if row["reason"] == "explore"]
    counts = [known[0]] * (explored_floor.WINDOW + 1 - len(known)) + known
    setattr(policy, explored_floor.MEMORY, {
        "floor": last.floor_key, "seen": set(policy._remembered_known_t),
        "counts": tuple(counts[-(explored_floor.WINDOW + 1):])})
    return policy, last


class N1c217ExploreDwell1120Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        policy, last = replay(cls)
        cls.policy, cls.last = policy, last
        cls.candidates = policy._loot_candidates(last)
        cls.reached = HELM in sealed_loot.reach(policy, last)
        cls.dead_end = explored_floor.dead_end(policy, last)
        cls.key = policy.choose_key(last)
        # The same board with a way into the helm (sealed_loot answering, as with Stone to Mud
        # or 周辺感知 carried): the explore's rung asks it before the read.
        asked, cls.asked_board = replay(cls)

        def way_in(policy, snapshot):
            policy.last_reason = sealed_loot.MAP_REASON
            return "5"

        with mock.patch.object(sealed_loot, "key", way_in):
            cls.asked_key = asked.choose_key(cls.asked_board)
        cls.asked = asked

    def test_capture_is_the_live_dwell(self):
        explore = [row for row in DECISIONS if row["reason"] == "explore"]
        self.assertGreaterEqual(len(explore), 200)
        self.assertLessEqual(explore[-1]["known"] - explore[0]["known"], 2)
        self.assertTrue(all(row["loot"]["known"] == [{"y": HELM.y, "x": HELM.x}]
                            and row["loot"]["target"] is None and row["loot"]["blocker"] is None
                            for row in DECISIONS))

    def test_the_helm_is_the_only_candidate_and_no_walk_reaches_it(self):
        self.assertEqual(self.candidates, {HELM})
        self.assertFalse(self.reached)
        self.assertTrue(self.dead_end)

    def test_sealed_loot_is_asked_before_the_read(self):
        # The owner's ways into loot no walk reaches (11-13 melt, 11-18 mapping) come first.
        self.assertEqual(self.asked.last_reason, sealed_loot.MAP_REASON, self.asked_key)
        self.assertNotEqual(self.asked._last_return_trigger, explored_floor.TRIGGER)

    def test_explored_dead_end_floor_is_left_by_recall(self):
        policy, last, key = self.policy, self.last, self.key
        # Live: "explore" for ever.  Now the window has stalled (with the last explore decision)
        # and the unreachable helm holds nothing: no way in (no melt, no mapping means carried in
        # the replay), so Word of Recall is read.
        self.assertTrue(explored_floor.stalled(policy, last))
        self.assertEqual(policy.last_reason, explored_floor.REASON, key)
        self.assertEqual(policy._last_return_trigger, explored_floor.TRIGGER)


if __name__ == "__main__":
    unittest.main()
