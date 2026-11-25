"""Quest 33 on n1-b life-419 (2026-11-26 08:07:18-08:09:23): the sweep stopped by name with the third
Bokrug asleep in the west room.

The chain (Zombie Magic-Eater Lv41, HP 896, telepathy; sweep-kills: the three Its, the three Dagons and
two of the three Bokrugs):

 * 08:08 (turn 3866785, [6,12], after the fight with the Grendels): the telepathy and the detection
   showed the third ボクラグ (race 489: vision 20, speed +0) asleep at [20,7], in the west room of the
   lower floor.
 * quest_detect_remaining walked to the next cast's cell [15,39] (the Queens, GOOD, are no Detect Evil's)
   and cast Detect Evil there: the Gachapins in their room.
 * No stand of 段1 had anything coming (quest_wait_placement), 段2's lure waits for every Bokrug dead
   (``lure_approach.after_races_dead`` [393, 595, 489]) and 段3's stands for the Queens: a full pass found
   no stop to walk or hold and the sweep stopped by name on [15,39], quest:blocked:sweep-nothing-comes
   (the level-30 first stop halted the bot).  The round before had fought, so the walk was not over,
   and a tracked summoner lived, so the patrol (kill_all_patrol) was not asked either.

The rule (owner 2026-11-13 「全滅クエストで作戦を終えても終わらない時は周回して探す・感知があれば感知して
探す」): the stops having nothing to do is the plan's walk ended.  With no tracked summoner alive the
patrol takes the floor (quest_room_sweep ``_walk_over``, the same verdict as a round that found
nothing); with one alive the plan's own walk goes to the known members of the races the lure phase
does not own (``_hunt_key``: the Bokrug, not the Gachapins nor the Queens), ahead of the walk to the
next cast's cell that drew the player away from it.

Recorded: tests/fixtures/n1b-419-q33-nothing-comes-1126 (tests/extract_n1b_419_q33_nothing_comes_1126_fixture.py):
the same process's town-arrival checkpoint (08:06:26), the records the process left at the stop
(quest-plan.pkl, sweep-kills.json, map-memory.pkl), the stop board, the detection board and the last
~f skill list.

DECLARED CONSTRUCTED: the policy is restored as a restart restores it (the arrival checkpoint with the
records of the stop set to be read on its first board, the skill list given), which is how the halted
bot resumes.  The restart's first decision on the stop board casts the powered Rod of Detection (the
arrival's rod list shows it ready); the stop board is then decided again as the board after the cast
(the same turn: its result pending).  ``WalkTest`` moves the player along the keys and shows the
Bokrug where the game would (telepathy within 20, in view within the light of 3); ``PatrolTest``
credits every tracked race's placements dead, the plan record's pass with nothing to do read against
those kills (the 段3 stands would be walked otherwise), and the tracked races the stop board shows by
telepathy taken off it.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import collections
import copy
import dataclasses
import json
import lzma
import pickle
import tempfile
import unittest
from pathlib import Path

from hengbot import kill_all_patrol, quest_detect_remaining, quest_room_sweep
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-419-q33-nothing-comes-1126"
CASE = json.loads(lzma.decompress((FIXTURE / "boards.json.xz").read_bytes()).decode("utf-8", "surrogateescape"))
QUEST = 33
BOKRUG = 489
BOKRUG_CELL = (20, 7)
TRACKED = (581, 393, 441, 489, 595)
STEPS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
DETECTION = "me-power:quest-remaining-unseen:"


def restarted(scratch: Path, kills=None) -> HengbotPolicy:
    """The arrival policy with the stop's records to restore on its first board (a restart).  With
    ``kills`` added, the plan record's pass with nothing to do is read against them (``PatrolTest``)."""
    deciding = restore_checkpoint_bytes(HengbotPolicy, lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes()))
    (scratch / "map-memory.pkl").write_bytes(lzma.decompress((FIXTURE / "map-memory.pkl.xz").read_bytes()))
    held = pickle.loads(lzma.decompress((FIXTURE / "quest-plan.pkl.xz").read_bytes()))
    record = copy.deepcopy(CASE["sweep_kills"])
    record["kills"].extend(kills or ())
    if kills:
        navigator = held["navigators"][QUEST]
        navigator.wait_idle = (tuple(sorted(collections.Counter(race for race, _turn in record["kills"]).items())),
                               navigator.wait_spent)
    (scratch / "quest-plan.pkl").write_bytes(pickle.dumps(held))
    (scratch / "sweep-kills.json").write_text(json.dumps(record), encoding="utf-8")
    deciding._quest_plan_record_path = scratch / "quest-plan.pkl"
    deciding._map_memory_record_path = scratch / "map-memory.pkl"
    deciding._sweep_kill_record_path = scratch / "sweep-kills.json"
    for mark in ("_quest_plan_record_read", "_sweep_kill_record_read", "_map_memory_record_read"):
        deciding.__dict__.pop(mark, None)
    deciding._skill_exp_request_inflight = True
    deciding.consume_skill_knowledge(copy.deepcopy(CASE["knowledge"]))
    return deciding


def decide(deciding, raw):
    snapshot = parse_snapshot(copy.deepcopy(raw), deciding._monrace_knowledge)
    key = str(deciding.choose_key(snapshot))
    deciding.confirm_key_posted(key)
    return snapshot, key, deciding.last_reason


def walk_length(deciding, snapshot, start: tuple[int, int]) -> int:
    """The plan's own walk from ``start`` to a cell beside the Bokrug."""
    navigator = deciding._quest_navigators[QUEST]
    plan = deciding.approved_quest_strategy(QUEST).engagement_plan["room_sweep"]
    moved = dataclasses.replace(snapshot, player=dataclasses.replace(snapshot.player, position=Position(*start)))
    goals = {Position(BOKRUG_CELL[0] + dy, BOKRUG_CELL[1] + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx}
    path = quest_room_sweep._path(deciding, navigator, plan, moved, goals)
    return len(path) if path else 999


def bokrug(raw):
    return [monster for monster in (*raw["visible_monsters"], *raw["detected_monsters"]) if monster["race_id"] == BOKRUG]


class TheRecordingTest(unittest.TestCase):

    def test_the_stop_came_with_the_third_bokrug_known(self):
        last = CASE["recorded"][-1]
        self.assertEqual((last["turn"], last["position"], last["reason"]),
                         (3867119, [15, 39], quest_room_sweep.NOTHING_COMES_REASON))
        races = [race for race, _turn in CASE["sweep_kills"]["kills"]]
        self.assertEqual((races.count(393), races.count(595), races.count(BOKRUG)), (3, 3, 2))
        (seen,) = bokrug(CASE["detection_board"])
        self.assertEqual(((seen["y"], seen["x"]), seen["asleep"]), (BOKRUG_CELL, True))
        reasons = [row["reason"] for row in CASE["recorded"]]
        self.assertIn(quest_detect_remaining.WALK_REASON, reasons)
        quest = next(quest for quest in CASE["stop_board"]["progress"]["quests"] if quest["id"] == QUEST)
        self.assertEqual(quest["status"], 1)   # taken, not completed


class RestartTest(unittest.TestCase):

    def test_the_stops_with_nothing_to_do_hunt_the_bokrug(self):
        with tempfile.TemporaryDirectory() as scratch:
            deciding = restarted(Path(scratch))
            _snapshot, _key, reason = decide(deciding, CASE["stop_board"])
            self.assertTrue(reason.startswith(DETECTION), reason)
            snapshot, key, reason = decide(deciding, CASE["stop_board"])
            navigator = deciding._quest_navigators[QUEST]
            self.assertEqual((navigator.sweep_stage, navigator.sweep_round), (7, 1))
            self.assertNotEqual(reason, quest_room_sweep.NOTHING_COMES_REASON)
            self.assertEqual(reason, quest_room_sweep.HUNT_REASON)
            dy, dx = STEPS[key]
            here = (snapshot.player.position.y, snapshot.player.position.x)
            self.assertLess(walk_length(deciding, snapshot, (here[0] + dy, here[1] + dx)),
                            walk_length(deciding, snapshot, here))


class WalkTest(unittest.TestCase):

    def test_the_hunt_walks_to_the_bokrug_and_shoots_it(self):
        with tempfile.TemporaryDirectory() as scratch:
            deciding = restarted(Path(scratch))
            raw = copy.deepcopy(CASE["stop_board"])
            (shown,) = bokrug(CASE["detection_board"])
            decide(deciding, raw)   # the restart's detection
            reasons = []
            for step in range(80):
                raw["turn"] = CASE["stop_board"]["turn"] + 10 * step
                raw["messages"] = []
                far = max(abs(raw["player"]["y"] - BOKRUG_CELL[0]), abs(raw["player"]["x"] - BOKRUG_CELL[1]))
                raw["detected_monsters"] = [dict(shown, detected=False, esp=True)] if 3 < far <= 20 else []
                raw["visible_monsters"] = [dict(shown, detected=False, esp=False)] if far <= 3 else []
                _snapshot, key, reason = decide(deciding, raw)
                reasons.append(reason)
                if key not in STEPS:
                    if not reason.startswith(DETECTION):
                        break
                    continue
                dy, dx = STEPS[key]
                raw["player"]["y"] += dy
                raw["player"]["x"] += dx
            self.assertTrue(reasons[-1].startswith("ranged:"), reasons[-1])
            self.assertIn(f"@{BOKRUG_CELL[0]},{BOKRUG_CELL[1]}", key)
            self.assertLessEqual(set(reasons[:-1]), {quest_room_sweep.HUNT_REASON}
                                 | {reason for reason in reasons if reason.startswith(DETECTION)})


class PatrolTest(unittest.TestCase):

    def test_with_every_tracked_summoner_dead_the_patrol_takes_the_floor(self):
        dead = [[race, 3867000] for race, count in ((BOKRUG, 1), (441, 3), (581, 3)) for _ in range(count)]
        with tempfile.TemporaryDirectory() as scratch:
            deciding = restarted(Path(scratch), dead)
            raw = copy.deepcopy(CASE["stop_board"])
            for monsters in (raw["visible_monsters"], raw["detected_monsters"]):
                monsters[:] = [monster for monster in monsters if monster["race_id"] not in TRACKED]
            _snapshot, _key, reason = decide(deciding, raw)
            self.assertNotEqual(reason, quest_room_sweep.NOTHING_COMES_REASON)
            self.assertTrue(reason.startswith(kill_all_patrol.REASON), reason)


if __name__ == "__main__":
    unittest.main()
