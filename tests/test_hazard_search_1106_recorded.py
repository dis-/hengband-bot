"""No wall search on ground that hurts, on n1-a life-492's boards (Orc cave 23F, 11-06 23:55).

The pocket (15,84)/(16,84) opens only through HEAVY_ELECTRICAL_ZONE (terrain 229, about
25 HP a step for this player, who resists electricity and is not immune).  On the zone,
next to unsearched walls, the ladder answered a wall search; damaging_ground.leave_first
turned it into the step back toward the pocket, and the walk out stepped onto the zone
again: loop-detected after cycles of HP 731 -> 546, each replaced search recorded as made.

Recorded: tests/extract_hazard_search_1106_fixture.py, the boards in order (the player
moved as recorded).  The skill-exp cache is DECLARED CONSTRUCTED from the board's level,
as in test_hazard_exit_1104_recorded.  The live walk was stuck:seek-stairs; a chooser
primed on the first board walks the same cells as exploration and reaches the same
searches once its moves oscillate.  The standstill that leave_first replaces is read
through a spy on damaging_ground.step_off_key (it still decides).  The levitating walk is
DECLARED CONSTRUCTED: the recorded boards with temporary levitation set on each.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hengbot import damaging_ground
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import SEARCH_KEY
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "hazard-search-1106.json.gz"
HEAVY_ELECTRICAL_ZONE = 229  # DEEP + ELEC_PUDDLE, lib/edit/TerrainDefinitions.jsonc


class HazardSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def walk(self, *, levitating=False):
        """(the standstill leave_first saw or None, key, reason, board) of each board."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = self.boards[0]
        policy.prime(parse_snapshot(copy.deepcopy(first), self.monrace))
        policy._skill_exp_cache = (0, 0, first["player"]["level"], None)
        seen = []
        step_off = damaging_ground.step_off_key

        def spy(policy_, snapshot, key):
            seen.append(key)
            return step_off(policy_, snapshot, key)

        rows = []
        with patch.object(damaging_ground, "step_off_key", spy):
            for raw in self.boards:
                raw = copy.deepcopy(raw)
                if levitating:
                    raw["player"]["ability_sources"]["levitation"]["temporary"] = True
                board = policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))
                seen.clear()
                key = policy.choose_key(board)
                rows.append((seen[-1] if seen else None, key, policy.last_reason, board))
                if key:
                    policy.confirm_key_posted(key)
        return policy, rows

    def test_no_search_is_chosen_or_counted_on_the_zone(self):
        policy, rows = self.walk()
        on_zone = [row for row in rows if damaging_ground.hurts_here(policy, row[3])]
        self.assertGreaterEqual(len(on_zone), 10)
        # The walls beside the zone cells are the ones the live searches chose.
        self.assertTrue(all(policy._undersearched_walls(row[3].player.position) for row in on_zone))
        self.assertEqual([(row[1], row[2], row[3].player.position)
                          for row in on_zone if row[0] == SEARCH_KEY], [])
        self.assertNotIn(SEARCH_KEY, [row[1] for row in on_zone])
        for row in on_zone:
            position = row[3].player.position
            self.assertEqual(policy._search_counts[(position.y, position.x)], 0, position)

    def test_a_levitating_player_still_does_not_search_on_the_zone(self):
        # HEAVY_ELECTRICAL_ZONE is DEEP: deal_damege_by_feat (hp-mp-processor.cpp) deals a
        # fifth of its damage over it to a levitating player, so it still hurts.
        policy, rows = self.walk(levitating=True)
        self.assertTrue(all("levitation" in row[3].player.abilities for row in rows))
        on_zone = [row for row in rows
                   if row[3].grid_at(row[3].player.position).terrain_id == HEAVY_ELECTRICAL_ZONE]
        self.assertGreaterEqual(len(on_zone), 10)
        self.assertNotIn(SEARCH_KEY, [row[0] for row in on_zone])
        self.assertNotIn(SEARCH_KEY, [row[1] for row in on_zone])
        for row in on_zone:
            position = row[3].player.position
            self.assertEqual(policy._search_counts[(position.y, position.x)], 0, position)

    def test_the_secret_wall_stops_leave_out_ground_that_hurts(self):
        policy, rows = self.walk()
        board = next(row[3] for row in rows if damaging_ground.hurts_here(policy, row[3]))
        policy._claim_target_capture = []
        policy._secret_wall_search_step(board)
        stop = policy._take_claim_target()
        self.assertIsNotNone(stop)
        self.assertFalse(damaging_ground.hurts_at(policy, board, stop), stop)


if __name__ == "__main__":
    unittest.main()
