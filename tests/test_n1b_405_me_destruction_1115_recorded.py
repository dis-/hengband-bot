"""n1-b life-405 2026-11-15: the absorbed *Destruction* and the 49F-50F-49F stair cycle.

Defect 1, owner 2026-11-15 (verbatim): 「破壊の取り込み数が5回あるので行動がおかしい」.  The
Magic-Eater Lv42 (152,888 gold, Q25 done) has *Destruction* absorbed five times (the staff
list: success 95%, ``max`` 5).  A dive spent its charges (22:53:16 Angband 77F, the means-spent
return of owner 2026-11-14 「手段が尽きた時点で帰還させる」), and in town the 50F+ rule
(destruction_use.holds_means: me_capability's *Destruction* row counted the charges left) read
no means: ``town:entrance-step-off:fundraising:no-safe-destination:depth-gate:destination-77:
missing-destruction`` (22:53:34) and ``...destination-80:missing-destruction`` (23:10:23), and the
character mined 1F.  Game (C:/hengband/src): cmd-building/cmd-inn.cpp stay_inn ->
charge_magic_eating_energy sets every absorbed staff and wand to ``count * EATER_CHARGE``; and
hpmp/hp-mp-regenerator.cpp regenmagic refills them over time.  In town the row now counts the
count while the inn would refill it (me_inn_refill.refill_open), and the departure stays the
night before the recall when the displayed charges are short (me_inn_refill.destruction_key).

Defect 2, the owner the same night (verbatim): 「破壊が絡んだとき探索がおかしくなることがある。
現にn1-bは同じ範囲をループしている。」.  23:28-23:5x, the Castle: ``descend`` from 49F (23,63),
50F's arrival (37,35) two cells from a sleeping 年経たマグマのエレメンタル and three more sleepers
(T1; the means held: depth_safety missing nothing), ``emergency:stairs`` '<', 49F explored
through the 200-decision cooldown, ``seek-downstairs`` back to (23,63), ``descend`` -- the same
saved 50F (floor/floor-leaver.cpp set_grid_by_leaving_floor: the stair's ``grid.special`` is
the floor it leads to), about every 30 seconds.  Not the *Destruction* means: the escape
cooldown's intent (owner 2026-10-31 「逃げた階に戻らないための決定」) did not hold on a saved
floor.  fled_floor_stairs records the stair the escape landed on and the descent owners take
another stair of the floor.

Recorded (tests/extract_n1b_405_me_destruction_1115_fixture.py): the town-arrival checkpoint of
the 23:18:10 visit with 21 journal rows (row 17 the recall read to the Castle's 49F), the
23:21:22 checkpoint the Castle dive went on with, and seven state lines of the cycle.

DECLARED CONSTRUCTED:
* ``spent``: the staff list's *Destruction* row with ``current`` 0 (the recorded list showed 5
  after the dive's means-spent return had regenerated; the 22:53 and 23:10 visits' checkpoints
  were rotated away), as the 22:53 town board read it.
* ``beside_inn``: the player one step south of the Outpost inn (building 0 at (37,119)).
* ``shown_stunned``: the staff list as a NORMAL stun shows it (fail 5 + 20, the
  get_magic_chance_penalty of cmd-magiceat.cpp), the stun recorded with the list's board.
* The cycle's 49F stair board (turn 2801676) after the arrival's detections and the
  200-decision cooldown: the new-floor uses entered in the power memory and the countdown at 0
  (the 49F exploration between them is not replayed).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import dataclasses
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import (
    destruction_use, fled_floor_stairs, me_capability, me_inn_refill, me_power_success, me_powers,
)
from hengbot.input_executor import ScreenKind
from hengbot.model import SV_STAFF_DESTRUCTION, TVAL_STAFF, Position, parse_snapshot
from hengbot.observed_input import compile_observed_input
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-405-me-destruction-1115"
POWER = ("staff", SV_STAFF_DESTRUCTION)
STAFF = (TVAL_STAFF, SV_STAFF_DESTRUCTION)
RECALL_ROW = 17
BESIDE_INN = Position(38, 119)   # the Outpost inn (37,119): its step north enters it
STAIR_49 = Position(23, 63)
ARRIVAL_50 = Position(37, 35)


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def spent(policy):
    """DECLARED CONSTRUCTED: the *Destruction* row with no charge left."""
    turn, rows = policy._me_device_lists["staff"]
    names = me_capability.names(*POWER)
    policy._me_device_lists["staff"] = (turn, tuple(
        dict(row, current=0) if row.get("name") in names else row for row in rows))


def replay(policy, steps, until):
    """choose_key over the recorded rows before ``until``; (keys, reasons), the next board."""
    played = []
    for recorded, supply in steps[:until]:
        key = policy.choose_key(supply())
        played.append((key, policy.last_reason))
        post(policy, key)
    return played, steps[until][1]()


class TownDestructionMeansRecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, self.journal, self.steps = load(FIXTURE / "town", Path(scratch.name))
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)
        self.board = self.steps[0][1]()

    def test_a_the_recorded_list(self):
        row = me_capability.observed_row(self.policy, *POWER)
        self.assertEqual((row["success"], row["current"], row["max"]), (95, 5, 5))
        self.assertEqual(me_capability.count(self.policy, self.board, *POWER), 5)
        self.assertEqual(self.board.player.class_id, 16)
        self.assertTrue(self.board.in_town)
        self.assertEqual((self.journal[RECALL_ROW]["key"], self.journal[RECALL_ROW]["reason"]),
                         ("rgf", "town:recall-to-alt-dungeon"))

    def test_b_spent_charges_still_count_in_town(self):
        spent(self.policy)
        self.assertEqual(me_capability.charges(self.policy, self.board, *POWER), 0)
        # The count the inn gives back: the means holds, 80F is no gap.
        self.assertTrue(me_inn_refill.refill_open(self.policy, self.board))
        self.assertEqual(me_capability.replacing_charges(self.policy, self.board, STAFF), 5)
        self.assertTrue(destruction_use.holds_means(self.policy, self.board))
        self.assertNotIn("destruction", self.policy._missing_required_abilities(self.board, 80))
        self.assertTrue(self.policy._destination_depth_allowed(self.board, 80))
        self.assertTrue(me_inn_refill.destruction_short(self.policy, self.board))
        # In the dungeon the charges left (owner 2026-11-14 「手段が尽きた時点で帰還させる」).
        dungeon = dataclasses.replace(self.board, floor_key=(1, 77, 0), town_flag=False)
        self.assertFalse(me_inn_refill.refill_open(self.policy, dungeon))
        self.assertFalse(destruction_use.holds_means(self.policy, dungeon))

    def test_c_without_the_inn_the_gate_reads_the_charges_left(self):
        spent(self.policy)
        me_inn_refill.state(self.policy).closed = True  # the walk to the inn closed this stay
        self.assertFalse(destruction_use.holds_means(self.policy, self.board))
        self.assertFalse(self.policy._destination_depth_allowed(self.board, 80))
        self.assertEqual(self.policy.last_reason, "depth-gate:destination-80:missing-destruction")

    def test_c2_a_list_shown_stunned_is_still_reliable(self):
        """The known defect B of 2026-11-14 on this path: the gate's 80% is the power's rate,
        not the stun the last list was shown under."""
        turn, rows = self.policy._me_device_lists["staff"]
        names = me_capability.names(*POWER)
        self.policy._me_device_lists["staff"] = (turn, tuple(
            dict(row, fail=25, success=75) if row.get("name") in names else row for row in rows))
        boards = dict(getattr(self.policy, "_me_device_list_boards", None) or {})
        boards["staff"] = (2, me_power_success._inputs(self.board))
        self.policy._me_device_list_boards = boards
        self.assertEqual(me_powers.unstunned_success(self.policy, self.board, POWER), 95)
        self.assertTrue(me_capability.reliable(self.policy, self.board, POWER))
        self.assertTrue(destruction_use.holds_means(self.policy, self.board))

    def test_d_the_recorded_visit_with_its_charges_replays_unchanged(self):
        played, board = replay(self.policy, self.steps, RECALL_ROW)
        self.assertFalse(me_inn_refill.destruction_short(self.policy, board))
        key = self.policy.choose_key(board)
        self.assertEqual((key, self.policy.last_reason), ("rgf", "town:recall-to-alt-dungeon"))

    def test_e_spent_charges_stay_the_night_before_the_recall(self):
        spent(self.policy)
        played, board = replay(self.policy, self.steps, RECALL_ROW)
        # The recall reads the Castle's 49F: its first descent asks the 50F+ gate.
        self.assertEqual(self.policy._intended_dive_depth(board), 49)
        key = self.policy.choose_key(board)
        self.assertEqual(self.policy.last_reason, me_inn_refill.DESTRUCTION_APPROACH_REASON)
        self.assertNotEqual(key, "rgf")
        # Beside the inn: the step in carries the night and the leave, through the executor port.
        beside = dataclasses.replace(board, player=dataclasses.replace(board.player,
                                                                       position=BESIDE_INN))
        key = me_inn_refill.destruction_key(self.policy, beside)
        self.assertEqual((key, self.policy.last_reason),
                         ("8r\x1b", me_inn_refill.DESTRUCTION_REST_REASON))
        first, steps = compile_observed_input(key, ScreenKind.COMMAND, {}, self.policy.last_reason, [])
        self.assertEqual(first, "8")
        self.assertEqual([(step.kinds, step.keys) for step in steps],
                         [(frozenset({ScreenKind.BUILDING}), "r"),
                          (frozenset({ScreenKind.BUILDING}), "\x1b")])
        # Posted once: the charges count while the lists are browsed again, and no second night.
        self.assertEqual(me_inn_refill.state(self.policy).posted_turn, board.turn)
        self.assertTrue(destruction_use.holds_means(self.policy, board))
        self.assertIsNone(me_inn_refill.destruction_key(self.policy, beside))
        self.assertTrue(self.policy._me_power_refresh_pending)


class StairCycleRecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, _, _ = load(FIXTURE / "castle", Path(scratch.name))
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)
        lines = lzma.decompress((FIXTURE / "cycle-boards.jsonl.xz").read_bytes()).decode("utf-8")
        self.lines = [json.loads(line) for line in lines.splitlines()]

    def board(self, index):
        return parse_snapshot(self.lines[index], self.policy._monrace_knowledge)

    def flee(self):
        """The recorded 49F stair, the 50F arrival and the 49F arrival through choose_key."""
        keys = []
        for index in (0, 1, 3):
            board = self.board(index)
            key = self.policy.choose_key(board)
            keys.append((board.floor_key[1], board.player.position, key, self.policy.last_reason))
            post(self.policy, key)
        return keys

    def explored(self):
        """DECLARED CONSTRUCTED: the 49F stair board after the arrival's detections and the
        cooldown (turn 2801676; the recorded decision there was '>' descend)."""
        board = self.board(6)
        memory = getattr(self.policy, me_powers.MEMORY)
        for power in me_powers.POWERS:
            if "new-floor" in power.triggers:
                memory.uses.append(me_powers.Use(power.ident, power.ident, "new-floor",
                                                 board.player.position, self.lines[3]["turn"]))
        memory.pending = None
        self.policy._descent_block_countdown = 0
        self.policy._descent_blocked = False
        return board

    def test_a_the_recorded_cycle(self):
        keys = self.flee()
        self.assertEqual(keys[1][:4], (50, ARRIVAL_50, "<", "emergency:stairs"))
        self.assertEqual(keys[2][:2], (49, STAIR_49))
        arrival = self.board(1)
        sleepers = sorted((monster.race_id, monster.position.y, monster.position.x)
                          for monster in arrival.visible_monsters if monster.asleep)
        self.assertIn((1142, 39, 36), sleepers)  # 年経たマグマのエレメンタル
        # The means held at 50F: the cycle is not the 50F+ gate.
        self.assertNotIn("destruction", self.policy._missing_required_abilities(arrival, 50))
        self.assertEqual(self.board(6).player.position, STAIR_49)
        self.assertTrue(self.board(6).grid_at(STAIR_49).has_down_stairs)

    def test_b_the_stair_back_to_the_fled_floor_is_not_taken(self):
        self.flee()
        board = self.explored()
        self.assertTrue(fled_floor_stairs.leads_back(self.policy, board, STAIR_49))
        self.assertFalse(self.policy._is_descent_target(board, board.grid_at(STAIR_49)))
        self.assertNotIn(STAIR_49, self.policy._usable_downstairs(board))
        key = self.policy.choose_key(board)
        self.assertNotEqual(key, ">")
        self.assertEqual(self.policy.last_reason, "approach-descent")
        target = self.policy._nav_ledger.descent_target
        self.assertIsNotNone(target)
        self.assertNotEqual(target, STAIR_49)
        self.assertTrue(board.grid_at(target).has_down_stairs)

    def test_c_town_forgets_the_record(self):
        self.flee()
        self.assertTrue(getattr(self.policy, fled_floor_stairs.MEMORY))
        town = dataclasses.replace(self.board(6), floor_key=(0, 0, 0), town_flag=True)
        fled_floor_stairs.observe_floor_change(self.policy, town, (12, 49, 0))
        self.assertEqual(getattr(self.policy, fled_floor_stairs.MEMORY), {})


if __name__ == "__main__":
    unittest.main()
