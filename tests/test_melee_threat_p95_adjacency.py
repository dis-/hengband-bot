"""Pins: melee threat as the true 95th percentile, capped by adjacency.

User decisions (verbatim):
- 「危険度の評価を見直し。特に近接の危険度評価が過剰ではないか？」
- 「1に加え、最大隣接可能数を考慮に入れる。視界内にいる全ての敵を単純に加算しない。」
- 「検知敵の段階にも適用する」

Specification (topic melee-threat-p95-adjacency): per monster the operational
melee value is the exact 95th percentile of its melee damage over the horizon
(per-blow hit probability, rolled dice after the per-blow reductions, over the
attack count the movement/TELE_TO logic allows); the expected value uses the
average reduced die; the theoretical maximum stays as ``total``.  Only the K
monsters with the largest operational melee that can become adjacent (K = the
cells around the player a monster could stand on; wall cells too for
PASS_WALL / KILL_WALL) contribute melee; every other monster contributes its
ranged part only.

Substrates:
- T1/T3: a restarted policy (a bot restart on the parked game) decides the
  recorded input row of decision 158 of the 2026-09-22 03:11:43-03:15:09 bot
  process (tests/fixtures/morivant-travel-retired-20260922.jsonl.gz, the same
  frozen lifetime the Morivant pins replay; one input row).  Live 158 was
  ('rf', 'emergency:teleport') against 闘トロル (race 631) at HP 341 with the
  operational prediction 372.  T1 re-races that recorded adjacent troll.
- T2: synthetic geometry (corridor / open room / walls) through the public
  threat_prediction.
- T5: synthetic ranged-only casters.
Walls: Home history/disposal files and the calibration file live in a
temporary directory (the helper shared with the esp-threat-rest pins).  No
wall touches the threat producer or the emergency ladder.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import Position, Snapshot
from hengbot.monrace_knowledge import (
    MonraceKnowledge,
    MonsterBlow,
    load_monrace_knowledge,
)
from hengbot.monster_ranged_evaluator import (
    SpellSelectionContext,
    ability_selection_probabilities,
    aggregate_ranged_damage_percentile,
)
from hengbot.policy import HengbotPolicy

from policy_fixtures import grid, hostile, player
from test_esp_threat_rest_recorded import EDIT, _policy
from test_morivant_travel_retired_recorded import (
    BOUNDARIES_SHA256,
    FIXTURE,
    FIXTURE_SHA256,
)


TROLL_DECISION = 158
TROLL = 631  # 闘トロル


def _independent_percentile(policy, snapshot, knowledge, attacks, stunned=False):
    """Pure-Python exact convolution (independent of the numpy evaluator)."""
    per_action = {0: 1.0}
    mean = 0.0
    for blow in knowledge.blows:
        hit = policy._melee_hit_probability(
            blow.effect, knowledge.level, snapshot.player.ac, stunned
        )
        rolls = {0: 1}
        for _ in range(blow.dice_num if blow.dice_sides > 0 else 0):
            following = {}
            for subtotal, count in rolls.items():
                for face in range(1, blow.dice_sides + 1):
                    following[subtotal + face] = (
                        following.get(subtotal + face, 0) + count
                    )
            rolls = following
        outcomes = sum(rolls.values())
        blow_distribution = {0: 1.0 - hit}
        for roll, count in rolls.items():
            damage = policy._maximum_melee_blow_damage(snapshot, blow.effect, roll)
            blow_distribution[damage] = (
                blow_distribution.get(damage, 0.0) + hit * count / outcomes
            )
            mean += hit * count / outcomes * damage
        following = {}
        for left, p_left in per_action.items():
            for right, p_right in blow_distribution.items():
                following[left + right] = (
                    following.get(left + right, 0.0) + p_left * p_right
                )
        per_action = following
    total = {0: 1.0}
    for _ in range(attacks):
        following = {}
        for left, p_left in total.items():
            for right, p_right in per_action.items():
                following[left + right] = (
                    following.get(left + right, 0.0) + p_left * p_right
                )
        total = following
    cumulative = 0.0
    for damage in sorted(total):
        cumulative += total[damage]
        if cumulative >= 0.95 - 1e-12:
            return damage, attacks * mean
    return max(total), attacks * mean


class RecordedTrollBoardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        boundaries_path = FIXTURE.with_suffix(".boundaries.json")
        assert hashlib.sha256(boundaries_path.read_bytes()).hexdigest() == (
            BOUNDARIES_SHA256
        )
        cls.boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        cls.starts = [0]
        for count in cls.boundaries["input_rows"]:
            cls.starts.append(cls.starts[-1] + count)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def _fresh(self, sequence):
        """A restarted bot decides the recorded input row of ``sequence``."""
        policy = _policy(self.directory, self.monrace)
        segment = self.lines[self.starts[sequence - 1] : self.starts[sequence]]
        _decoded, snapshots = _consume_response_sequence(
            segment, policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        return policy, snapshots[-1]

    def _troll(self, snapshot):
        (troll,) = [m for m in snapshot.visible_monsters if m.hostile]
        self.assertEqual((troll.race_id, troll.distance), (TROLL, 1))
        return troll

    # ------------------------------------------------------------------ T1
    def test_t1_per_monster_p95_and_average_die_at_cl31_ac54_speed_plus4(self):
        policy, snapshot = self._fresh(TROLL_DECISION)
        self.assertEqual(
            (snapshot.player.level, snapshot.player.ac, snapshot.player.speed),
            (31, 54, 114),
        )
        self.assertIn("resist_fire", snapshot.player.abilities)
        troll = self._troll(snapshot)
        # threat_prediction memoises on object identity: keep every re-raced
        # monster alive so no id is reused within this snapshot.
        alive = []
        # race: (actions, theoretical total, exact p95, mean); reviewer's
        # 20,000-sample simulation: p95 272 / 210 / 70 / 10, mean 226 / 169 /
        # 50 / 6.
        expected = {
            1019: (8, 496, 273, 225.3413),
            631: (6, 372, 210, 169.0060),
            612: (6, 120, 70, 50.0229),
            899: (3, 24, 11, 6.0626),
        }
        for race_id, (actions, total, p95, mean) in expected.items():
            with self.subTest(race_id=race_id):
                knowledge = self.monrace[race_id]
                monster = replace(
                    troll,
                    race_id=race_id,
                    speed=knowledge.speed,
                    level=knowledge.level,
                    max_melee_damage=knowledge.max_melee_damage,
                    max_ranged_damage=0,
                )
                alive.append(monster)
                prediction = policy.threat_prediction(snapshot, [monster], 3)
                row = prediction["monsters"][0]
                self.assertEqual(row["actions"], actions)
                self.assertEqual(row["melee_prediction"], total)
                self.assertEqual(prediction["total"], total)
                self.assertEqual(row["operational_melee_prediction"], p95)
                self.assertAlmostEqual(
                    row["expected_melee_prediction"], mean, places=3
                )
                independent_p95, independent_mean = _independent_percentile(
                    policy, snapshot, knowledge, actions
                )
                self.assertEqual(row["operational_melee_prediction"], independent_p95)
                self.assertAlmostEqual(
                    row["expected_melee_prediction"], independent_mean, places=9
                )
                self.assertTrue(row["melee_slot"])
                self.assertEqual(prediction["operational_total"], p95)

    # ------------------------------------------------------------------ T3
    def test_t3_recorded_troll_at_hp_341_is_fought_not_teleported(self):
        self.assertEqual(
            self.boundaries["recorded"][TROLL_DECISION - 1],
            ["rf", "emergency:teleport"],
        )
        policy, snapshot = self._fresh(TROLL_DECISION)
        troll = self._troll(snapshot)
        self.assertEqual(snapshot.player.hp, 341)

        key = policy.choose_key(snapshot)

        # Live: operational 372 (six actions of every blow at maximum dice)
        # >= HP 341 -> emergency:teleport.  Now the p95 is 210 < 341 and the
        # adjacent troll is fought.
        self.assertEqual((key, policy.last_reason), ("6", "melee"))
        prediction = policy.threat_prediction(snapshot, [troll], 3)
        self.assertEqual(
            (
                prediction["total"],
                prediction["operational_total"],
                prediction["expected_total"],
            ),
            (372, 210, 170),
        )
        self.assertEqual(
            policy._predicted_damage(snapshot, [troll], 3), 210
        )


def _knowledge(sides, *, flags=frozenset(), speed=110):
    return MonraceKnowledge(
        max_hp=100,
        average_hp=100,
        speed=speed,
        can_summon=False,
        friendly=False,
        level=10,
        max_melee_damage=sides,
        flags=flags,
        blows=(MonsterBlow("HIT", "HURT", 1, sides),),
    )


class AdjacencyCapTest(unittest.TestCase):
    ORIGIN = Position(10, 10)

    def _snapshot(self, floors, walls, monsters):
        grids = {self.ORIGIN: grid(10, 10)}
        for position in floors:
            grids[position] = grid(position.y, position.x)
        for position in walls:
            grids[position] = grid(position.y, position.x, passable=False)
        for monster in monsters:
            cell = grids[monster.position]
            grids[monster.position] = replace(cell, has_monster=True)
        return Snapshot(
            replace(player(10, 10, hp=500, max_hp=500), ac=0),
            grids,
            monsters,
        )

    def _monster(self, index, y, x, race_id):
        return hostile(
            index, y, x,
            distance=self.ORIGIN.distance_to(Position(y, x)),
            max_melee_damage=race_id,
            race_id=race_id,
        )

    def _single(self, policy, snapshot, monster):
        return policy.threat_prediction(snapshot, [monster], 3)

    # ------------------------------------------------------------------ T2
    def test_t2_corridor_counts_only_the_two_largest_melee_values(self):
        # An east-west corridor: floor at x-1 and x+1 only (K = 2).  Five
        # melee monsters in the corridor, all able to reach within 3 turns.
        floors = [Position(10, x) for x in range(5, 16) if x != 10]
        walls = [
            Position(y, x) for y in (9, 11) for x in range(5, 16)
        ]
        placements = [(10, 11, 20), (10, 12, 30), (10, 9, 10), (10, 8, 40), (10, 13, 50)]
        monsters = [
            self._monster(index, y, x, sides)
            for index, (y, x, sides) in enumerate(placements, 1)
        ]
        policy = HengbotPolicy(
            monrace_knowledge={sides: _knowledge(sides) for *_, sides in placements}
        )
        snapshot = self._snapshot(floors, walls, monsters)

        prediction = policy.threat_prediction(snapshot, monsters, 3)

        self.assertEqual(prediction["melee_slots"], (2, 6))
        singles = {
            monster.race_id: self._single(policy, snapshot, monster)[
                "operational_total"
            ]
            for monster in monsters
        }
        top_two = sorted(singles.values(), reverse=True)[:2]
        self.assertEqual(
            sorted(
                row["race_id"] for row in prediction["monsters"] if row["melee_slot"]
            ),
            [40, 50],
        )
        self.assertEqual(prediction["operational_total"], sum(top_two))
        self.assertEqual(
            prediction["operational_total"], singles[40] + singles[50]
        )
        self.assertEqual(
            prediction["expected_total"],
            -(-sum(
                row["expected_melee_prediction"]
                for row in prediction["monsters"] if row["race_id"] in (40, 50)
            ) // 1),
        )
        # The theoretical maximum still sums every monster.
        self.assertEqual(
            prediction["total"],
            sum(row["melee_prediction"] for row in prediction["monsters"]),
        )

    def test_t2_open_ground_counts_up_to_eight(self):
        # A 7x7 lit room: all 8 neighbours are floor (K = 8).  Nine melee
        # monsters, all within reach: the eight largest count.
        floors = [
            Position(y, x)
            for y in range(7, 14)
            for x in range(7, 14)
            if (y, x) != (10, 10)
        ]
        cells = [
            (9, 9), (9, 10), (9, 11), (10, 9), (10, 11),
            (11, 9), (11, 10), (11, 11), (8, 10),
        ]
        sides = [11, 12, 13, 14, 15, 16, 17, 18, 5]
        monsters = [
            self._monster(index, y, x, value)
            for index, ((y, x), value) in enumerate(zip(cells, sides), 1)
        ]
        policy = HengbotPolicy(
            monrace_knowledge={value: _knowledge(value) for value in sides}
        )
        snapshot = self._snapshot(floors, [], monsters)

        prediction = policy.threat_prediction(snapshot, monsters, 3)

        self.assertEqual(prediction["melee_slots"], (8, 0))
        singles = {
            monster.race_id: self._single(policy, snapshot, monster)[
                "operational_total"
            ]
            for monster in monsters
        }
        self.assertEqual(
            sorted(
                row["race_id"] for row in prediction["monsters"] if row["melee_slot"]
            ),
            [11, 12, 13, 14, 15, 16, 17, 18],
        )
        self.assertEqual(
            prediction["operational_total"],
            sum(singles[value] for value in sides[:8]),
        )
        self.assertLess(
            prediction["operational_total"], sum(singles.values())
        )

    def test_t2_wall_passer_takes_a_wall_slot(self):
        # The corridor (K = 2 floor, 6 wall) with two strong walkers and a
        # weaker PASS_WALL monster standing inside the wall north of the
        # player: it takes a wall slot and its melee counts; the same weaker
        # monster without PASS_WALL is left without a slot.  KILL_WALL too.
        floors = [Position(10, x) for x in range(5, 16) if x != 10]
        walls = [Position(y, x) for y in (9, 11) for x in range(5, 16)]
        for flag in ("PASS_WALL", "KILL_WALL", None):
            with self.subTest(flag=flag):
                monsters = [
                    self._monster(1, 10, 11, 30),
                    self._monster(2, 10, 9, 40),
                    self._monster(3, 9, 10, 20),
                ]
                knowledge = {30: _knowledge(30), 40: _knowledge(40)}
                knowledge[20] = _knowledge(
                    20, flags=frozenset({flag}) if flag else frozenset()
                )
                policy = HengbotPolicy(monrace_knowledge=knowledge)
                snapshot = self._snapshot(floors, walls, monsters)

                prediction = policy.threat_prediction(snapshot, monsters, 3)

                singles = {
                    monster.race_id: self._single(policy, snapshot, monster)[
                        "operational_total"
                    ]
                    for monster in monsters
                }
                slotted = sorted(
                    row["race_id"]
                    for row in prediction["monsters"]
                    if row["melee_slot"]
                )
                if flag is None:
                    self.assertEqual(slotted, [30, 40])
                    self.assertEqual(
                        prediction["operational_total"],
                        singles[30] + singles[40],
                    )
                else:
                    self.assertEqual(slotted, [20, 30, 40])
                    self.assertEqual(
                        prediction["operational_total"],
                        singles[20] + singles[30] + singles[40],
                    )

    def test_t2_outside_the_slots_the_ranged_part_still_counts(self):
        # Corridor K = 2: a third walker with a ranged attack keeps its
        # ranged operational value when it has no melee slot.
        floors = [Position(10, x) for x in range(5, 16) if x != 10]
        walls = [Position(y, x) for y in (9, 11) for x in range(5, 16)]
        archer_knowledge = replace(
            _knowledge(10),
            abilities=frozenset({"BO_FIRE"}),
            spell_frequency=50,
            max_ranged_damage=21,
        )
        archer = replace(self._monster(3, 10, 12, 10), max_ranged_damage=21)
        monsters = [
            self._monster(1, 10, 11, 30),
            self._monster(2, 10, 9, 40),
            archer,
        ]
        policy = HengbotPolicy(
            monrace_knowledge={
                30: _knowledge(30), 40: _knowledge(40), 10: archer_knowledge
            }
        )
        snapshot = self._snapshot(floors, walls, monsters)

        prediction = policy.threat_prediction(snapshot, monsters, 3)

        archer_row = next(
            row for row in prediction["monsters"] if row["race_id"] == 10
        )
        self.assertFalse(archer_row["melee_slot"])
        self.assertGreater(archer_row["operational_ranged_prediction"], 0)
        self.assertEqual(
            archer_row["operational_contribution"],
            archer_row["operational_ranged_prediction"],
        )
        self.assertEqual(
            prediction["operational_total"],
            sum(
                self._single(policy, snapshot, monster)["operational_total"]
                for monster in monsters[:2]
            )
            + archer_row["operational_ranged_prediction"],
        )


class RangedOnlyUnchangedTest(unittest.TestCase):
    # ------------------------------------------------------------------ T5
    def test_t5_ranged_only_predictions_are_unchanged(self):
        # Four ranged-only casters (no blows) in a corridor (K = 2): the
        # adjacency cap never touches ranged, so the operational total is
        # the sum of every caster's aggregate ranged p95, exactly as before
        # the change (measured on 3f27b90 with this exact board: total 1248,
        # operational 188 = 4 x 47, expected 21; every row identical).
        caster = MonraceKnowledge(
            max_hp=100,
            average_hp=100,
            speed=110,
            can_summon=False,
            friendly=False,
            level=20,
            max_ranged_damage=32,
            abilities=frozenset({"BO_FIRE", "BLINK"}),
            spell_frequency=25,
        )
        floors = [Position(10, x) for x in range(5, 16) if x != 10]
        walls = [Position(y, x) for y in (9, 11) for x in range(5, 16)]
        monsters = [
            hostile(
                index, 10, x,
                distance=abs(x - 10),
                max_ranged_damage=32,
                race_id=500,
            )
            for index, x in enumerate((12, 13, 8, 7), 1)
        ]
        grids = {Position(10, 10): grid(10, 10)}
        for position in floors:
            grids[position] = grid(position.y, position.x)
        for position in walls:
            grids[position] = grid(position.y, position.x, passable=False)
        snapshot = Snapshot(
            replace(player(10, 10, hp=500, max_hp=500), ac=0),
            grids,
            monsters,
        )
        policy = HengbotPolicy(monrace_knowledge={500: caster})

        prediction = policy.threat_prediction(snapshot, monsters, 3)

        per_monster = []
        for monster in monsters:
            context = SpellSelectionContext(distance=monster.distance)
            per_monster.append(
                aggregate_ranged_damage_percentile(
                    caster,
                    actions=4,
                    selection_probabilities=ability_selection_probabilities(
                        caster, context
                    ),
                    player_hp=500,
                ).total_damage
            )
        self.assertEqual(
            [row["operational_ranged_prediction"] for row in prediction["monsters"]],
            per_monster,
        )
        self.assertTrue(
            all(not row["melee_slot"] for row in prediction["monsters"])
        )
        self.assertEqual(prediction["operational_total"], sum(per_monster))
        self.assertEqual(
            (
                prediction["total"],
                prediction["operational_total"],
                prediction["expected_total"],
            ),
            (1248, 188, 21),
        )


if __name__ == "__main__":
    unittest.main()
