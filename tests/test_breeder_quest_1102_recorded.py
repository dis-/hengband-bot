"""breeder-quest-1102: a breeder stalemate on a quest floor, by quest type.

Recorded: n1-c life-098 on 鉄獄24階, random quest 41 (RANDOM, target race
1329, never perceived on these boards), 2026-11-02 00:10-00:14
(tests/fixtures/breeder-swarm-20261102.json.gz, the breeder-swarm-1102
fixture).  breeder_stalemate latches the floor after the 20th player action
without a reduction, counted from the first attack (owner 2026-11-07; turn
2199896); the quest exit lock then left the
breakthrough no exit, and the recorded process searched and broke out
beside the growing Software bug swarm.

Owner 2026-11-02 (verbatim): 「20ターンの数え方はそれで良い。　全滅要求の
クエストは達成できないので放棄。ランダムクエストなどターゲット討伐要求の場合は
テレポートで距離を取り、増殖モンスターの近くを避けて続行」 (breeder_quest):

* the target quest reads a Scroll of Teleportation on the first board of the
  latch (turn 2199905: _update_combat_outcome latches after the 20th
  action's decision), keeps the floor, and routes clear of the bite ring of
  every perceived breeder;
* without a Scroll of Teleportation the floor keeps the breakthrough's
  behaviour (here: the random quest's teleport reserve releases the exit
  lock and Recall is read, as before);
* a kill-all quest floor is left by Word of Recall (the quest fails).

Every decision is the public ``choose_key``; posted keys go through the
production executor port (test_breeder_swarm_1102_recorded.PostedSwarmKey;
a read is answered by the game's scroll chooser).
DECLARED RECONSTRUCTED (as in test_breeder_swarm_1102_recorded):
``_fixed_quest_speed_attempted`` is true; the restart boards start latched.
DECLARED CONSTRUCTED: the recorded boards after the teleport still show the
player where the recording had it (the recorded process did not teleport);
the kill-all case is the same boards with the floor's quest switched to
quest 28 (lib/edit/quests/025_HauntedHouse.jsonc: KILL_ALL, PRESET+ONCE, on
the fixed-quest allowlist), TAKEN, and random quest 41 removed; the
no-teleport case removes the Scrolls of Teleportation from the pack.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from unittest import mock

from hengbot import breeder_quest, breeder_stalemate
from hengbot.model import Position
from hengbot.policy_constants import DIRECTION_KEYS, UP_STAIRS_KEY
from tests import test_breeder_swarm_1102_recorded as swarm


CASE = swarm.CASE
QUEST_FLOOR = swarm.QUEST_FLOOR
FLEE_TURN = swarm.FLEE_TURN
RECORDED_WINDOW = 20    # the recorded build's window (owner 2026-11-02/03)
LATCHED_TURN = 2199905  # the first board after the 20th action's decision (the last board)
TARGET_RACE = 1329
KILL_ALL_QUEST = 28
SV_TELEPORT, SV_RECALL, TVAL_SCROLL = 9, 11, 70
LEAVING = ("breeder-breakthrough:recall", "breeder-breakthrough:ascend",
           "breeder-breakthrough:seek-", "ranged:")


def kill_all(raw):
    """DECLARED CONSTRUCTED: the floor's quest is the allowlisted, unapproved quest 28, typed kill-all here."""
    raw = copy.deepcopy(raw)
    raw["floor"]["quest_id"] = KILL_ALL_QUEST
    quests = [quest for quest in raw["progress"]["quests"] if quest["id"] != 41]
    quests.append({"fixed": True, "id": KILL_ALL_QUEST, "level": 24,
                   "name": "unapproved quest", "status": 1, "type": 6})
    raw["progress"]["quests"] = quests
    return raw


def without_teleport(raw):
    """DECLARED CONSTRUCTED: no Scroll of Teleportation in the pack."""
    raw = copy.deepcopy(raw)
    raw["inventory"] = [item for item in raw["inventory"]
                        if (item["tval"], item["sval"]) != (TVAL_SCROLL, SV_TELEPORT)]
    return raw


def slot(raw, sval):
    return next(item["slot"] for item in raw["inventory"]
                if (item["tval"], item["sval"]) == (TVAL_SCROLL, sval))


def bite_ring(raw):
    return {
        Position(monster["y"] + dy, monster["x"] + dx)
        for monster in raw["visible_monsters"] + raw.get("detected_monsters", [])
        if monster["race_id"] == swarm.SOFTWARE_BUG
        for dy, dx in (*DIRECTION_KEYS, (0, 0))
    }


class BreederQuestRecordedTest(swarm.PostedSwarmKey):
    def setUp(self):
        super().setUp()
        # DECLARED WALL: the response to a latch is the subject here, so the swarm boards latch
        # under the recorded build's 20-attack window (owner 2026-11-09 made it 100; under 100
        # these boards stay in one window, test_breeder_swarm_1102_recorded).
        patcher = mock.patch.object(breeder_stalemate, "FLEE_AFTER_PLAYER_ACTIONS", RECORDED_WINDOW)
        patcher.start()
        self.addCleanup(patcher.stop)

    def drive_engagement(self, boards):
        policy = swarm.new_policy(boards)
        rows = {raw["turn"]: (key, reason) for raw, key, reason in self.drive(policy, boards)}
        return policy, rows

    def test_recorded_floor_is_a_target_quest_with_teleports(self):
        raw = CASE["engage"][0]
        self.assertEqual(raw["floor"]["quest_id"], 41)
        quest = next(q for q in raw["progress"]["quests"] if q["id"] == 41)
        self.assertEqual((quest["type"], quest["status"], quest["r_idx"]), (7, 1, TARGET_RACE))
        teleports = next(item for item in raw["inventory"]
                         if (item["tval"], item["sval"]) == (TVAL_SCROLL, SV_TELEPORT))
        self.assertEqual(teleports["count"], 7)
        self.assertFalse(any(monster["race_id"] == TARGET_RACE
                             for board in CASE["engage"] + CASE["restart"] + CASE["swarm"]
                             for monster in board["visible_monsters"]
                             + board.get("detected_monsters", [])))
        rows = swarm.recorded()
        self.assertFalse(any(rows[raw["turn"]][0].endswith("teleport")
                             for raw in CASE["engage"] + CASE["swarm"]))

    def test_target_quest_teleports_once_and_keeps_the_floor(self):
        policy, rows = self.drive_engagement(CASE["engage"])
        for turn, (key, reason) in rows.items():
            if turn < LATCHED_TURN:
                self.assertIn(reason, {"melee", "ranged:fire"}, turn)
            elif turn == LATCHED_TURN:
                self.assertEqual((key, reason), ("r" + slot(CASE["engage"][0], SV_TELEPORT),
                                                 breeder_quest.TELEPORT_REASON))
            else:
                # The 20-action window restarted: no second read, no exit.
                self.assertNotEqual(reason, breeder_quest.TELEPORT_REASON, turn)
                self.assertFalse(reason.startswith(LEAVING), (turn, reason))
                self.assertNotEqual(key, UP_STAIRS_KEY, turn)
        self.assertEqual(policy._breeder_breakthrough_floor, QUEST_FLOOR)
        self.assertFalse(policy._returning_to_town)

    def test_target_quest_routes_clear_of_the_breeders(self):
        boards = [raw for raw in CASE["restart"] if raw["turn"] >= swarm.RESTART_SKILL_TURN]
        policy = swarm.new_policy(boards)
        policy._breeder_breakthrough_floor = QUEST_FLOOR
        offsets = {key: offset for offset, key in DIRECTION_KEYS.items()}
        walked = 0
        for raw in boards:
            rows = self.drive(policy, [raw])
            _, key, reason = rows[0]
            ring = bite_ring(raw)
            self.assertTrue(ring)
            self.assertLessEqual(ring & set(swarm.board(policy, raw).grids),
                                 policy._engagement_avoid_cells, raw["turn"])
            self.assertFalse(reason.startswith(LEAVING), (raw["turn"], reason))
            if key in offsets:
                dy, dx = offsets[key]
                step = Position(raw["player"]["y"] + dy, raw["player"]["x"] + dx)
                self.assertNotIn(step, ring, (raw["turn"], key, reason))
                walked += 1
        self.assertGreater(walked, 0)
        self.assertFalse(policy._returning_to_town)

    def test_without_teleportation_the_reserve_rule_still_leaves(self):
        # Unchanged behaviour: with fewer than five Scrolls of Teleportation
        # the random quest's exit lock is released (random_quest_reserve,
        # owner 2026-11-01 「テレポートが残り少なくなったら帰る」) and the
        # breakthrough reads Recall, as before this change.
        boards = [without_teleport(raw) for raw in CASE["engage"]]
        policy, rows = self.drive_engagement(boards)
        self.assertEqual(rows[LATCHED_TURN],
                         ("r" + slot(boards[0], SV_RECALL), "breeder-breakthrough:recall"))
        self.assertTrue(policy._returning_to_town)

    def test_kill_all_quest_floor_is_abandoned_by_recall(self):
        boards = [kill_all(raw) for raw in CASE["engage"]]
        policy, rows = self.drive_engagement(boards)
        self.assertEqual(rows[LATCHED_TURN],
                         ("r" + slot(boards[0], SV_RECALL), "breeder-breakthrough:recall"))
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._active_fixed_quest_id(swarm.board(policy, boards[0])),
                         KILL_ALL_QUEST)
        # The stairs answer 「本当にこの階を去りますか？」 there too.
        latched = swarm.board(policy, boards[-1])
        self.assertTrue(policy.quest_leave_confirmation_owned(latched, UP_STAIRS_KEY))


if __name__ == "__main__":
    unittest.main()
