"""Recorded pins: what a purchase rung bought is not surplus once it stops firing.

Issue #96 part 2 (defect class #69 #70 #73 #87 #95 #96): a purchase rung buys
an item that no branch of the single retention authority
(``_retention_reservation``) covers once the rung stops firing, so the
Home-full relief / sale / destroy treats it as surplus and the rung buys it
again.  Live soak c4-a life-014, 2026-10-20:

* 10:48:51 a Treasure Detection staff (471 G) was bought as MANA food beside
  one 4-charge Clone Monster wand (the only ``mana-device`` reserve slot);
  after the recall trip (visit purchases cleared) the 10:51:47
  weight-overload deposit stored it and the 10:56:40 Home-full relief sold it
  for 152 G (seq 4187 ``5pF\\x1b``, seq 4190 ``d0y``).
* 13:57:03 six Treasure Detection scrolls were bought for the identify-staff
  stockout mining plan (mode ``prepare``, seq 6639-6642); the 13:57:25 restart
  started a fresh policy (fundraising mode None, the plan lives only in the
  process) and the Home-full relief sold them at 13:58:23-13:58:27 (seq 48-52)
  before the same plan re-armed at 13:58:56 (seq 79).

Fixture rows: the issue #67 capture B (sale-inscribe-buy-20261018 rows 4-6,
the same soak character, a MANA eater): the Home ``~9`` list, the outside
approach board and the Home page board.

DECLARED CONSTRUCTED:
* mana food: the Home Darkness staff becomes the 19-charge Treasure Detection
  staff of 10:48; for the pin the pack is the 10:48 pack: the Stone to Mud
  wands (j) become one 4-charge Clone Monster wand (the reserve slot) and the
  Door/Stair staff (n) and two Identify staves (k, l) are removed, so the
  ledger is short (7 of 15 charges).  The unconstructed pack is the control:
  the Home staff is beyond the target.
* restart: the pre-restart process's visit purchase of the Home Treasure
  Detection stack (5; the live purchase was 6) is set directly, then written
  by an ordinary board; the second policy is the restarted process.
* Stone to Mud: the player is made a ration eater and the Home Darkness staff
  a charged Stone to Mud wand; the pin removes the carried wands (j).  The
  every-wand pin keeps the carried wands (j, 5 wands) and also makes the Home
  wand an empty one; the control makes the Home staff a Magic Missile wand.
"""

from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime state for standalone module runs
import argparse
import copy
import gzip
import json
import os
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from hengbot.cli import _configure_policy_output_paths, _parse_items
from hengbot.model import RESTORE_POTION_SVAL_BY_STAT, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.purchase_rungs import PurchaseContext, purchase_rung_retention
from hengbot.runtime_paths import (RUNTIME_DIR_ENV,
                                   isolate_restored_runtime_paths)
from test_esp_threat_rest_recorded import EDIT, _policy
from test_home_full_sale_keeps_recall_recorded import _without_home_junk


FIXTURE = Path(__file__).parent / "fixtures" / "sale-inscribe-buy-20261018.jsonl.gz"
DETECTION_NAME = "財宝感知の巻物"
DARKNESS_PREFIX = "暗闇の杖"
STAFF_NAME = "財宝感知の杖 (19回分)"
STM_NAME = "岩石溶解の魔法棒 (12回分)"
MM_NAME = "マジック・ミサイルの魔法棒 (12回分)"


def _home_items(board):
    return (board["knowledge"]["items"] if "knowledge" in board
            else board["store"]["items"])


def _home_device(board, **fields):
    board = copy.deepcopy(board)
    item = next(item for item in _home_items(board)
                if item["name"].startswith(DARKNESS_PREFIX))
    item.update(**fields)
    return board


def _treasure_staff(board):
    return _home_device(board, name=STAFF_NAME, sval=10, charges=19, pval=19)


def _stone_to_mud(board, charges=12):
    board = _home_device(board, name=f"岩石溶解の魔法棒 ({charges}回分)",
                         tval=65, sval=6, charges=charges, pval=charges)
    board["player"]["food_type"] = 0
    return board


def _magic_missile(board):
    board = _home_device(board, name=MM_NAME, tval=65, sval=15, charges=12,
                         pval=12)
    board["player"]["food_type"] = 0
    return board


def _ration(board):
    board = copy.deepcopy(board)
    board["player"]["food_type"] = 0
    return board


def _short_pack(board):
    """The 10:48 pack: one 4-charge Clone Monster wand, few food charges."""
    board = _without_pack(board, "k", "l", "n")
    wand = next(item for item in board["inventory"] if item["slot"] == "j")
    wand.update(name="クローン・モンスターの魔法棒 (4回分)", sval=2, count=1,
                charges=4, pval=4)
    return board


def _without_pack(board, *slots):
    board = copy.deepcopy(board)
    board["inventory"] = [item for item in board["inventory"]
                          if item["slot"] not in slots]
    return board


class PurchaseRetentionRootRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.home, cls.approach, cls.inside = rows[4], rows[5], rows[6]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _policy_on(self, home, approach, purchase_path=None):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        policy._in_store_ops_enabled = True
        policy._equipment_optimization_last_depth = 20
        if purchase_path is not None:
            policy._town_visit_purchase_path = purchase_path
        snapshot = parse_snapshot(approach, self.monrace)
        policy.prime(snapshot)
        policy._skill_exp_cache = (
            0, 0, snapshot.player.level, policy._town_visit_epoch
        )
        home = _without_home_junk(home)
        policy.consume_home_knowledge(tuple(_parse_items(
            home["knowledge"]["items"], protocol=home.get("protocol_version"),
        )))
        return policy

    def _stack(self, policy, prefix):
        return next(item for item in policy._home_knowledge_items
                    if item.name.startswith(prefix))

    def _home_reservation(self, policy, snapshot, stack):
        probe_item = replace(stack, slot="home-surplus")
        probe = replace(snapshot, inventory=(*snapshot.inventory, probe_item))
        return policy._retention_reservation_detail(probe, probe_item)

    # -- the declared rung -> retention table --------------------------------

    def test_every_live_rung_declares_its_retention(self):
        policy = self._policy_on(self.home, self.approach)
        snapshot = parse_snapshot(self.inside, self.monrace)
        snapshot = replace(snapshot, player=replace(
            snapshot.player,
            drained_stats=tuple(RESTORE_POTION_SVAL_BY_STAT)))
        strategy = SimpleNamespace(required_force={})
        with mock.patch.object(type(policy), "_carry_procurement_strategy",
                               return_value=strategy):
            rungs = policy._purchase_rungs(PurchaseContext(snapshot))
        ids = [rung.rung_id for rung in rungs]
        # Census of the ladder (drained stats and a quest strategy enable the
        # conditional rungs).
        self.assertEqual(len(ids), 31 + len(RESTORE_POTION_SVAL_BY_STAT))
        for stat in RESTORE_POTION_SVAL_BY_STAT:
            self.assertIn(f"restore:{stat}", ids)
        for name in ("quest:carry", "quest:speed", "quest:healing",
                     "tail:mana-food", "black-market:stone-to-mud"):
            self.assertIn(name, ids)
        missing = [rung.rung_id for rung in rungs if not rung.retention]
        self.assertEqual(missing, [])

    def test_an_undeclared_rung_has_no_retention(self):
        # A new rung added to the ladder without a table entry carries None,
        # which the census test above rejects.
        self.assertIsNone(purchase_rung_retention("tail:new-purchase"))
        self.assertEqual(purchase_rung_retention("restore:str"),
                         "consumed-on-use")
        self.assertEqual(purchase_rung_retention("tail:mana-food"),
                         "supply-ledger:mana-food")

    # -- MANA food held in Home ---------------------------------------------

    def test_home_mana_food_staff_is_kept_while_the_pack_is_short(self):
        home = _treasure_staff(_short_pack(self.home))
        approach = _short_pack(self.approach)
        inside = _treasure_staff(_short_pack(self.inside))
        policy = self._policy_on(home, approach)
        snapshot = parse_snapshot(inside, self.monrace)
        self.assertLess(policy._supply_ledger(
            snapshot, policy._planned_depth())["food"].count, 15)
        stack = self._stack(policy, STAFF_NAME)
        # dce3c120: (0, None) and a destroy candidate.
        self.assertEqual(self._home_reservation(policy, snapshot, stack),
                         (1, "supply-ledger:mana-food"))
        self.assertIsNone(policy._home_full_sale_candidate(snapshot, stack))
        self.assertIsNone(policy._home_full_discard_candidate(snapshot, stack))

    def test_control_home_staff_beyond_the_mana_food_target_is_surplus(self):
        policy = self._policy_on(_treasure_staff(self.home), self.approach)
        snapshot = parse_snapshot(_treasure_staff(self.inside), self.monrace)
        stack = self._stack(policy, STAFF_NAME)
        self.assertEqual(self._home_reservation(policy, snapshot, stack),
                         (0, None))
        self.assertIsNotNone(
            policy._home_full_discard_candidate(snapshot, stack))

    # -- a restart inside the town visit -------------------------------------

    def _restarted(self, edit_record=None):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "town-visit-purchases.json"
        before = self._policy_on(self.home, self.approach, path)
        signature = before._item_signature(self._stack(before, DETECTION_NAME))
        before._town_visit_purchases.add(signature)
        before._town_visit_purchase_quantities[signature] = 5
        before._observe(parse_snapshot(self.approach, self.monrace))
        if edit_record is not None:
            record = json.loads(path.read_text(encoding="utf-8"))
            edit_record(record)
            path.write_text(json.dumps(record), encoding="utf-8")
        return self._policy_on(self.home, self.approach, path)

    def test_mining_kit_bought_this_visit_survives_a_restart(self):
        policy = self._restarted()
        snapshot = parse_snapshot(self.inside, self.monrace)
        self.assertIsNone(policy._fundraising_mode)
        stack = self._stack(policy, DETECTION_NAME)
        # dce3c120: the restarted process sold it (sale candidate, store 4).
        self.assertEqual(self._home_reservation(policy, snapshot, stack),
                         (5, "visit-purchase"))
        self.assertIsNone(policy._home_full_sale_candidate(snapshot, stack))
        self.assertIsNone(policy._home_full_discard_candidate(snapshot, stack))

    def test_control_a_record_from_a_later_turn_is_not_restored(self):
        # A record newer than the board (another character / a rolled-back
        # save) is not this visit: the stack stays sale stock.
        def later(record):
            record["turn"] += 1
        policy = self._restarted(later)
        snapshot = parse_snapshot(self.inside, self.monrace)
        stack = self._stack(policy, DETECTION_NAME)
        self.assertEqual(policy._town_visit_purchases, set())
        self.assertIsNotNone(policy._home_full_sale_candidate(snapshot, stack))

    def test_control_a_record_from_another_floor_is_not_restored(self):
        def dungeon(record):
            record["floor"] = [1, 30, 0]
        policy = self._restarted(dungeon)
        self.assertEqual(policy._town_visit_purchases, set())

    def test_control_home_full_relief_still_makes_room_after_a_restart(self):
        policy = self._restarted()
        snapshot = parse_snapshot(self.inside, self.monrace)
        policy.observe_store_screen(True)
        key = policy.choose_key(snapshot)
        policy.confirm_key_posted(key)
        relief = policy._home_full_relief or {}
        self.assertEqual(relief.get("mode"), "sale")
        picked = relief["sale"][0][0]
        self.assertNotEqual(picked, DETECTION_NAME)

    def test_cli_points_the_record_beside_the_decision_log(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        args = argparse.Namespace(
            character_dump_file=None, dump_interval_seconds=0,
            decision_log=Path(directory.name) / "bot-decisions.jsonl",
            capture_home_entry=False, capture_latch_onset=False,
            recorder_log_generations=1,
        )
        _configure_policy_output_paths(policy, args)
        self.assertEqual(policy._town_visit_purchase_path,
                         Path(directory.name) / "town-visit-purchases.json")

    def test_the_written_record_is_a_registered_retention_source(self):
        from item_sink_lint import analyze_repository
        self.assertEqual([finding for finding in analyze_repository()
                          if "_town_visit_purchase_record" in finding], [])

    def test_a_restored_checkpoint_writes_the_isolated_record(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        holder = SimpleNamespace(
            _town_visit_purchase_path=Path("jsonlog") / "town-visit-purchases.json")
        with mock.patch.dict(os.environ, {RUNTIME_DIR_ENV: directory.name}):
            isolate_restored_runtime_paths(holder)
        self.assertEqual(holder._town_visit_purchase_path,
                         Path(directory.name) / "town-visit-purchases.json")

    # -- Stone to Mud (black-market:stone-to-mud) ----------------------------

    def test_home_stone_to_mud_is_kept_when_none_is_carried(self):
        home = _stone_to_mud(_without_pack(self.home, "j"))
        approach = _ration(_without_pack(self.approach, "j"))
        inside = _stone_to_mud(_without_pack(self.inside, "j"))
        policy = self._policy_on(home, approach)
        snapshot = parse_snapshot(inside, self.monrace)
        self.assertFalse(policy._has_charged_stone_to_mud(snapshot))
        stack = self._stack(policy, STM_NAME)
        # dce3c120: (0, None) and a destroy candidate.
        self.assertEqual(self._home_reservation(policy, snapshot, stack),
                         (1, "utility:stone-to-mud"))
        self.assertIsNone(policy._home_full_discard_candidate(snapshot, stack))

    def test_every_stone_to_mud_wand_is_kept(self):
        # User 2026-10-20: every Stone to Mud wand is kept (the recharge
        # facility recharges by the number of wands), carried or in Home,
        # charged or empty.
        policy = self._policy_on(_stone_to_mud(self.home),
                                 _ration(self.approach))
        snapshot = parse_snapshot(_stone_to_mud(self.inside), self.monrace)
        self.assertTrue(policy._has_charged_stone_to_mud(snapshot))
        carried = next(item for item in snapshot.inventory if item.slot == "j")
        self.assertEqual(carried.count, 5)
        # 72e85c6d: the carried stack (5, 'utility:stone-to-mud'), the Home
        # wand (0, None) and a destroy candidate.
        self.assertEqual(policy._retention_reservation_detail(
            snapshot, carried), (5, "utility:stone-to-mud"))
        stack = self._stack(policy, STM_NAME)
        self.assertEqual(self._home_reservation(policy, snapshot, stack),
                         (1, "utility:stone-to-mud"))
        self.assertIsNone(policy._home_full_sale_candidate(snapshot, stack))
        self.assertIsNone(policy._home_full_discard_candidate(snapshot, stack))

        policy = self._policy_on(_stone_to_mud(self.home, charges=0),
                                 _ration(self.approach))
        snapshot = parse_snapshot(_stone_to_mud(self.inside, charges=0),
                                  self.monrace)
        stack = self._stack(policy, "岩石溶解の魔法棒 (0回分)")
        self.assertEqual(self._home_reservation(policy, snapshot, stack),
                         (1, "utility:stone-to-mud"))
        self.assertIsNone(policy._home_full_sale_candidate(snapshot, stack))
        self.assertIsNone(policy._home_full_discard_candidate(snapshot, stack))

    def test_control_another_wand_kind_is_still_surplus(self):
        # A wand no retention branch targets stays Home-full stock beside the
        # kept Stone to Mud wands.
        policy = self._policy_on(_magic_missile(self.home),
                                 _ration(self.approach))
        snapshot = parse_snapshot(_magic_missile(self.inside), self.monrace)
        stack = self._stack(policy, MM_NAME)
        self.assertEqual(self._home_reservation(policy, snapshot, stack),
                         (0, None))
        self.assertIsNotNone(
            policy._home_full_discard_candidate(snapshot, stack))

if __name__ == "__main__":
    unittest.main()
