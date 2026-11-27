"""Drop hunting (supervisor 2026-11-28, drop_hunt): a good dropper whose drop can be the Ring of
Speed is killed while the speed row is unmet, not erased by *Destruction*.

Recorded (tests/extract_drop_hunt_1128_fixture.py), n1-b life-419 (Magic-Eater CL50, permanent
speed +17, Angband 80F under the unmet +25 row, depth_gap_gear ``speed_row``):

* 2026-11-28 05:52, turn 14477853 at (32,33): ソーラー (race 943, L64, DROP_GOOD, a summoner)
  almost dead (270 of 3000) 2 off; me_powers' THREAT occasion read it unbeatable (the 2026-11-09
  summoner leave, threat_tiers ``_worsens_leave`` through ``leave_due``) and the absorbed
  *Destruction* was cast before the Teleport Away ('mA3',
  'emergency:destruction:before-teleport-away:absorbed-power').  Alone from contact it is T3,
  one action, 166 incoming against HP 1019 less the reserve 166: a hunt target.
* 04:22, turn 14221566 at the warp-demon floor: ナイトウォーカー (race 768, L59, DROP_GOOD)
  wounded 2 off, *Destruction* cast ('mA3').  Alone it dies in 6 actions taking 609 (HP 1111,
  reserve 149): tests 4-5 pass, but L59 is under the level line 140 - 80 = 60.
* 03:57, turn 14151005: 『アトラク・ナクア』 4 off after a loss of 422 (HP 706): the emergency
  ladder's lethal reading (the observed loss three times reaches the HP) cast *Destruction*.

The boards are replayed through ``choose_key`` as recorded, one decision a board, each completed
as the executor would (``_completed_operation_owner`` the previous reason), from the first board
of the window; the asked board is decided by the code under test.

DECLARED CONSTRUCTED:
* the absorbed-power lists (``_me_device_lists``) are the same life's checkpoint 20261128-050851
  (tests/fixtures/loot-before-destruction-1128/me-device-lists.json.xz);
* test (b) meets the speed row by patching depth_gap_gear ``speed_row`` to None (the board has
  no such kit);
* test (e) is the Solar board after the kill: the monster removed and an unaware ring (tval 45)
  put on its cell as the found item it would drop, with the detected monster 10 off as the
  hostile a non-urgent *Destruction* would leave;
* the revert of the level line in test (c) patches ``drop_hunt.level_line`` to 0.
"""
import tests  # noqa: F401 -- isolate live runtime files

import contextlib
import copy
import io
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import depth_gap_gear, destruction_use, drop_hunt, hunt_items, threat_tiers
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "drop-hunt-1128"
LISTS = Path(__file__).with_name("fixtures") / "loot-before-destruction-1128" / "me-device-lists.json.xz"
SOLAR, NIGHTWALKER, ATLACH = 943, 768, 809
DESTRUCTION_KEY = "mA3"


def _boards(name):
    lines = lzma.decompress((FIXTURE / name).read_bytes()).decode("utf-8")
    return [json.loads(line) for line in lines.splitlines() if line.strip()]


class LevelLineTest(unittest.TestCase):

    def test_the_level_line_is_the_games_kind_level_reaching_the_ring_depth(self):
        # monster-death.cpp:389 object_level = (dun_level + race level) / 2; floor-object.cpp
        # get_base_floor adds 10 (AM_GOOD) or 15 (AM_GREAT); the Ring of Speed's allocation
        # depth is 80 (BaseitemDefinitions id 136).
        for depth in range(50, 101):
            for great, boost in ((False, 10), (True, 15)):
                lowest = next(level for level in range(0, 200)
                              if (depth + level) // 2 + boost >= 80)
                self.assertEqual(drop_hunt.level_line(depth, great), lowest)
        self.assertEqual(drop_hunt.level_line(80, False), 60)
        self.assertEqual(drop_hunt.level_line(90, False), 50)
        self.assertEqual(drop_hunt.level_line(80, True), 50)


class DropHunt1128RecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.lists = json.loads(lzma.decompress(LISTS.read_bytes()).decode("utf-8"))

    def replay(self, name, asked):
        """(policy, the asked raw board completed as the executor would)."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        raws = _boards(name)
        start = parse_snapshot(copy.deepcopy(raws[0]), self.monrace)
        policy.prime(start)
        policy._skill_exp_cache = (0, 0, start.player.level, policy._town_visit_epoch)
        # DECLARED CONSTRUCTED (module docstring): the absorbed-power lists.
        policy._me_device_lists = {kind: (start.turn, tuple(rows))
                                   for kind, (_turn, rows) in self.lists.items()}
        previous, seen = None, set()
        for raw in raws:
            if raw["turn"] in seen:
                continue
            seen.add(raw["turn"])
            raw = copy.deepcopy(raw)
            if previous is not None:
                raw["_completed_operation_sequence"] = len(seen)
                raw["_completed_operation_owner"] = previous
            if raw["turn"] == asked:
                return policy, raw
            _board, key, reason = self.decide(policy, raw)
            previous = reason if key else None
            if key:
                policy.confirm_key_posted(key)
        raise AssertionError(f"board {asked} is not in the fixture")

    def decide(self, policy, raw):
        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        return board, key, policy.last_reason

    @staticmethod
    def shown(board, race):
        return next(monster for monster in board.visible_monsters if monster.race_id == race)

    def test_a_the_almost_dead_solar_is_shot_not_erased(self):
        policy, raw = self.replay("boards-solar.jsonl.xz", 14477853)
        board, key, reason = self.decide(policy, raw)
        solar = self.shown(board, SOLAR)
        self.assertIsNotNone(depth_gap_gear.speed_row(policy, board))
        self.assertEqual((solar.hp, solar.distance), (270, 2))
        self.assertTrue(drop_hunt.race_qualifies(policy, board, solar))
        self.assertEqual(drop_hunt.kill_reading(policy, board, solar), (1, 166, 166))
        self.assertTrue(drop_hunt.target(policy, board, solar))
        self.assertIn(solar.index, threat_tiers.kill_before_leave(policy, board, [solar]))
        self.assertFalse(threat_tiers.leave_due(policy, board, [solar]))
        # The emergency ladder's exposed summoner and a use that waits for no blow yield too;
        # the 11-08 leave's use (``loot`` False) does not.
        self.assertTrue(drop_hunt.covers(policy, board, [solar]))
        leaving = list(board.detected_monsters)
        self.assertTrue(drop_hunt.holds_use(policy, board, leaving, loot=True))
        self.assertFalse(drop_hunt.holds_use(policy, board, leaving, loot=False))
        # Live: 'emergency:destruction:before-teleport-away:absorbed-power' 'mA3'.
        self.assertNotEqual(key, DESTRUCTION_KEY)
        self.assertNotIn("destruction", reason)
        self.assertEqual(reason, "ranged:magic-eater-powerful")

    def test_b_the_same_board_with_the_speed_row_met_erases_as_recorded(self):
        policy, raw = self.replay("boards-solar.jsonl.xz", 14477853)
        # DECLARED CONSTRUCTED (module docstring): the +25 row met.
        with mock.patch.object(depth_gap_gear, "speed_row", return_value=None):
            board, key, reason = self.decide(policy, raw)
            self.assertFalse(drop_hunt.target(policy, board, self.shown(board, SOLAR)))
        self.assertEqual((reason, key),
                         ("emergency:destruction:before-teleport-away:absorbed-power", DESTRUCTION_KEY))

    def test_c_a_good_dropper_under_the_level_line_is_no_target(self):
        policy, raw = self.replay("boards-nightwalker.jsonl.xz", 14221566)
        board, key, reason = self.decide(policy, raw)
        walker = self.shown(board, NIGHTWALKER)
        self.assertEqual(self.monrace[NIGHTWALKER].level, 59)
        self.assertEqual(drop_hunt.level_line(board.dungeon_level, False), 60)
        # Tests 4-5 alone would pass: 6 actions, 609 incoming below HP 1111 less the reserve 149.
        self.assertEqual(drop_hunt.kill_reading(policy, board, walker), (6, 609, 149))
        self.assertTrue(drop_hunt.passes(policy, board, walker))
        self.assertFalse(drop_hunt.race_qualifies(policy, board, walker))
        self.assertFalse(drop_hunt.target(policy, board, walker))
        self.assertEqual((reason, key), ("emergency:destruction:absorbed-power", DESTRUCTION_KEY))

    def test_c_revert_without_the_level_line_the_walker_would_be_hunted(self):
        policy, raw = self.replay("boards-nightwalker.jsonl.xz", 14221566)
        # DECLARED CONSTRUCTED (module docstring): the level line removed.
        with mock.patch.object(drop_hunt, "level_line", return_value=0):
            board, key, reason = self.decide(policy, raw)
            self.assertTrue(drop_hunt.target(policy, board, self.shown(board, NIGHTWALKER)))
        self.assertNotEqual(key, DESTRUCTION_KEY)

    def test_d_the_lethal_board_keeps_the_emergency_destruction(self):
        policy, raw = self.replay("boards-atlach.jsonl.xz", 14151005)
        board, key, reason = self.decide(policy, raw)
        atlach = self.shown(board, ATLACH)
        self.assertEqual(board.player.hp, 706)
        self.assertTrue(drop_hunt.race_qualifies(policy, board, atlach))
        self.assertIsNone(drop_hunt.kill_reading(policy, board, atlach))  # T1 alone
        self.assertFalse(drop_hunt.target(policy, board, atlach))
        self.assertEqual((reason, key), ("emergency:destruction:absorbed-power", DESTRUCTION_KEY))

    def test_e_after_the_kill_the_drop_is_fetched_before_a_non_urgent_destruction(self):
        policy, raw = self.replay("boards-solar.jsonl.xz", 14477853)
        # DECLARED CONSTRUCTED (module docstring): the kill and its drop.
        raw = copy.deepcopy(raw)
        cell = next((m["y"], m["x"]) for m in raw["visible_monsters"] if m["race_id"] == SOLAR)
        raw["visible_monsters"] = [m for m in raw["visible_monsters"] if m["race_id"] != SOLAR]
        grid = raw["grid_map"]
        grid["found_items"].append([cell[0], cell[1], 1, 45])
        grid["found_item_ids"].append([cell[0], cell[1], {}])
        grid["found_item_names"].append([cell[0], cell[1], "指輪"])
        board = policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))
        drop = Position(*cell)
        self.assertIn(drop, hunt_items.hunt_piles(policy, board))
        leaving = list(board.detected_monsters)
        self.assertTrue(destruction_use.usable(policy, board, leaving=leaving))
        with contextlib.redirect_stdout(io.StringIO()):
            answer = destruction_use.loot_then_use(policy, board, leaving)
        self.assertFalse(answer.used)
        self.assertIsNotNone(answer.key)
        self.assertTrue(policy.last_reason.startswith("destruction-loot:"))


if __name__ == "__main__":
    unittest.main()
