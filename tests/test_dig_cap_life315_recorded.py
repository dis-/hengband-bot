"""The dig cap: n1-b life-315's granite dig (owner 2026-11-06).

Owner, the option 「見込み100回を超えたら掘らない」: 「成功の見込みから、掘り抜くのに平均
100回を超える壁は選びません。ゲームの式から数え、実際に掘り続けた回数でも打ち切ります。」

Recorded: n1-b life-315 (Magic-Eater Lv7, 2026-11-05) mining on Yeek cave 1F
swapped its Shovel in ('ta', 'wg' at turns 111276-111281) and posted T9 from
(5, 55) into the granite wall at (4, 56) 577 times from turn 111300 on, each
post 99 tries (「花崗岩の壁に穴を掘っている。 <x99>」, about 990 game turns at
speed 110), until its light ran dry.  Digging showed 18 with the Short Sword
(turn 94640) and 36 with the Shovel (turn 666059).  exe_tunnel
(tunnel-execution.cpp) breaks granite (power 40) only when
skill_dig > 40 + randint0(1600): never at 36.  The boards and decision rows
are frozen in tests/fixtures/dig-cap-life315-20261105.json.gz
(tests/extract_dig_cap_life315_fixture.py).  Every decision goes through the
public ``choose_key``.

DECLARED CONSTRUCTED: the floor around the recorded cells (the capture keeps
no dungeon map): the recorded player cell (5, 55) on floor in a small room,
the recorded wall (4, 56) in solid granite, the room the torch lights, permanent rock on the map's edge,
a vein with treasure (or the up staircase) behind the wall or in its place; the worn light (the
turn-666059 board's torch was burnt out: the recorded 1900-turn torch of the
turn-94640 pack is worn instead, with the light radius 1 recorded when that
torch was worn at decision 2198); the sword board (the turn-666059 board with
the recorded Short Sword in the main hand, the Shovel in the pack and the
recorded digging 18 of turn 94640).  DECLARED RECONSTRUCTED: the mining-run
state (mode "mine", one planned run, the detection read on this floor, the
quiet streak).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
import string
import unittest

from hengbot import tunnel_feasibility
from hengbot.model import Position, parse_snapshot
from hengbot.policy import ConservativePolicy
from hengbot.policy_constants import MINING_THREAT_FREE_LIMIT


FIXTURE = Path(__file__).with_name("fixtures") / "dig-cap-life315-20261105.json.gz"
SWORD, SHOVEL, TORCH = "ショート・ソード", "シャベル", "松明(1900"
HERE, WALL, BEHIND = (5, 55), (4, 56), (3, 57)
WIDTH, HEIGHT = 66, 44
# grid_map palette rows [terrain id, lighting, terrain bits, known], as the
# Yeek cave 1F boards of tests/fixtures/me-barehand-mining-20261031.json.gz
# print them (the bits: model._GRID_TERRAIN_NAMES).
PALETTE = {
    "floor": [1, 2, 416, 1],
    "granite": [56, 2, 163840, 1],
    "permanent": [60, 2, 164352, 1],
    "quartz_treasure": [55, 2, 163904, 1],      # power 20
    "quartz_treasure_2": [240, 2, 163904, 1],   # power 30
    "up_stairs": [6, 2, 70528, 1],
}
ROOM = {(y, x) for y in (5, 6) for x in range(54, 57)}


def reletter(raw):
    for letter, item in zip(string.ascii_lowercase, raw["inventory"]):
        item["slot"] = letter
    return raw


class DigCapLife315RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def decision(self, sequence):
        return next(row for row in self.case["decisions"]
                    if row["decision_sequence"] == sequence)

    def character(self, *, sword=False):
        board = copy.deepcopy(self.case["boards"]["shovel"])
        torch = next(item for item in self.case["boards"]["sword"]["inventory"]
                     if item["name"].startswith(TORCH))
        board["equipment"] = [item for item in board["equipment"] if item["slot"] != "light"]
        board["equipment"].append(dict(copy.deepcopy(torch), slot="light", is_equipment=True))
        board["player"]["light_radius"] = self.decision(2198)["light_radius"]
        if sword:
            shovel = next(i for i in board["equipment"] if i["slot"] == "main_hand")
            blade = next(i for i in board["inventory"] if i["name"].startswith(SWORD))
            board["equipment"].remove(shovel)
            board["inventory"].remove(blade)
            board["equipment"].append(dict(blade, slot="main_hand", is_equipment=True))
            board["inventory"].append(dict(shovel, slot="?", is_equipment=False))
            board["player"]["skill_ratings"]["digging"] = copy.deepcopy(
                self.case["boards"]["sword"]["player"]["skill_ratings"]["digging"])
        return reletter(board)

    def board(self, turn, *, wall="granite", behind="quartz_treasure", sword=False):
        raw = self.character(sword=sword)
        floor = self.decision(1667)["floor"]
        raw["floor"] = {
            "dungeon_id": floor["dungeon_id"], "dungeon_name": "イークの洞穴",
            "feeling": 0, "height": HEIGHT, "in_town": False, "inside_arena": False,
            "level": floor["level"], "quest_id": 0, "town_id": 0, "town_index": 1,
            "width": WIDTH,
        }
        raw["player"]["y"], raw["player"]["x"] = HERE
        raw["turn"] = turn
        raw["messages"] = []
        raw["visible_monsters"], raw["detected_monsters"] = [], []
        names = list(PALETTE)
        cells = {}
        for y in range(HEIGHT):
            for x in range(WIDTH):
                edge = y in (0, HEIGHT - 1) or x in (0, WIDTH - 1)
                cells[(y, x)] = "permanent" if edge else "granite"
        for cell in ROOM:
            cells[cell] = "floor"
        cells[WALL] = wall
        if behind is not None:
            cells[BEHIND] = behind
        runs = [[y, x, 1, names.index(name)] for (y, x), name in sorted(cells.items())]
        raw["grid_map"] = {"cells": [], "found_item_ids": [], "found_item_names": [],
                           "found_items": [], "h": HEIGHT, "w": WIDTH,
                           "palette": [PALETTE[name] for name in names], "runs": runs,
                           "unsafe_rows": []}
        return raw

    def policy(self, raw):
        policy = ConservativePolicy()
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy.prime(snapshot)
        two_weapon, shield = self.case["skill_exp"]
        policy.consume_skill_knowledge({
            "knowledge": {"skills": [{"id": 1, "exp": two_weapon}, {"id": 3, "exp": shield}]},
            "player": {"level": raw["player"]["level"]},
        })
        # DECLARED RECONSTRUCTED (module docstring).
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs, policy._mining_runs_completed = 1, 0
        policy._mining_scroll_used_floor = snapshot.floor_key
        policy._mining_threat_free_streak = MINING_THREAT_FREE_LIMIT
        return policy

    @staticmethod
    def decide(policy, raw):
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        return str(key), policy.last_reason

    def test_capture_pins_the_recorded_scene(self):
        rows = {row["decision_sequence"]: row for row in self.case["decisions"]}
        self.assertEqual([(rows[s]["reason"], rows[s]["key"]) for s in (1664, 1665, 1667, 1668)],
                         [("fundraise:wield-digging-tool", "ta"),
                          ("fundraise:wield-digging-tool", "wg"),
                          ("fundraise:dig-to-treasure", "T9"),
                          ("fundraise:dig-to-treasure", "T9")])
        self.assertEqual({(rows[s]["position"]["y"], rows[s]["position"]["x"]) for s in rows},
                         {HERE})
        self.assertEqual(rows[1668]["messages"], ["花崗岩の壁に穴を掘っている。 <x99>"])
        self.assertEqual(rows[1668]["turn"] - rows[1667]["turn"], 956)
        for name, skill in (("sword", 18), ("shovel", 36)):
            self.assertEqual(
                self.case["boards"][name]["player"]["skill_ratings"]["digging"]["value"], skill)

    def test_swap_skill_is_the_recorded_shovel_skill(self):
        raw = self.board(self.decision(1667)["turn"], sword=True)
        policy = self.policy(raw)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(snapshot.player.digging_skill, 18)
        # 18 - 8 (Short Sword weight 80) + 20 (Shovel pval 1) + 6 (weight 60).
        self.assertEqual(tunnel_feasibility.dig_skill(policy, snapshot), 36)
        granite = snapshot.grids[Position(*WALL)]
        self.assertTrue(tunnel_feasibility.not_dug(policy, snapshot, granite))

    def test_recorded_granite_is_not_dug(self):
        raw = self.board(self.decision(1667)["turn"])
        key, reason = self.decide(self.policy(raw), raw)
        self.assertFalse(key.startswith("T"), (key, reason))

    def test_vein_over_100_expected_tries_is_not_chosen(self):
        # Quartz with treasure, power 30: 1200 / (36 - 30) = 200 tries on average.
        raw = self.board(self.decision(1667)["turn"], wall="quartz_treasure_2", behind=None)
        key, reason = self.decide(self.policy(raw), raw)
        self.assertNotEqual(key, "T9", reason)

    def test_dig_stops_after_100_tries_on_one_cell(self):
        # Quartz with treasure, power 20: 800 / 16 = 50 tries on average.  The
        # recorded cadence: T9 at 111300, the next boards at 112256 and 113163.
        policy = None
        keys = []
        for sequence in (1667, 1668, 1669):
            raw = self.board(self.decision(sequence)["turn"], wall="quartz_treasure", behind=None)
            policy = policy or self.policy(raw)
            keys.append(self.decide(policy, raw))
        self.assertEqual([key for key, _ in keys[:2]], ["T9", "T9"], keys)
        self.assertNotEqual(keys[2][0], "T9", keys)

    def test_walk_out_does_not_wield_for_granite(self):
        # The way up is behind the recorded granite; with the Short Sword worn
        # the board shows 18, the Shovel the swap would wield gives 36.
        raw = self.board(self.decision(1667)["turn"], behind="up_stairs", sword=True)
        policy = self.policy(raw)
        policy._returning_to_town = True
        key, reason = self.decide(policy, raw)
        self.assertFalse(key.startswith(("t", "w", "T")), (key, reason))


if __name__ == "__main__":
    unittest.main()
