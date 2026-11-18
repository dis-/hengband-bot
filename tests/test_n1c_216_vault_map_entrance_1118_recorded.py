"""n1-c life-216, Castle 64F (2026-11-17, the "01:22" scene): sensed loot in a vault whose outside
the map does not know.

Owner 2026-11-18, asked whether the melt into a walled pocket (owner 2026-11-13 「価値に関係なく溶かす」,
sealed_loot) should melt through grids the map does not know: 「周辺感知があれば使用して入口を探す。
なければ諦める。」  The item detection of turn 3719474 showed an amulet of the Magi at (38,18) and
eight more items in a vault at (26,4)-(49,27) whose ring and outer walls the map did not know.  The
melt's pockets are walled by known walls only, so none was found and nothing was done for them:
the visit went on to the down stair.  Now sealed_loot walks to the reached grid nearest the loot
and casts the absorbed 周辺感知 there, once an enclosure a floor visit; without a means the loot is
given up as before.

Recorded: tests/fixtures/n1c-216-vault-map-entrance-1118.jsonl.gz
(tests/extract_n1c_216_vault_map_entrance_1118_fixture.py), the 23 boards from the detection to
turn 3719559, where nothing hostile is seen or sensed.  They are replayed in a fresh policy with
the life's skill list and absorbed power lists, as test_n1c_216_deep_loot_leftover_1117_recorded
does.  A replay of the whole visit from its first board gives the same enclosure on this board.
DECLARED CONSTRUCTED: the absorbed power lists are the 2026-11-17 15:50 town-arrival checkpoint's
at full counts (the visit's own were not recorded; 周辺感知 is absorbed there as a staff and as a
rod); the replayed boards' absorbed-power casts are not asked (``me_powers.power_key`` None while
replaying, as in the 11-17 test); the walk to the grid nearest the loot moves the player on the
last board one step a key (the record went on toward the stair); the list without 周辺感知 takes
both of its rows out.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

from hengbot import area_mapping, me_powers, sealed_loot
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.model import Position, game_distance, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import DIRECTION_DELTAS
from tests.support import recorded


FIXTURES = Path(__file__).with_name("fixtures")
FIXTURE = FIXTURES / "n1c-216-vault-map-entrance-1118.jsonl.gz"
FIXTURE_SHA256 = "d6c8fde62b9c89aa1dff39e82f104b2a3dfb160c39c99008b76ab51eb2faaddb"
LISTS_FIXTURE = FIXTURES / "n1c-216-deep-loot-leftover-1117.jsonl.gz"
SKILL_FIXTURE = FIXTURES / "n1c-loot-rules-1113.jsonl.gz"
AMULET = Position(38, 18)
MAP_NAME = "周辺感知"
MAP_CAST = "me-power:loot-enclosure:map-area"
WALK_LIMIT = 40


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
BOARDS = [row["board"] for row in _rows(FIXTURE)]
LISTS = next(row["lists"] for row in _rows(LISTS_FIXTURE) if row["role"] == "me-lists")
with gzip.open(SKILL_FIXTURE, "rt", encoding="utf-8") as _stream:
    SKILL = next(json.loads(line)["board"] for line in _stream if '"skill-knowledge"' in line)
MONRACE = load_monrace_knowledge(recorded.EDIT / "MonraceDefinitions.jsonc")
COSTS = load_baseitem_costs(recorded.EDIT / "BaseitemDefinitions.jsonc")
NO_MAP_LISTS = {kind: (turn, [row for row in rows if row["name"] != MAP_NAME])
                for kind, (turn, rows) in LISTS.items()}


class VaultMapEntrance1118Test(unittest.TestCase):
    def replay(self, lists=LISTS):
        policy = HengbotPolicy(monrace_knowledge=MONRACE, baseitem_costs=COSTS)
        policy.consume_skill_knowledge(SKILL)
        policy._skill_exp_request_key = lambda snapshot: None
        self.lists = lists
        snapshot = None
        with mock.patch.object(me_powers, "power_key", lambda *args, **kwargs: None):
            for raw in BOARDS:
                self.set_lists(policy)
                snapshot = parse_snapshot(copy.deepcopy(raw), MONRACE)
                key = policy.choose_key(snapshot)
                if key:
                    policy.confirm_key_posted(key)
        return policy, snapshot

    def set_lists(self, policy):
        policy._me_device_lists = {kind: (turn, tuple(rows)) for kind, (turn, rows) in self.lists.items()}

    def walk_to_cast(self, policy):
        """Ask sealed_loot on the last board, moving the player along each walk step (constructed),
        until it asks for something else."""
        raw = copy.deepcopy(BOARDS[-1])
        for _ in range(WALK_LIMIT):
            snapshot = parse_snapshot(copy.deepcopy(raw), MONRACE)
            self.set_lists(policy)
            key = sealed_loot.key(policy, snapshot)
            if policy.last_reason != sealed_loot.MAP_REASON:
                return snapshot, key
            self.assertIn(key, DIRECTION_DELTAS)
            dy, dx = DIRECTION_DELTAS[key]
            raw["player"]["y"] += dy
            raw["player"]["x"] += dx
        self.fail("the walk did not end")

    def test_the_vault_is_no_walled_pocket(self):
        """Why the 11-13 melt did nothing: the amulet is loot no walk reaches, its surroundings hold
        grids the map does not know, and no pocket walled by known walls holds it."""
        policy, snapshot = self.replay()
        reach = sealed_loot._reach(policy, snapshot)
        self.assertIn(AMULET, policy._loot_candidates(snapshot))
        self.assertNotIn(AMULET, reach)
        self.assertEqual(sealed_loot.pockets(policy, snapshot, reach), [])
        self.assertTrue(sealed_loot._safe(snapshot))
        found = sealed_loot.enclosures(policy, snapshot, reach)
        self.assertTrue(any(AMULET in loot for loot in found))

    def test_with_mapping_the_player_walks_near_and_maps_once(self):
        policy, snapshot = self.replay()
        self.assertTrue(area_mapping.means_held(policy, snapshot))
        start = snapshot.player.position
        first = sealed_loot.key(policy, snapshot)
        self.assertEqual(policy.last_reason, sealed_loot.MAP_REASON, first)
        snapshot, key = self.walk_to_cast(policy)
        self.assertEqual(policy.last_reason, MAP_CAST, key)
        self.assertTrue(key.startswith("m"), key)
        reach = sealed_loot._reach(policy, snapshot)
        here = snapshot.player.position
        self.assertLess(game_distance(here, AMULET), game_distance(start, AMULET))
        self.assertEqual(game_distance(here, AMULET), min(game_distance(cell, AMULET) for cell in reach))
        # Once an enclosure a floor visit: asked again, nothing is mapped and nothing walks.
        policy.last_reason = None
        self.assertIsNone(sealed_loot.key(policy, snapshot))
        self.assertIsNone(policy.last_reason)

    def test_without_mapping_the_loot_is_given_up(self):
        """Declared constructed: 周辺感知 taken out of the absorbed staff and rod lists."""
        policy, snapshot = self.replay(NO_MAP_LISTS)
        self.assertFalse(area_mapping.means_held(policy, snapshot))
        policy.last_reason = None
        self.assertIsNone(sealed_loot.key(policy, snapshot))
        self.assertIsNone(policy.last_reason)


if __name__ == "__main__":
    unittest.main()
