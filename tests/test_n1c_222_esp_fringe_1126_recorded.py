"""n1-c life-222 2026-11-26 10:15-10:16: the rest slot's hunt and the descent walked back and forth on
Angband 93F until the loop detector stopped the bot (build bot-9b7f2c3b4).

The character (Zombie Magic-Eater Lv50, HP 818-876 of 1078, telepathy) was not on the finale's
expedition: the preparation phase stood ``idle`` (the second 100F battle had returned at 10:04 and
the supplies were short), so the ordinary 95F exploration held, and on 93F (an up shaft from 95F)
the descent walked toward the down stairs.  With HP under the rest target the rest slot asked the
ESP tier (policy_combat ``_esp_threat_rest_key``) on every board.  Telepathy showed a 巨大首なし
(race 653) at (16,37) and a kobold (30) to the north; at its edges it reached a level-52 monster
(1226) at (27,44) only from (16,29) and a level-20 monster (339) at (12,5) only from (13,25):

* (16,29): {653, 1226, 30}, MEDIUM (0.14): no hunt, the descent walked NW ('7', '4');
* (15,28)-(14,26): {653, 30}, within the held group: MEDIUM held, the descent walked on;
* (13,25): {653, 339, 30}, not within the held {653, 1226, 30}: WEAK decided again, and the hunt
  walked SE ('3', '6') back to (16,29), five times.

esp_tier_hold now keeps the floor's members read before when a new member decides again, so at
(13,25) the group is within the held one: MEDIUM holds and the rest slot hands the board to the
descent (PASS) instead of hunting.

Recorded: tests/fixtures/n1c-222-esp-fringe-1126 (tests/extract_n1c_222_esp_fringe_1126_fixture.py).
Every decision is the rest layer's (ladder_rest ``key``) of a policy built as the live one
(tests.support.recorded._policy: the game's definitions).
DECLARED RECONSTRUCTION: the policy is primed on the first recorded board of the loop (turn
12405791) and decides the recorded boards in order, as the live one did; the map memory record the
process wrote at the stop is restored on that first board with its turn set to the first board's
(map_memory_record restores only a record of the same or an earlier turn), so the hunt's walk knows
the floor as the live process did.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import pickle
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import esp_tier_hold, ladder_rest
from hengbot.dungeon_ladder import PASS
from hengbot.map_memory_record import FILE_NAME
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-222-esp-fringe-1126"
HUNT = "esp-threat:hunt-weak"
FIRST = 12405791
WEST_EDGE, EAST_EDGE = (13, 25), (16, 29)
FRINGE_WEST, FRINGE_EAST = 339, 1226


def _load(name):
    return json.loads(lzma.decompress((FIXTURE / name).read_bytes()).decode("utf-8", "surrogateescape"))


def _cell(raw):
    return raw["player"]["y"], raw["player"]["x"]


def _races(raw):
    return {monster["race_id"] for monster in raw["detected_monsters"]}


def _old_held(policy, snapshot, tier, tiered):
    """esp_tier_hold ``held`` before the fix: a group not within the held one decides again alone."""
    group = frozenset((monster.index, monster.race_id) for monster in tiered)
    memory = policy.__dict__.get(esp_tier_hold.HOLD)
    if (tier in esp_tier_hold.HELD_TIERS and memory is not None and memory[0] == snapshot.floor_key
            and memory[1] in esp_tier_hold.HELD_TIERS and group <= memory[2]):
        return memory[1]
    setattr(policy, esp_tier_hold.HOLD, (snapshot.floor_key, tier, group))
    return tier


class EspFringeRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.boards = [raw for raw in _load("boards.json.xz") if raw["turn"] >= FIRST]
        cls.decisions = {row["turn"]: row for row in _load("decisions.json.xz")}

    def replay(self):
        """[(cell, rest layer's key or PASS, its reason, the tier acted on)] over the recorded boards."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        scratch = Path(directory.name)
        policy = _policy(scratch, self.monrace)
        held = pickle.loads(lzma.decompress((FIXTURE / "map-memory.pkl.xz").read_bytes()))
        held["turn"] = FIRST
        (scratch / FILE_NAME).write_bytes(pickle.dumps(held))
        policy._map_memory_record_path = scratch / FILE_NAME
        policy.__dict__.pop("_map_memory_record_read", None)
        policy.prime(parse_snapshot(copy.deepcopy(self.boards[0]), self.monrace))
        rows = []
        for raw in self.boards:
            board = parse_snapshot(copy.deepcopy(raw), self.monrace)
            policy.last_reason = None
            key = ladder_rest.key(policy, board, strategic_hostiles=[])
            rows.append((_cell(raw), PASS if key is PASS else key, policy.last_reason,
                         (policy._esp_threat_assessment or {}).get("tier")))
        return rows

    def test_the_recording(self):
        reasons = [(tuple(row["position"]), row["reason"]) for turn, row in sorted(self.decisions.items())
                   if turn >= FIRST and row["reason"] in (HUNT, "approach-descent")]
        self.assertIn((WEST_EDGE, HUNT), reasons)
        self.assertIn((EAST_EDGE, "approach-descent"), reasons)
        self.assertEqual(self.decisions[max(self.decisions)]["reason"], "loop-detected")
        for raw in self.boards:
            self.assertEqual(FRINGE_WEST in _races(raw), _cell(raw) == WEST_EDGE, raw["turn"])
            self.assertEqual(FRINGE_EAST in _races(raw), _cell(raw) == EAST_EDGE, raw["turn"])

    def test_the_old_hold_hunts_again_from_the_west_edge(self):
        original = esp_tier_hold.held
        esp_tier_hold.held = _old_held
        self.addCleanup(setattr, esp_tier_hold, "held", original)
        rows = self.replay()
        first_east = next(index for index, row in enumerate(rows) if row[0] == EAST_EDGE)
        west_after = [row for row in rows[first_east:] if row[0] == WEST_EDGE]
        self.assertTrue(west_after)
        for _cell_, key, reason, tier in west_after:
            self.assertEqual((key, reason, tier), ("3", HUNT, "weak"))
        # From the east edge on, the rest slot's choice is the recorded one on every board: the
        # hunt's key where the live bot hunted, the hand-over to the descent where it walked down.
        for raw, row in list(zip(self.boards, rows))[first_east:]:
            recorded = self.decisions[raw["turn"]]
            if recorded["reason"] == "approach-descent":
                self.assertEqual(row[1:3], (PASS, None), raw["turn"])
            elif recorded["reason"] == HUNT:
                recorded = self.decisions[raw["turn"]]
                self.assertEqual((row[1], row[2]), (recorded["key"], recorded["reason"]), raw["turn"])

    def test_medium_holds_after_the_east_edge_and_the_descent_walks(self):
        rows = self.replay()
        first_east = next(index for index, row in enumerate(rows) if row[0] == EAST_EDGE)
        self.assertEqual([row[2] for row in rows[:first_east]], [HUNT] * first_east)
        for cell, key, reason, tier in rows[first_east:]:
            self.assertEqual((key, reason, tier), (PASS, None, "medium"), cell)


if __name__ == "__main__":
    unittest.main()
