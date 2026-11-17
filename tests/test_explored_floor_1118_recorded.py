"""The explored dead-end floor's Recall reads "explored" as the owner said it, on both ends (1118).

Owner 2026-11-17 (verbatim 「適当な閾値を決めて、探索が済んだら帰還する。閾値は任せる。」,
explored_floor).  The 2026-11-18 measurement (C:/hengband-backups/pdca/deep-efficiency-after-1118,
REPORT.md section 2) found both ends wrong:

1. The "nothing left to explore" end read Recall on floors barely explored: 3 of the 10
   explored-dead-end-floor returns.  The explore's "nothing" is no reachable frontier on one board
   (its own *Destruction* and a Stone to Mud walk around the player, a sensed summoner's vetoes),
   while the map was still growing.  Now that end, too, needs a full window of explore decisions
   on the floor (explored_floor ``explored``); before it, the ladder below answers as before.
2. The map-growth end almost never fired on the Glass castle 60F: the window counted the cells
   swept by the player's own light (``_remembered_marked_t``), which there go on growing long
   after the map has shown them (the glass walls show far rooms the light reaches much later),
   and every own *Destruction* shrank that map and started the window again.  Now it counts the
   cells the map has shown on the visit (the union of ``_remembered_known_t``: the known map the
   threshold was chosen on, deep-efficiency-1117 impl_threshold.py), which a *Destruction* does
   not shrink.

Recorded (tests/fixtures/q1-explored-recall-1118.jsonl.xz, tests/extract_q1_explored_recall_1118_fixture.py):

- ``n1c-0256``: n1-c life-216, dungeon 14 (Mountain) 50F, its last floor, from the first board to
  the live Recall read at 02:56:01 (turn 6204776): 2 explore decisions, then its own
  *Destruction*, a livelock Stone to Mud and the read.
- ``n1b-0347``: n1-b life-411, Angband 80F (81F asks speed +25), from the first board to the
  live read at 03:47:07 (turn 6471499): 143 explore decisions, 144 frontiers open.
- ``glass``: n1-c life-216, Glass castle 60F (its last floor), from the bot's restart at 04:13:10
  (the game reloaded, the policy fresh) to turn 6297323; ``glass-explore`` the turns the live bot
  explored on.  Live, the window first stalled at 04:24:18 (after 5,129 explore decisions).

DECLARED RECONSTRUCTED: the absorbed *Destruction* (a staff row, 22 charges at 95%; the snapshots
keep no device list), without which the 50F+ means-spent return reads Recall first.  In 1 and 2
the last board is decided by the idle ladder with the explore finding nothing, as live (the
decision rows' safety gates show sealed_loot's, which is asked only then) and the absorbed-power
casts not asked (``me_powers.power_key`` None: the replay cannot feed their results).  In the
Glass castle replay the boards are merged into the map (``_build_grid_index``) and the explore
decisions are the live bot's; the *Destruction* of 04:13:32 (turn 6295553, the flash on the
board, the known map 6,154 -> 5,906 in the decision log) is forgotten from the map as the
destruction observer does (``destruction_use.forget_circle`` at the player), since the replay
cannot observe its own use.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import destruction_use, explored_floor, ladder_idle, me_capability, me_powers
from hengbot.model import SV_STAFF_DESTRUCTION, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "q1-explored-recall-1118.jsonl.xz"
GLASS_FLASH_TURN = 6295553

with lzma.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    ROWS = [json.loads(line) for line in _stream if line.strip()]
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")


def boards(role):
    return [row["board"] for row in ROWS if row["role"] == role]


def counts(policy):
    """The explore window's counts (explored_floor ``MEMORY``)."""
    return (getattr(policy, explored_floor.MEMORY, None) or {}).get("counts", ())


GLASS_EXPLORE = frozenset(next(row["turns"] for row in ROWS if row["role"] == "glass-explore"))


class ExploredFloor1118Test(unittest.TestCase):
    def policy(self, first):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), MONRACE)
        board = parse_snapshot(copy.deepcopy(first), MONRACE)
        policy.prime(board)
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {"staff": (board.turn, ({
            "name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 22,
            "max": 22, "fail": 5, "success": 95},))}
        return policy

    def exhausted_at_the_read(self, role):
        """The visit replayed up to the live read's board, which the idle ladder decides with the
        explore finding nothing."""
        rows = boards(role)
        policy = self.policy(rows[0])
        snapshot = None
        for raw in rows:
            snapshot = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), MONRACE))
            key = policy.choose_key(snapshot)
            if key:
                policy.confirm_key_posted(key)
        with mock.patch.object(policy, "_explore_step", lambda snapshot: None), \
                mock.patch.object(policy, "_hunt_step", lambda snapshot, hostiles: None), \
                mock.patch.object(me_powers, "power_key", lambda *args, **kwargs: None):
            key = ladder_idle.key(
                policy, snapshot, strategic_hostiles=policy._strategic_hostiles(snapshot),
                physical_hostiles=policy._physical_hostiles(snapshot),
                here=snapshot.grid_at(snapshot.player.position))
        return policy, snapshot, key

    def assert_not_read(self, role):
        policy, snapshot, key = self.exhausted_at_the_read(role)
        self.assertTrue(explored_floor.dead_end(policy, snapshot))
        self.assertTrue(policy._find_recall_scroll(snapshot) is not None)
        self.assertNotEqual(policy.last_reason, explored_floor.REASON, key)
        self.assertNotEqual(policy._last_return_trigger, explored_floor.TRIGGER, key)
        self.assertLessEqual(len(counts(policy)), explored_floor.WINDOW)
        self.assertFalse(explored_floor.explored(policy, snapshot, exhausted=True))

    # -- 1. the "nothing left" end on a floor barely explored ---------------------------------

    def test_n1c_mountain_50f_sealed_by_its_own_destruction_is_not_explored(self):
        self.assert_not_read("n1c-0256")

    def test_n1b_angband_80f_after_143_explore_decisions_is_not_explored(self):
        self.assert_not_read("n1b-0347")

    # -- 2. the growth end on the Glass castle --------------------------------------------------

    def glass(self):
        """The Glass castle boards merged into the map, the live explore decisions noted; the
        marked map's size at each of them beside (the window's measure before 1118)."""
        rows = boards("glass")
        policy = self.policy(rows[0])
        marked = []
        snapshot = None
        for raw in rows:
            snapshot = parse_snapshot(raw, MONRACE)
            if snapshot.turn == GLASS_FLASH_TURN:
                destruction_use.forget_circle(policy, snapshot.player.position)
            policy._build_grid_index(snapshot)
            if snapshot.turn in GLASS_EXPLORE:
                explored_floor.note_explore(policy, snapshot)
                marked.append(len(policy._remembered_marked_t))
        return policy, snapshot, marked

    def test_glass_castle_window_stalls_on_the_known_map(self):
        policy, snapshot, marked = self.glass()
        self.assertTrue(explored_floor.dead_end(policy, snapshot))
        self.assertTrue(explored_floor.stalled(policy, snapshot))
        window = counts(policy)
        self.assertEqual(len(window), explored_floor.WINDOW + 1)
        # The known map grew by 27 cells over the last 300 explore decisions (0.44%) ...
        self.assertLess(window[-1] - window[0], explored_floor.GROWTH_RATIO * window[-1])
        self.assertTrue(explored_floor.explored(policy, snapshot, exhausted=False))
        # ... while the cells swept by the player's light grew past the threshold.
        window = marked[-(explored_floor.WINDOW + 1):]
        self.assertGreaterEqual(window[-1] - window[0], explored_floor.GROWTH_RATIO * window[-1])

    def test_the_own_destruction_neither_shrinks_nor_restarts_the_window(self):
        rows = boards("glass")
        policy = self.policy(rows[0])
        before = None
        for raw in rows:
            snapshot = parse_snapshot(raw, MONRACE)
            if snapshot.turn == GLASS_FLASH_TURN:
                before = counts(policy)
                known = len(policy._remembered_known_t)
                destruction_use.forget_circle(policy, snapshot.player.position)
                self.assertLess(len(policy._remembered_known_t), known)
                policy._build_grid_index(snapshot)
                explored_floor.note_explore(policy, snapshot)
                after = counts(policy)
                break
            policy._build_grid_index(snapshot)
            if snapshot.turn in GLASS_EXPLORE:
                explored_floor.note_explore(policy, snapshot)
        self.assertGreater(len(before), 100)
        self.assertEqual(after[:-1], before[-explored_floor.WINDOW:])
        self.assertGreaterEqual(after[-1], before[-1])


if __name__ == "__main__":
    unittest.main()
