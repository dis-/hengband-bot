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
from hengbot.model import (
    DUNGEON_YEEK_CAVE,
    MonsterState,
    Position,
    Snapshot,
    StoreState,
    STORE_GENERAL,
    STORE_ALCHEMIST,
    STORE_HOME,
    SV_FLASK_OIL,
    SV_LITE_LANTERN,
    SV_LITE_TORCH,
    SV_LITE_FEANOR,
    SV_SCROLL_IDENTIFY,
    SV_SCROLL_STAR_IDENTIFY,
    SV_STAFF_IDENTIFY,
    SV_SCROLL_DETECT_TREASURE,
    TVAL_DIGGING,
    TVAL_FLASK,
    TVAL_FOOD,
    TVAL_LITE,
    TVAL_POTION,
    TVAL_SCROLL,
    TVAL_STAFF,
    TVAL_SWORD,
    TVAL_WAND,
)
from hengbot.monrace_knowledge import (
    find_monrace_definitions,
    load_monrace_knowledge,
)
from hengbot.policy import (
    ConservativePolicy, FULL_IDENTIFY_DISMISS_SUFFIX, READ_KEY, REFILL_KEY,
    USE_STAFF_KEY, equipment_identity,
)
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_navigator import QuestFloorNavigator
from hengbot.quest_strategies import load_quest_strategies
from hengbot.terrain_knowledge import load_damaging_terrain_ids
from hengbot.town_maps import parse_town_map
from hengbot.wilderness_map import load_wilderness_map
from hengbot.policy import LEAVE_STORE_KEY, WAIT_KEY
from hengbot.policy_constants import (
    IDENTIFY_PRESSURE_FREE_SLOTS, PACK_CAPACITY, Q2_BREACH_POSITION,
)
from hengbot.policy_identification import IDENTIFY_ITEM_PROMPT, SOURCE_PROMPT
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from tests.policy_fixtures import grid, item, player, store_item


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


class DungeonIdentificationPins(unittest.TestCase):
    def setUp(self) -> None:
        self.scratch = tempfile.TemporaryDirectory(prefix="hengbot-d6-pin-")
        sandbox = Path(self.scratch.name)
        previous = Path.cwd()
        os.chdir(sandbox)
        os.environ["HENGBOT_HOME_HISTORY_DIR"] = str(sandbox)
        try:
            self.policy = _fresh_policy(sandbox)
        finally:
            os.chdir(previous)

    def tearDown(self) -> None:
        self.scratch.cleanup()

    @staticmethod
    def _snapshot(*, feeling="", monsters=(), source=True, turn=100) -> Snapshot:
        inventory = []
        if source:
            inventory.append(
                item(
                    "i", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=10,
                    name="Staff of Identify",
                )
            )
        inventory.append(
            item(
                "s", TVAL_SWORD, 1, known=False, is_equipment=True,
                pseudo_feeling=feeling, name="Unknown sword",
            )
        )
        return Snapshot(
            player(10, 10, class_id=0),
            {Position(10, 10): grid(10, 10, lit=True, in_view=True)},
            list(monsters),
            inventory=inventory,
            floor_key=(DUNGEON_YEEK_CAVE, 3, 0),
            turn=turn,
        )

    def test_pin_d6_1_real_dungeon_producer(self):
        snap = self._snapshot()
        key = self.policy.choose_key(snap)
        self.assertEqual(
            (self.policy.last_reason, key),
            ("identify:dungeon-equipment", "uis"),
        )
        chain = self.policy.peek_staged_prompt_chain()
        self.assertIs(chain, self.policy.peek_staged_prompt_chain())
        self.assertEqual(
            chain,
            {
                "owner": "identify:dungeon-equipment",
                "key": "uis",
                "sequence": self.policy._decision_sequence,
                "turn": snap.turn,
                "gates": (
                    (1, SOURCE_PROMPT[USE_STAFF_KEY]),
                    (2, IDENTIFY_ITEM_PROMPT),
                ),
            },
        )

    def test_pin_d6_2_visible_hostile_blocks_producer(self):
        hostile = MonsterState(
            1, Position(20, 20), 5, 5, 14, False, False,
            asleep=True, name="distant hostile",
        )
        key = self.policy.choose_key(self._snapshot(monsters=[hostile]))
        self.assertNotEqual(self.policy.last_reason, "identify:dungeon-equipment")
        self.assertNotEqual(key, "uis")
        self.assertIsNone(self.policy.peek_staged_prompt_chain())

    def test_pin_d6_3_no_source_never_leaks_wield_key(self):
        snap = self._snapshot(source=False)
        first = self.policy.choose_key(snap)
        first_reason = self.policy.last_reason
        second = self.policy.choose_key(replace(snap, turn=snap.turn + 1))
        self.assertFalse(first_reason.startswith("identify:"), (first_reason, first))
        self.assertFalse(self.policy.last_reason.startswith("identify:"))
        self.assertNotEqual(first, "w")
        self.assertNotEqual(second, "w")
        self.assertIsNone(self.policy.peek_staged_prompt_chain())

    def test_pin_d6_4_curse_suspect_feelings_are_excluded(self):
        for feeling in ("cursed", "terrible", "worthless"):
            with self.subTest(feeling=feeling):
                policy = _fresh_policy(Path(self.scratch.name))
                key = policy.choose_key(self._snapshot(feeling=feeling))
                self.assertFalse(
                    policy.last_reason.startswith("identify:"),
                    (feeling, policy.last_reason, key),
                )
                self.assertIsNone(policy.peek_staged_prompt_chain())
        policy = _fresh_policy(Path(self.scratch.name))
        self.assertEqual(policy.choose_key(self._snapshot()), "uis")

    def test_pin_prompt_chain_resets_at_each_choose_key(self):
        snap = self._snapshot()
        self.assertEqual(self.policy.choose_key(snap), "uis")
        self.assertIsNotNone(self.policy.peek_staged_prompt_chain())
        without_source = replace(
            snap,
            turn=snap.turn + 1,
            inventory=[item(
                "s", TVAL_SWORD, 1, known=False, is_equipment=True,
                pseudo_feeling="", name="Unknown sword",
            )],
        )
        self.policy.choose_key(without_source)
        self.assertIsNone(self.policy.peek_staged_prompt_chain())

    def test_pin_f_s1_pack_pressure_shared_tail_and_no_port_narrowing(self):
        filler = [
            item(chr(ord("a") + n), TVAL_WAND, n, name=f"filler-{n}")
            for n in range(
                PACK_CAPACITY - IDENTIFY_PRESSURE_FREE_SLOTS - 2
            )
        ]
        staff = item(
            "s", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=10,
            name="Staff of Identify",
        )
        unknown = item("t", TVAL_POTION, 3, known=False, name="murky potion")
        snap = replace(
            self._snapshot(),
            inventory=[*filler, staff, unknown],
            floor_key=(DUNGEON_YEEK_CAVE, 12, 0),
        )
        self.assertEqual(self.policy._pack_pressure_identify_key(snap), "ust")
        chain = self.policy.peek_staged_prompt_chain()
        self.assertIsNotNone(chain)
        self.assertEqual(chain["owner"], "identify:pack-pressure")
        self.assertEqual(chain["key"], "ust")
        self.assertEqual(
            chain["gates"],
            ((1, SOURCE_PROMPT[USE_STAFF_KEY]), (2, IDENTIFY_ITEM_PROMPT)),
        )

        no_port = _fresh_policy(Path(self.scratch.name))
        no_port._prompt_gated_posting = False
        before = no_port.last_reason
        self.assertIsNone(no_port._pack_pressure_identify_key(snap))
        self.assertEqual(no_port.last_reason, before)
        self.assertIsNone(no_port.peek_staged_prompt_chain())
        d6_key = no_port.choose_key(self._snapshot())
        self.assertFalse(no_port.last_reason.startswith("identify:"), d6_key)

    def test_pin_restore_checkpoint_prompt_chain_defaults(self):
        encoded = checkpoint(self.policy)
        state = self.policy.__dict__
        staged = state.pop("_staged_prompt_chain")
        gated = state.pop("_prompt_gated_posting")
        try:
            legacy = checkpoint(self.policy)
        finally:
            state["_staged_prompt_chain"] = staged
            state["_prompt_gated_posting"] = gated
        restored = restore_checkpoint(type(self.policy), legacy)
        self.assertIn("_staged_prompt_chain", restored.__dict__)
        self.assertIn("_prompt_gated_posting", restored.__dict__)
        self.assertIsNone(restored._staged_prompt_chain)
        self.assertIs(restored._prompt_gated_posting, True)
        current = restore_checkpoint(type(self.policy), encoded)
        self.assertIsNone(current._staged_prompt_chain)
        self.assertIs(current._prompt_gated_posting, True)


class DiggerQuestPins(unittest.TestCase):
    def setUp(self) -> None:
        self.scratch = tempfile.TemporaryDirectory(prefix="hengbot-digger-pin-")
        sandbox = Path(self.scratch.name)
        previous = Path.cwd()
        os.chdir(sandbox)
        os.environ["HENGBOT_HOME_HISTORY_DIR"] = str(sandbox)
        try:
            self.policy = _fresh_policy(sandbox)
        finally:
            os.chdir(previous)

    def tearDown(self) -> None:
        self.scratch.cleanup()

    @staticmethod
    def _snapshot(
        inventory, *, equipment=(), town=False, store=None, gold=5000,
        floor_key=None,
    ) -> Snapshot:
        if floor_key is None:
            floor_key = (0, 0, 0) if town else (DUNGEON_YEEK_CAVE, 1, 0)
        return Snapshot(
            player(10, 10, gold=gold, class_id=0),
            {Position(10, 10): grid(10, 10, lit=True, in_view=True)},
            [],
            inventory=list(inventory),
            equipment=list(equipment),
            floor_key=floor_key,
            town_flag=town,
            town_id=0 if town else -1,
            store=store,
        )

    @staticmethod
    def _common_diggers():
        unknown = item(
            "x", TVAL_DIGGING, 1, known=False, is_equipment=True,
            pseudo_feeling="",
        )
        pick = item("y", TVAL_DIGGING, 4, pval=1, is_equipment=True)
        mattock = item("z", TVAL_DIGGING, 7, pval=2, is_equipment=True)
        return unknown, pick, mattock

    @staticmethod
    def _light(slot, sval, *, fuel, known=True, cursed=False):
        return item(
            slot, TVAL_LITE, sval, fuel=fuel, known=known,
            is_cursed=cursed, is_equipment=True,
        )

    def _assert_light_not_removed(self, key, worn):
        self.assertFalse(
            key.startswith("t") and worn.slot in key,
            (self.policy.last_reason, key),
        )

    def test_pin_a3_d5_last_resort_family(self):
        unknown = self._light("f", SV_LITE_FEANOR, fuel=0, known=False)
        cases = []

        empty = self._snapshot([unknown])
        empty = replace(empty, player=replace(empty.player, class_id=-1))
        cases.append(("A3a", empty, "wf", "wield-light"))

        for name, fuel, town, extras, expected, reason in (
            ("A3b", 100, False, (), "wf", "wield-light"),
            ("A3c", 101, False, (), None, None),
            ("A3d", 100, False,
             (item("o", TVAL_FLASK, SV_FLASK_OIL, name="Flask of oil", fuel=5000),),
             REFILL_KEY + "o", "refill-light"),
            ("A3e", 100, False,
             (self._light("t", SV_LITE_TORCH, fuel=5000),),
             "wt", "wield-light"),
            ("A3f", 100, True, (), None, None),
            ("A3g", 0, False, (), "wf", "wield-light"),
        ):
            worn = self._light("light", SV_LITE_LANTERN, fuel=fuel)
            snap = self._snapshot([unknown, *extras], equipment=[worn], town=town)
            snap = replace(snap, player=replace(snap.player, class_id=-1))
            cases.append((name, snap, expected, reason))

        for name, snap, expected, reason in cases:
            with self.subTest(pin=name):
                policy = _fresh_policy(Path(self.scratch.name))
                key = policy.choose_key(snap)
                if expected is None:
                    self.assertNotEqual(key, "wf", (policy.last_reason, key))
                    self.assertNotEqual(policy.last_reason, "wield-light")
                else:
                    self.assertEqual(key, expected, (policy.last_reason, key))
                    self.assertEqual(policy.last_reason, reason)
                worn = next((it for it in snap.equipment if it.is_light), None)
                if worn is not None:
                    self.assertFalse(key.startswith("t") and worn.slot in key)

    def test_pin_a3h_unknown_empty_slot_is_dungeon_only(self):
        unknown = self._light("k", SV_LITE_FEANOR, fuel=0, known=False)

        town_policy = _fresh_policy(Path(self.scratch.name))
        town = self._snapshot([unknown], town=True)
        town = replace(town, player=replace(town.player, class_id=-1))
        town_key = town_policy.choose_key(town)
        self.assertFalse(
            town_key.startswith("w") and "k" in town_key,
            (town_policy.last_reason, town_key),
        )
        self.assertNotEqual(town_policy.last_reason, "wield-light")

        dungeon_policy = _fresh_policy(Path(self.scratch.name))
        dungeon = self._snapshot([unknown])
        dungeon = replace(dungeon, player=replace(dungeon.player, class_id=-1))
        dungeon_key = dungeon_policy.choose_key(dungeon)
        self.assertEqual(dungeon_key, "wk", (dungeon_policy.last_reason, dungeon_key))
        self.assertEqual(dungeon_policy.last_reason, "wield-light")

    def test_pin_f1_f2_and_f2_prime_fundraising_light(self):
        known_torch = self._light("t", SV_LITE_TORCH, fuel=5000)
        unknown_lamp = self._light("f", SV_LITE_FEANOR, fuel=0, known=False)
        worn_lantern = self._light("light", SV_LITE_LANTERN, fuel=99)
        self.policy._fundraising_mode = "mine"
        snap = self._snapshot(
            [known_torch, unknown_lamp], equipment=[worn_lantern]
        )
        self.assertEqual(self.policy.choose_key(snap), "wt")
        self.assertEqual(self.policy.last_reason, "fundraise:wield-light")

        for fuel, expected in ((99, "wl"), (200, None)):
            with self.subTest(pin="F2" if fuel == 99 else "F2-prime"):
                policy = _fresh_policy(Path(self.scratch.name))
                policy._fundraising_mode = "mine"
                worn = self._light("light", SV_LITE_TORCH, fuel=fuel)
                lantern = self._light("l", SV_LITE_LANTERN, fuel=0, known=False)
                oils = item(
                    "o", TVAL_FLASK, SV_FLASK_OIL, name="Flask of oil",
                    count=5, fuel=5000
                )
                key = policy.choose_key(self._snapshot(
                    [lantern, oils], equipment=[worn]
                ))
                if expected is None:
                    self.assertNotEqual(key, "wl", (policy.last_reason, key))
                    self.assertNotEqual(policy.last_reason, "fundraise:wield-light")
                else:
                    self.assertEqual(key, expected, (policy.last_reason, key))
                    self.assertEqual(policy.last_reason, "fundraise:wield-light")

    def test_pin_d3_1_restore_weapon_guard_equivalence(self):
        digger = item(
            "main_hand", TVAL_DIGGING, 1, is_equipment=True, known=True
        )
        variants = (
            (item("s", TVAL_SWORD, 1, is_equipment=True, known=True,
                  is_ego=True, fully_known=False), True),
            (item("s", TVAL_SWORD, 1, is_equipment=True, known=False), False),
            (item("s", TVAL_SWORD, 1, is_equipment=True, known=True,
                  is_cursed=True), False),
        )
        for sword, should_wield in variants:
            with self.subTest(known=sword.known, cursed=sword.is_cursed):
                policy = _fresh_policy(Path(self.scratch.name))
                policy._fundraising_mode = "mine"
                snap = self._snapshot([sword], equipment=[digger], town=True)
                key = policy.choose_key(snap)
                if should_wield:
                    self.assertTrue(key.startswith("ws"), (policy.last_reason, key))
                    self.assertEqual(policy.last_reason, "town:restore-combat-weapon")
                else:
                    self.assertFalse(
                        key.startswith("ws") and
                        policy.last_reason == "town:restore-combat-weapon",
                        (policy.last_reason, key),
                    )

    def test_pin_d3_2_full_identify_does_not_start_alternation(self):
        sword = item(
            "main_hand", TVAL_SWORD, 1, is_equipment=True, known=True,
            is_ego=True, fully_known=False,
        )
        scroll = item("i", TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, known=True)
        snap = self._snapshot([scroll], equipment=[sword], town=True)
        key = self.policy.choose_key(snap)
        self.assertEqual(key, READ_KEY + "i/a" + FULL_IDENTIFY_DISMISS_SUFFIX)
        self.assertEqual(self.policy.last_reason, "identify:full-equipped")
        self.assertNotIn("t", key)
        self.assertFalse(self.policy._equip_blocked_by_identification(sword))
        self.assertTrue(self.policy._identification_flow_candidate(sword))

    def test_pin_c1_calibration_drops_identify_blocked_redress(self):
        lamp = self._light("k", SV_LITE_FEANOR, fuel=0, known=False)
        snap = self._snapshot([lamp], town=True)
        self.policy._calibration_worn_before = (
            ("light", equipment_identity(lamp)),
        )
        self.policy._calibration_stripped_unrestored = True
        self.assertIsNone(self.policy._calibration_redress_key(snap))
        self.assertEqual(self.policy._calibration_worn_before, ())
        key = self.policy.choose_key(snap)
        self.assertNotEqual(key, "wk", (self.policy.last_reason, key))

    def test_pin_l1_darkness_torch_rejects_cursed(self):
        cursed = self._light("c", SV_LITE_TORCH, fuel=3000, cursed=True)
        dark = replace(
            self._snapshot([cursed]), can_see_own_grid=False,
        )
        self.assertIsNone(self.policy._darkness_torch(dark))
        key = self.policy.choose_key(dark)
        self.assertNotEqual(key, "wc", (self.policy.last_reason, key))

        safe = self._light("d", SV_LITE_TORCH, fuel=2000)
        changed = replace(dark, inventory=[cursed, safe])
        self.assertEqual(self.policy.choose_key(changed), "wd")
        self.assertEqual(self.policy.last_reason, "wield-light")

    def test_pin_q34_2_exemption_is_call_site_scoped(self):
        lantern = self._light("l", SV_LITE_LANTERN, fuel=0, known=False)
        torch = self._light("light", SV_LITE_TORCH, fuel=5000)
        snap = self._snapshot(
            [lantern], equipment=[torch], floor_key=(0, 34, 0)
        )
        self.assertIsNone(self.policy._equipment_wield(
            snap, "quest-launcher", lantern, "light"
        ))
        self.assertEqual(
            self.policy.last_reason, "equipment-mutation:identify-first"
        )
        key = self.policy.choose_key(snap)
        self.assertNotEqual(key, "wl", (self.policy.last_reason, key))
        occurrences = []
        root = Path(__file__).resolve().parents[1] / "src" / "hengbot"
        for source in root.glob("*.py"):
            for number, line in enumerate(
                source.read_text(encoding="utf-8").splitlines(), 1
            ):
                if "quest_contract_exempt=True" in line:
                    occurrences.append((source.name, number, line.strip()))
        self.assertEqual(len(occurrences), 1, occurrences)
        self.assertEqual(occurrences[0][0], "policy_quest.py")

    def _d4_inventory(self, detection_count, *, source=True, digger=True):
        inventory = [
            self._light("k", SV_LITE_FEANOR, fuel=0, known=False),
            item("f", TVAL_FOOD, 35, count=5),
        ]
        if source:
            inventory.extend((
                item("i", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=10),
                item("j", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=10),
            ))
        if digger:
            inventory.append(item(
                "d", TVAL_DIGGING, 4, pval=1, is_equipment=True
            ))
        if detection_count:
            inventory.append(item(
                "r", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE,
                count=detection_count,
            ))
        return inventory

    def test_pin_d4_1_and_d4_2_identification_gate_order(self):
        worn = self._light("light", SV_LITE_LANTERN, fuel=5000)
        for count, complete in ((5, True), (0, False)):
            with self.subTest(pin="D4-1" if complete else "D4-2"):
                policy = _fresh_policy(Path(self.scratch.name))
                policy._fundraising_mode = "prepare"
                snap = self._snapshot(
                    self._d4_inventory(count), equipment=[worn], town=True
                )
                snap = replace(
                    snap, player=replace(snap.player, device_skill=24)
                )
                key = policy.choose_key(snap)
                if complete:
                    self.assertEqual(key, USE_STAFF_KEY + "ik")
                    self.assertEqual(policy.last_reason, "identify:normal")
                    self.assertNotIn("wk", key)
                else:
                    self.assertFalse(
                        policy.last_reason.startswith("identify:"),
                        (policy.last_reason, key),
                    )
                    self.assertFalse(key.startswith("w"), (policy.last_reason, key))

    def test_pin_d4_3_identify_purchase_uses_post_kit_gold(self):
        worn = self._light("light", SV_LITE_LANTERN, fuel=5000)
        oil = item(
            "o", TVAL_FLASK, SV_FLASK_OIL, count=5, fuel=5000
        )
        inventory = [*self._d4_inventory(5, source=False), oil]
        self.policy._fundraising_mode = "prepare"
        outside = self._snapshot(
            inventory, equipment=[worn], town=True, gold=200
        )
        self.policy.choose_key(outside)
        self.assertEqual(self.policy._identification_need, "normal")

        identify = store_item(
            "a", TVAL_SCROLL, SV_SCROLL_IDENTIFY, price=50,
            name="Scroll of Identify",
        )
        alchemist = replace(
            outside,
            store=StoreState(STORE_ALCHEMIST, [identify]),
        )
        self.assertIs(self.policy._next_purchase(alchemist), identify)

        incomplete = replace(
            alchemist,
            player=replace(alchemist.player, gold=30),
            inventory=[
                carried for carried in alchemist.inventory
                if not carried.is_digging_tool
            ],
        )
        self.assertIsNot(self.policy._next_purchase(incomplete), identify)

    def _assert_unknown_digger_fixture(self, snapshot, unknown) -> None:
        self.assertEqual(self.policy._retention_surplus(snapshot, unknown), unknown.count)
        self.assertTrue(self.policy._entire_stack_is_surplus(snapshot, unknown))
        self.assertFalse(self.policy._is_surplus_digging_tool(snapshot, unknown))
        self.assertTrue(
            self.policy._disposal_protected_by_identification(unknown)
        )

    def _pressured_pack(self, *extras) -> Snapshot:
        filler_count = PACK_CAPACITY - len(extras)
        filler = [
            item(chr(ord("a") + index), TVAL_WAND, index, name=f"filler-{index}")
            for index in range(filler_count)
        ]
        return self._snapshot([*filler, *extras])

    def _drive_home_knowledge_scan(self, items) -> None:
        outside = self._snapshot([], town=True)
        home_position = Position(10, 11)
        outside = replace(
            outside,
            grids={
                **outside.grids,
                home_position: replace(
                    grid(10, 11), store_number=STORE_HOME
                ),
            },
        )
        key = self.policy.choose_key(outside)
        self.assertEqual(key, "~9\x1b\x1b")
        self.assertEqual(self.policy.last_reason, "home:request-knowledge-scan")
        self.assertTrue(self.policy.confirm_key_posted(key))
        _consume_response(self.policy, {
            "type": "knowledge",
            "knowledge": {
                "category": "home", "menu_key": "9", "items": items,
            },
        })
        self.assertTrue(self.policy._equipment_catalog.home_scan_complete)

    def test_pin_m1_mining_loadout_identify_first(self):
        unknown = item("p", TVAL_DIGGING, 1, known=False, is_equipment=True)
        known = item("q", TVAL_DIGGING, 4, pval=1, is_equipment=True)
        snapshot = self._snapshot([unknown, known])
        self.policy._fundraising_mode = "mine"

        key = self.policy._wield_digging_tool_key(
            snapshot, "fundraise:wield-digging-tool"
        )
        self.assertIsNotNone(key)
        self.assertTrue(key.startswith("wq"), key)
        self.assertNotIn("p", key)

        only_unknown = replace(snapshot, inventory=[unknown])
        self.assertIsNone(self.policy._wield_digging_tool_key(
            only_unknown, "fundraise:wield-digging-tool"
        ))
        chosen = self.policy.choose_key(only_unknown)
        self.assertFalse(chosen.startswith("wp"), (self.policy.last_reason, chosen))
        self.assertNotEqual(
            self.policy.last_reason, "fundraise:wield-digging-tool"
        )
        self.assertNotEqual(
            self.policy.last_reason, "fundraise:abandon-unwieldable-digger"
        )

    def test_pin_m2_unknown_pack_digger_does_not_complete_kit(self):
        unknown = item("p", TVAL_DIGGING, 1, known=False, is_equipment=True)
        detection = item(
            "d", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=5
        )
        food = item("f", TVAL_FOOD, 35, count=5)
        lantern = item(
            "light", TVAL_LITE, SV_LITE_LANTERN, is_equipment=True, fuel=5000
        )
        snapshot = self._snapshot(
            [unknown, detection, food], equipment=[lantern], town=True, gold=500
        )
        self.policy._fundraising_mode = "prepare"

        self.assertFalse(self.policy._has_digging_tool(snapshot))
        self.assertEqual(self.policy._digging_tool_count(snapshot), 0)
        self.assertEqual(self.policy._withdrawable_digging_tool_count(snapshot), 0)
        self.assertFalse(self.policy._fundraising_supplies_ready(snapshot))
        needs = self.policy._town_need_candidates(snapshot)
        self.assertTrue(any(
            need.store_type == STORE_GENERAL and need.category == "mining-digger"
            for need in needs
        ), needs)
        key = self.policy.choose_key(snapshot)
        self.assertNotEqual(
            self.policy.last_reason, "fundraise:abandon-unwieldable-digger"
        )
        self.assertNotEqual(key, "wp")

    def test_pin_m2_unknown_home_digger_does_not_satisfy_home_first(self):
        self._drive_home_knowledge_scan([{
            "slot": 1,
            "name": "Shovel",
            "count": 1,
            "tval": TVAL_DIGGING,
            "sval": 1,
            "aware": True,
            "known": False,
            "is_equipment": True,
        }])
        detection = item(
            "d", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE, count=5
        )
        food = item("f", TVAL_FOOD, 35, count=5)
        lantern = item(
            "light", TVAL_LITE, SV_LITE_LANTERN, is_equipment=True, fuel=5000
        )
        snapshot = self._snapshot(
            [detection, food], equipment=[lantern], town=True, gold=500
        )
        self.policy._fundraising_mode = "prepare"
        self.assertEqual(self.policy._withdrawable_digging_tool_count(snapshot), 0)
        self.assertFalse(self.policy._fundraising_supplies_ready(snapshot))
        needs = self.policy._town_need_candidates(snapshot)
        self.assertFalse(any(
            need.store_type == STORE_HOME and need.category == "stored-digger"
            for need in needs
        ), needs)
        self.assertTrue(any(
            need.store_type == STORE_GENERAL and need.category == "mining-digger"
            for need in needs
        ), needs)

    def test_pin_m3_destroy_and_average_invariant(self):
        unknown, pick, mattock = self._common_diggers()
        potion = item("w", TVAL_POTION, 28, name="slowness potion")
        snapshot = self._pressured_pack(unknown, potion, pick, mattock)
        self.assertIs(self.policy._find_disposable_item(snapshot), potion)
        self.assertIn("w", self.policy._full_pack_destroy_key(snapshot))
        self.assertEqual(
            self.policy.last_reason, "inventory:destroy-disposable-item"
        )
        self._assert_unknown_digger_fixture(snapshot, unknown)

        average = replace(unknown, pseudo_feeling="average")
        average_snapshot = replace(snapshot, inventory=[
            average if carried is unknown else carried
            for carried in snapshot.inventory
        ])
        self.assertFalse(
            self.policy._disposal_protected_by_identification(average)
        )
        self.assertTrue(
            self.policy._is_surplus_digging_tool(average_snapshot, average)
        )
        self.assertIs(
            self.policy._find_disposable_item(average_snapshot), average
        )

    def test_pin_m3_sale(self):
        unknown, pick, mattock = self._common_diggers()
        unknown = replace(unknown, inscription="@0")
        snapshot = self._snapshot(
            [unknown, pick, mattock], town=True,
            store=StoreState(STORE_GENERAL, []),
        )
        self._assert_unknown_digger_fixture(snapshot, unknown)
        self.assertTrue(self.policy._sale_retains_digging_tool(snapshot, unknown))
        self.assertEqual(
            self.policy._batch_sell_key(snapshot, [unknown]), LEAVE_STORE_KEY
        )
        self.assertEqual(
            self.policy.last_reason, "shop:retain-standing-digging-tool"
        )
        self.assertIsNone(self.policy._batch_sell_pending)

    def test_pin_m3_sale_finder_agrees_with_gate(self):
        cursed = item(
            "c", TVAL_DIGGING, 4, known=True, is_equipment=True,
            is_ego=True, is_cursed=True, pval=1,
        )
        better = item("y", TVAL_DIGGING, 4, pval=2, is_equipment=True)
        mattock = item("z", TVAL_DIGGING, 7, pval=2, is_equipment=True)
        one_better = self._snapshot([cursed, better], town=True)
        self.assertFalse(
            self.policy._disposal_protected_by_identification(cursed)
        )
        self.assertTrue(
            self.policy._sale_retains_digging_tool(one_better, cursed)
        )
        self.assertIsNone(self.policy._find_low_level_sale(one_better))

        two_better = replace(one_better, inventory=[cursed, better, mattock])
        self.assertFalse(
            self.policy._sale_retains_digging_tool(two_better, cursed)
        )
        self.assertIs(self.policy._find_low_level_sale(two_better), cursed)

    def test_pin_m3_transaction_home_selector(self):
        unknown, pick, mattock = self._common_diggers()
        snapshot = self._snapshot(
            [unknown, pick, mattock], town=True,
            store=StoreState(STORE_HOME, []),
        )
        self.assertIsNone(self.policy._find_home_deposit(snapshot))
        self._assert_unknown_digger_fixture(snapshot, unknown)

    def test_pin_m3_organization_after_real_home_scan(self):
        self._drive_home_knowledge_scan([])
        unknown, pick, mattock = self._common_diggers()
        snapshot = self._snapshot(
            [unknown, pick, mattock], town=True,
            store=StoreState(STORE_HOME, []),
        )
        self.assertIsNone(
            self.policy._find_town_organization_surplus(snapshot)
        )
        self._assert_unknown_digger_fixture(snapshot, unknown)

    def test_pin_m3_exchange(self):
        unknown, pick, mattock = self._common_diggers()
        shovel_cost = self.policy._baseitem_costs[(TVAL_DIGGING, 1)]
        potion_sval, potion_cost = next(
            ((tval_sval[1], cost) for tval_sval, cost in self.policy._baseitem_costs.items()
             if tval_sval[0] == TVAL_POTION and shovel_cost < cost < 50),
        )
        potion = item("w", TVAL_POTION, potion_sval)
        snapshot = self._snapshot([unknown, potion, pick, mattock])
        self._assert_unknown_digger_fixture(snapshot, unknown)
        self.assertGreater(potion_cost, shovel_cost)
        self.assertIs(self.policy._cheapest_exchange_item(snapshot), potion)

    def test_pin_m3_keep_slot_excludes_cursed_digger(self):
        cursed = item(
            "c", TVAL_DIGGING, 4, known=True, is_equipment=True,
            is_cursed=True, pval=3,
        )
        shovel = item("s", TVAL_DIGGING, 1, pval=1, is_equipment=True)
        mattock = item("m", TVAL_DIGGING, 7, pval=2, is_equipment=True)
        snapshot = self._snapshot([cursed, shovel, mattock], town=True)
        self.assertFalse(
            self.policy._disposal_protected_by_identification(cursed)
        )
        self.assertFalse(self.policy._is_surplus_digging_tool(snapshot, shovel))
        self.assertFalse(self.policy._is_surplus_digging_tool(snapshot, mattock))
        self.assertTrue(self.policy._is_surplus_digging_tool(snapshot, cursed))

    def test_pin_q1_q2_breach_rejects_cursed_digger(self):
        q2 = self.policy._quest_knowledge[2]
        self.assertIsNotNone(q2.battlefield)
        navigator = QuestFloorNavigator(2, q2.battlefield)
        navigator.reset_for_floor((0, 1, 2))
        grids = {
            Position(6, 47): grid(6, 47),
            **{
                Position(y, 47): grid(y, 47, passable=False, can_dig=True)
                for y in range(7, Q2_BREACH_POSITION.y + 1)
            },
        }
        cursed = item(
            "d", TVAL_DIGGING, 1, known=True, is_equipment=True,
            is_cursed=True, pval=3,
        )
        snapshot = Snapshot(
            player(6, 47, class_id=0), grids, [], floor_key=(0, 1, 2),
            inventory=[cursed],
        )
        self.assertEqual(
            self.policy._q2_breach_key(snapshot, navigator), WAIT_KEY
        )
        self.assertEqual(self.policy.last_reason, "quest:blocked:q2-breach-tool")

        uncursed = replace(cursed, is_cursed=False)
        key = self.policy._q2_breach_key(
            replace(snapshot, inventory=[uncursed]), navigator
        )
        self.assertTrue(key.startswith("wd"), key)
        self.assertEqual(
            self.policy.last_reason, "quest-strategy:q2-breach-wield"
        )


if __name__ == "__main__":
    unittest.main()
