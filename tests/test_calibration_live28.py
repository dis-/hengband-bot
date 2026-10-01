"""Recorded live28 deposit and restore, stopping at the first changed macro.

Deposit producers register real debt. Historical withdrawal intents are rebuilt
from their exact recorded selectors, and observed on their recorded responses.
A new command gets a constructed physical response, never a later live board.
"""
import tests  # noqa: F401
import gzip
import json
import pickle
import re
import unittest
from dataclasses import replace
from pathlib import Path
from hengbot.model import STORE_HOME, _parse_items, parse_snapshot
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).parent / "fixtures/live28-calibration-restore-20261001.jsonl.gz"
DEPOSITS = ((932862, "dhdg2\rdf10\rde15\rdddc4\rdb10\rda5\r"),
            (932877, "dh2\rdgdfde2\rdd2\rdcdbda6\r"),
            (932879, "dc99\rdbda"))
LIVE_FIRST = "5pXpFpw2\rpupt2\rps2\rprpppm6\rplpk2\rpj10\rpi15\rph1\rpg4\rpf10\rpb5\r\x1b"

def rows():
    with gzip.open(FIXTURE, "rt", encoding="utf8") as source:
        return list(map(json.loads, source))

def outside(raw, turn):
    return parse_snapshot(next(r for r in raw if r.get("turn") == turn
                               and r.get("type") == "player_turn"), {})

def catalogue(policy, raw, turn):
    page = next(r for r in raw if r.get("turn") == turn
                and r.get("knowledge", {}).get("category") == "home")
    policy.consume_home_knowledge(tuple(_parse_items(page["knowledge"]["items"])))
    policy._home_page_size = next(r["store"]["page_size"] for r in raw if r.get("store"))
    policy._shopping_approach_store_type = STORE_HOME

def deposited(raw):
    policy = HengbotPolicy()
    policy._observe(outside(raw, 932862))
    policy._crossarea_fundraising_enforced = True
    policy._calibration_redress_loaded = True
    policy._calibration_phase = "deposit"
    for turn, macro in DEPOSITS:
        board = outside(raw, turn)
        keys = []
        for slot, amount in re.findall(r"d([a-z])(\d*\r)?", macro):
            item = next(i for i in board.inventory if i.slot == slot)
            keys.append(policy._home_deposit_key(board, item,
                        forced_count=int(amount) if amount else 1))
        if "".join(keys) != macro:
            raise AssertionError((keys, macro))
    policy._calibration_phase = "restore-supplies"
    return policy

def historical_first_pending(policy, raw):
    catalogue(policy, raw, 933258)
    entries = []
    for letter, amount in re.findall(r"p([a-zA-Z])(\d*\r)?", LIVE_FIRST):
        index = ord(letter) - ord("a") if letter.islower() else 26 + ord(letter) - ord("A")
        item = policy._home_knowledge_items[index]
        entries.append((policy._item_signature(item), 0, item,
                        int(amount) if amount else 1, index))
    return (*entries[0][:4], tuple(entries))

class Live28CalibrationTest(unittest.TestCase):
    def test_historical_first_observation_keeps_four_charge_debt(self):
        raw = rows()
        for restored in (False, True):
            policy = deposited(raw)
            pending = historical_first_pending(policy, raw)
            policy._home_atomic_withdraw_pending = pending
            if restored:
                policy = pickle.loads(pickle.dumps(policy))
            policy._observe_calibration_restore_batch(outside(raw, 933266), pending)
            staff = [sig for sig in policy._calibration_restore_signatures if sig[1] == 55]
            original = next(i for i in outside(raw, 932877).inventory
                            if i.tval == 55 and i.charges == 4)
            self.assertEqual(staff, [policy._item_signature(original)])
            catalogue(policy, raw, 933266)
            board = outside(raw, 933266)
            key = policy._calibration_town_key(board)
            self.assertEqual(key, "5pN99\rpl1\r\x1b")
            print("live28 first changed action", repr(key), "live", repr("5pN99\r\x1b"))
            pending = policy._home_atomic_withdraw_pending
            entries = pending[4]
            # Construct the effect of this NEW macro from its posted quantities.
            carried = list(board.inventory)
            for sig, before, item, quantity, index in entries:
                carried.append(replace(item, slot=f"response:{index}", count=quantity))
            response = replace(board, turn=board.turn + 1, inventory=carried)
            policy._observe_calibration_restore_batch(response, pending)
            policy._calibration_observe(response)
            self.assertEqual(policy._calibration_restore_signatures, [])
            self.assertIsNone(policy._calibration_phase)

    def test_fresh_restore_includes_merged_stack_and_completes(self):
        raw = rows()
        policy = deposited(raw)
        catalogue(policy, raw, 933258)
        board = outside(raw, 933258)
        key = policy._calibration_town_key(board)
        self.assertEqual(key, LIVE_FIRST.replace("pupt", "pv1\rpupt"))
        print("live28 first changed action", repr(key), "live", repr(LIVE_FIRST))
        pending = policy._home_atomic_withdraw_pending
        entries = pending[4]
        carried = [replace(item, slot=f"response:{index}", count=quantity)
                   for sig, before, item, quantity, index in entries]
        response = replace(board, turn=board.turn + 1, inventory=carried)
        policy._observe_calibration_restore_batch(response, pending)
        self.assertEqual([sig[1] for sig in policy._calibration_restore_signatures], [16])

    def test_old_checkpoint_already_carried_target_reconciles(self):
        raw = rows()
        policy = deposited(raw)
        pending = historical_first_pending(policy, raw)
        policy._home_atomic_withdraw_pending = pending
        policy._observe_calibration_restore_batch(outside(raw, 933266), pending)
        # Old live checkpoint had incorrectly removed four-charge debt and
        # retained 21-charge debt. Keep only that historical terminal target.
        sig = next(policy._item_signature(i) for i in outside(raw, 933277).inventory
                   if i.tval == 55 and i.charges == 21)
        policy._calibration_restore_signatures = [sig]
        policy._home_pending_quantities[sig] = 1
        catalogue(policy, raw, 933266)
        policy = pickle.loads(pickle.dumps(policy))
        policy._calibration_observe(outside(raw, 933277))
        self.assertEqual(policy._calibration_restore_signatures, [])
        self.assertIsNone(policy._calibration_phase)

if __name__ == "__main__":
    unittest.main()
