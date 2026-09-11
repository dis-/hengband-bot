from __future__ import annotations

from dataclasses import replace
import ast
import gzip
import inspect
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.cli import _parse_items
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.home_disposal import HomeDisposalState
from hengbot.model import STORE_HOME, STORE_WEAPON, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import ConservativePolicy
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from hengbot.terrain_knowledge import load_damaging_terrain_ids
from hengbot.town_maps import parse_town_map
from hengbot.wilderness_map import load_wilderness_map


FIXTURE = Path(__file__).parent / "fixtures" / "town-stall-restart-20260911.json.gz"
AMMO_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "departure-blocked-ammo-fragmentation-20260910.json.gz"
)


def _game_edit_dir() -> Path:
    configured = os.environ.get("HENGBOT_TEST_GAME_EDIT_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "bot-json-output" / "lib" / "edit"


def _fresh_incident_policy(sandbox: Path) -> ConservativePolicy:
    edit = _game_edit_dir()
    if not edit.is_dir():
        raise unittest.SkipTest(f"Hengband edit data unavailable: {edit}")
    town_files = {
        0: "01_Outpost_Full.txt",
        1: "02_Telmora.txt",
        2: "03_Morivant.txt",
        3: "04_Angwil.txt",
        4: "05_Zul.txt",
    }
    town_maps = {
        town_id: parse_town_map(edit / "towns" / filename)
        for town_id, filename in town_files.items()
    }
    disposal = HomeDisposalState(
        sandbox / "home-withdraw-history.jsonc",
        sandbox / "home-disposal-decisions.jsonc",
        sandbox / "home-disposal-queue.json",
        sandbox / "sol-events.jsonl",
    )
    policy = ConservativePolicy(
        town_map=town_maps[0],
        town_maps=town_maps,
        wilderness_map=load_wilderness_map(edit / "WildernessDefinition.txt"),
        dungeon_knowledge=load_dungeon_knowledge(edit / "DungeonDefinitions.jsonc"),
        monrace_knowledge=load_monrace_knowledge(edit / "MonraceDefinitions.jsonc"),
        damaging_terrain_ids=load_damaging_terrain_ids(edit / "TerrainDefinitions.jsonc"),
        quest_knowledge=load_quest_knowledge(edit / "quests"),
        quest_strategies=load_quest_strategies(
            Path(__file__).resolve().parents[1] / "strategy" / "quests"
        ),
        exploration_ledger_path=sandbox / "exploration-ledger.json",
        baseitem_costs=load_baseitem_costs(edit / "BaseitemDefinitions.jsonc"),
        home_disposal_state=disposal,
    )
    policy._loadout_report_path = sandbox / "loadout-report.jsonl"
    policy._confirmed_loadout_path = sandbox / "confirmed-loadout.json"
    calibration = sandbox / "character-calibration.json"
    shutil.copyfile(
        Path(__file__).parent / "fixtures" / "character-calibration-20260911.json",
        calibration,
    )
    policy._character_calibration_path = calibration
    return policy


def _consume_response(policy, response):
    if response.get("type") == "knowledge":
        knowledge = response.get("knowledge") or {}
        if (
            knowledge.get("category") == "home"
            and knowledge.get("menu_key") == "9"
            and policy._home_knowledge_scan_inflight
        ):
            policy.consume_home_knowledge(tuple(_parse_items(knowledge.get("items", ()))))
    elif response.get("type") == "character":
        character = response.get("character")
        if isinstance(character, dict):
            policy.observe_character_snapshot(character)


class TownStallIncidentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(prefix="hengbot-town-stall-")
        sandbox = Path(cls.scratch.name)
        previous = Path.cwd()
        os.chdir(sandbox)
        try:
            with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
                cls.rows = json.load(stream)
            cls.policy = _fresh_incident_policy(sandbox)
            cls.records = []
            cls.home_checks = []
            cls.shopping_stuck_events = []
            cls.probe_count_checks = []
            original_latch = cls.policy._set_town_store_attempted

            def record_latch(store_type, turn, reason, *args, **kwargs):
                if reason == "shopping-stuck":
                    cls.shopping_stuck_events.append((store_type, turn, reason))
                return original_latch(store_type, turn, reason, *args, **kwargs)

            cls.policy._set_town_store_attempted = record_latch
            for method_name in (
                "_commit_boxed_town_breakout_key",
                "_purchase_has_fresh_home_absence",
                "_town_procurement_progress_key",
            ):
                original = getattr(cls.policy, method_name)

                def record_probe_count(*args, _name=method_name, _original=original, **kwargs):
                    before = cls.policy._shop_approach_stuck_count
                    result = _original(*args, **kwargs)
                    if cls.current_fixture_index <= 52:
                        cls.probe_count_checks.append(
                            (_name, before, cls.policy._shop_approach_stuck_count)
                        )
                    return result

                setattr(cls.policy, method_name, record_probe_count)
            for index, row in enumerate(cls.rows):
                cls.current_fixture_index = index
                snapshot = parse_snapshot(row["snapshot"], cls.policy._monrace_knowledge)
                if snapshot.store is not None and snapshot.store.store_type == STORE_HOME:
                    ammo = [item for item in snapshot.inventory if item.tval == 18]
                    cls.home_checks.append((
                        row["decision"]["decision_sequence"],
                        [cls.policy._retention_surplus(snapshot, item) for item in ammo],
                        cls.policy._find_home_deposit(snapshot),
                    ))
                key = cls.policy.choose_key(snapshot)
                cls.records.append((key, cls.policy.last_reason, cls.policy._shop_approach_stuck_count))
                if key and row["decision"]["reason"] != "posting-contract:identical-repost-unobserved":
                    cls.policy.confirm_key_posted(key)
                for response in row.get("responses", ()):
                    _consume_response(cls.policy, response)
        finally:
            os.chdir(previous)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_01_single_snapshot_reserves_all_available_compatible_ammo(self):
        target = next(
            row for row in self.rows
            if row["decision"]["turn"] == 2768714
            and row["decision"]["decision_sequence"] >= 877
            and len([item for item in row["snapshot"].get("inventory", ()) if item.get("tval") == 18]) == 4
        )
        snapshot = parse_snapshot(target["snapshot"], self.policy._monrace_knowledge)
        strategy = self.policy._carry_procurement_strategy(snapshot)
        self.assertIsNotNone(strategy)
        status = self.policy._quest_carry_status(snapshot, strategy.required_force)
        self.assertEqual(status["throwing_items.launcher_ammo"]["required"], 99)
        ammo = [item for item in snapshot.inventory if item.tval == 18]
        details = [self.policy._retention_reservation_detail(snapshot, item) for item in ammo]
        self.assertEqual(details, [
            (11, "carry-strategy:launcher_ammo"),
            (31, "carry-strategy:launcher_ammo"),
            (19, "carry-strategy:launcher_ammo"),
            (19, "carry-strategy:launcher_ammo"),
        ])
        self.assertEqual([self.policy._retention_surplus(snapshot, item) for item in ammo], [0] * 4)
        deposit = self.policy._find_home_deposit(snapshot)
        self.assertTrue(deposit is None or deposit.tval != 18)

    def test_02_count_modified_inferior_stack_preserves_exact_target(self):
        with gzip.open(AMMO_FIXTURE, "rt", encoding="utf-8-sig") as stream:
            rows = json.load(stream)
        snapshot = None
        for row in rows:
            snapshot = parse_snapshot(row["snapshot"])
        weakest = next(item for item in snapshot.inventory if item.slot == "o")
        launcher = self.policy._equipped_launcher(snapshot)
        measured = self.policy._quest_launcher_average_damage(
            snapshot, launcher, require_carried_ammo=True
        )
        weakest = replace(
            weakest, to_d=weakest.to_d + max(0, math.ceil(25 - measured))
        )
        strongest = sorted(
            (item for item in snapshot.inventory if item.tval == weakest.tval and item is not weakest),
            key=lambda item: item.damage_dice_num * (item.damage_dice_sides + 1) / 2 + item.to_d,
            reverse=True,
        )
        strongest[0] = replace(strongest[0], count=99)
        changed = replace(
            snapshot,
            inventory=[
                strongest[0] if item.slot == strongest[0].slot
                else weakest if item.slot == weakest.slot else item
                for item in snapshot.inventory
            ],
        )
        self.assertGreaterEqual(
            self.policy._quest_launcher_average_damage(
                changed, launcher, require_carried_ammo=True
            ),
            25,
        )
        self.assertEqual(self.policy._retention_reservation(changed, weakest), 0)
        self.assertEqual(
            sum(self.policy._retention_reservation(changed, item) for item in changed.inventory if item.tval == weakest.tval),
            99,
        )

    def test_02b_excess_is_on_weakest_stack_in_single_ordered_pass(self):
        target = next(
            row for row in self.rows
            if row["decision"]["decision_sequence"] == 878
        )
        snapshot = parse_snapshot(target["snapshot"], self.policy._monrace_knowledge)
        ammo = [item for item in snapshot.inventory if item.tval == 18]
        strongest = max(
            ammo,
            key=lambda item: item.damage_dice_num * (item.damage_dice_sides + 1) / 2 + item.to_d,
        )
        changed = replace(
            snapshot,
            inventory=[
                replace(item, count=57) if item.slot == strongest.slot else item
                for item in snapshot.inventory
            ],
        )
        changed_ammo = [item for item in changed.inventory if item.tval == 18]
        self.assertEqual(sum(item.count for item in changed_ammo), 118)
        reservations = {
            item.slot: self.policy._retention_reservation(changed, item)
            for item in changed_ammo
        }
        surpluses = {
            item.slot: self.policy._retention_surplus(changed, item)
            for item in changed_ammo
        }
        self.assertEqual(reservations, {"o": 0, "p": 23, "q": 19, "r": 57})
        self.assertEqual(surpluses, {"o": 11, "p": 8, "q": 0, "r": 0})
        self.assertEqual(sum(reservations.values()), 99)
        self.assertEqual(sum(surpluses.values()), 19)
        state = self.policy.retention_reservation_state(changed)
        self.assertEqual(
            sum(
                row["reservation"] for row in state["retention_reservations"]
                if row["tval"] == 18
            ),
            99,
        )

    def test_02c_seed_home_pages_never_offer_compatible_ammo_for_deposit(self):
        checked = [entry for entry in self.home_checks if entry[0] >= 331]
        self.assertTrue(checked)
        for sequence, surpluses, deposit in checked:
            with self.subTest(sequence=sequence):
                self.assertTrue(all(surplus == 0 for surplus in surpluses))
                self.assertTrue(deposit is None or deposit.tval != 18)

    def test_03_seed_has_no_shopping_stuck_latch(self):
        self.assertEqual(self.shopping_stuck_events, [])
        for sequence in (882, 886, 888, 889):
            index = next(i for i, row in enumerate(self.rows) if row["decision"]["decision_sequence"] == sequence)
            self.assertEqual(self.records[index][0], self.rows[index]["decision"]["key"])
        row_890 = next(i for i, row in enumerate(self.rows) if row["decision"]["decision_sequence"] == 890)
        self.assertEqual(self.records[row_890][1], "shop:approach")
        self.assertEqual(self.policy._shopping_approach_store_type, STORE_WEAPON)
        self.assertNotIn(STORE_WEAPON, self.policy._town_store_attempted)

    def test_04_probe_paths_do_not_write_approach_stuck_count(self):
        self.assertTrue(self.probe_count_checks)
        self.assertTrue(all(before == after for _, before, after in self.probe_count_checks))

    def test_04b_only_settlement_writes_the_approach_counter(self):
        roots = Path(__file__).resolve().parents[1] / "src" / "hengbot"
        writes = []
        for source_path in roots.glob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                targets = []
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, ast.AugAssign):
                    targets = [node.target]
                if any(
                    isinstance(target, ast.Attribute)
                    and target.attr == "_shop_approach_stuck_count"
                    for target in targets
                ):
                    writes.append((source_path.name, node.lineno))
        allowed_files = {"policy.py", "policy_observation.py", "policy_shop.py"}
        self.assertTrue(writes)
        self.assertTrue(all(filename in allowed_files for filename, _ in writes))
        self.assertNotIn(
            "_shop_approach_stuck_count",
            inspect.getsource(type(self.policy)._shopping_approach_step),
        )
        self.assertNotIn(
            "_shop_approach_stuck_count",
            inspect.getsource(type(self.policy)._shopping_approach_key),
        )


if __name__ == "__main__":
    unittest.main()
