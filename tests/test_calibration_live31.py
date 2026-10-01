"""Recorded live31 deposit/restore; stop at the first changed command.

The response to that new command is constructed from posted quantities, never
borrowed from later historical boards. Historical terminal reconciliation is
tested separately by rebuilding the intents actually sent live.
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

FIXTURE = Path(__file__).parent / "fixtures/live31-calibration-restore-20261001.jsonl.gz"
DEPOSITS = ((1086339, "dh4\rdg9\rdf4\rde5\rdddcdbda3\r"),
            (1086352, "dhdg2\rdf2\rde3\rdddcdb10\rda13\r"),
            (1086358, "de66\rdddcdbda3\r"))
FIRST = "5pKpD3\rpCpA2\rpz2\rprpqpp10\rpo13\rpm4\rpl9\rpk4\rpf5\rpe3\rpdpcpb\x1b"
SECOND = "5pT66\rpQpM\x1b"


def rows():
    with gzip.open(FIXTURE, "rt", encoding="utf8") as source:
        return list(map(json.loads, source))


def outside(raw, turn):
    return parse_snapshot(next(r for r in raw if r.get("turn") == turn
        and r.get("type") == "player_turn" and not r.get("store")), {})


def catalogue(policy, raw, turn):
    page = next(r for r in raw if r.get("turn") == turn
                and r.get("knowledge", {}).get("category") == "home")
    policy.consume_home_knowledge(tuple(_parse_items(page["knowledge"]["items"])))
    policy._home_page_size = next(r["store"]["page_size"] for r in raw if r.get("store"))
    policy._shopping_approach_store_type = STORE_HOME


def deposited(raw):
    policy = HengbotPolicy()
    policy._crossarea_fundraising_enforced = True
    policy._calibration_redress_loaded = True
    policy._calibration_phase = "deposit"
    for turn, macro in DEPOSITS:
        board = outside(raw, turn)
        commands = []
        for slot, amount in re.findall(r"d([a-z])(\d*\r)?", macro):
            item = next(i for i in board.inventory if i.slot == slot)
            commands.append(policy._home_deposit_key(board, item,
                            forced_count=int(amount) if amount else 1))
        if "".join(commands) != macro:
            raise AssertionError((commands, macro))
    policy._calibration_phase = "restore-supplies"
    return policy


def historical_pending(policy, macro):
    entries = []
    for letter, amount in re.findall(r"p([a-zA-Z])(\d*\r)?", macro):
        index = ord(letter) - (ord("a") if letter.islower() else ord("A") - 26)
        item = policy._home_knowledge_items[index]
        entries.append((policy._item_signature(item), 0, item,
                        int(amount) if amount else 1, index))
    return (*entries[0][:4], tuple(entries))


class Live31CalibrationTest(unittest.TestCase):
    def test_first_changed_macro_includes_pooled_wand_and_restores(self):
        raw = rows()
        for checkpoint in (False, True):
            policy = deposited(raw)
            catalogue(policy, raw, 1086764)
            if checkpoint:
                policy = pickle.loads(pickle.dumps(policy))
            board = outside(raw, 1086764)
            initial_shelf = policy._home_knowledge_items
            key = policy._calibration_town_key(board)
            self.assertEqual(key, FIRST.replace("pz2\r", "pz2\rpy3\r"))
            print("live31 first divergence", repr(key), "live", repr(FIRST))
            pending = policy._home_atomic_withdraw_pending
            carried = []
            for sig, before, item, quantity, index in pending[4]:
                # Wands split their total charges proportionally. This is a
                # constructed physical response to the NEW posted macro.
                charges = item.charges * quantity // item.count if item.tval == 65 else item.charges
                carried.append(replace(item, slot=f"response:{index}", count=quantity,
                    charges=charges, pval=charges if item.tval == 65 else item.pval,
                    name=re.sub(r"\(\d+回分\)", f"({charges}回分)", item.name)
                         if item.tval == 65 else item.name))
            response = replace(board, turn=board.turn + 1, inventory=carried)
            policy._observe_calibration_restore_batch(response, pending)
            self.assertEqual([sig[1] for sig in policy._calibration_restore_signatures], [16, 20, 22])
            # Construct the remaining shelf from the PRE-decision catalogue.
            # No historical board after the divergence is used as an effect.
            takes = {entry[4]: entry[3] for entry in pending[4]}
            remaining = []
            for index, item in enumerate(initial_shelf):
                quantity = takes.get(index, 0)
                count = item.count - quantity
                if count:
                    charges = item.charges - item.charges * quantity // item.count if item.tval == 65 else item.charges
                    remaining.append(replace(item, count=count, charges=charges,
                        pval=charges if item.tval == 65 else item.pval,
                        name=re.sub(r"\(\d+回分\)", f"({charges}回分)", item.name)
                             if item.tval == 65 else item.name))
            policy.consume_home_knowledge(tuple(remaining))
            policy._calibration_town_key(response)
            pending2 = policy._home_atomic_withdraw_pending
            self.assertEqual(len(pending2[4]), 3)
            response2 = replace(response, turn=response.turn + 1, inventory=carried + [
                replace(item, slot=f"last:{index}", count=quantity)
                for sig, before, item, quantity, index in pending2[4]])
            policy._observe_calibration_restore_batch(response2, pending2)
            policy._calibration_observe(response2)
            self.assertEqual(policy._calibration_restore_signatures, [])
            self.assertIsNone(policy._calibration_phase)

    def test_historical_terminal_board_has_addressable_debt(self):
        raw = rows()
        policy = deposited(raw)
        for turn, macro, next_turn in ((1086764, FIRST, 1086772),
                                      (1086772, SECOND, 1086783)):
            catalogue(policy, raw, turn)
            pending = historical_pending(policy, macro)
            policy._home_atomic_withdraw_pending = pending
            policy._observe_calibration_restore_batch(outside(raw, next_turn), pending)
        self.assertEqual(policy._calibration_restore_signatures,
                         [("岩石溶解の魔法棒 (25回分)", 65, 6)])
        catalogue(policy, raw, 1086783)
        board = outside(raw, 1086783)
        policy = pickle.loads(pickle.dumps(policy))
        key = policy._calibration_town_key(board)
        self.assertEqual(key, "5po3\r\x1b")
        print("live31 terminal recovery", repr(key), "live", None,
              "town:blocked:calibration-restore-target-absent")
        item = policy._home_atomic_withdraw_pending[2]
        response = replace(board, turn=board.turn + 1, inventory=board.inventory + [
            replace(item, slot="u", count=3, charges=21, pval=21,
                    name="岩石溶解の魔法棒 (21回分)")])
        # This is a single-entry macro, observed through carried reconciliation.
        policy._home_atomic_withdraw_pending = None
        policy._home_knowledge_items = ()
        policy._calibration_observe(response)
        self.assertEqual(policy._calibration_restore_signatures, [])
        self.assertIsNone(policy._calibration_phase)
        self.assertEqual(policy._calibration_restore_outcomes[
            ("岩石溶解の魔法棒 (25回分)", 65, 6)], "calibration-restore:carried")
        restored = pickle.loads(pickle.dumps(policy))
        self.assertEqual(restored._calibration_restore_outcomes,
                         policy._calibration_restore_outcomes)

    def test_known_equipment_annotation_and_added_knowledge(self):
        raw = rows()
        policy = deposited(raw)
        original = next(i for i in outside(raw, 1086358).inventory if i.tval == 22)
        owner = policy._item_signature(original)
        changed = replace(original, name=original.name + " {new inscription}",
                          inscription="new inscription", fully_known=True)
        self.assertEqual(policy._calibration_restore_item_matches(owner, changed), True)
        self.assertEqual(policy._calibration_restore_item_matches(owner,
                         replace(changed, to_d=changed.to_d + 1)), False)

    def test_hidden_kinds_retain_distinct_observed_flavours(self):
        raw = rows()
        policy = deposited(raw)
        mushrooms = [i for i in outside(raw, 1086339).inventory if i.tval == 80]
        self.assertEqual([i.sval for i in mushrooms], [-1, -1, -1, -1])
        owner = policy._item_signature(mushrooms[0])
        self.assertEqual([policy._calibration_restore_item_matches(owner, i)
                          for i in mushrooms], [True, False, False, False])

    def test_worn_identity_discharge_is_typed_and_checkpointed(self):
        raw = rows()
        policy = deposited(raw)
        original = next(i for i in outside(raw, 1086358).inventory if i.tval == 22)
        owner = policy._item_signature(original)
        board = outside(raw, 1086764)
        response = replace(board, equipment=[replace(original, slot="main_hand")])
        remaining = [sig for sig in policy._calibration_restore_signatures if sig != owner]
        policy._calibration_observe(response)
        self.assertEqual(policy._calibration_restore_signatures, remaining)
        self.assertEqual(policy._calibration_restore_outcomes[owner], "calibration-restore:worn")
        restored = pickle.loads(pickle.dumps(policy))
        self.assertEqual(restored._calibration_restore_outcomes[owner], "calibration-restore:worn")

    def test_older_checkpoint_defaults_new_observation_field(self):
        policy = deposited(rows())
        del policy._calibration_restore_items
        del policy._calibration_restore_outcomes
        restored = pickle.loads(pickle.dumps(policy))
        restored.choose_key(outside(rows(), 1086764))
        self.assertEqual(restored._calibration_restore_items, {})
        self.assertEqual(restored._calibration_restore_outcomes, {})


if __name__ == "__main__":
    unittest.main()
