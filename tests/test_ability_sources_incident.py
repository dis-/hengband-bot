import json
import unittest
from pathlib import Path
from unittest.mock import patch

from hengbot.equipment_optimizer import (
    EvaluatedLoadout,
    LoadoutMetrics,
    OptimizationResult,
    OwnedEquipmentCatalog,
    current_loadout,
    divable_depth,
)
from hengbot.equipment_transaction_planner import EquipmentTransactionPlan
from hengbot.model import MonsterState, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy, RESIST_FLAG_BY_ABILITY
from hengbot.warrior_optimization import CharacterCalibration, WarriorOptimizationPreparation


FIXTURES = Path(__file__).parent / "fixtures"
TOWN_FIXTURE = FIXTURES / "abilities-depth34-pre-recall-town.json"
LANDED_FIXTURE = FIXTURES / "abilities-depth34-landed-dungeon.json"
PERMANENT = frozenset({
    "resist_cold", "resist_fear", "resist_neth", "resist_pois",
    "see_invisible",
})


def _parse(path):
    return parse_snapshot(json.loads(path.read_text(encoding="utf-8")), {})


class AbilitySourcesIncidentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.town = _parse(TOWN_FIXTURE)
        cls.landed = _parse(LANDED_FIXTURE)

    @staticmethod
    def _departure_policy(snapshot):
        policy = HengbotPolicy()
        policy.prime(snapshot)
        policy._char_dump_done_this_visit = True
        policy._town_visit_ledger.blocked_stores.update(range(8))
        policy._town_store_attempted.update({store: snapshot.turn for store in range(8)})

        def completed_worn_optimization(candidate):
            policy._equipment_catalog.refresh_carried(
                candidate.inventory, candidate.equipment
            )
            worn = current_loadout(policy._equipment_catalog.items)
            policy._equipment_optimizer_input_key = "0" * 64
            evaluated = EvaluatedLoadout(worn, LoadoutMetrics(0.0, 0.0, 0.0))
            result = OptimizationResult(
                best=evaluated,
                alternatives=(),
                pareto_frontier=(),
                dominated_item_ids=frozenset(),
                combinations_considered=1,
                combinations_evaluated=1,
                invalid_combinations=0,
                elapsed_seconds=0.0,
                timed_out=False,
                incomplete_item_ids=frozenset(),
            )
            return WarriorOptimizationPreparation(
                current=worn,
                result=result,
                transaction=EquipmentTransactionPlan((), (), len(candidate.inventory)),
                blockers=(),
            )

        # Same already-completed, zero-action prerequisite used by the existing
        # public choose_key departure tests; the destination gate remains real.
        policy._prepare_equipment_optimization = completed_worn_optimization
        return policy

    def test_depth34_pre_recall_town_snapshot_refuses_public_departure(self):
        policy = self._departure_policy(self.town)

        key = policy.choose_key(self.town)

        self.assertNotEqual(key, "rHa")
        self.assertEqual(policy.last_reason, "town:blocked:no-safe-recall-destination")
        self.assertEqual(
            policy._missing_required_abilities(self.town, 34),
            frozenset({"resist_chaos"}),
        )

    def test_depth34_landed_snapshot_starts_public_resist_gap_recovery(self):
        policy = HengbotPolicy()

        key = policy.choose_key(self.landed)

        self.assertEqual(key, "rH")
        self.assertEqual(policy.last_reason, "return:recall")
        self.assertEqual(policy._last_return_trigger, "resist-gap")
        self.assertEqual(
            policy._missing_required_abilities(self.landed, 34),
            frozenset({"resist_chaos"}),
        )

    def test_evidence_permanent_sources_are_the_five_true_intrinsics(self):
        actual = frozenset(
            ability
            for ability, sources in self.landed.player.ability_sources.items()
            if "permanent" in sources
        )
        self.assertEqual(actual, PERMANENT)

    def test_contaminated_depth_fallback_uses_permanent_sources(self):
        policy, preparation = self._contaminated_optimization()

        with patch("hengbot.policy.prepare_warrior_optimization", return_value=preparation):
            policy._prepare_equipment_optimization(self.town)

        self.assertEqual(policy._equipment_optimization_last_depth, 19)

    def test_contaminated_depth_cache_fallback_uses_permanent_sources(self):
        policy, preparation = self._contaminated_optimization()

        with patch("hengbot.policy.prepare_warrior_optimization", return_value=preparation):
            policy._prepare_equipment_optimization(self.town)
            policy._equipment_optimization_last_depth = None
            policy._prepare_equipment_optimization(self.town)

        self.assertEqual(policy._equipment_optimization_last_depth, 19)

    def _contaminated_optimization(self):
        catalog = OwnedEquipmentCatalog()
        catalog.refresh_carried(self.town.inventory, self.town.equipment)
        loadout = current_loadout(catalog.items)
        contaminated = frozenset(self.town.player.ability_sources)
        calibration = CharacterCalibration(
            race_id=self.town.player.race_id,
            class_id=self.town.player.class_id,
            personality_id=self.town.player.personality_id,
            level=self.town.player.level,
            stat_cur=self.town.player.stat_cur,
            base_stats=self.town.player.stat_use,
            base_hp=self.town.player.max_hp,
            base_ac_bonus=0,
            intrinsic_abilities=contaminated,
        )
        self.assertEqual(divable_depth(loadout, intrinsic_abilities=contaminated), 49)
        evaluated = EvaluatedLoadout(loadout, LoadoutMetrics(0.0, 0.0, 0.0))
        result = OptimizationResult(
            best=evaluated,
            alternatives=(),
            pareto_frontier=(),
            dominated_item_ids=frozenset(),
            combinations_considered=1,
            combinations_evaluated=1,
            invalid_combinations=0,
            elapsed_seconds=0.0,
            timed_out=False,
            incomplete_item_ids=frozenset(),
        )
        preparation = WarriorOptimizationPreparation(
            current=loadout,
            result=result,
            transaction=EquipmentTransactionPlan((), (), len(self.town.inventory)),
            blockers=(),
        )
        policy = HengbotPolicy()
        policy.prime(self.town)
        policy._character_calibration = calibration
        policy._equipment_catalog.refresh_carried(
            self.town.inventory, self.town.equipment
        )
        return policy, preparation

    def test_player_state_is_hashable_and_sources_lookup_for_both_wire_formats(self):
        self.assertIsInstance(hash(self.landed.player), int)
        self.assertEqual(
            self.landed.player.ability_sources["resist_fire"],
            frozenset({"equipment"}),
        )
        raw = json.loads(TOWN_FIXTURE.read_text(encoding="utf-8"))
        raw["player"]["abilities"] = {"resist_fire": True, "resist_chaos": False}
        flat = parse_snapshot(raw, {}).player
        self.assertIsInstance(hash(flat), int)
        self.assertEqual(len(flat.ability_sources), 0)
        self.assertIn("resist_fire", flat.abilities)

    def test_renamed_ability_sources_key_parses_like_the_pinned_capture(self):
        """hengband PR #5517 emits the per-source objects as player.ability_sources.

        The pinned captures predate the rename and still say "abilities"; reading
        only the new key would make every ability vanish, and reading only the old
        key would make every ability vanish once the emitter lands.  Both must
        yield the same parse.
        """
        raw = json.loads(LANDED_FIXTURE.read_text(encoding="utf-8"))
        raw["player"]["ability_sources"] = raw["player"].pop("abilities")
        renamed = parse_snapshot(raw, {}).player

        self.assertEqual(renamed.abilities, self.landed.player.abilities)
        self.assertEqual(
            dict(renamed.ability_sources), dict(self.landed.player.ability_sources)
        )
        self.assertEqual(
            frozenset(
                ability
                for ability, sources in renamed.ability_sources.items()
                if "permanent" in sources
            ),
            PERMANENT,
        )

    def test_real_status_and_resistance_consumers_see_parsed_abilities(self):
        monster = MonsterState(1, self.landed.player.position, 10, 10, 0, False, False, race_id=7)
        knowledge = MonraceKnowledge(
            10, 110, False, False,
            blows=(MonsterBlow("HIT", "CONFUSE"), MonsterBlow("HIT", "PARALYZE")),
        )
        policy = HengbotPolicy(monrace_knowledge={7: knowledge})
        self.assertEqual(
            policy._unresisted_melee_status_threats(self.landed, [monster]),
            [monster],
        )
        flags = frozenset(
            flag
            for ability, flag in RESIST_FLAG_BY_ABILITY.items()
            if ability in self.landed.player.abilities
        )
        self.assertIn(RESIST_FLAG_BY_ABILITY["resist_fire"], flags)
        self.assertNotIn(RESIST_FLAG_BY_ABILITY["resist_chaos"], flags)
        self.assertNotIn(RESIST_FLAG_BY_ABILITY["resist_conf"], flags)


if __name__ == "__main__":
    unittest.main()
