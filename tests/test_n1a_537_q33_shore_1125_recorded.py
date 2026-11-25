"""Quest 33 on n1-a life-537 (2026-11-25 10:10:58-10:11:52): the lure and the fire answer alternate
at the 船幽霊's water.

The chain (Zombie warrior Lv48, HP 1169, no bolts for the heavy crossbow; decisions 71077-71102 of
the quest floor, one process, in the summon answer's steps after a disengage, ``luring``):

 * The member lured is the 船幽霊 38 (race 1389: AQUATIC, 10d10 HP, BO_WATE/SCARE 1_IN_8; it never
   leaves the deep water, quest_summon_answer ``_stays``), so the lure closes on it at once, to a
   cell it is seen from (``summoned-lure-walk``), and holds there for what follows.
 * There the two 船幽霊 in [12..13,43..44] cast water bolts; no shot reaches them (no bolts), so the
   fire answer walks out of their line (``fire-disengage-walk``); out of it, the lure walks back.
 * The two (and the hold between them) alternated on [15..18,39..41] until the livelock stop, while
   one blow (expected 100 a player action against the 10d10 HP) from the shore cell [14,42] beside
   [13,43] kills one.  Decisions 70035-70047 (the same pair at [2..3,43..45]) had ended in the
   livelock guard's teleport the same way.

The rule (owner 2026-11-19 「地形と敵の位置、敵のアルゴリズムを確認して有効な場所で待つ」, the plan's
「召還持ちを優先して周辺のモンスターを倒す」; owner 2026-11-13 pingpong: one verdict for the walkers):
the cells a monster that never comes is killed from (``attack_cells``: its shot, or the dry cell
beside it a blow reaches) are where both the fire answer and the lure go.

Recorded: tests/fixtures/n1a-537-q33-shore-1125 (tests/extract_n1a_537_q33_shore_1125_fixture.py):
the policy replayed by the code of the live process from the town arrival through the floor's
boards up to decision 71077 (it reproduces the recorded decisions), and the boards 71077 to the
stop.  The policy decides them in order through the public ``choose_key``, each key confirmed as
posted; the boards are the recorded cells, not where the replayed keys lead.

DECLARED CONSTRUCTED (``ShoreBlowTest``): the board of 71099 (both 船幽霊 in view on [13,43] and
[13,44]) with the player moved onto [14,42], beside [13,43].
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path

from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot import quest_plan_base, quest_summon_answer
from hengbot.quest_plan_base import MELEE_REASON

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-537-q33-shore-1125"
CASE = json.loads(lzma.decompress((FIXTURE / "boards.json.xz").read_bytes()))
PHANTOM_SHIP = 1389
SHORE = Position(14, 42)
LOOP = range(71089, 71103)
STEPS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def policy():
    return restore_checkpoint_bytes(HengbotPolicy, lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes()))


def drive(boards=None):
    """[(recorded row, the board, key, reason, the cells the 船幽霊 are killed from)] of the boards
    decided in order by the fixture's policy."""
    deciding = policy()
    out = []
    for raw, row in zip(CASE["boards"] if boards is None else boards, CASE["recorded"]):
        snapshot = parse_snapshot(copy.deepcopy(raw), deciding._monrace_knowledge)
        key = str(deciding.choose_key(snapshot))
        navigator = deciding._quest_navigators.get(33)
        ground = (frozenset() if navigator is None else frozenset(
            cell for cell, kind in quest_plan_base._terrain_of(navigator, snapshot, water=False).items()
            if kind in {"floor", "passage"}))
        # The shore: the dry ground beside a 船幽霊 (no bolts: no shot is taken from anywhere).
        cells = {Position(monster.position.y + dy, monster.position.x + dx) for monster in ships(snapshot)
                 for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                 if (monster.position.y + dy, monster.position.x + dx) in ground}
        out.append((row, snapshot, key, deciding.last_reason, (cells, ground)))
        deciding.confirm_key_posted(key)
    return out


def walk_length(ground, start, cells) -> int:
    """The fewest steps over the dry ground from ``start`` to one of ``cells``."""
    goals = {(cell.y, cell.x) for cell in cells}
    frontier, seen, steps = [(start.y, start.x)], {(start.y, start.x)}, 0
    while frontier:
        if goals & set(frontier):
            return steps
        steps += 1
        frontier = [(y + dy, x + dx) for y, x in frontier for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                    if (y + dy, x + dx) in ground and (y + dy, x + dx) not in seen]
        seen |= set(frontier)
    return 999


def ships(snapshot):
    return [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
            if monster.race_id == PHANTOM_SHIP]


class TheRecordingTest(unittest.TestCase):

    def test_the_lure_and_the_fire_answer_alternate_at_the_water(self):
        rows = {row["sequence"]: (row, raw) for raw, row in zip(CASE["boards"], CASE["recorded"]) if row}
        reasons = [rows[sequence][0]["reason"] for sequence in LOOP]
        self.assertEqual(set(reasons), {quest_summon_answer.LURE_WALK_REASON, quest_summon_answer.FIRE_WALK_REASON,
                                        "quest-strategy:hold"})
        self.assertGreaterEqual(reasons.count(quest_summon_answer.FIRE_WALK_REASON), 5)
        self.assertGreaterEqual(reasons.count(quest_summon_answer.LURE_WALK_REASON), 3)
        cells = {(raw["player"]["y"], raw["player"]["x"]) for _row, raw in (rows[s] for s in LOOP)}
        self.assertLessEqual(cells, {(y, x) for y in range(15, 19) for x in range(39, 42)})
        self.assertIn("船幽霊がウォーター・ボルトの呪文を唱えた。", rows[71101][1]["messages"])
        self.assertIsNone(CASE["recorded"][-1])   # the stop's board: no decision recorded

    def test_the_phantom_ship_never_leaves_its_water(self):
        deciding = policy()
        knowledge = deciding._monrace_knowledge[PHANTOM_SHIP]
        self.assertIn("AQUATIC", knowledge.flags)
        self.assertTrue(quest_summon_answer._stays(deciding, PHANTOM_SHIP))


class OneVerdictTest(unittest.TestCase):

    def test_the_fire_answer_closes_on_the_shore_and_never_leaves(self):
        answers = drive()
        loop = [answer for answer in answers if answer[0] is not None and answer[0]["sequence"] in LOOP]
        reasons = {answer[3] for answer in loop}
        self.assertNotIn(quest_summon_answer.FIRE_WALK_REASON, reasons)
        # No hold with a 船幽霊 in view (the one at 71089, both known by telepathy only and out of
        # line, is the plan's wait for what comes).
        self.assertEqual([row["sequence"] for row, snapshot, _key, reason, _cells in loop
                          if reason == "quest-strategy:hold"
                          and any(monster.race_id == PHANTOM_SHIP for monster in snapshot.visible_monsters)], [])
        # Every step of the loop's boards (the lure's and the fire answer's alike) heads for the cells
        # the 船幽霊 are killed from (the shore beside them), never away.
        steps = 0
        for row, snapshot, key, reason, (cells, ground) in loop:
            if key not in STEPS:
                continue
            steps += 1
            self.assertTrue(cells, row["sequence"])
            dy, dx = STEPS[key]
            here = snapshot.player.position
            there = Position(here.y + dy, here.x + dx)
            self.assertLess(walk_length(ground, there, cells), walk_length(ground, here, cells),
                            (row["sequence"], reason, key))
        self.assertGreaterEqual(steps, 10)
        # From [15,41] the step is onto the shore [14,42], beside the 船幽霊 on [13,43].
        on_shore_side = {key for _row, snapshot, key, _reason, _cells in loop
                         if snapshot.player.position == Position(15, 41)}
        self.assertEqual(on_shore_side, {"9"})


class ShoreBlowTest(unittest.TestCase):

    def test_beside_the_phantom_ship_the_blow(self):
        boards = copy.deepcopy(CASE["boards"])
        index = next(i for i, row in enumerate(CASE["recorded"]) if row and row["sequence"] == 71099)
        boards[index]["player"] = {**boards[index]["player"], "y": SHORE.y, "x": SHORE.x}
        row, snapshot, key, reason, _cells = drive(boards[:index + 1])[-1]
        self.assertEqual(row["sequence"], 71099)
        self.assertIn(Position(13, 43), {monster.position for monster in ships(snapshot)})
        self.assertEqual((reason, key), (MELEE_REASON, "9"))


# -- the second process (restart 12:32:51, main 12c52ae3b): the lure's wait ---------------------------
#
# Stopped again by the livelock guard at 12:37:33.  The member lured was the 巨大火アリ 9 (race 548,
# vision 14, in the tree-and-pit pocket [25..27,53..54]); it stepped between [27,53] and [26,54].
# [29,40] is 14 game grids (quest_exposure.game_distance) from [27,53] and 15 from [26,54], so it was
# a pulling cell (the fewest others acting) on one board and none on the next: the lure walked
# '6' to [29,41]/[29,42] and '4' back and held between (decisions 2424-2446).  The 巨大火アリ is an
# animal pack that hides from a player at full HP (the third process below): it never comes, so it
# is not waited for (quest_summon_answer ``never_comes``).  Owner 2026-11-25 (b)-1 (only a monster
# that never leaves the water or never moves is closed on to melee): with no shot (no bolts) it is
# not closed on either but left to the plan; the lure goes on with the others.
#
# Recorded: tests/fixtures/n1a-537-q33-lure-hold-1125 (tests/extract_n1a_537_q33_lure_hold_1125_fixture.py;
# DECLARED CONSTRUCTED there: the restart).  The policy decides the boards from decision 2400 in order.

SECOND = Path(__file__).with_name("fixtures") / "n1a-537-q33-lure-hold-1125"
SECOND_CASE = json.loads(lzma.decompress((SECOND / "boards.json.xz").read_bytes()))
FIRE_ANT = 548
WAIT = range(2424, 2447)


def drive_second():
    """``drive_pack`` of the second process."""
    return drive_pack(SECOND, SECOND_CASE)


class TheLureWaitRecordingTest(unittest.TestCase):

    def test_the_lure_walks_off_and_back_between_holds(self):
        rows = {row["sequence"]: (row, raw) for raw, row in zip(SECOND_CASE["boards"], SECOND_CASE["recorded"]) if row}
        reasons = [rows[sequence][0]["reason"] for sequence in WAIT]
        self.assertEqual(set(reasons), {quest_summon_answer.LURE_WALK_REASON, "quest-strategy:hold"})
        self.assertGreaterEqual(reasons.count(quest_summon_answer.LURE_WALK_REASON), 5)
        cells = {(raw["player"]["y"], raw["player"]["x"]) for _row, raw in (rows[s] for s in WAIT)}
        self.assertEqual(cells, {(29, 40), (29, 41), (29, 42)})
        ants = {(monster["y"], monster["x"]) for _row, raw in (rows[s] for s in WAIT)
                for monster in (*raw["visible_monsters"], *raw["detected_monsters"]) if monster["race_id"] == FIRE_ANT}
        self.assertLessEqual(ants, {(y, x) for y in range(25, 28) for x in range(53, 55)})
        self.assertIsNone(SECOND_CASE["recorded"][-1])   # the stop's board


class TheLureWaitLeftToThePlanTest(unittest.TestCase):

    def test_no_wait_and_the_pack_not_closed_on(self):
        # Owner 2026-11-25 (b)-1 changes this pin: it was 「every step toward the pack」 (7ad573ec7b).
        assert_left_to_the_plan(self, drive_second(), WAIT)


# -- the third process (restart 13:15:05, main 5d2d334da): the pack that hides ------------------------
#
# Stopped by the livelock guard at 13:18:15.  The members left were 巨大火アリ (race 548: FRIENDS,
# ANIMAL, no spell, speed -10) on the open floor by the tree columns [24..27,51..55].  An animal pack
# hides from a player at full HP and SP (monster-sweep-grid.cpp HidingMoveGridDecider: the open grids
# round the player, less 2 in a room and 2 for no spell, below 8 x (HP + SP) / (max HP + max SP),
# asked while it sees him or is within MAX_PLAYER_SIGHT / 2), so it never comes.  The lure held 200
# boards for one (decisions 1487-1686), then walked to where it was last seen and the sweep to where
# it last saw one, in turn (1696-1725).  The one verdict (quest_summon_answer ``never_comes``): it
# does not come, so it is not waited for; owner 2026-11-25 (b)-1 (only a monster that never leaves
# the water or never moves is closed on to melee): with no shot it is left to the plan
# (``_unreached``), and the lure goes on with the others.
#
# Recorded: tests/fixtures/n1a-537-q33-hiding-pack-1125 (tests/extract_n1a_537_q33_hiding_pack_1125_fixture.py;
# DECLARED CONSTRUCTED there: the two restarts).  The policy decides the boards from decision 1080.

THIRD = Path(__file__).with_name("fixtures") / "n1a-537-q33-hiding-pack-1125"
THIRD_CASE = json.loads(lzma.decompress((THIRD / "boards.json.xz").read_bytes()))
CYCLE = range(1696, 1726)


def drive_third():
    """``drive_pack`` of the third process."""
    return drive_pack(THIRD, THIRD_CASE)


def drive_pack(fixture, case):
    """{sequence: (snapshot, reason, key, the dry cells beside the 巨大火アリ known, the dry ground,
    the race of the member lured, the 巨大火アリ members left to the plan)} of a fixture's boards
    decided in order."""
    deciding = restore_checkpoint_bytes(HengbotPolicy, lzma.decompress((fixture / "policy.pkl.xz").read_bytes()))
    out = {}
    for raw, row in zip(case["boards"], case["recorded"]):
        snapshot = parse_snapshot(copy.deepcopy(raw), deciding._monrace_knowledge)
        key = str(deciding.choose_key(snapshot))
        navigator = deciding._quest_navigators.get(33)
        ground = (frozenset() if navigator is None else frozenset(
            cell for cell, kind in quest_plan_base._terrain_of(navigator, snapshot, water=False).items()
            if kind in {"floor", "passage"}))
        beside = {Position(m.position.y + dy, m.position.x + dx)
                  for m in (*snapshot.visible_monsters, *snapshot.detected_monsters) if m.race_id == FIRE_ANT
                  for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (m.position.y + dy, m.position.x + dx) in ground}
        if row is not None:
            group = {} if navigator is None else navigator.summon_group
            target = None if navigator is None else group.get(navigator.summon_target, (None,))[0]
            left = frozenset() if navigator is None else frozenset(
                index for index in navigator.summon_unreached if group.get(index, (None,))[0] == FIRE_ANT)
            out[row["sequence"]] = (snapshot, deciding.last_reason, key, beside, ground, target, left)
        deciding.confirm_key_posted(key)
    return out


class TheHidingPackRecordingTest(unittest.TestCase):

    def test_the_lure_and_the_sweep_walk_in_turn(self):
        rows = {row["sequence"]: (row, raw) for raw, row in zip(THIRD_CASE["boards"], THIRD_CASE["recorded"]) if row}
        reasons = [rows[sequence][0]["reason"] for sequence in CYCLE]
        self.assertEqual(set(reasons), {quest_summon_answer.LURE_WALK_REASON, "quest-strategy:sweep-walk"})
        self.assertGreaterEqual(reasons.count("quest-strategy:sweep-walk"), 6)
        self.assertEqual([rows[sequence][0]["reason"] for sequence in range(1487, 1687)],
                         ["quest-strategy:hold"] * 200)
        self.assertIsNone(THIRD_CASE["recorded"][-1])   # the stop's board

    def test_the_fire_ant_is_a_pack_that_hides(self):
        deciding = restore_checkpoint_bytes(HengbotPolicy, lzma.decompress((THIRD / "policy.pkl.xz").read_bytes()))
        flags = set(deciding._monrace_knowledge[FIRE_ANT].flags)
        self.assertLessEqual({"FRIENDS", "ANIMAL"}, flags)
        self.assertFalse({"PASS_WALL", "KILL_WALL", "CAN_FLY"} & flags)


class TheHidingPackLeftToThePlanTest(unittest.TestCase):

    def test_no_wait_nor_sweep_and_the_pack_not_closed_on(self):
        # Owner 2026-11-25 (b)-1 changes this pin: it was 「every step toward the pack」 (7ad573ec7b).
        answers = drive_third()
        assert_left_to_the_plan(self, answers, CYCLE)
        # The pack that hides is left to the plan (no shot: no bolts).
        self.assertTrue(any(answers[sequence][6] for sequence in CYCLE))


def assert_left_to_the_plan(test, answers, sequences):
    """No hold and no sweep walk on ``sequences`` (the livelock's two sides), no 巨大火アリ lured, and
    no step onto the cells beside one (owner 2026-11-25 (b)-1: a pack that hides is not closed on to
    melee)."""
    reasons = {answers[sequence][1] for sequence in sequences}
    test.assertNotIn("quest-strategy:sweep-walk", reasons)
    test.assertNotIn("quest-strategy:hold", reasons)
    test.assertNotIn(FIRE_ANT, {answers[sequence][5] for sequence in sequences})
    for sequence in sequences:
        snapshot, reason, key, beside, _ground, _target, _left = answers[sequence]
        if key not in STEPS or not beside:
            continue
        dy, dx = STEPS[key]
        here = snapshot.player.position
        test.assertNotIn(Position(here.y + dy, here.x + dx), beside, (sequence, reason, key))


# -- n1-b life-418 (Magic-Eater Lv44, 2026-11-25 13:32:21, main 5d2d334da): the pocket of trees ------
#
# A levitating Magic-Eater was put on [20,42] (decision 6338), a dark pit between two tree columns.
# The plans' walks cross only the walked ground (quest_exposure ``_WALKABLE_KINDS``), so no walk led
# out: every member of the group was left as no walk reaches it, the 巨大火アリ were shot as they came
# into view and held for in between (126 holds), and the sweep stopped by name
# (quest:blocked:sweep-nothing-comes, 6595).  The game lets him walk out (TREE has MOVE, DARK_PIT
# CAN_FLY for a levitating player): the walk leaves the pocket over them when no other walk leads
# (quest_plan_base ``_pocket_ground``), and the plan goes on.
#
# Recorded: tests/fixtures/n1b-418-q33-blocked-1125 (tests/extract_n1b_418_q33_blocked_1125_fixture.py):
# the arrival policy replayed by the live code over the floor's boards up to decision 6300, and the
# boards from it to the stop (with the one skill-list answer among them).

POCKET = Path(__file__).with_name("fixtures") / "n1b-418-q33-blocked-1125"
POCKET_CASE = json.loads(lzma.decompress((POCKET / "boards.json.xz").read_bytes()))
IN_POCKET = range(6345, 6596)


def drive_pocket():
    """{sequence: (cell, reason, key)} of n1-b life-418's boards decided in order."""
    deciding = restore_checkpoint_bytes(HengbotPolicy, lzma.decompress((POCKET / "policy.pkl.xz").read_bytes()))
    out = {}
    for raw, row in zip(POCKET_CASE["boards"], POCKET_CASE["recorded"]):
        if raw.get("type") == "knowledge":
            if getattr(deciding, "_skill_exp_request_inflight", False):
                deciding.consume_skill_knowledge(raw)
            continue
        snapshot = parse_snapshot(copy.deepcopy(raw), deciding._monrace_knowledge)
        key = str(deciding.choose_key(snapshot))
        if row is not None:
            out[row["sequence"]] = ((snapshot.player.position.y, snapshot.player.position.x),
                                    deciding.last_reason, key)
        deciding.confirm_key_posted(key)
    return out


class ThePocketRecordingTest(unittest.TestCase):

    def test_held_in_the_pocket_until_the_named_stop(self):
        rows = {row["sequence"]: (row, raw) for raw, row in zip(POCKET_CASE["boards"], POCKET_CASE["recorded"]) if row}
        self.assertEqual(rows[6595][0]["reason"], "quest:blocked:sweep-nothing-comes")
        self.assertEqual({(raw["player"]["y"], raw["player"]["x"]) for _row, raw in (rows[s] for s in IN_POCKET)},
                         {(20, 42)})
        reasons = [rows[s][0]["reason"] for s in IN_POCKET]
        self.assertGreaterEqual(reasons.count("quest-strategy:hold"), 100)
        self.assertTrue(any(raw["player"]["ability_sources"]["levitation"]["equipment"]
                            or raw["player"]["ability_sources"]["levitation"]["temporary"]
                            or raw["player"]["ability_sources"]["levitation"]["permanent"]
                            for _row, raw in (rows[6595],)))


class ThePocketLeftTest(unittest.TestCase):

    def test_the_walk_leaves_the_pocket(self):
        answers = drive_pocket()
        in_pocket = [answers[s] for s in IN_POCKET]
        self.assertNotIn("quest:blocked:sweep-nothing-comes", {reason for _cell, reason, _key in in_pocket})
        self.assertNotIn("quest-strategy:hold", {reason for _cell, reason, _key in in_pocket})
        self.assertGreaterEqual(sum(1 for _cell, _reason, key in in_pocket if key in STEPS), 100)


# -- n1-b life-418, the second process (restart 15:07:38, main c56d737dd): the turning walk ----------
#
# Stopped by the livelock guard at 15:08:59.  The member lured was Fang (race 55: RAND_25,
# BASH_DOOR, ANIMAL) in its locked room [24..26,1..4].  Read afresh from each cell it stepped to, it
# came on one board and not on the next (quest_summon_answer ``never_comes``), and the lure walked
# toward its pulling cells and toward the cells beside it in turn: [25,11] <-> [26,12], then
# [26,12] <-> [26,11] (decisions 653-662).  The verdict is kept for the member while it stays in
# the group (navigator ``summon_comes``), so one walk holds for it.
#
# Recorded: tests/fixtures/n1b-418-q33-lure-target-1125
# (tests/extract_n1b_418_q33_lure_target_1125_fixture.py; DECLARED CONSTRUCTED there: the restart).
# The policy decides the boards from decision 600.

TURNING = Path(__file__).with_name("fixtures") / "n1b-418-q33-lure-target-1125"
TURNING_CASE = json.loads(lzma.decompress((TURNING / "boards.json.xz").read_bytes()))
TURNS = range(653, 663)
FANG = 70


def drive_turning():
    """{sequence: (cell, reason, key, the lured member)} of the boards decided in order."""
    deciding = restore_checkpoint_bytes(HengbotPolicy, lzma.decompress((TURNING / "policy.pkl.xz").read_bytes()))
    out = {}
    for raw, row in zip(TURNING_CASE["boards"], TURNING_CASE["recorded"]):
        if raw.get("type") == "knowledge":
            if getattr(deciding, "_skill_exp_request_inflight", False):
                deciding.consume_skill_knowledge(raw)
            continue
        snapshot = parse_snapshot(copy.deepcopy(raw), deciding._monrace_knowledge)
        key = str(deciding.choose_key(snapshot))
        if row is not None:
            out[row["sequence"]] = ((snapshot.player.position.y, snapshot.player.position.x),
                                    deciding.last_reason, key, deciding._quest_navigators[33].summon_target)
        deciding.confirm_key_posted(key)
    return out


class TheTurningWalkRecordingTest(unittest.TestCase):

    def test_the_lure_walks_back_and_forth(self):
        rows = {row["sequence"]: (row, raw) for raw, row in zip(TURNING_CASE["boards"], TURNING_CASE["recorded"]) if row}
        self.assertEqual({rows[s][0]["reason"] for s in TURNS}, {quest_summon_answer.LURE_WALK_REASON})
        self.assertEqual({(raw["player"]["y"], raw["player"]["x"]) for _row, raw in (rows[s] for s in TURNS)},
                         {(25, 10), (25, 11), (26, 12), (26, 11)})
        keys = [rows[s][0]["key"] for s in TURNS]
        self.assertTrue({"3", "7"} <= set(keys) and {"4", "6"} <= set(keys))


class TheTurningWalkHeldTest(unittest.TestCase):

    def test_one_walk_toward_the_member(self):
        answers = drive_turning()
        self.assertEqual({answers[s][3] for s in TURNS}, {FANG})
        self.assertEqual({answers[s][1] for s in TURNS}, {quest_summon_answer.LURE_WALK_REASON})
        # Fang's room is west, behind its door [25,5]: every step goes west, none back east.
        self.assertEqual({answers[s][2] for s in TURNS} & {"3", "6", "9"}, set())


if __name__ == "__main__":
    unittest.main()
