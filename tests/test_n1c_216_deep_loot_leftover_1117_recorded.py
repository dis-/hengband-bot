"""n1-c life-216 left valuable items behind on 50F+ floors it explored to the end (2026-11-16/17).

Owner rules: loot comes before the explore with no distance cap (2026-09-23); loot the player saw
with no known way to it steers the explore (2026-11-13 「その品の方へ探索を寄せる」, loot_frontier);
sensed loot walled in is melted into with Stone to Mud when nothing is seen or sensed, whatever it
is worth (2026-11-13 「価値に関係なく溶かす」, sealed_loot).

1. Detected on unmapped grids (detected_loot).  Castle 64F, 2026-11-16 23:00: the item detection
   on turn 3506513 showed nine items at (13,82)-(31,104) (a potion of speed, a scroll of
   *Destruction*, an amulet and four rings among them) in a part of the floor the map did not
   know.  The game lists them in ``found_items``; the grid runs leave their cells unknown, and the
   loot memory was filled from the grids alone, so they were never loot: no steering, and the
   floor was left by its up stair 24-46 cells from them.  521 of the 621 valuable-looking items
   life-216 left on 50F+ floors (11-16 18:00 - 11-17 15:00) lay on such grids.
2. Walled in on a floor with nothing left to explore (ladder_idle).  Angband 80F, 2026-11-17
   13:57: an amulet at (7,125) in a granite room and corridor no walk reaches, the floor known to
   the last cell, Stone to Mud absorbed (99) and nothing in sight; the idle ladder took the up
   stair under the player ('<' ``stuck:ascend``, the next board was 79F).  The melt was asked only
   by the stuck escape, which a known stair answers first.

Recorded: tests/fixtures/n1c-216-deep-loot-leftover-1117.jsonl.gz
(tests/extract_n1c_216_deep_loot_leftover_1117_fixture.py).  Each case replays its boards in a
fresh policy (the life's ~f skill list of tests/fixtures/n1c-loot-rules-1113.jsonl.gz, as
test_sealed_loot_melt_1113_recorded does).  DECLARED CONSTRUCTED: the absorbed power lists are
the 15:50 town-arrival checkpoint's at full counts (the visits' own were not recorded); the
replayed windows' absorbed-power casts are not asked (``me_powers.power_key`` None: the replay
cannot feed their results, so the first one would be asked again on every board); in case 2 the
explore and the hunt have nothing left (the floor known to the last cell, as live; a fresh
policy holds none of the visit's spent frontiers).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

from hengbot import detected_loot, explored_floor, ladder_idle, loot_frontier, me_powers, sealed_loot
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.model import Position, game_distance, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests.support import recorded


FIXTURES = Path(__file__).with_name("fixtures")
FIXTURE = FIXTURES / "n1c-216-deep-loot-leftover-1117.jsonl.gz"
FIXTURE_SHA256 = "5fe36e82423f5cade1f9f7bb4e8f1b2bb74ab26a5b9a858f8c870ee675344ae9"
SKILL_FIXTURE = FIXTURES / "n1c-loot-rules-1113.jsonl.gz"
DETECTION_TURN = 3506513
CASTLE_ITEMS = frozenset(Position(y, x) for y, x in (
    (13, 82), (13, 84), (15, 88), (17, 98), (17, 102), (19, 90), (21, 98), (21, 100), (31, 104)))
POCKET_AMULET = Position(7, 125)


def _rows():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


ROWS = _rows()
LISTS = next(row["lists"] for row in ROWS if row["role"] == "me-lists")
CASTLE = [row["board"] for row in ROWS if row["role"] == "castle"]
ANGBAND = [row["board"] for row in ROWS if row["role"] == "angband"]
with gzip.open(SKILL_FIXTURE, "rt", encoding="utf-8") as _stream:
    SKILL = next(json.loads(line)["board"] for line in _stream if '"skill-knowledge"' in line)
MONRACE = load_monrace_knowledge(recorded.EDIT / "MonraceDefinitions.jsonc")
COSTS = load_baseitem_costs(recorded.EDIT / "BaseitemDefinitions.jsonc")


class DeepLootLeftover1117Test(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(me_powers, "power_key", lambda *args, **kwargs: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def replay(self, boards, lists=LISTS):
        policy = HengbotPolicy(monrace_knowledge=MONRACE, baseitem_costs=COSTS)
        policy.consume_skill_knowledge(SKILL)
        policy._skill_exp_request_key = lambda snapshot: None
        snapshot = None
        for raw in boards:
            policy._me_device_lists = {kind: (turn, tuple(rows)) for kind, (turn, rows) in lists.items()}
            snapshot = parse_snapshot(copy.deepcopy(raw), MONRACE)
            key = policy.choose_key(snapshot)
            if key:
                policy.confirm_key_posted(key)
        return policy, snapshot

    # -- 1. detected on unmapped grids --------------------------------------------------

    def test_the_detected_items_on_unmapped_grids_are_loot(self):
        detection = next(index for index, raw in enumerate(CASTLE) if raw["turn"] == DETECTION_TURN)
        board = CASTLE[detection]
        listed = {Position(row[0], row[1]) for row in board["grid_map"]["found_items"]}
        self.assertLessEqual(CASTLE_ITEMS, listed)
        snapshot = parse_snapshot(copy.deepcopy(board), MONRACE)
        self.assertFalse(any((grid := snapshot.grids.get(cell)) is not None and grid.known
                             for cell in CASTLE_ITEMS))
        policy, _ = self.replay(CASTLE[:detection])
        self.assertFalse(CASTLE_ITEMS & policy._known_loot)
        policy, snapshot = self.replay(CASTLE[:detection + 1])
        self.assertLessEqual(CASTLE_ITEMS, policy._known_loot)
        self.assertLessEqual(CASTLE_ITEMS, policy._loot_candidates(snapshot))

    def test_the_unreachable_detected_items_steer_the_explore(self):
        policy, snapshot = self.replay(CASTLE)
        noted = getattr(policy, loot_frontier.NOTE)
        self.assertLessEqual(CASTLE_ITEMS, noted[2])
        self.assertGreaterEqual(noted[3], loot_frontier.STEER_AFTER_BOARDS)
        path = loot_frontier.explore_path(policy, snapshot, set())
        self.assertTrue(path)
        goal = path[-1]
        self.assertTrue(policy._is_remembered_frontier(snapshot, goal))
        nearest = min(game_distance(goal, item) for item in CASTLE_ITEMS)
        self.assertLess(nearest, min(game_distance(snapshot.player.position, item)
                                     for item in CASTLE_ITEMS))

    def test_a_detected_item_the_game_no_longer_lists_is_forgotten(self):
        """Declared constructed: the board after the detection with one found row taken out."""
        detection = next(index for index, raw in enumerate(CASTLE) if raw["turn"] == DETECTION_TURN)
        policy, _ = self.replay(CASTLE[:detection + 1])
        raw = copy.deepcopy(CASTLE[detection + 1])
        gone = Position(19, 90)
        raw["grid_map"]["found_items"] = [row for row in raw["grid_map"]["found_items"]
                                          if (row[0], row[1]) != (gone.y, gone.x)]
        policy._deferred_loot.add(gone)
        detected_loot.observe(policy, parse_snapshot(raw, MONRACE))
        self.assertNotIn(gone, policy._known_loot)
        self.assertNotIn(gone, policy._deferred_loot)
        self.assertLessEqual(CASTLE_ITEMS - {gone}, policy._known_loot)

    def test_a_detected_skeleton_on_an_unmapped_grid_is_no_loot(self):
        """Declared constructed: one detected row's class made a skeleton (tval 10)."""
        detection = next(index for index, raw in enumerate(CASTLE) if raw["turn"] == DETECTION_TURN)
        policy, _ = self.replay(CASTLE[:detection])
        raw = copy.deepcopy(CASTLE[detection])
        bones = Position(19, 90)
        raw["grid_map"]["found_items"] = [
            [row[0], row[1], 1, 10] if (row[0], row[1]) == (bones.y, bones.x) else row
            for row in raw["grid_map"]["found_items"]]
        detected_loot.observe(policy, parse_snapshot(raw, MONRACE))
        self.assertNotIn(bones, policy._known_loot)
        self.assertIn(Position(17, 98), policy._known_loot)

    # -- 2. walled in on a floor with nothing left to explore --------------------------

    def idle(self, lists=LISTS):
        policy, snapshot = self.replay(ANGBAND, lists)
        self.assertTrue(snapshot.grid_at(snapshot.player.position).has_up_stairs)
        with mock.patch.object(policy, "_explore_step", lambda snapshot: None), \
                mock.patch.object(policy, "_hunt_step", lambda snapshot, hostiles: None):
            key = ladder_idle.key(
                policy, snapshot, strategic_hostiles=policy._strategic_hostiles(snapshot),
                physical_hostiles=policy._physical_hostiles(snapshot),
                here=snapshot.grid_at(snapshot.player.position))
        return policy, snapshot, key

    def test_the_walled_amulet_is_melted_into_before_the_stair(self):
        policy, snapshot, key = self.idle()
        self.assertIn(POCKET_AMULET, policy._loot_candidates(snapshot))
        self.assertEqual((key, policy.last_reason), ("9", sealed_loot.REASON))

    def test_without_stone_to_mud_the_floor_is_left_by_recall(self):
        """Declared constructed: the absorbed Stone to Mud taken out of the wand list.  With no melt
        the explored 80F (a dead end: 81F asks speed +25) is left by Word of Recall, not its up
        stair (explored_floor, owner 2026-11-17 「探索が済んだら帰還する」; until then '<'
        ``stuck:ascend`` as live)."""
        lists = {kind: (turn, [row for row in rows if not (kind == "wand" and row["name"] == "岩石溶解")])
                 for kind, (turn, rows) in LISTS.items()}
        policy, _snapshot, key = self.idle(lists)
        self.assertEqual(policy.last_reason, explored_floor.REASON, key)
        self.assertEqual(policy._last_return_trigger, explored_floor.TRIGGER)


if __name__ == "__main__":
    unittest.main()
