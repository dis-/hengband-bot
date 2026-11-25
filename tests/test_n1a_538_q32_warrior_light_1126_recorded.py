"""Quest 32 on n1-a life-538 (2026-11-26): the summoners summoned from a dark room, and were shot when walked to.

Zombie warrior Lv30 (HP ~600 of 728).  閾に棲む者 (263) x6 stand in the west middle room [8,1]-[13,3], dark;
the player's light radius is 2.  Between turns 1312077 and 1314967 the floor printed 27 summons by
何か, the player read 14 of 15 Scrolls of Teleportation (summons:leave-teleport 9: the owner's
2026-11-04 rule 2 「見えない召喚が2回で離れる」), and one 閾に棲む者 of six died.  The strategy's four
Scrolls of Light (one per ``light_areas`` row) were read only by the Magic-Eater's shot.

Owner 2026-11-26:
 1. 「戦士も光の巻物で部屋を照らす」: the warrior lights the room with the plan's scroll, so the summoner
    is an enemy in view; 見えた召喚者には「見えない召喚が2回で離れる」を当てない.
 2. 「期待値の高い方（殴る）」: the shot and the walk to the summoner and its blows, compared per 10 game
    turns with the walk's time in it; the higher is taken.

Recorded: tests/fixtures/n1a-538-q32-warrior-light-1126 (tests/extract_n1a_538_q32_warrior_light_1126_fixture.py):
three windows of the floor's boards with their recorded decisions.  The arrival checkpoint and the stop's
plan record are the n1a-538-q32-hold-sweep-1126 fixture's (the same capture).

DECLARED CONSTRUCTED: the plan record of the stop is restored on the arrival checkpoint as a restart
restores it, its turn put back to the window's first board (as test_n1a_538_q32_hold_sweep_1126_recorded),
and the policy is given the repository's strategy files (the pickled policy holds the recording day's,
as a deploy loads them).  The boards are the recorded ones: after the light the fixed policy reads, the
recorded boards still show the room dark (the game's answer to the read is not in the recording), so
the spared leave is also checked on the recorded board with the summoner in view and the unseen run
the floor had counted put back in the summons memory.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import pickle
import tempfile
import unittest
from pathlib import Path

from hengbot import quest_strategies, quest_summoner_light, summon_response
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import SV_SCROLL_LIGHT, TVAL_SCROLL, Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.quest_strategies import load_quest_strategies

FIXTURES = Path(__file__).with_name("fixtures")
FIXTURE = FIXTURES / "n1a-538-q32-warrior-light-1126"
CHECKPOINT = FIXTURES / "n1a-538-q32-hold-sweep-1126"
STRATEGIES = Path(__file__).resolve().parents[1] / "strategy" / "quests"
CASE = json.loads(lzma.decompress((FIXTURE / "boards.json.xz").read_bytes()))["windows"]
QUEST = 32
SUMMONER = 263       # 閾に棲む者
WEST_ROOM = "西の中部屋"
LEAVE = "summons:leave-teleport"
STEPS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def policy(first_turn: int, scratch: Path) -> HengbotPolicy:
    """The arrival checkpoint, the stop's plan record to restore on the first board, today's strategies."""
    deciding = restore_checkpoint_bytes(HengbotPolicy, lzma.decompress((CHECKPOINT / "policy.pkl.xz").read_bytes()))
    held = pickle.loads(lzma.decompress((CHECKPOINT / "quest-plan.pkl.xz").read_bytes()))
    held["turn"] = first_turn
    record = scratch / "quest-plan.pkl"
    record.write_bytes(pickle.dumps(held))
    deciding._quest_plan_record_path = record
    deciding._quest_plan_record_read = False
    deciding._quest_plan_record = None
    deciding._character_dump_path = scratch / "bot-test.txt"
    deciding._quest_strategies = load_quest_strategies(STRATEGIES)
    return deciding


def drive(deciding, boards):
    out = []
    for raw in boards:
        snapshot = parse_snapshot(copy.deepcopy(raw), deciding._monrace_knowledge)
        key = str(deciding.choose_key(snapshot))
        out.append((snapshot, key, deciding.last_reason))
        deciding.confirm_key_posted(key)
    return out


def window(name):
    return CASE[name]["boards"], CASE[name]["recorded"]


def unseen_summons(raw) -> int:
    return sum(not summon.seen for message in raw["messages"] for summon in summon_response.summons_of(message))


class TheRecordingTest(unittest.TestCase):

    def test_the_summons_came_from_the_dark_and_the_second_was_left_by_teleportation(self):
        boards, recorded = window("unseen")
        by_turn = {row["turn"]: row for row in recorded}
        summoned = [raw["turn"] for raw in boards if unseen_summons(raw)]
        self.assertEqual(summoned[:2], [1313114, 1313131])
        self.assertEqual(by_turn[1313114]["reason"], "quest-strategy:melee")
        self.assertEqual(by_turn[1313131]["reason"], LEAVE)
        # Nothing of the summoner's race was in view, and no Light was read.
        self.assertFalse(any(monster["race_id"] == SUMMONER for raw in boards for monster in raw["visible_monsters"]))
        self.assertFalse(any("light" in row["reason"] for row in recorded))

    def test_the_summoner_in_view_was_shot_with_the_plain_arrows(self):
        boards, recorded = window("walk")
        shots = [(raw, row) for raw, row in zip(boards, recorded) if row["reason"].startswith("summoner:ranged-kill")]
        self.assertEqual(len(shots), 3)
        for raw, _row in shots:
            self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (15, 6))
            self.assertEqual([(m["race_id"], m["y"], m["x"]) for m in raw["visible_monsters"]
                              if m["race_id"] == SUMMONER], [(SUMMONER, 10, 1)])
        self.assertTrue(any("62/turn" in message for raw, _row in shots for message in raw["messages"]))


class TheLightTest(unittest.TestCase):

    def test_the_first_unseen_summons_reads_the_plans_light_and_the_leave_does_not_follow(self):
        boards, _recorded = window("unseen")
        with tempfile.TemporaryDirectory() as raw:
            deciding = policy(boards[0]["turn"], Path(raw))
            answers = drive(deciding, boards)
            spent = deciding._quest_light_areas_read
        by_turn = {snapshot.turn: (snapshot, key, reason) for snapshot, key, reason in answers}
        snapshot, key, reason = by_turn[1313114]
        self.assertEqual(reason, quest_summoner_light.LIGHT_REASON)
        light, = [item for item in snapshot.inventory if item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_LIGHT]
        self.assertEqual(key, "r" + light.slot)
        self.assertIn(((0, 25, QUEST), WEST_ROOM), spent)
        # One reading: the area is spent, and the second unseen summons starts no leave.
        self.assertEqual([reason for _s, _k, reason in answers].count(quest_summoner_light.LIGHT_REASON), 1)
        self.assertNotEqual(by_turn[1313131][2], LEAVE)
        self.assertNotIn(LEAVE, [reason for _s, _k, reason in answers])


class TheSummonerInViewTest(unittest.TestCase):

    def _board(self, name: str, turn: int, scratch: str):
        boards, _recorded = window(name)
        deciding = policy(boards[0]["turn"], Path(scratch))
        raw, = [raw for raw in boards if raw["turn"] == turn]
        return deciding, raw

    def test_the_leave_is_not_due_while_the_summoner_is_in_view(self):
        with tempfile.TemporaryDirectory() as scratch:
            deciding, raw = self._board("walk", 1314506, scratch)
            drive(deciding, [raw])
            snapshot = parse_snapshot(copy.deepcopy(raw), deciding._monrace_knowledge)
            memory = summon_response._memory(deciding)
            # The floor's run of unseen casts at the player's cell, as the summons memory counts it.
            memory.unseen_run, memory.last_unseen = 2, (memory.decisions, snapshot.player.position)
            self.assertTrue(quest_summoner_light.spares_leave(deciding, snapshot))
            self.assertFalse(summon_response.leave_due(deciding, snapshot))
            hidden = copy.deepcopy(raw)
            hidden["visible_monsters"] = [m for m in hidden["visible_monsters"] if m["race_id"] != SUMMONER]
            dark = parse_snapshot(hidden, deciding._monrace_knowledge)
            self.assertFalse(quest_summoner_light.spares_leave(deciding, dark))
            self.assertTrue(summon_response.leave_due(deciding, dark))

    def test_four_steps_away_the_walk_and_the_blows_beat_the_plain_arrows(self):
        with tempfile.TemporaryDirectory() as scratch:
            deciding, raw = self._board("walk", 1314500, scratch)
            drive(deciding, [raw])
            snapshot = parse_snapshot(copy.deepcopy(raw), deciding._monrace_knowledge)
            summoner, = [m for m in snapshot.visible_monsters if m.race_id == SUMMONER]
            found = quest_summoner_light.figures(deciding, snapshot, summoner)
        self.assertEqual(found["steps"], 4)
        self.assertGreater(found["walk_and_strike"], found["shot"])

    def test_the_summoner_in_view_is_walked_to_not_shot(self):
        boards, _recorded = window("walk")
        with tempfile.TemporaryDirectory() as raw:
            deciding = policy(boards[0]["turn"], Path(raw))
            answers = drive(deciding, boards)
        seen = [(snapshot, key, reason) for snapshot, key, reason in answers
                if any(m.race_id == SUMMONER for m in snapshot.visible_monsters)]
        self.assertEqual(len(seen), 3)
        for snapshot, key, reason in seen:
            self.assertEqual(reason, quest_summoner_light.WALK_REASON, snapshot.turn)
            self.assertIn(key, STEPS)
            dy, dx = STEPS[key]
            here = snapshot.player.position
            there = Position(here.y + dy, here.x + dx)
            # A step no farther from the summoner at [10,1].
            self.assertLessEqual(there.distance_to(Position(10, 1)), here.distance_to(Position(10, 1)))
        # Out of view on the next board, the walk is kept, not handed back to the hold.
        self.assertEqual(answers[-1][2], quest_summoner_light.WALK_REASON)

    def test_six_steps_away_the_shot_is_the_higher_figure_and_is_kept(self):
        boards, recorded = window("shot")
        with tempfile.TemporaryDirectory() as raw:
            deciding = policy(boards[0]["turn"], Path(raw))
            answers = drive(deciding, boards)
            snapshot = answers[2][0]
            summoner = min((m for m in snapshot.visible_monsters if m.race_id == SUMMONER),
                           key=lambda m: m.distance)
            found = quest_summoner_light.figures(deciding, snapshot, summoner)
        self.assertGreater(found["shot"], found["walk_and_strike"] or 0.0)
        shots = [reason for (_s, _k, reason), row in zip(answers, recorded) if row["reason"].startswith("ranged:")]
        self.assertTrue(shots)
        self.assertTrue(all(reason.startswith("ranged:") for reason in shots), shots)


class ThePlanTest(unittest.TestCase):

    def test_quest_32_names_the_west_middle_room_for_its_summoner(self):
        profile = load_quest_strategies(STRATEGIES)[QUEST]
        self.assertEqual(profile.engagement_plan[quest_summoner_light.FIELD], {"race": SUMMONER, "area": WEST_ROOM})

    def test_an_area_not_among_the_light_areas_is_refused(self):
        areas = [{"name": WEST_ROOM, "bounds": [8, 1, 13, 3]}]
        self.assertTrue(quest_summoner_light.valid({"race": SUMMONER, "area": WEST_ROOM}, areas))
        self.assertFalse(quest_summoner_light.valid({"race": SUMMONER, "area": "東の中部屋"}, areas))
        self.assertFalse(quest_summoner_light.valid({"race": 0, "area": WEST_ROOM}, areas))
        self.assertTrue(hasattr(quest_strategies, "quest_summoner_light"))


if __name__ == "__main__":
    unittest.main()
