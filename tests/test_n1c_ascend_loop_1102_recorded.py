"""n1-c Magic-Eater, Angband 5F (life-099, 2026-11-02 00:34-00:39): the
arrival room of a shaft is sealed by a secret door, and the bot went back up
instead of searching for it (owner: 「n1-cが3Fで進展のない動きをしばらく繰り返している」).

Recorded (tests/fixtures/n1c-ascend-loop-1102.json.gz, see
tests/extract_n1c_ascend_loop_1102.py): eight times the 3F down shaft (29,102)
led to 5F (5,46), an up shaft in a lit room that the board shows walled on
every side.  The arrival cast detect-evil, detect-traps and map-area; the
mapping showed the downstairs (6,25) beyond the room's west wall (a secret
door maps as granite, spells-floor.cpp map_area), and the next decision was
stuck:ascend back to the saved 3F, where 200 decisions of descent cooldown
later the same shaft was taken again.

The secret-exit search ran only on a floor with no known downstairs.  A
mapped downstairs that no route reaches is not a way down: the search now
runs unless a known downstairs is reachable.

Through the public choose_key and the production executor port.
DECLARED CONSTRUCTED: the floor's map-area use is seeded at the arrival cell
from the recorded me-power row (as tests/test_mapped_rooms_1101_recorded.py);
the skill knowledge the live process held is given; the unaware scroll (slot
k) is settled as unidentifiable, as the live process had it (no
identify:pack-pressure in the 2606 recorded decisions with 20 of 23 slots used).
"""
import tests  # noqa: F401 -- isolate live runtime files
from recorded_junk_scope import install_past_destroyed_junk

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot import mapped_area, me_powers
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from tests import test_me_mining_death_recorded as mining

FIXTURE = Path(__file__).parent / "fixtures" / "n1c-ascend-loop-1102.json.gz"
ARRIVAL = Position(5, 46)
MAPPED_DOWNSTAIRS = Position(6, 25)
MAPPING = ("staff", me_powers.SV_STAFF_MAPPING)


def _harness(name):
    return getattr(mining.MagicEaterMiningDeathRecordedTest, name)


_undo_past_junk = None


def setUpModule():
    # Owner 2026-11-02: these boards carry junk the first safe decision destroys.
    global _undo_past_junk
    _undo_past_junk = install_past_destroyed_junk()


def tearDownModule():
    _undo_past_junk()


class N1cAscendLoopRecordedTest(mining.harness.ProductionHarness):
    choose = _harness("choose")
    post = _harness("post")

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        facts = dict(cls.data["dungeon"], flags=frozenset(cls.data["dungeon"]["flags"]))
        cls.dungeons = {facts["id"]: DungeonInfo(**facts)}

    def test_sealed_arrival_room_searches_instead_of_ascending(self):
        rows = self.data["rows"]
        ascents = [row for row in rows if row["reason"] == "stuck:ascend"]
        self.assertEqual(len(ascents), 8)
        for row in ascents:
            previous = rows[rows.index(row) - 1]
            self.assertEqual(previous["reason"], "me-power:new-floor:map-area")
            self.assertEqual((row["floor"]["level"], row["position"]), (5, {"y": 5, "x": 46}))

        raw = copy.deepcopy(self.data["board"])
        policy = HengbotPolicy(dungeon_knowledge=dict(self.dungeons))
        board = parse_snapshot(raw, policy._monrace_knowledge)
        policy.prime(board)
        memory = me_powers.FloorMemory(board.floor_key, raw["turn"])
        memory.uses.append(me_powers.Use(MAPPING, MAPPING, "new-floor", ARRIVAL, raw["turn"] - 1))
        policy._me_power_floor = memory
        unaware = next(item for item in board.inventory if item.slot == "k")
        policy._unidentifiable_sigs.add(policy._item_signature(unaware))
        self.assertEqual(board.player.position, ARRIVAL)
        self.assertTrue(board.grid_at(ARRIVAL).has_up_stairs)
        self.assertTrue(board.grid_at(MAPPED_DOWNSTAIRS).has_down_stairs)

        key = self.choose(policy, raw)
        self.assertNotEqual(policy.last_reason, "stuck:ascend", key)
        self.assertIn(policy.last_reason, {"search", "seek-secret-wall"}, key)
        self.assertIsNotNone(mapped_area.current(policy))
        self.assertFalse(policy._known_downstairs_reachable(board))
        game, _ = self.post(policy, raw, key, [])
        self.assertEqual(game.accepted, [key])


if __name__ == "__main__":
    unittest.main()
