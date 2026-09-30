"""Live25 recorded deposit/restore producer pin.

Entry wall: reconstruct calibration's deposit phase and visit epoch. Each
deposit producer is called with the pack slot/count in the historical macro.
Recorded boards through the last deposit are genuine command responses.
After the changed restore macro, responses are constructed by applying its
pending quantities to pack and Home; historical responses are not fed as if
they followed the changed commands. No producer, retention or owner is mocked.
"""
import tests  # noqa: F401 -- runtime file isolation
import gzip
import hashlib
import json
import pickle
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import STORE_HOME, _parse_items, parse_snapshot
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).parent / "fixtures/live25-calibration-restore-20261001.jsonl.gz"
DEPOSITS = ((688489, "dh13\rdgdf4\rde14\rdddc5\rdbda\x1b"),
            (688498, "dhdgdf5\rde2\rdd2\rdcdbda8\r\x1b"),
            (688511, "dc72\rdbda\x1b"))


def rows():
    with gzip.open(FIXTURE, "rt", encoding="utf8") as source:
        return list(map(json.loads, source))


def outside(raw, turn):
    return parse_snapshot(next(r for r in raw if r.get("turn") == turn
                               and r.get("type") == "player_turn"), {})


def deposited(raw, s33=False):
    import re
    policy = HengbotPolicy()
    policy._observe(outside(raw, 688489))
    policy._crossarea_fundraising_enforced = True
    policy._town_claim_bar_enforced = s33
    policy._calibration_redress_loaded = True
    policy._calibration_phase = "deposit"
    for turn, macro in DEPOSITS:
        board = outside(raw, turn)
        commands = []
        for slot, amount in re.findall(r"d([a-z])(\d*\r)?", macro):
            item = next(i for i in board.inventory if i.slot == slot)
            count = int(amount) if amount else 1
            commands.append(policy._home_deposit_key(board, item, forced_count=count))
        assert "".join(commands) + "\x1b" == macro
    policy._calibration_phase = "restore-supplies"
    policy._shopping_approach_store_type = STORE_HOME
    page = next(r for r in raw if r.get("turn") == 688636 and r.get("knowledge"))
    policy.consume_home_knowledge(tuple(_parse_items(page["knowledge"]["items"])))
    policy._home_page_size = next(r["store"]["page_size"] for r in raw
                                if r.get("store", {}).get("store_type") == STORE_HOME)
    return policy


class Live25CalibrationTest(unittest.TestCase):
    def test_recorded_weights_and_identical_redress(self):
        raw = rows()
        with gzip.open(FIXTURE, "rb") as source:
            self.assertEqual(hashlib.sha256(source.read()).hexdigest(),
                             "3a2ec98082b07f2ec8f5303ca1f258c797ab2d99348fd3c56bec0f198ddd15f1")
        self.assertEqual(len(raw), 63)
        policy = HengbotPolicy()
        before = outside(raw, 688511)
        dressed = outside(raw, 688636)
        historical = outside(raw, 688644)
        self.assertEqual(policy._inventory_weight(before), 1004)
        self.assertEqual(policy._inventory_weight(dressed), 404)
        self.assertEqual(policy._inventory_weight(historical), 1700)
        self.assertEqual(policy._inventory_weight_limit(historical), 1700)
        self.assertEqual([(i.slot, i.tval, i.sval, i.weight) for i in before.equipment],
                         [(i.slot, i.tval, i.sval, i.weight) for i in dressed.equipment])
        self.assertEqual(before.player.stat_index, dressed.player.stat_index)

    def test_recorded_deposits_restore_completes_with_excess_kept_home(self):
        raw = rows()
        for s33 in (False, True):
            for checkpoint in (False, True):
                with self.subTest(s33=s33, checkpoint=checkpoint):
                    policy = deposited(raw, s33)
                    if checkpoint:
                        policy = pickle.loads(pickle.dumps(policy))
                    board = outside(raw, 688636)
                    for batch in range(4):
                        key = policy._atomic_home_withdraw_key(board, board.player.position)
                        self.assertIsNotNone(key, policy.last_reason)
                        self.assertEqual(policy.last_reason, "calibration:atomic-restore-withdraw")
                        pending = policy._home_atomic_withdraw_pending
                        entries = pending[4] if len(pending) == 5 else (pending[:4] + (0,),)
                        carried = list(board.inventory)
                        home = list(policy._home_knowledge_items)
                        for sig, before, item, quantity, index in entries:
                            carried.append(replace(item, slot=f"carried:{len(carried)}", count=quantity))
                            match = next(i for i, shelf in enumerate(home)
                                         if policy._item_signature(shelf) == sig)
                            shelf = home[match]
                            if shelf.count == quantity:
                                home.pop(match)
                            else:
                                home[match] = replace(shelf, count=shelf.count - quantity)
                        board = replace(board, turn=board.turn + 1, inventory=carried)
                        policy._observe_calibration_restore_batch(board, (*pending[:4], tuple(entries)))
                        self.assertLessEqual(policy._inventory_weight(board), 1700)
                        policy.consume_home_knowledge(tuple(home))
                        policy._shopping_approach_store_type = STORE_HOME
                        if not policy._calibration_restore_signatures:
                            break
                    self.assertEqual(policy._calibration_restore_signatures, [])
                    self.assertEqual(batch, 0)
                    self.assertEqual(key, "5pQ72\rpMpLpx5\rpopl8\rpk13\rpi4\rph10\rpgpc5\r\x1b")
                    self.assertEqual(policy._inventory_weight(board), 1379)
                    self.assertEqual(next(i.count for i in board.inventory if i.is_torch), 5)
                    policy._calibration_observe(board)
                    self.assertIsNone(policy._calibration_phase)
                    self.assertIsNone(policy._home_atomic_deposit_pending)
                    kept = policy._calibration_restore_kept_home
                    self.assertEqual(policy.calibration_entry_state(board)["kept_in_home"],
                        [{"signature": list(sig), "quantity": n} for sig, n in sorted(kept.items())])
                    self.assertEqual(sum(n for sig, n in kept.items() if sig[1] in {21, 22, 37}), 2)
                    self.assertEqual(sum(i.weight * i.count for i in policy._home_knowledge_items
                                         if i.tval in {22, 37} and any(
                                             policy._item_signature(i) == sig for sig in kept)), 630)
                    self.assertEqual(next(i.count for i in board.inventory if i.is_ammo), 72)
                    self.assertEqual(next(i.count for i in board.inventory if i.is_recall_scroll), 8)
                    self.assertEqual(next(i.count for i in board.inventory if i.is_teleport_scroll), 13)
                    self.assertEqual(next(i.count for i in board.inventory
                                          if i.tval == 75 and i.sval == 36), 10)
                    with gzip.open(FIXTURE.with_name(
                            "live25-calibration-decisions-20261001.jsonl.gz"),
                            "rt", encoding="utf8") as source:
                        live = next(r for r in map(json.loads, source)
                                    if r["decision_sequence"] == 1272)
                    print("live25 restore:", json.dumps({
                        "s33": s33, "checkpoint": checkpoint,
                        "live_key": live["key"], "live_reason": live["reason"],
                        "new_key": key, "phase": policy._calibration_phase,
                        "weight": policy._inventory_weight(board),
                        "limit": policy._inventory_weight_limit(board),
                        "debt": policy._calibration_restore_signatures,
                        "kept_in_home": policy.calibration_entry_state(board)["kept_in_home"],
                    }, ensure_ascii=False))
                    if checkpoint:
                        self.assertEqual(pickle.loads(pickle.dumps(policy))._calibration_restore_kept_home, kept)

    def test_old_checkpoint_has_no_new_field_until_it_keeps_excess(self):
        raw = rows()
        policy = deposited(raw)
        del policy._calibration_restore_kept_home
        # Old checkpoint still owes all fourteen of the recorded cure potions.
        signature = next(sig for sig in policy._calibration_restore_signatures
                         if sig[1:] == (75, 36))
        policy._home_pending_quantities[signature] = 14
        policy = pickle.loads(pickle.dumps(policy))
        board = outside(raw, 688636)
        # Explicit capacity counterfactual: full old-checkpoint debt is 1395;
        # an additional 400 equipment weight makes supply capping necessary.
        equipment = list(board.equipment)
        equipment[0] = replace(equipment[0], weight=equipment[0].weight + 400)
        board = replace(board, equipment=equipment)
        self.assertIsNotNone(policy._atomic_home_withdraw_key(board, board.player.position))
        self.assertEqual(next(n for sig, n in policy._calibration_restore_kept_home.items()
                              if sig[1:] == (75, 36)), 4)

    def test_required_debt_alone_over_limit_still_stops_without_lowering_targets(self):
        raw = rows()
        policy = deposited(raw)
        board = outside(raw, 688636)
        equipment = list(board.equipment)
        equipment[0] = replace(equipment[0], weight=equipment[0].weight + 1295)
        heavy = replace(board, equipment=equipment)
        key = policy._atomic_home_withdraw_key(heavy, heavy.player.position)
        self.assertIsNone(policy._enforce_town_claim_result(heavy, key))
        self.assertEqual(policy.last_reason, "town:blocked:calibration-restore-weight-limit")
        self.assertEqual(next(n for sig, n in policy._home_pending_quantities.items()
                              if sig[1:] == (77, 0)), 5)
        self.assertIsNone(policy._home_atomic_withdraw_pending)

    def test_full_owed_restore_at_limit_and_one_over_after_checkpoint(self):
        raw = rows()
        for s33 in (False, True):
            for checkpoint in (False, True):
                for extra in (321, 322):
                    with self.subTest(s33=s33, checkpoint=checkpoint, extra=extra):
                        policy = deposited(raw, s33)
                        board = outside(raw, 688636)
                        # Capacity counterfactual on the recorded equipment;
                        # full debt weighs 1379, so these straddle limit 1700.
                        equipment = list(board.equipment)
                        equipment[0] = replace(equipment[0],
                            weight=equipment[0].weight + extra)
                        board = replace(board, equipment=equipment)
                        owed = policy._home_pending_quantities.copy()
                        kept = policy._calibration_restore_kept_home.copy()
                        if checkpoint:
                            policy = pickle.loads(pickle.dumps(policy))
                        key = policy._atomic_home_withdraw_key(board, board.player.position)
                        self.assertIsNotNone(key)
                        entries = policy._home_atomic_withdraw_pending[4]
                        torches = [e for e in entries if e[2].is_torch]
                        if extra == 321:
                            self.assertEqual(len(torches), 1)
                            self.assertEqual(torches[0][3], 5)
                            self.assertEqual(policy._calibration_restore_kept_home, kept)
                            for sig, _, _, quantity, _ in entries:
                                self.assertEqual(quantity, owed[sig])
                            self.assertEqual(policy._inventory_weight(board) + sum(
                                i.weight * n for _, _, i, n, _ in entries), 1700)
                        else:
                            self.assertEqual(torches, [])
                            torch_sig = next(sig for sig in owed if sig[1] == 39)
                            self.assertEqual(policy._calibration_restore_kept_home[torch_sig], 5)
                            self.assertNotIn(torch_sig, policy._calibration_restore_signatures)
                            self.assertEqual(policy._inventory_weight(board) + sum(
                                i.weight * n for _, _, i, n, _ in entries), 1551)
                        self.assertIsNone(policy._home_atomic_deposit_pending)

    def test_next_calibration_resets_kept_home_accounting(self):
        raw = rows()
        policy = deposited(raw)
        self.assertTrue(policy._calibration_restore_kept_home)
        policy._begin_character_calibration(outside(raw, 688636))
        self.assertEqual(policy._calibration_restore_kept_home, {})
