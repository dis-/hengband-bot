"""n1-c Magic-Eater: when the absorbed Staff of Magic Mapping (周辺感知) is
cast while exploring (owner 2026-11-01 「魔道具術師が未知領域を探索するときに
周辺感知するときとしないときがある。調査して」).

Boards and decision rows are recorded
(tests/fixtures/me-mapping-1101.json.gz, see tests/extract_me_mapping_1101.py)
and go through the public choose_key and the production executor.

life-073, Angband 3F (decisions 1876-2000): map-area at (7,61) showed the
downstairs (16,33); the frontier approach to it expired at decision 1928 and
the next 5 minutes explored without mapping again, because the trigger
``stairs-needed-and-unknown`` counted the expired stair as known while descent
refused it (``expired-or-ineligible-downstairs``).

life-065, Yeek cave 1F (decisions 6468-6494, owner 2026-11-01 「脅威でなければ
感知する」): an asleep level-1 monster stayed in view from the arrival, the
common gate refused every power while a hostile was visible, and the visit
ended without mapping.  Mapping is now cast while the visible hostiles are not
dangerous by the combat ladder's own judgement; the other powers keep the gate.

DECLARED CONSTRUCTED: the absorbed staff list (5 charges each; the recorded
rows cast detect-evil, detect-traps, map-area and lite-area); the earlier uses
on the floor are seeded from the recorded me-power rows; the ledger expiry of
(16,33) is set from the recorded refusal (decision 1928 left approach-descent
for explore) instead of replaying the 32 stalled approach decisions; the
dangerous case on the life-065 board wakes the recorded monster and gives its
race a ranged attack worth the whole HP.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
from dataclasses import replace
import gzip
import json
from pathlib import Path
import unittest

from hengbot import me_powers
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from tests import test_me_mining_death_recorded as mining
from tests import test_me_stage2_powers as stage2

FIXTURE = Path(__file__).parent / "fixtures" / "me-mapping-1101.json.gz"
STAIR = Position(16, 33)
MAP_AREA = "me-power:stairs-needed-and-unknown:map-area"
ARRIVAL_MAP = "me-power:new-floor:map-area"


def _harness(name):
    return getattr(mining.MagicEaterMiningDeathRecordedTest, name)


class MagicEaterMappingRecordedTest(mining.harness.ProductionHarness):
    choose = _harness("choose")
    post = _harness("post")
    cast = stage2.MagicEaterStage2PowersTest.cast
    assertPower = stage2.MagicEaterStage2PowersTest.assertPower

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        cls.races = {}
        for key, facts in cls.data["monraces"].items():
            facts = copy.deepcopy(facts)
            for name in ("flags", "abilities"):
                facts[name] = frozenset(facts[name])
            facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
            cls.races[int(key)] = MonraceKnowledge(**facts)

    def board(self, life):
        raw = copy.deepcopy(self.data[life]["board"])
        raw["_magic_eater_power_list"] = stage2.staff_list(stage2.staff_rows())
        return raw

    def policy(self, raw, races=None):
        policy = HengbotPolicy(monrace_knowledge=dict(races or self.races))
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        return policy

    def seed_recorded_uses(self, policy, life, raw):
        """The floor's recorded me-power rows before the board."""
        board = parse_snapshot(raw, policy._monrace_knowledge)
        memory = me_powers.FloorMemory(board.floor_key, raw["turn"])
        for row in self.data[life]["rows"]:
            if row["turn"] < raw["turn"] and row["reason"].startswith(me_powers.REASON + ":"):
                ident = ("staff", me_powers.decode_letter(row["key"][2]))
                trigger = row["reason"].split(":")[1]
                position = Position(row["position"]["y"], row["position"]["x"])
                memory.uses.append(me_powers.Use(ident, ident, trigger, position, row["turn"]))
        policy._me_power_floor = memory
        return memory

    def test_life073_expired_stair_remaps_the_far_floor(self):
        rows = {row["decision_sequence"]: row for row in self.data["life-073"]["rows"]}
        # Recorded: mapped at (7,61), approached (16,33), then explored with
        # the stair still remembered and no further mapping.
        self.assertEqual((rows[1880]["reason"], rows[1880]["position"]),
                         ("me-power:new-floor:map-area", {"y": 7, "x": 61}))
        self.assertEqual(rows[1927]["reason"], "approach-descent")
        self.assertEqual(rows[1928]["reason"], "explore")
        self.assertEqual(rows[2000]["reason"], "explore")
        self.assertEqual(rows[2000]["down_stairs"], [[STAIR.y, STAIR.x]])
        raw = self.board("life-073")
        policy = self.policy(raw)
        memory = self.seed_recorded_uses(policy, "life-073", raw)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        here = board.player.position
        mapping = me_powers.BY_KEY[("staff", stage2.MAPPING)]
        self.assertTrue(all(me_powers.game_distance(here, use.position) >= me_powers.DETECT_RAD
                            for use in memory.uses if use.used == mapping.ident))
        self.assertIn(STAIR, policy._remembered_downstairs)

        with self.subTest("stair still usable: descend, no mapping"):
            usable = self.policy(raw)
            self.seed_recorded_uses(usable, "life-073", raw)
            key = self.choose(usable, raw)
            self.assertEqual(usable.last_reason, "approach-descent", key)

        policy._nav_ledger.expire("descend", STAIR)
        key = self.choose(policy, raw)
        self.assertPower(policy, key, mapping.letter, MAP_AREA)
        self.assertEqual(policy._usable_downstairs(board), set())
        self.cast(policy, raw, key, stage2.staff_rows())

    @staticmethod
    def floor_power(policy, snapshot):
        """me_powers' answer on a fresh floor visit (no earlier uses)."""
        me_powers.observe(policy, snapshot)
        return me_powers.power_key(policy, snapshot, me_powers.FLOOR)

    def test_life065_harmless_visible_monster_maps_on_arrival(self):
        # The 1F visit: arrival (turn 4665358) to the ascent (4665638).
        rows = [row for row in self.data["life-065"]["rows"] if 4665358 <= row["turn"] <= 4665638]
        # Recorded: the monster in view from the arrival kept every power
        # back; detect-evil came only when nothing was visible and the visit
        # ended (ascend) without map-area.
        in_view = [row for row in rows if row["visible_hostiles"]]
        powers = [row for row in rows if row["reason"].startswith(me_powers.REASON + ":")]
        self.assertFalse(any(row["reason"].startswith(me_powers.REASON) for row in in_view))
        self.assertEqual([(row["decision_sequence"], row["reason"], row["visible_hostiles"]) for row in powers],
                         [(6487, "me-power:new-floor:detect-evil", 0)])
        self.assertEqual(rows[-1]["reason"], "fundraise:ascend")
        raw = self.board("life-065")
        policy = self.policy(raw)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertEqual(len(policy._physical_hostiles(board)), 1)
        mapping = me_powers.BY_KEY[("staff", stage2.MAPPING)]

        key = self.choose(policy, raw)
        self.assertPower(policy, key, mapping.letter, ARRIVAL_MAP)
        self.cast(policy, raw, key, stage2.staff_rows())

        with self.subTest("dangerous visible hostile: no power"):
            dangerous = copy.deepcopy(raw)
            for monster in dangerous["visible_monsters"]:
                monster["asleep"] = False
            races = dict(self.races)
            races[21] = replace(races[21], max_ranged_damage=board.player.max_hp)
            policy = self.policy(dangerous, races)
            snapshot = parse_snapshot(dangerous, policy._monrace_knowledge)
            self.assertTrue(policy._is_material_threat(snapshot, policy._physical_hostiles(snapshot)))
            self.assertIsNone(self.floor_power(policy, snapshot))
        with self.subTest("just hit: no power"):
            policy = self.policy(raw)
            self.assertEqual(self.floor_power(policy, board), mapping.key)
            policy._took_damage = True
            self.assertIsNone(self.floor_power(policy, board))


if __name__ == "__main__":
    unittest.main()
