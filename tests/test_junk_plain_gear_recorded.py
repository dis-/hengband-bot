"""#95 slice 1b-1: plain gear worse than the selected loadout is junk.

Owner Q1 (2026-10-20): 「拾って鑑定したあと不要であれば壊す」.  Owner Q-D
(2026-10-22): a melee plain weapon is judged only while the selected main
weapon is an ego or artifact.  Slice 1b-1 classed identified plain gear with
no positive bonus only; owner Q-A (2026-10-22, 「壊す」) adds identified {good}
non-ego gear (slice 1b-3a), so the counts below include positive modifiers.

Recorded board R1: tests/fixtures/teleport-items-safe-c4a-20261021.jsonl.gz,
state rows 0-6 (life-014, Level 33, the 10-21 19:37 town visit; row 5 is the
~9 answer of the Home, row 6 the Home page after it).  The selected loadout
is the optimizer's own result on that Home catalog.

DECLARED CONSTRUCTED: the character calibration (the capture has no
calibration file; it is seeded from the board with the character row 12
stat tops as the displayed stats and the board's printed stat key), the ~f
skill-exp cache, and in the named tests the edited loadout / worn item /
copied stack / missing optimizer result.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import copy
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import InventoryItem
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import PACK_CAPACITY
from hengbot.warrior_loadout_search import _catalog_dominates
from policy_fixtures import seed_character_calibration
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "teleport-items-safe-c4a-20261021.jsonl.gz"
SHA256 = "4fd2324f203d448b74572905a6e90b3b0e2241d3333412238e3db5164a5a8075"
KNOWLEDGE_ROW = 5
HOME_ROW = 6
CHARACTER_ROW = 12
ARMOUR = {30, 31, 32, 33, 34, 35, 36, 37, 38}


class JunkPlainGearRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = FIXTURE.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == SHA256
        cls.lines = gzip.decompress(payload).decode("utf-8").splitlines()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.temporary = TemporaryDirectory()
        cls.directory = Path(cls.temporary.name)
        policy = _policy(cls.directory, cls.monrace)
        policy._crossarea_fundraising_enforced = True
        policy._in_store_ops_enabled = True
        tops = tuple(stat["top"] for stat in
                     json.loads(cls.lines[CHARACTER_ROW])["character"]["stats"])
        for index in range(HOME_ROW + 1):
            board = cls._feed(policy, cls.lines[index])
            if board is None:
                continue
            if index == 0:
                # DECLARED CONSTRUCTED: the calibration (see the docstring).
                seed_character_calibration(policy, replace(
                    board, player=replace(board.player, stat_cur=tops,
                                          stat_use=tops)))
                policy._character_calibration = replace(
                    policy._character_calibration,
                    stat_cur=tuple(board.player.printed_stat_cur_key))
            cls.key = policy.choose_key(board)
        cls.policy = policy
        cls.board = policy._decision_input_snapshot

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def _feed(cls, policy, line):
        knowledge = json.loads(line).get("type") == "knowledge"
        if knowledge:
            # DECLARED CONSTRUCTED: the fresh policy awaits the recorded ~9.
            policy._home_knowledge_scan_inflight = True
            policy._home_knowledge_scan_epoch = None
        _decoded, snapshots = _consume_response_sequence(
            [line], policy, lambda _key: True, cls.monrace,
            knowledge_ledger_path=cls.directory / "knowledge.jsonl",
        )
        if knowledge or not snapshots:
            return None
        board = snapshots[-1]
        # DECLARED CONSTRUCTED: the ~f skill-exp cache.
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        return board

    def _copy(self):
        return copy.deepcopy(self.policy)

    @staticmethod
    def _owned_items(policy, board):
        home = [entry.item for entry in policy._equipment_catalog._home.values()]
        return [*board.inventory, *home]

    def _classes(self, policy, board):
        return {id(item): policy._junk_class(board, item)
                for item in self._owned_items(policy, board)}

    @staticmethod
    def _loadout(policy):
        return policy._equipment_optimization_preparation.result.best.loadout

    @staticmethod
    def _with_loadout(policy, loadout):
        preparation = policy._equipment_optimization_preparation
        best = replace(preparation.result.best, loadout=loadout)
        policy._equipment_optimization_preparation = replace(
            preparation, result=replace(preparation.result, best=best))
        policy._decision_sequence += 1

    def test_recorded_home_plain_gear_counts(self):
        policy = self._copy()
        self.assertEqual(self.policy.last_reason, "home:atomic-deposit")
        counts = {}
        for item in self._owned_items(policy, self.board):
            junk = policy._junk_class(self.board, item)
            if junk is not None:
                counts[(junk, item.tval)] = counts.get((junk, item.tval), 0) + 1
        self.assertEqual(counts, {
            ("plain-gear", 19): 7,
            ("plain-gear", 21): 18, ("plain-gear", 22): 30, ("plain-gear", 23): 30,
            # USER DECISION 2026-10-23 「合計で比べる」: no plain helmet (tval 32) is junk beside the selected 闇の陣笠.
            ("plain-gear", 30): 6, ("plain-gear", 34): 8,
            ("plain-gear", 35): 6, ("plain-gear", 36): 13, ("plain-gear", 37): 2,
        })

    def test_recorded_controls_stay(self):
        policy = self._copy()
        loadout = self._loadout(policy)
        selected = {id(entry.item) for _, entry in loadout.slots}
        checked = set()
        for item in self._owned_items(policy, self.board):
            control = (
                item.is_artifact or item.is_ego
                or item.tval in {20, 31, 39, 40, 45, 55, 65, 66, 90, 91}
                or item.tval in {16, 17, 18}
                or not item.known or id(item) in selected
            )
            if control:
                checked.add(item.tval)
                self.assertIsNone(policy._junk_class(self.board, item), item.name)
        for worn in self.board.equipment:
            self.assertIsNone(policy._junk_class(self.board, worn), worn.name)
        # Artifacts / egos, the unidentified gauntlets' slot, identify staves
        # and stone-to-mud wands are all on this board.
        self.assertTrue({31, 55, 65}.issubset(checked))
        # Owner Q-A: a positive modifier no longer keeps a plain item that is
        # worse than the selected loadout; better ones and flagged kinds stay.
        names = {item.name: policy._junk_class(self.board, item)
                 for item in self._owned_items(policy, self.board)}
        self.assertEqual(names["汚れたボロ服 [1,+4]"], "plain-gear")
        for kept in ("鋼鉄ヘルメット [6,+5]", "鋼鉄ヘルメット [6,+4]",
                     "金属帽子 [3,+7]", "マン・ゴーシュ (1d5) (+3,+10)",
                     "カオス・ブレード (6d5) (+3,+6)"):
            self.assertIsNone(names[kept], kept)

    def test_selected_dominance_implies_plain_gear(self):
        # M3: plain armour R1-dominated by the selected loadout is plain gear.
        policy = self._copy()
        loadout = self._loadout(policy)
        dominated = 0
        for entry in policy._equipment_catalog._home.values():
            item = entry.item
            if item.tval not in ARMOUR or not policy._is_plain_gear(item):
                continue
            slot = policy._plain_gear_armour_slot(item)
            for _, reference in loadout.slots:
                if (policy._plain_gear_armour_slot(reference.item) == slot
                        and _catalog_dominates(reference, entry)):
                    dominated += 1
                    self.assertEqual(policy._junk_class(self.board, item),
                                     "plain-gear", item.name)
        self.assertGreater(dominated, 0)

    def test_empty_slot_keeps_best_plain_shield(self):
        policy = self._copy()
        shields = {item.name: policy._junk_class(self.board, item)
                   for item in self._owned_items(policy, self.board)
                   if item.tval == 34}
        # Owner Q-A: the keeper is the plain shield with the highest total AC.
        self.assertIsNone(shields["金属製ラージ・シールド [8,+2]"])
        self.assertEqual(shields["革製ラージ・シールド [6,+0]"], "plain-gear")
        self.assertEqual(shields["金属製スモール・シールド [5,+0]"], "plain-gear")
        # DECLARED CONSTRUCTED: the keeper's copy in another (pack) stack.
        keeper = next(entry.item for entry in policy._equipment_catalog._home.values()
                      if entry.item.name == "金属製ラージ・シールド [8,+2]")
        copy_stack = replace(keeper, slot="z", count=1)
        self.assertIsNone(policy._junk_class(
            replace(self.board, inventory=(*self.board.inventory, copy_stack)),
            copy_stack))

    def test_selected_plain_item_and_its_copy_stay(self):
        # DECLARED CONSTRUCTED: the plain Home boots selected for the feet.
        policy = self._copy()
        loadout = self._loadout(policy)
        boots = next(entry for entry in policy._equipment_catalog._home.values()
                     if entry.item.name == "鉄鋲底の靴 [6,+0]")
        self._with_loadout(policy, replace(loadout, slots=tuple(
            (slot, boots if slot == "feet" else entry)
            for slot, entry in loadout.slots)))
        copy_stack = replace(boots.item, slot="z", count=1)
        board = replace(self.board, inventory=(*self.board.inventory, copy_stack))
        self.assertIsNone(policy._junk_class(board, boots.item))
        self.assertIsNone(policy._junk_class(board, copy_stack))
        soft = next(entry.item for entry in policy._equipment_catalog._home.values()
                    if entry.item.name == "軟革ブーツ [2,+0]")
        self.assertEqual(policy._junk_class(board, soft), "plain-gear")

    def test_plain_selected_main_weapon_keeps_every_melee_weapon(self):
        # M1 / owner Q-D: DECLARED CONSTRUCTED plain Home weapon selected as
        # the main weapon.
        policy = self._copy()
        loadout = self._loadout(policy)
        plain = next(entry for entry in policy._equipment_catalog._home.values()
                     if entry.item.name.startswith("ダガー (1d4)"))
        self._with_loadout(policy, replace(loadout, slots=tuple(
            (slot, plain if slot == "main_hand" else entry)
            for slot, entry in loadout.slots)))
        classes = {}
        for item in self._owned_items(policy, self.board):
            junk = policy._junk_class(self.board, item)
            if junk is not None:
                classes[item.tval] = classes.get(item.tval, 0) + 1
        self.assertFalse({21, 22, 23}.intersection(classes))
        self.assertEqual(classes.get(36), 13)

    def test_missing_optimizer_result_keeps_everything(self):
        policy = self._copy()
        policy._equipment_optimization_preparation = None
        policy._decision_sequence += 1
        self.assertEqual(set(self._classes(policy, self.board).values()), {None})

    def test_lowered_worn_armour_keeps_everything(self):
        # S4: DECLARED CONSTRUCTED worn boots whose to_a acid lowered; the
        # old selection no longer names an owned item.
        policy = self._copy()
        board = replace(self.board, equipment=tuple(
            replace(worn, to_a=worn.to_a - 1, name="鉄鋲底の靴 [6,+4]")
            if worn.slot == "feet" else worn
            for worn in self.board.equipment))
        policy._decision_sequence += 1
        self.assertEqual(set(self._classes(policy, board).values()), {None})

    def test_baseline_built_once_per_decision(self):
        # M2: the Home probes of one decision share one baseline.
        policy = self._copy()
        policy._decision_sequence += 1
        with patch.object(policy, "_build_plain_gear_baseline",
                          wraps=policy._build_plain_gear_baseline) as build:
            for item in self._owned_items(policy, self.board):
                probe = replace(self.board, inventory=(*self.board.inventory, item))
                policy._junk_class(probe, item)
        self.assertEqual(build.call_count, 1)

    def test_checkpoint_drops_derived_plain_gear_caches(self):
        # The baseline and the expected-damage memo are derived from policy
        # state and rebuilt on first use; a checkpoint never restores them.
        policy = self._copy()
        self._classes(policy, self.board)
        self.assertIsNotNone(policy._plain_gear_baseline_cache)
        self.assertTrue(policy._plain_gear_dps_memo[1])
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertNotIn("_plain_gear_baseline_cache", restored.__dict__)
        self.assertNotIn("_plain_gear_dps_memo", restored.__dict__)

    def test_weapon_sale_offers_no_junk(self):
        # S7: the inferior-weapon sale branch no longer takes plain gear.
        policy = self._copy()
        weapons = tuple(entry.item for entry in policy._equipment_catalog._home.values()
                        if entry.item.tval in {21, 22, 23}
                        and policy._junk_class(self.board, entry.item) == "plain-gear")
        self.assertTrue(weapons)
        pack = tuple(replace(item, slot=chr(ord("a") + index))
                     for index, item in enumerate(weapons[:PACK_CAPACITY // 2]))
        board = replace(self.board, inventory=pack, store=None)
        self.assertIsNone(policy._find_weapon_sale(board))

    def test_home_full_relief_checks_retention_lazily(self):
        # #95 section 5: the retention gate runs in rank order up to the
        # first junk ware that passes; the pick is the eager pick.
        policy = self._copy()
        board = self.board
        policy._home_full_relief = {
            "deposits": (), "remaining": 1, "sale": None, "withdrawn": False,
            "town": policy._effective_town_id(board),
        }
        reference = copy.deepcopy(policy)
        stock = tuple(reference._home_knowledge_items)
        reference._junk_board = board
        eager = []
        for item in stock:
            taken = (item if isinstance(item, InventoryItem)
                     else reference._inventory_item_from_store_item(item))
            if reference._is_worthless_junk(taken):
                candidate = reference._home_full_discard_candidate(board, item)
                if candidate is not None:
                    eager.append(candidate)
        del reference._junk_board
        expected = min(eager, key=lambda entry:
                       reference._home_full_discard_rank(board, entry))
        with patch.object(policy, "_home_full_discard_candidate",
                          wraps=policy._home_full_discard_candidate) as gate,                 patch.object(policy, "_file_home_errand", return_value=False) as filed:
            policy._home_full_relief_key(board)
        request = filed.call_args.args[1]
        self.assertEqual((request.signature, request.purpose),
                         (policy._item_signature(expected), "full-home-discard"))
        self.assertGreater(len(eager), 1)
        self.assertEqual(gate.call_count, 1)


if __name__ == "__main__":
    unittest.main()
