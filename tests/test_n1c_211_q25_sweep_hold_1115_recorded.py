"""Quest 25 on n1-c life-211 (2026-11-15 09:25-09:36): the sweep holding for a quylthulg in a sealed pocket, recorded.

After the empty-detection fix (bot-30aeba85b) twelve races were absent at turn 4034801 and the plan
went on; the quylthulgs' phase shot at [7,14] between recharge rests until 09:25:21, and the sweep
(phase6_sweep, PHASES index 8; owner 2026-11-06 「感知が使えるなら使って見つけ、倒す」) cast the absorbed
Rod of Detection on [5,2] (turn 4076115).  Its board (4076127) showed the two Nexus quylthulgs (480)
on [7,4] and [1,15].  From 09:25:23 to the stop at 09:36 every decision was ``quest-strategy:hold``
'5' on [5,2] (5,265 of them; ``survival:mana-absorb`` six times).

What it waited for: the sweep walks toward the first cell the detection showed, [7,4].  That cell
is the map's sealed pocket 『Z』 (rows 6-9, columns 2-5): permanent walls and the granite [9,3]
(QUEST_25 ``phase1`` (6): the hound's pocket, opened only through the granite).  No walk reaches it,
``_walk`` answered nothing and the sweep held; the quylthulg on [1,15], at the end of the north
corridor a walk reaches, was never gone for.

The fix (quest25_battle ``_sweep``, ``_sweep_reachable``): the sweep goes for the nearest monster or
remembered cell a walk reaches (it or a cell beside it), and forgets only the cell it reached before it
detects again.  A monster only in a sealed pocket is no walk's goal; when only such cells are left,
the pocket is opened by melting the granite [9,3] (owner 2026-11-15 「溶かして撃つ・無ければ帰還」,
quest25_pocket).

Recorded: tests/fixtures/n1c-211-q25-sweep-hold-1115.json.gz
(tests/extract_n1c_211_q25_sweep_hold_1115_fixture.py): the boards of turns 4076000-4076300 and the
last 20 before the stop, their decisions, every decision after the detection, the stop's record.  A
fresh policy restores the record through the real path and decides the recorded boards through the
public ``choose_key``; a step is posted through the production executor.

DECLARED RECONSTRUCTED: the remembered magic-eater lists (tests/test_n1c_208_q25_patrol_1115_recorded).
The stop's record (turn 4134533) is set to the board's turn, as the earlier Q25 replays do; for the
detection's own board its ``detected`` is cleared (the sweep reads it from that board).
DECLARED CONSTRUCTED: the board after the posted step (the player one cell on), and the controls,
each changing one thing.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_battle_record
from hengbot.model import parse_snapshot
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay
from tests import test_n1c_211_q25_absent_wait_1115_recorded as wait

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-211-q25-sweep-hold-1115.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

geo = battle.geo
STAND = (5, 2)
CAST_TURN = 4076115          # the sweep's ``mCg``
SHOWN_TURN = 4076127         # its board: the quylthulgs on [7,4] and [1,15]
HELD_TURN = 4076134          # the first hold after it, nothing shown
SEALED, OPEN = (7, 4), (1, 15)
SWEEP = battle.phase_index("sweep")
STEPS = {"7": (-1, -1), "8": (-1, 0), "9": (-1, 1), "4": (0, -1), "6": (0, 1), "1": (1, -1),
         "2": (1, 0), "3": (1, 1)}


def board(turn: int) -> dict:
    return copy.deepcopy(next(raw for raw in CASE["boards"] if raw["turn"] == turn))


def record(turn: int, **changes) -> dict:
    """DECLARED RECONSTRUCTED (module note): the stop's record at ``turn``."""
    found = copy.deepcopy(CASE["stop_record"])
    found["turn"] = turn
    for name, value in changes.items():
        found["battle"][name] = quest25_battle_record._encode(value)
    return found


def at(raw: dict, cell) -> dict:
    moved = copy.deepcopy(raw)
    moved["player"] = dict(moved["player"], y=cell[0], x=cell[1])
    return moved


def decided(directory, turn, raw=None, **changes):
    raw = board(turn) if raw is None else raw
    policy = wait.new_policy(Path(directory), record(turn, **changes), raw)
    key = wait.decide_past_reads(policy, raw)
    return policy, key


class TheRecordingTest(unittest.TestCase):

    def test_the_detection_showed_both_and_the_sweep_held(self):
        shown = board(SHOWN_TURN)
        self.assertEqual(sorted((m["race_id"], m["y"], m["x"]) for m in shown["detected_monsters"]),
                         [(geo.QUYL, 1, 15), (geo.QUYL, 7, 4)])
        recorded = {(row["turn"], row["reason"], row["key"]) for row in CASE["decisions"]}
        self.assertIn((CAST_TURN, f"{battle.DETECT_REASON}:detect-all", "mCg"), recorded)
        after = CASE["after_detection"]
        holds = [row for row in after if (row[1], row[2], tuple(row[3])) == (battle.HOLD_REASON, "5", STAND)]
        self.assertEqual(len(holds), 5265)
        self.assertEqual({row[1] for row in after} - {battle.HOLD_REASON}, {"survival:mana-absorb"})

    def test_the_stop_record_is_the_sweep_remembering_both_cells(self):
        fought = CASE["stop_record"]["battle"]
        self.assertEqual(fought["phase"], SWEEP)
        self.assertEqual(quest25_battle_record._decode(fought["detected"]), (SEALED, OPEN))
        self.assertNotIn(geo.QUYL, dict(map(tuple, fought["kills"]["dict"])))

    def test_the_pocket_is_sealed_and_the_corridor_cell_is_reached(self):
        with TemporaryDirectory() as directory:
            policy, _key = decided(directory, HELD_TURN)
            ctx = battle._ctx(policy, parse_snapshot(board(HELD_TURN), policy._monrace_knowledge))
            self.assertFalse(battle._sweep_reachable(ctx, SEALED))
            self.assertTrue(battle._sweep_reachable(ctx, OPEN))


class TheSweepWalkTest(replay._Replay):

    def test_on_the_recorded_hold_it_walks_toward_the_corridor_quylthulg(self):
        with TemporaryDirectory() as directory:
            policy, key = decided(directory, HELD_TURN)
            self.assertEqual((key, policy.last_reason, wait.phase_name(policy)), ("7", battle.WALK_REASON, "sweep"))
            step = STEPS[key]
            following = at(board(HELD_TURN), (STAND[0] + step[0], STAND[1] + step[1]))
            following["turn"] = HELD_TURN + 10
            self.post(policy, board(HELD_TURN), key, following)
            self.assertEqual(wait.fight(policy).detected, (SEALED, OPEN))

    def test_on_the_detections_board_it_walks_toward_the_reachable_one(self):
        with TemporaryDirectory() as directory:
            policy, key = decided(directory, SHOWN_TURN, detected=None)
            self.assertEqual((key, policy.last_reason), ("7", battle.WALK_REASON))
            self.assertEqual(set(wait.fight(policy).detected), {SEALED, OPEN})

    def test_beside_the_cell_it_is_forgotten_and_the_detection_cast_again(self):
        """DECLARED CONSTRUCTED: the hold's board with the player on [1,14], beside [1,15]."""
        raw = at(board(HELD_TURN), (1, 14))
        with TemporaryDirectory() as directory:
            policy, key = decided(directory, HELD_TURN, raw)
            fight = wait.fight(policy)
            self.assertEqual(fight.detected, (SEALED,))
            self.assertEqual((key, policy.last_reason), ("mCg", f"{battle.DETECT_REASON}:detect-all"))

    def test_control_only_the_sealed_cell_left_goes_to_melt_it(self):
        """DECLARED CONSTRUCTED: the record remembering [7,4] alone.  Owner 2026-11-15 「溶かして撃つ・
        無ければ帰還」 (tests/test_n1c_211_q25_sealed_quylthulg_1115_recorded): the walk to [10,2]."""
        from hengbot import quest25_pocket

        with TemporaryDirectory() as directory:
            policy, key = decided(directory, HELD_TURN, detected=(SEALED,))
            self.assertEqual((key, policy.last_reason), ("1", quest25_pocket.WALK_REASON))
            self.assertEqual(wait.phase_name(policy), "sweep")


if __name__ == "__main__":
    unittest.main()
