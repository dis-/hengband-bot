"""Quest 32 on n1-a life-538 (2026-11-26 04:35:41, livelock:exhausted): the hold and the sweep took turns.

The chain (Zombie warrior Lv30, HP ~620 of 728; the opening hold [19,4] done; 閾に棲む者 in the dark west
room summoning whenever it saw the player, 「何かが魔法で仲間を召喚した！」):

 * The sweep's verdict (_quest_strategy_may_leave_hold, #47: one verdict for the sweep and the retake of
   the hold) was read afresh on every board.  From [17,6] and [18,6] a グリッドバグ (awake, biting) was in
   view: "hold", and ``quest-strategy:retake-hold`` stepped toward [19,4].  From [19,5], [19,6] or the
   hold itself it was not: "leave", and ``quest-strategy:sweep-engage-mobile`` stepped back north toward
   the kept target, a cloud giant's last-seen cell [6,4] (that giant had come to the hold and been
   killed at turn 1314663).  Two producers, two cells, one board apart, until the ping-pong guard's
   escalation and the livelock stop.
 * Earlier on the same floor (turn 1313331-1313539) the same pair alternated over the スタンウォール the plan
   walks to (``engage_never_move_races``): taken out of the never-moving races, they no longer had the
   distant stationary enemy's exemption, and every one in view sent the player back to the hold.  So did
   a 閾に棲む者 in view (it summons), the plan's first target (QUEST_32 「閾に棲む者が見えたら最優先で…
   隣まで歩いて殴る」).

The rule: the retake is a step away for the enemies the board named; the owner's rule for a step away
(2026-11-13 「離れたマスの共通の記録」: the reason is kept until it is gone) keeps the hold's verdict
until those enemies are gone (retreat_veto_life's lifetime, owner 2026-11-06 「脅威が見えなくなったら
消す」) or a board shows them and allows leaving (quest_sweep_target ``hold_kept``).  The never-moving
races the plan walks to are no reason to hold, and a target of a higher priority than the kept one
replaces it (quest_sweep_target ``engage_step``).

Recorded: tests/fixtures/n1a-538-q32-hold-sweep-1126 (tests/extract_n1a_538_q32_hold_sweep_1126_fixture.py):
the capture's town-arrival checkpoint, the plan record the process left at the stop, the boards of the
last window (turn 1314585, on the hold, to the stop) with their recorded decisions, and two single boards.

DECLARED CONSTRUCTED: the plan record of the stop is restored on the arrival checkpoint as a restart
restores it (quest_plan_record.restore), its turn put back to the window's first board (the record
holds the kept target [6,4] that the whole window walked to).  So set, the policy without this fix
answers the window's boards with the recorded owners (the recorded ``sweep-engage-mobile`` boards
included); the keys of a few retake steps differ (the ping-pong guard's records of the live process are
not in the checkpoint).  The boards are the recorded ones: the player's cell is the recorded walk, not
the walk the fixed policy would take.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import pickle
import tempfile
import unittest
from collections import deque
from pathlib import Path

from hengbot import quest_sweep_target
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import Position, parse_snapshot
from hengbot.monster_memory import UNSEEN_GAME_TURNS
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-538-q32-hold-sweep-1126"
CASE = json.loads(lzma.decompress((FIXTURE / "boards.json.xz").read_bytes()))
QUEST = 32
HOLD = Position(19, 4)
GRID_BUG = 34
SUMMONER = 263       # 閾に棲む者
STUN_WALL = 326
RETAKE = "quest-strategy:retake-hold"
SWEEP = "quest-strategy:sweep-engage-mobile"
HOLD_REASON = "quest-strategy:hold"
HOLD_MEMORY = "_quest_hold_threats"   # quest_sweep_target.HOLD_ATTRIBUTE
STEPS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def policy(first_turn: int, scratch: Path) -> HengbotPolicy:
    """The arrival checkpoint with the stop's plan record to restore on the first board."""
    deciding = restore_checkpoint_bytes(HengbotPolicy, lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes()))
    held = pickle.loads(lzma.decompress((FIXTURE / "quest-plan.pkl.xz").read_bytes()))
    held["turn"] = first_turn
    record = scratch / "quest-plan.pkl"
    record.write_bytes(pickle.dumps(held))
    deciding._quest_plan_record_path = record
    deciding._quest_plan_record_read = False
    deciding._quest_plan_record = None
    deciding._character_dump_path = scratch / "bot-test.txt"
    return deciding


def drive(deciding, boards):
    out = []
    for raw in boards:
        snapshot = parse_snapshot(copy.deepcopy(raw), deciding._monrace_knowledge)
        key = str(deciding.choose_key(snapshot))
        out.append((snapshot, key, deciding.last_reason))
        deciding.confirm_key_posted(key)
    return out


def walk_length(deciding, snapshot, start, goal, *, reach: int = 0) -> int:
    """The fewest steps of the walk model from ``start`` to within ``reach`` of ``goal``."""
    seen, frontier = {start}, deque([(start, 0)])
    while frontier:
        cell, steps = frontier.popleft()
        if max(abs(cell.y - goal.y), abs(cell.x - goal.x)) <= reach:
            return steps
        for neighbor in deciding._walkable_neighbors(snapshot, cell):
            if neighbor not in seen:
                seen.add(neighbor)
                frontier.append((neighbor, steps + 1))
    return 999


def monsters(raw, race):
    return [monster for monster in raw["visible_monsters"] if monster["race_id"] == race]


class TheRecordingTest(unittest.TestCase):

    def test_the_retake_and_the_sweep_took_turns_on_whether_a_grid_bug_was_in_view(self):
        rows = list(zip(CASE["boards"], CASE["recorded"]))
        self.assertEqual(rows[-1][1]["reason"], "livelock:exhausted")
        sweeps = [raw for raw, row in rows if row["reason"] == SWEEP]
        retakes = [raw for raw, row in rows if row["reason"] == RETAKE]
        self.assertGreaterEqual(len(sweeps), 15)
        self.assertGreaterEqual(len(retakes), 15)
        # Every sweep step was decided with no enemy in view; most retakes with a grid bug in view.
        self.assertEqual({len(raw["visible_monsters"]) for raw in sweeps}, {0})
        self.assertGreaterEqual(sum(bool(monsters(raw, GRID_BUG)) for raw in retakes), len(retakes) // 2)
        # Both on the same seven cells of the hold's corner: neither got anywhere.
        cells = {(raw["player"]["y"], raw["player"]["x"]) for raw, row in rows if row["reason"] in (SWEEP, RETAKE)}
        self.assertEqual(cells, {(17, 6), (18, 6), (18, 7), (19, 4), (19, 5), (19, 6), (19, 7)})


class TheWindowTest(unittest.TestCase):

    def test_the_hold_holds_while_the_enemies_it_was_retaken_for_are_there(self):
        with tempfile.TemporaryDirectory() as raw:
            deciding = policy(CASE["boards"][0]["turn"], Path(raw))
            answers = drive(deciding, CASE["boards"])
        reasons = [reason for _snapshot, _key, reason in answers]
        self.assertNotIn(SWEEP, reasons)
        self.assertNotIn("quest-strategy:placement-sweep", reasons)
        self.assertGreaterEqual(reasons.count(RETAKE), 30)
        for snapshot, key, reason in answers:
            here = snapshot.player.position
            if here == HOLD:
                self.assertIn(reason, (HOLD_REASON, "quest-strategy:melee"), snapshot.turn)
            if reason == RETAKE:   # never a step farther from the hold
                dy, dx = STEPS[key]
                there = Position(here.y + dy, here.x + dx)
                self.assertLessEqual(walk_length(deciding, snapshot, there, HOLD),
                                     walk_length(deciding, snapshot, here, HOLD), (snapshot.turn, key))

    def test_the_hold_is_released_once_they_are_gone(self):
        with tempfile.TemporaryDirectory() as raw:
            deciding = policy(CASE["boards"][0]["turn"], Path(raw))
            drive(deciding, CASE["boards"])
            # The window's last board on the hold with nothing in view, past the unseen window.
            quiet = copy.deepcopy(next(raw for raw in reversed(CASE["boards"])
                                       if (raw["player"]["y"], raw["player"]["x"]) == (HOLD.y, HOLD.x)
                                       and not raw["visible_monsters"]))
            quiet["turn"] = CASE["boards"][-1]["turn"] + UNSEEN_GAME_TURNS
            (_snapshot, key, reason), = drive(deciding, [quiet])
        self.assertEqual(reason, SWEEP)
        self.assertIn(key, STEPS)
        self.assertIsNone(getattr(deciding, HOLD_MEMORY, None))


class ThePlanTargetsTest(unittest.TestCase):

    def _observed(self, turn: str, keep):
        board = copy.deepcopy(CASE["singles"][turn])
        board["visible_monsters"] = [monster for monster in board["visible_monsters"] if keep(monster)]
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        deciding = policy(board["turn"], Path(scratch.name))
        (snapshot, _key, _reason), = drive(deciding, [board])
        setattr(deciding, HOLD_MEMORY, None)   # what the board's own decision kept
        profile = deciding.approved_quest_strategy(QUEST)
        hostiles = [monster for monster in snapshot.visible_monsters if monster.hostile]
        return deciding, snapshot, profile, hostiles

    def test_a_stun_wall_in_view_is_no_reason_to_hold(self):
        deciding, snapshot, profile, hostiles = self._observed(
            "1313331", lambda monster: monster["race_id"] == STUN_WALL)
        self.assertEqual([monster.race_id for monster in hostiles], [STUN_WALL])
        self.assertTrue(deciding._quest_strategy_may_leave_hold(
            snapshot, profile, hostiles, initial_hold_complete=True))

    def test_a_summoner_in_view_is_closed_on_before_the_kept_target(self):
        deciding, snapshot, profile, hostiles = self._observed(
            "1314506", lambda monster: monster["race_id"] == SUMMONER)
        summoner, = hostiles
        self.assertEqual((summoner.race_id, summoner.position), (SUMMONER, Position(10, 1)))
        self.assertTrue(deciding._quest_strategy_may_leave_hold(
            snapshot, profile, hostiles, initial_hold_complete=True))
        kept = getattr(deciding, quest_sweep_target.COMMIT_ATTRIBUTE)
        self.assertNotEqual(kept[1], SUMMONER)   # the record's kept target: the cloud giant's [6,4]
        step = quest_sweep_target.engage_step(deciding, snapshot, profile, hostiles)
        self.assertIsNotNone(step)
        navigator = deciding._quest_navigators[QUEST]
        self.assertLess(len(navigator._static_path(step, {summoner.position})),
                        len(navigator._static_path(snapshot.player.position, {summoner.position})))
        self.assertEqual(getattr(deciding, quest_sweep_target.COMMIT_ATTRIBUTE)[1:],
                         (SUMMONER, summoner.position))


if __name__ == "__main__":
    unittest.main()
