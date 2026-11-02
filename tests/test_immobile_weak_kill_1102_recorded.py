"""immobile-weak-kill-1102: the recorded n1-c life-107 Labyrinth 18F eye (2026-11-02).

n1-c life-107 (Magic-Eater, Lv26, 366 HP, build bot-ddd9d4258) on 迷宮18階,
the Labyrinth's bottom floor where its guardian lives, turns 1801340-1801897
(20:02:15-20:02:21): a 発光アイ (race 80, NEVER_MOVE, GAZE:LOSE_STR, 18 HP)
sits at (6,7), the corner of the one-cell corridor the player walks up.  Its
stat-drain ring (immobile_threat_memory, survival2-1101) takes the corridor
out of every route.  From the corridor cells the eye was in view but never
projectable, so the ranged ladder fired three blind ``*t`` shots from each
cell (ranged:fire-target, RANGED_TARGET_FAILURE_LIMIT) and exploration turned
back; the floor visit went round this corner from 19:56 to 20:08.

Owner 2026-11-02: 「弱い動かない敵まで避けると不具合が大きそうなので遠距離攻撃、
召喚魔法がなければ普通に倒して」 and 「遠距離で安全に倒せるなら倒す方を優先する」.
The eye is now walked to (8,6), two cells short of the ring, where the bolt
path reaches it, and shot (one expected arrow kills it); without ammunition
it is still avoided (the survival2 stat-drain ring is kept, an owner
question); with neither a ranged attack, a summon nor a draining or lethal
touch it is an ordinary enemy (no ring, no retreat).

Fixture: tests/fixtures/immobile-weak-kill-20261102.json.gz
(tests/extract_immobile_weak_kill_1102_fixture.py).  Every decision is the
public ``choose_key``; posted keys go through the production executor port
(test_me_nokey_1031_recorded.PostedKey).
DECLARED RECONSTRUCTED: the ``_me_staff_sequence`` and the floor's
device-power uses come from the 19:55:03 policy-state of the same floor visit.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path

from hengbot import immobile_threat_memory, me_powers
from hengbot import me_staff_sequence as sequence
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.model import Position
from hengbot.policy_constants import DIRECTION_KEYS
from tests import test_me_nokey_1031_recorded as nokey
from tests import test_me_staff_loops_1031_recorded as loops
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen


FIXTURE = Path(__file__).with_name("fixtures") / "immobile-weak-kill-20261102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
EYE = 80
EYE_CELL = Position(6, 7)
SHOOTING_CELL = Position(8, 6)
FIRST_SIGHT = 1801400  # (15,6): recorded ranged:fire-target fn*t5
STEPS = {key: offset for offset, key in DIRECTION_KEYS.items()}
ARROWS = 17
# The floor's latest Detect Evil (turn 1763801) is 37,539 game turns old, so
# the first board searches for the Labyrinth guardian again (hunt-redetect-1102,
# 「1,000ゲームターン」).  DECLARED CONSTRUCTED: the cast's prompts
# (cmd-magiceat.cpp) and its completion on the following recorded board.
HUNT_SEARCH = "me-power:hunt-target-unseen:detect-evil"
HUNT_SEARCH_SCREENS = (prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
                       power_screen("staff", [("p", "邪悪存在感知", 14, 14, 5)]))


def recorded():
    return {row["turn"]: (row["reason"], row["key"]) for row in CASE["decisions"]}


def new_policy(boards, monraces=None):
    policy = loops.new_policy(dict(CASE, boards=boards), CASE["skill"],
                              monraces=CASE["monraces"] if monraces is None else monraces)
    sequence.state(policy).absorbed = {
        int(key) if key.isdigit() else key: count
        for key, count in CASE["sequence"]["absorbed"].items()}
    policy._dungeon_knowledge = {
        int(key): DungeonInfo(**dict(row, flags=frozenset(row["flags"])))
        for key, row in CASE["dungeons"].items()}
    floor = CASE["power_floor"]
    memory = me_powers.FloorMemory(tuple(floor["floor"]), floor["turn"])
    memory.uses.extend(
        me_powers.Use(tuple(use["served"]), tuple(use["used"]), use["trigger"],
                      Position(*use["position"]), use["turn"], use["reason"], use["key"])
        for use in floor["uses"])
    policy._me_power_floor = memory
    return policy


def without_arrows(raw):
    raw = copy.deepcopy(raw)
    raw["inventory"] = [item for item in raw["inventory"] if item.get("tval") != ARROWS]
    return raw


def weak_eye_races():
    """DECLARED CONSTRUCTED: the eye with no spells and two plain 10d10 hits --
    a touch the engagement gate counts as material (200 against 366 HP), not
    lethal in one turn, and no stat drain."""
    races = copy.deepcopy(CASE["monraces"])
    eye = races[str(EYE)]
    eye["abilities"] = []
    eye["blows"] = [{"method": "HIT", "effect": "HURT", "dice_num": 10, "dice_sides": 10}] * 2
    eye["max_melee_damage"] = 200
    eye["spell_frequency"] = 0
    return races


class ImmobileWeakKillRecordedTest(nokey.PostedKey):
    def walk(self, policy, boards, limit=10):
        """Posted keys from FIRST_SIGHT; DECLARED CONSTRUCTED: each following
        board is the FIRST_SIGHT board with the player moved by the step."""
        index = [raw["turn"] for raw in boards].index(FIRST_SIGHT)
        completed = None
        for raw in boards[:index]:
            if completed is not None:
                raw = dict(raw, _completed_operation_owner=completed)
            key = loops.decide(policy, raw)
            completed = None
            if policy.last_reason == HUNT_SEARCH:
                self.post(policy, raw, key, HUNT_SEARCH_SCREENS)
                completed = HUNT_SEARCH
            else:
                self.post(policy, raw, key)
            policy.confirm_key_posted(key)
        raw = copy.deepcopy(boards[index])
        rows = []
        for _ in range(limit):
            key = loops.decide(policy, raw)
            here = Position(raw["player"]["y"], raw["player"]["x"])
            rows.append((here, policy.last_reason, key))
            self.post(policy, raw, key)
            policy.confirm_key_posted(key)
            if key not in STEPS:
                break
            dy, dx = STEPS[key]
            if Position(here.y + dy, here.x + dx) == EYE_CELL:
                break  # a melee blow at the eye
            raw = copy.deepcopy(raw)
            raw["turn"] += 10
            raw["messages"] = []
            raw["player"]["y"] += dy
            raw["player"]["x"] += dx
        return rows

    def test_recorded_rows_fired_blind_and_turned_back(self):
        rows = recorded()
        self.assertEqual(rows[FIRST_SIGHT], ("ranged:fire-target", "fn*t5\x1b"))
        self.assertEqual(rows[1801509], ("explore", "7"))
        (eye,) = [row for row in CASE["boards"][[raw["turn"] for raw in CASE["boards"]]
                                               .index(FIRST_SIGHT)]["visible_monsters"]]
        self.assertEqual((eye["race_id"], eye["y"], eye["x"]), (EYE, 6, 7))

    def test_walks_to_the_shooting_cell_and_shoots_the_eye(self):
        policy = new_policy(CASE["boards"])
        rows = self.walk(policy, CASE["boards"])
        ring = immobile_threat_memory.route_cells(policy)
        self.assertIn(EYE_CELL, ring)  # the survival2 ring itself is kept
        here, reason, key = rows[-1]
        self.assertEqual((here, reason, key), (SHOOTING_CELL, "ranged:fire-target", "fn*t5\x1b"))
        self.assertTrue(all(reason == "immobile-threat:approach-to-shoot"
                            for _here, reason, _key in rows[:-1]), rows)
        self.assertFalse(ring & {here for here, _reason, _key in rows})

    def test_without_arrows_the_draining_eye_is_still_avoided(self):
        boards = [without_arrows(raw) for raw in CASE["boards"]]
        policy = new_policy(boards)
        rows = self.walk(policy, boards, limit=1)
        self.assertNotEqual(rows[0][1], "immobile-threat:approach-to-shoot")
        self.assertIn(EYE_CELL, immobile_threat_memory.route_cells(policy))

    def test_a_weak_never_moving_monster_is_an_ordinary_enemy(self):
        boards = [without_arrows(raw) for raw in CASE["boards"]]
        policy = new_policy(boards, weak_eye_races())
        rows = self.walk(policy, boards, limit=12)
        # No ring, no retreat: hunted up the corridor and struck in melee.
        self.assertEqual(immobile_threat_memory.route_cells(policy), frozenset())
        (eye,) = immobile_threat_memory.remembered(policy)
        self.assertFalse(immobile_threat_memory.is_avoidable_immobile(policy, eye))
        self.assertEqual(rows[-1], (Position(7, 6), "melee", "9"))
        self.assertFalse({reason for _here, reason, _key in rows}
                         & {"threat:avoid-engagement", "immobile-threat:step-out"}, rows)


if __name__ == "__main__":
    import unittest
    unittest.main()
