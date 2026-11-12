"""Quest 25 on n1-c life-200 (2026-11-12 12:01-12:03): the owner's three decisions of the same day, recorded.

The death: from [10,1] a Teleportation (decision 18165) dropped the player in the north-east, the
walk back west along row 1 went toward the spectral tyrannosaur (T1 from [1,4] on 18187); after
the restarts four more Teleportations (process 2 decisions 5 and 28, process 3 decisions 6 and 8)
landed in the great hall or in the south-middle room ([13,11], process 2 decision 29), from which
the walk back to the post went out by the hall door [10,11] (40, 41), a quylthulg threw the
player east into the hounds, and it died there.

Owner 2026-11-12 (strategy/quests/QUEST_25.jsonc ``hall_no_teleport``, ``sealed_rooms``,
``never_toward_all_phases``):
(1) 「大広間が危険な段階3まではテレポートが危険なので禁止。回復とテレポートアウェイで対処する。」,
    段階3 「ラアルとクイルスルグを倒すまで」 (battle phases 0-5): quest_no_teleport.q25_hall_forbids,
    quest_plan_base._below_line's Teleport Away then the potion.
(2) the sealed rooms (quest25_sealed_room): wait 100 actions intercepting, then by room.
(3) 「召喚された強敵や T1 の敵の方へは歩かない」 in every phase (quest25_battle._shunned).

Recorded: the boards of tests/fixtures/n1c-200-q25-warning-restart-1112.json.gz (all three
processes; tests/extract_n1c_200_q25_warning_restart_1112_fixture.py), decided by a fresh policy
per process through the public ``choose_key`` (the helpers of
tests/test_n1c_200_q25_warning_restart_1112_recorded.py).

DECLARED: the first process is replayed from decision 18062 (the first board its state ring
holds), not from its own start.  The boards carry no magic-eater lists; where the Teleport Away
answer is read, the lists are DECLARED CONSTRUCTED from the character's dump at death
(``DEVICE_LISTS``: the absorbed Teleport Away wand 56 and rod 1, Stone to Mud 99, the Thunder,
Acid and Ice Ball wands 21, 8 and 9).  The rooms' later steps are CONSTRUCTED from the recorded
board of process 2 decision 30 (the south-middle room, nothing in view) with the player put in
each room at full HP, the room's wait counted as given, and, where said, the door taken as open.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import pickle
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import me_capability, quest25_battle as battle, quest25_sealed_room as sealed_room
from hengbot import quest_no_teleport, quest_plan_base
from hengbot.model import (Position, SV_ROD_TELEPORT_AWAY, SV_WAND_STONE_TO_MUD,
                           SV_WAND_TELEPORT_AWAY, parse_snapshot)
from tests import test_n1c_200_q25_warning_restart_1112_recorded as recorded

CASE = recorded.CASE
TELEPORTS = (("first", 18165), ("second", 5), ("second", 28), ("third", 6), ("third", 8))
ROOM_LANDED = 29                 # process 2: on [13,11] after the Teleportation of 28
ROOM_WALKS = (30, 31, 40)        # the walks back to the post (live '7', '8', 'o9')
TOWARD_T1 = ("first", 18187)     # [1,9], the spectral tyrannosaur T1 on [1,4]: live '4'
TOWARD_PACK = ("third", 4)       # [6,29], the hounds: live '8' onto [5,29]
HEAL = "quest-strategy:heal"
AWAY = quest_plan_base.AWAY_REASON + ":absorbed-power"


def _wand(sval, count):
    return {"name": me_capability.names("wand", sval)[0], "fail": 5, "success": 95,
            "current": count, "max": count}


DEVICE_LISTS = {
    "wand": (0, (_wand(SV_WAND_TELEPORT_AWAY, 56), _wand(SV_WAND_STONE_TO_MUD, 99),
                 _wand(21, 21), _wand(20, 8), _wand(23, 9))),
    "rod": (0, ({"name": me_capability.names("rod", SV_ROD_TELEPORT_AWAY)[0], "fail": 5,
                 "success": 95, "charging": 0, "max": 1},)),
}


def replay(*, lists=False, wanted=(), patches=()):
    """{(part, sequence): (key, reason)} of every board, each process by its own fresh policy;
    ``wanted`` boards are decided twice on a copy (the second answer under ``(part, seq, 2)``)."""
    answers = {}
    with TemporaryDirectory() as directory:
        record = Path(directory) / "warning-cells.json"
        with _patched(patches):
            for part in ("first", "second", "third"):
                boards = CASE[part]["boards"]
                policy = recorded.new_policy(boards[0], record)
                if lists:
                    policy._me_device_lists = dict(DEVICE_LISTS)
                for raw, row in zip(boards, CASE[part]["recorded"]):
                    if (part, row["sequence"]) in wanted:
                        twice = pickle.loads(pickle.dumps(policy))
                        recorded.decide(twice, raw)
                        answers[part, row["sequence"], 2] = recorded.decide(twice, raw)[1:]
                    answers[part, row["sequence"]] = recorded.decide(policy, raw)[1:]
    return answers


class _patched:
    def __init__(self, patches):
        self.patches = [patch.object(*spec) for spec in patches]

    def __enter__(self):
        for each in self.patches:
            each.start()

    def __exit__(self, *_exc):
        for each in reversed(self.patches):
            each.stop()


RULE_1_OFF = ((quest_no_teleport, "q25_hall_forbids", lambda *_args: False),)
RULE_2_OFF = ((sealed_room, "key", lambda _ctx: None),)
RULE_3_OFF = ((battle, "_shunned", lambda _ctx: []),)
ANSWERS = {}


def answers():
    if not ANSWERS:
        ANSWERS.update(replay())
    return ANSWERS


class TheRecordingTest(unittest.TestCase):

    def test_the_teleports_and_the_walks(self):
        rows = {(part, row["sequence"]): (row["key"], row["reason"])
                for part in ("first", "second", "third") for row in CASE[part]["recorded"]}
        for board in TELEPORTS:
            self.assertEqual(rows[board], ("rh", "quest-strategy:sweep-teleport"), board)
        self.assertEqual([rows["second", seq][0] for seq in ROOM_WALKS], ["7", "8", "o9"])
        self.assertEqual(rows[TOWARD_T1], ("4", "quest25:walk"))
        self.assertEqual(rows[TOWARD_PACK], ("8", "quest25:walk"))
        landed = CASE["second"]["boards"][ROOM_LANDED]
        self.assertEqual((landed["player"]["y"], landed["player"]["x"]), (13, 11))


class NoTeleportTest(unittest.TestCase):
    """(1): no Teleportation through the tome's phase; Teleport Away, then the potion."""

    def test_every_recorded_teleport_is_answered_by_the_potion(self):
        for board in TELEPORTS:
            key, reason = answers()[board]
            self.assertEqual(reason, HEAL, board)
            self.assertFalse(key.startswith("r"), (board, key))

    def test_with_teleport_away_it_is_aimed_first_then_the_potion(self):
        found = replay(lists=True, wanted=TELEPORTS)
        for part, sequence in TELEPORTS:
            key, reason = found[part, sequence]
            self.assertEqual(reason, AWAY, (part, sequence))
            self.assertTrue(key.startswith("mC"), (part, sequence, key))   # the absorbed rod first
            self.assertEqual(found[part, sequence, 2][1], HEAL, (part, sequence))

    def test_control_without_the_rule_the_teleports_come_back(self):
        found = replay(patches=RULE_1_OFF)
        for board in TELEPORTS:
            self.assertEqual(found[board], ("rh", "quest-strategy:sweep-teleport"), board)

    def test_the_rule_ends_with_the_tome(self):
        raw = CASE["second"]["boards"][ROOM_LANDED + 1]
        with TemporaryDirectory() as directory:
            policy = recorded.new_policy(raw, Path(directory) / "warning-cells.json")
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            recorded.decide(policy, raw)
        fight = policy._quest_navigators[25].phase_battle
        for phase in range(len(battle.PHASES)):
            fight.phase = phase
            forbids = quest_no_teleport.q25_hall_forbids(policy, snapshot)
            self.assertEqual(forbids, phase <= battle.phase_index("tome"), battle.PHASES[phase].name)
            self.assertEqual(policy._find_teleport_scroll(snapshot) is None, forbids)
            self.assertEqual(policy._find_phase_scroll(snapshot) is None, forbids)


class SealedRoomTest(unittest.TestCase):
    """(2): the south-middle room the Teleportation of 28 dropped the player in."""

    def test_the_room_waits_instead_of_walking_out(self):
        for sequence in ROOM_WALKS:
            key, reason = answers()["second", sequence]
            self.assertNotIn(key, {"7", "8", "o9"}, sequence)
        self.assertEqual(answers()["second", 30], ("5", "quest-strategy:hold"))
        self.assertEqual(answers()["second", 31], ("5", "quest-strategy:hold"))
        # On [11,10], beside the door, the wait steps back to a post off the door.
        self.assertEqual(answers()["second", 40], ("2", "quest25:walk"))

    def test_control_without_the_room_the_walk_goes_out(self):
        found = replay(patches=RULE_2_OFF)
        self.assertEqual(found["second", 40][0], "o9")

    @staticmethod
    def _room(name, cell, actions, step="wait", *, door_open=False, hp_full=True):
        """DECLARED CONSTRUCTED from process 2 decision 30 (see the module note)."""
        boards = CASE["second"]["boards"]
        with TemporaryDirectory() as directory:
            policy = recorded.new_policy(boards[0], Path(directory) / "warning-cells.json")
            for raw in boards[:30]:
                recorded.decide(policy, raw)
            policy._me_device_lists = dict(DEVICE_LISTS)
            fight = policy._quest_navigators[25].phase_battle
            fight.room = (name, actions, step, None, 0)
            fight.browsed = frozenset({"wand", "rod", "staff"})   # the lists just read
            raw = copy.deepcopy(boards[30])
            raw["messages"] = []
            raw["player"]["y"], raw["player"]["x"] = cell
            if hp_full:
                raw["player"]["hp"] = raw["player"]["max_hp"]
            opened = (lambda _ctx, _door: True) if door_open else sealed_room._door_open
            with patch.object(sealed_room, "_door_open", opened):
                _snapshot, key, reason = recorded.decide(policy, raw)
            return key, reason, fight.room

    def test_the_wait_holds_until_the_hundredth_action(self):
        for name, cell in (("left", (12, 6)), ("centre", (13, 11)), ("right", (13, 16))):
            key, reason, room = self._room(name, cell, 98)
            self.assertEqual((key, reason, room[1:3]), ("5", "quest-strategy:hold", (99, "wait")), name)

    def test_left_and_centre_melt_the_door_from_a_summon_safe_cell(self):
        for name, cell, door in (("left", (12, 6), "@10,6"), ("centre", (13, 11), "@10,11")):
            key, reason, room = self._room(name, cell, 100)
            self.assertEqual(room[2], "clear", name)
            self.assertEqual(reason, battle.MELT_REASON, name)
            self.assertTrue(key.endswith(door), (name, key))

    def test_left_and_centre_ball_the_quylthulg_from_a_summon_safe_cell(self):
        for name, cell, centre in (("left", (12, 6), "@8,7"), ("centre", (13, 11), "@7,10")):
            key, reason, room = self._room(name, cell, 100, door_open=True)
            self.assertEqual((reason, room[2]), ("ranged:magic-eater-device", "clear"), name)
            self.assertTrue(key.startswith("mB") and key.endswith(centre), (name, key))

    def test_right_rests_full_first(self):
        key, reason, room = self._room("right", (13, 16), 100, hp_full=False)
        self.assertEqual((key, reason, room[2]), ("R&\r", battle.FULL_HP_REASON, "prepare"))

    def test_right_walks_to_the_cell_with_a_line_to_the_pen_and_shoots(self):
        key, reason, room = self._room("right", (13, 16), 100, door_open=True)
        self.assertEqual((key, reason, room[2]), ("4", battle.WALK_REASON, "ipsissimus"))
        key, reason, room = self._room("right", (13, 14), 100, "ipsissimus", door_open=True)
        self.assertEqual(reason, battle.SHOT_REASON)   # the strongest ranged attack at [7,17]
        self.assertIn("*p999888t", key)


class SealedRoomOutOfTheRoomTest(unittest.TestCase):
    """The pen's step of 左・中央 goes on out of the room (the walk to [7,1] crosses the hall)."""

    def test_the_pen_step_is_kept_in_the_hall(self):
        key, reason, room = SealedRoomTest._room("centre", (9, 11), 100, "ipsissimus")
        self.assertEqual(room[0:3], ("centre", 101, "ipsissimus"))
        self.assertIsNotNone(key)

    def test_a_wait_left_by_a_throw_is_forgotten(self):
        _key, _reason, room = SealedRoomTest._room("centre", (9, 11), 50, "wait")
        self.assertIsNone(room)


class NeverTowardTest(unittest.TestCase):
    """(3): no walk toward a T1 mover or a pack, in phase 0 too; the hold and the fight instead."""

    def test_the_stage_0_walk_stops_short_of_the_tyrannosaur(self):
        key, reason = answers()[TOWARD_T1]
        self.assertNotEqual(key, "4")
        self.assertNotEqual(reason, battle.WALK_REASON)

    def test_the_restart_does_not_walk_into_the_hounds(self):
        key, reason = answers()[TOWARD_PACK]
        self.assertNotEqual(key[:1], "8")
        self.assertNotEqual(reason, battle.WALK_REASON)

    def test_control_without_the_rule_both_walk(self):
        found = replay(patches=RULE_3_OFF)
        self.assertEqual(found[TOWARD_T1], ("4", battle.WALK_REASON))


if __name__ == "__main__":
    unittest.main()
