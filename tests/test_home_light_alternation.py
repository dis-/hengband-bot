from __future__ import annotations

from dataclasses import replace
import gzip
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.cli import _parse_items
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.home_disposal import HomeDisposalState
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import (
    find_monrace_definitions,
    load_monrace_knowledge,
)
from hengbot.policy import ConservativePolicy
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from hengbot.terrain_knowledge import load_damaging_terrain_ids
from hengbot.town_maps import parse_town_map
from hengbot.wilderness_map import load_wilderness_map


FIXTURE = Path(__file__).parent / "fixtures" / "home-light-loop-20260911.json.gz"


def _fresh_policy(sandbox: Path) -> ConservativePolicy:
    monrace_path = find_monrace_definitions(Path(__file__), None)
    quest_path = find_quest_definitions(Path(__file__))
    if monrace_path is None or quest_path is None:
        raise AssertionError("required Hengband edit definitions are unavailable")
    edit = monrace_path.parent
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
        monrace_knowledge=load_monrace_knowledge(monrace_path),
        damaging_terrain_ids=load_damaging_terrain_ids(
            edit / "TerrainDefinitions.jsonc"
        ),
        quest_knowledge=load_quest_knowledge(quest_path),
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


def _consume_response(policy: ConservativePolicy, response: dict) -> None:
    if response.get("type") != "knowledge":
        return
    knowledge = response.get("knowledge") or {}
    if (
        knowledge.get("category") == "home"
        and knowledge.get("menu_key") == "9"
        and policy._home_knowledge_scan_inflight
    ):
        policy.consume_home_knowledge(tuple(_parse_items(knowledge.get("items", ()))))


class HomeLightAlternationPins(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scratch = tempfile.TemporaryDirectory(prefix="hengbot-home-light-pin-")
        sandbox = Path(cls.scratch.name)
        previous = Path.cwd()
        os.chdir(sandbox)
        os.environ["HENGBOT_HOME_HISTORY_DIR"] = str(sandbox)
        try:
            with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
                cls.rows = json.load(stream)
            cls.policy = _fresh_policy(sandbox)
            cls.records = {}
            cls.snapshots = {}
            cls.home_refusals = []
            current_sequence = [None]
            original = cls.policy._equipment_transaction_home_key

            def record_home(snapshot, *args, **kwargs):
                result = original(snapshot, *args, **kwargs)
                if result is None and cls.policy.last_reason == (
                    "equipment-transaction:defer-identification"
                ):
                    cls.home_refusals.append(current_sequence[0])
                return result

            cls.policy._equipment_transaction_home_key = record_home
            for row in cls.rows:
                decision = row["decision"]
                sequence = decision["decision_sequence"]
                current_sequence[0] = sequence
                snapshot = parse_snapshot(
                    row["snapshot"], cls.policy._monrace_knowledge
                )
                cls.snapshots[sequence] = snapshot
                key = cls.policy.choose_key(snapshot)
                cls.records[sequence] = (cls.policy.last_reason, key)
                if key and decision["reason"] != (
                    "posting-contract:identical-repost-unobserved"
                ):
                    cls.policy.confirm_key_posted(key)
                for response in row.get("responses", ()):
                    _consume_response(cls.policy, response)
        finally:
            os.chdir(previous)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.scratch.cleanup()

    def test_pin_s_and_c_incident_trajectory(self):
        self.assertEqual(len(self.rows), 121)
        expected = {
            row["decision"]["decision_sequence"]: (
                row["decision"]["reason"], row["decision"]["key"]
            )
            for row in self.rows
        }
        for sequence in range(452, 487):
            self.assertEqual(self.records[sequence], expected[sequence])
        self.assertFalse(self.records[487][1].startswith("w"))
        self.assertEqual(self.records[496], expected[496])
        self.assertEqual(self.records[497], expected[497])
        self.assertEqual(
            self.records[499],
            ("equipment-transaction:defer-identification", "\x1b"),
        )
        self.assertNotEqual(self.records[500][0], "wield-light")
        tail = [self.records[sequence][0] for sequence in range(487, 568)]
        self.assertNotIn("wield-light", tail)
        self.assertNotIn("policy:none-store-exit", tail)
        self.assertIn(499, self.home_refusals)

    def test_pin_a1_unknown_upgrade_is_not_selected(self):
        snapshot = self.snapshots[487]
        unknown = next(item for item in snapshot.inventory if item.slot == "k")
        self.assertTrue(self.policy._equip_blocked_by_identification(unknown))
        self.assertIsNone(self.policy._light_to_wield(snapshot))

    def test_pin_a2_empty_slot_prefers_identified_light(self):
        snapshot = self.snapshots[487]
        worn = next(item for item in snapshot.equipment if item.is_light)
        unknown = next(item for item in snapshot.inventory if item.slot == "k")
        carried = replace(worn, slot="z")
        changed = replace(snapshot, equipment=[], inventory=[unknown, carried])
        self.assertIs(self.policy._light_to_wield(changed), carried)

    def test_pin_d_b1_executor_backstop(self):
        snapshot = self.snapshots[487]
        unknown = next(item for item in snapshot.inventory if item.slot == "k")
        self.assertIsNone(
            self.policy._equipment_wield(
                snapshot, "combat-loadout", unknown, "light"
            )
        )
        self.assertEqual(
            self.policy.last_reason, "equipment-mutation:identify-first"
        )

    def test_pin_p_struct_and_disposal_product(self):
        snapshot = self.snapshots[487]
        unknown = next(item for item in snapshot.inventory if item.slot == "k")
        for feeling in ("", "none", "good", "excellent", "special"):
            item = replace(unknown, pseudo_feeling=feeling)
            self.assertTrue(self.policy._equip_blocked_by_identification(item))
            self.assertTrue(
                self.policy._disposal_protected_by_identification(item)
            )
        for feeling in (
            "average", "uncursed", "cursed", "terrible", "worthless", "broken"
        ):
            self.assertFalse(
                self.policy._disposal_protected_by_identification(
                    replace(unknown, pseudo_feeling=feeling)
                )
            )


if __name__ == "__main__":
    unittest.main()
