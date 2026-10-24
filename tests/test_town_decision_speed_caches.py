import tests  # noqa: F401

import base64
import gzip
import json
import pickle
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import cli
from hengbot import policy as policy_module
from hengbot import policy_town as policy_town_module
from hengbot.item_reservation import decision_caches_disabled
from hengbot.latch_onset_capture import checkpoint
from hengbot.model import parse_snapshot
from hengbot.policy import ConservativePolicy


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "town-decision-speed"
EDIT = Path(r"C:\hengband\lib\edit")
CAPTURES = ("A", "B")


def build_policy():
    monrace = cli.load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
    costs = cli.load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc")
    damaging = cli.load_damaging_terrain_ids(EDIT / "TerrainDefinitions.jsonc")
    town_maps = {}
    outpost = cli.parse_town_map(EDIT / "towns" / "01_Outpost_Full.jsonc")
    town_maps[0] = outpost
    for index in range(2, 6):
        path = cli.find_town_map(index, EDIT.parent.parent / "x")
        if path is not None:
            town_maps[index - 1] = cli.parse_town_map(path)
    wild = cli.load_wilderness_map(EDIT / "WildernessDefinition.jsonc")
    dungeons = cli.load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")
    quests = cli.load_quest_knowledge(EDIT / "quests")
    strategies = cli.load_quest_strategies(Path("strategy") / "quests")
    policy = ConservativePolicy(
        town_map=outpost,
        town_maps=town_maps,
        wilderness_map=wild,
        dungeon_knowledge=dungeons,
        monrace_knowledge=monrace,
        damaging_terrain_ids=damaging,
        quest_knowledge=quests,
        quest_strategies=strategies,
        baseitem_costs=costs,
    )
    policy._crossarea_fundraising_enforced = True
    return policy


def load_rows(name):
    with gzip.open(FIXTURES / f"{name}.jsonl.gz", "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def parse_board(row):
    snapshot = parse_snapshot(row, {})
    if (
        snapshot.player.two_weapon_skill is None
        or snapshot.player.shield_skill is None
    ):
        snapshot = replace(
            snapshot,
            player=replace(
                snapshot.player,
                two_weapon_skill=0,
                shield_skill=0,
            ),
        )
    return snapshot


def checkpoint_without_elapsed_telemetry(policy):
    state = pickle.loads(base64.b64decode(checkpoint(policy)))
    telemetry = state.get("_in_store_telemetry")
    if isinstance(telemetry, dict):
        def strip_elapsed(value):
            if isinstance(value, dict):
                for key in tuple(value):
                    if key in {"ms", "shelf_observe_ms", "dry_run_ms"}:
                        value.pop(key)
                    else:
                        strip_elapsed(value[key])
            elif isinstance(value, list):
                for entry in value:
                    strip_elapsed(entry)

        strip_elapsed(telemetry)
    return pickle.dumps(state, protocol=5)


class TownDecisionSpeedCacheTest(unittest.TestCase):
    def test_full_decision_computes_equipment_optimization_once(self):
        from unittest.mock import patch
        from tests.test_policy_equipment import EquipmentQuarantineInvariantTest
        from hengbot import policy_equipment

        policy, board, _ring, _identity = (
            EquipmentQuarantineInvariantTest()._policy_with_home_ring())
        with patch.object(policy_equipment, 'prepare_warrior_optimization',
                          wraps=policy_equipment.prepare_warrior_optimization) as search:
            policy.choose_key(board)
        # This calibrated board must perform a real search. Cheap preparation
        # readers may hit the signature or in-flight-session caches afterwards.
        self.assertEqual(search.call_count, 1)

    def test_departure_material_prepares_equipment_once_per_decision(self):
        """Admission and the need-list reader share the real preparation.

        Constructed calibrated town board: one Home ring supplies the depth-31
        chaos gate. This runs the optimizer, unlike uncalibrated replay boards.
        """
        from unittest.mock import patch
        from tests.test_policy_equipment import EquipmentQuarantineInvariantTest

        policy, board, _ring, _identity = (
            EquipmentQuarantineInvariantTest()._policy_with_home_ring())
        policy._build_grid_index(board)
        policy._map_predicate_snapshot = board
        policy._decision_sequence = 1
        with patch.object(policy, '_prepare_equipment_optimization',
                          wraps=policy._prepare_equipment_optimization) as prepare:
            codes = []
            policy._equipment_departure_ready(
                board, destination_depth=31, commit=False, codes=codes)
            preparation = policy._equipment_optimization_preparation
            self.assertIsNotNone(preparation.result)
            self.assertEqual(policy._equipment_optimization_telemetry['result_source'],
                             'fresh-search')
            # Supplying codes bypasses the bool memo: this must share the
            # preparation memo even when computing another depth's verdict.
            policy._equipment_departure_ready(
                board, destination_depth=40, commit=False, codes=[])
            self.assertIs(policy._equipment_optimization_preparation, preparation)
            self.assertEqual(prepare.call_count, 1)
            # A new decision must read again, rather than retaining the memo.
            policy._equipment_transaction_session = None
            policy._decision_sequence += 1
            policy._equipment_departure_ready(
                board, destination_depth=31, commit=False, codes=[])
            self.assertEqual(prepare.call_count, 2)

    def test_recorded_boards_keep_key_and_reason_with_caches_enabled(self):
        for capture in CAPTURES:
            rows = load_rows(capture)
            uncached = build_policy()
            cached = build_policy()
            uncached.prime(parse_board(rows[0]))
            cached.prime(parse_board(rows[0]))
            for index, row in enumerate(rows):
                # Parse a separate board object for each policy so the oracle
                # cannot observe any accidental mutation by the cached run.
                uncached_board = parse_board(row)
                cached_board = parse_board(row)
                with decision_caches_disabled():
                    uncached_key = uncached.choose_key(uncached_board)
                cached_key = cached.choose_key(cached_board)
                self.assertEqual(
                    (cached_key, cached.last_reason),
                    (uncached_key, uncached.last_reason),
                    f"{capture} decision {index + 1}",
                )
                self.assertEqual(
                    checkpoint_without_elapsed_telemetry(cached),
                    checkpoint_without_elapsed_telemetry(uncached),
                    f"{capture} policy state after decision {index + 1}",
                )
            self.assertFalse(
                any("decision_memo" in name or "query_memo" in name
                    for name in cached.__dict__),
                f"{capture} retained a decision cache on the policy",
            )

    def test_recorded_board_pins_retention_computation_counts(self):
        for capture in ("A",):
            boards = [parse_board(row) for row in load_rows(capture)]
            board = max(boards, key=lambda candidate: len(candidate.inventory))
            counts = {}
            for enabled in (False, True):
                policy = build_policy()
                policy.prime(board)
                original = policy._retention_reservation_baseline_detail
                original_surplus = policy._compute_retention_surplus
                calls = 0
                surplus_computations = 0

                def counted(snapshot, item):
                    nonlocal calls
                    calls += 1
                    return original(snapshot, item)

                def counted_surplus(snapshot, item):
                    nonlocal surplus_computations
                    surplus_computations += 1
                    return original_surplus(snapshot, item)

                policy._retention_reservation_baseline_detail = counted
                policy._compute_retention_surplus = counted_surplus
                if enabled:
                    policy.choose_key(board)
                else:
                    with decision_caches_disabled():
                        policy.choose_key(board)
                counts[enabled] = calls, surplus_computations
            self.assertGreater(counts[False][0], 0, capture)
            self.assertLess(
                counts[True][0], counts[False][0] // 2,
                f"{capture} baseline calls: uncached={counts[False][0]}, cached={counts[True][0]}",
            )
            self.assertLess(
                counts[True][1], counts[False][1] // 2,
                f"{capture} surplus computations: uncached={counts[False][1]}, cached={counts[True][1]}",
            )

    def test_recorded_board_pins_fixed_quest_computation_counts(self):
        board = max(
            [parse_board(row) for row in load_rows("B")],
            key=lambda candidate: len(candidate.inventory),
        )
        counts = {}
        for enabled in (False, True):
            policy = build_policy()
            policy.prime(board)
            known_calls = 0
            head_calls = 0
            original_known = policy._build_known_fixed_quests
            original_head = policy._build_fixed_quest_head

            def counted_known(snapshot):
                nonlocal known_calls
                known_calls += 1
                return original_known(snapshot)

            def counted_head(snapshot):
                nonlocal head_calls
                head_calls += 1
                return original_head(snapshot)

            policy._build_known_fixed_quests = counted_known
            policy._build_fixed_quest_head = counted_head
            if enabled:
                policy.choose_key(board)
            else:
                with decision_caches_disabled():
                    policy.choose_key(board)
            counts[enabled] = known_calls, head_calls
        self.assertGreater(counts[False][0], 0)
        self.assertGreater(counts[False][1], 0)
        self.assertLess(counts[True][0], counts[False][0])
        self.assertLess(counts[True][1], counts[False][1])

    def test_recorded_board_pins_claim_candidate_reuse(self):
        board = max(
            [parse_board(row) for row in load_rows("A")],
            key=lambda candidate: len(candidate.inventory),
        )
        counts = {}
        for enabled in (False, True):
            policy = build_policy()
            policy.prime(board)
            original = policy._town_need_candidates
            calls = 0

            def counted(snapshot):
                nonlocal calls
                calls += 1
                return original(snapshot)

            policy._town_need_candidates = counted
            if enabled:
                policy.choose_key(board)
            else:
                with decision_caches_disabled():
                    policy.choose_key(board)
            counts[enabled] = calls
        self.assertGreater(counts[False], 0)
        self.assertLess(
            counts[True], counts[False] // 2,
            f"claim candidates: uncached={counts[False]}, cached={counts[True]}",
        )

    def test_unchanged_map_reuses_fixed_quest_offers(self):
        board = parse_board(load_rows("A")[0])
        policy = build_policy()
        policy.prime(board)
        original = policy_module._fixed_quest_offers_from_grids
        calls = 0

        def counted(grids):
            nonlocal calls
            calls += 1
            return original(grids)

        policy_module._fixed_quest_offers_from_grids = counted
        try:
            policy._begin_map_predicate_cache(board)
            policy._begin_map_predicate_cache(replace(board))
        finally:
            policy_module._fixed_quest_offers_from_grids = original
        self.assertEqual(calls, 1)

    def test_town_fact_refresh_reuses_store_position_index(self):
        board = parse_board(load_rows("A")[0])
        policy = build_policy()
        policy.prime(board)
        policy._town_fact_region = policy._grid_region(board)
        policy._town_fact_snapshot = None
        policy_town_module._town_store_position_indices.pop(policy, None)
        original = policy_town_module._build_town_store_position_index
        calls = 0

        def counted(current):
            nonlocal calls
            calls += 1
            return original(current)

        policy_town_module._build_town_store_position_index = counted
        try:
            policy._begin_map_predicate_cache(board)
            policy._begin_map_predicate_cache(replace(board))
        finally:
            policy_town_module._build_town_store_position_index = original
        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()
