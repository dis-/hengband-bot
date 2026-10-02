"""First divergence of three recorded pins under the 2026-10-02 launcher rule.

USER DECISION 2026-10-02 (verbatim): 「上質以下同士の比較ならスリングより
ライトクロスボウを優先。スリングが高級品以上なら威力評価。」  On the recorded
tpstockout, classC2 and live27 boards the character wears an ordinary Sling,
Home holds a Light Crossbow (+4,+3) and a current-town supplier shelf sells
plain bolts at 3 gold, so the current policy's first changed decision is the
launcher swap.  Per R4 only that first divergent decision is asserted; no later
recorded board is used as its effect.  The pins' original subjects stay
asserted in their own modules behind the declared shelf wall
(tests/xbow_pref_walls.py).

classC2 and live27 freeze capture-time optimizer outputs; the swap inputs use
the declared supplement entries (tests/recorded_equipment_decisions.py
SUPPLEMENT_SHA256, produced by tests/extract_xbow_pref_optimizer_supplement.py).
"""
import tests  # noqa: F401 -- isolate runtime writes

import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.ammo_carry import is_plain_store_ammo
from hengbot.cli import _consume_response_sequence
from hengbot.latch_onset_capture import checkpoint
from hengbot.model import (
    STORE_GENERAL,
    STORE_WEAPON,
    SV_BOW_LIGHT_XBOW,
    SV_BOW_SLING,
    TVAL_BOLT,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
import recorded_equipment_decisions as frozen
import test_classC2_departure_recorded as classC2
import test_identify_staff_live27_recorded as live27
import test_tpstockout_restart_recorded as tpstockout
from test_esp_threat_rest_recorded import EDIT, _policy
from extraction_calibration import (
    install_extraction_calibration,
    restore_recorded_checkpoint,
)

SWAP_KEY = "\x1b`n(."
SWAP_REASON = "equipment-transaction:travel-home"


def plain_bolts(page):
    return [(item.count, item.price) for item in page.items
            if item.tval == TVAL_BOLT and is_plain_store_ammo(item)]


def swap_plan(policy):
    """(target loadout, transaction actions or None, catalog by id)."""
    best = policy._equipment_optimization_preparation.result.best
    session = policy._equipment_transaction_session
    actions = (
        None if session is None
        else [(action.kind, action.item_id) for action in session.plan.actions]
    )
    catalog = {owned.id: owned for owned in policy._equipment_catalog.items}
    return best.loadout, actions, catalog


def classC2_public_board_decisions():
    with frozen.recorded_equipment_decisions("classC2"), TemporaryDirectory() as raw:
        policy, board, _capture = classC2.attachment(Path(raw))
        # The recorded process decided with the frozen calibration.
        install_extraction_calibration(policy)
        bolts = plain_bolts(policy._town_supplier_stock[STORE_WEAPON])
        saved = checkpoint(policy)
        outcomes = []
        for subject in (policy, restore_recorded_checkpoint(HengbotPolicy, saved)):
            key = subject.choose_key(board)
            outcomes.append((str(key), subject.last_reason, *swap_plan(subject)))
        sling = next(item for item in board.equipment if item.slot == "bow")
        return bolts, sling, outcomes


def live27_unwalled_first_divergence():
    """live27's own replay loop (test_identify_staff_live27_recorded) without
    the shelf wall, stopped at the first decision that differs from live."""
    fixture = live27.FIXTURE
    data = json.loads(fixture.with_suffix(".boundaries.json").read_text(encoding="utf-8"))
    lines = list(gzip.open(fixture, "rt", encoding="utf-8"))
    monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
    with frozen.recorded_equipment_decisions("live27"), TemporaryDirectory() as raw:
        directory = Path(raw)
        policy = _policy(directory, monrace)
        policy._crossarea_fundraising_enforced = True
        policy._character_calibration_path.write_bytes(
            fixture.with_suffix(".calibration.json").read_bytes())
        install_extraction_calibration(policy)
        cursor = 0
        for index, count in enumerate(data["input_rows"]):
            segment = lines[cursor:cursor + count]
            cursor += count
            if index:
                previous = data["recorded"][index - 1]
                row = json.loads(segment[-1])
                row["_completed_operation_sequence"] = previous["decision_sequence"]
                row["_completed_operation_owner"] = previous["reason"]
                segment = segment[:-1] + [json.dumps(row, ensure_ascii=False) + "\n"]
            _, snapshots = _consume_response_sequence(
                segment, policy, lambda _key: True, monrace,
                knowledge_ledger_path=directory / "knowledge.jsonl")
            board = snapshots[-1]
            recorded = data["recorded"][index]
            if recorded["reason"] == "periodic:game-save":
                policy.request_game_save()
            elif recorded["reason"] == "periodic:character-dump":
                policy.request_character_dump()
            key = policy.choose_key(board)
            if (str(key), policy.last_reason) != (recorded["key"], recorded["reason"]):
                bolts = plain_bolts(policy._town_supplier_stock[STORE_GENERAL])
                sling = next(item for item in board.equipment if item.slot == "bow")
                return (index, recorded["key"], recorded["reason"], str(key),
                        policy.last_reason, bolts, sling, board, *swap_plan(policy))
            policy.confirm_key_posted(key)
    raise AssertionError("live27 replay did not diverge")


class XbowPrefRecordedDivergenceTest(unittest.TestCase):
    def assert_crossbow_target(self, sling, loadout):
        self.assertEqual((sling.sval, sling.is_ego, sling.is_artifact),
                         (SV_BOW_SLING, False, False))
        target = loadout.item_at("bow")
        self.assertEqual((target.item.sval, target.item.to_h, target.item.to_d,
                          target.item.is_ego, target.origin),
                         (SV_BOW_LIGHT_XBOW, 4, 3, False, "home"))
        return target

    def assert_crossbow_swap(self, sling, loadout, actions, catalog,
                             also_emptied=()):
        """Withdraw and equip the Home crossbow; take off and shelve the worn
        Sling (plus any slot the current optimizer empties)."""
        target = self.assert_crossbow_target(sling, loadout)
        worn = {owned.equipped_slot: owned.id for owned in catalog.values()
                if owned.origin == "equipped"}
        self.assertEqual(catalog[worn["bow"]].item.name, sling.name)
        displaced = {worn["bow"], *(worn[slot] for slot in also_emptied)}
        for slot in also_emptied:
            self.assertIsNone(loadout.item_at(slot))
        by_kind = {}
        for kind, item_id in actions:
            by_kind.setdefault(kind, []).append(item_id)
        self.assertEqual(set(by_kind), {"withdraw", "takeoff", "equip", "deposit"})
        self.assertEqual(by_kind["withdraw"], [target.id])
        self.assertEqual(by_kind["equip"], [target.id])
        self.assertEqual(set(by_kind["takeoff"]), displaced)
        self.assertEqual(set(by_kind["deposit"]), displaced)

    def test_tpstockout_first_decision_is_the_crossbow_swap(self):
        with TemporaryDirectory() as directory:
            policy, board, capture = tpstockout.attachment(directory)
            self.assertEqual(plain_bolts(policy._town_supplier_stock[STORE_WEAPON]),
                             [(83, 3)])
            sling = next(item for item in board.equipment if item.slot == "bow")
            saved = checkpoint(policy)
            for subject in (policy, restore_recorded_checkpoint(HengbotPolicy, saved)):
                with self.subTest(restored=subject is not policy):
                    key = subject.choose_key(board)
                    print("TPSTOCKOUT XBOW FIRST DIVERGENCE live",
                          repr(capture["decision"]["key"]), capture["decision"]["reason"],
                          "new", repr(key), subject.last_reason)
                    self.assertEqual((key, subject.last_reason), (SWAP_KEY, SWAP_REASON))
                    self.assert_crossbow_swap(sling, *swap_plan(subject))

    def test_classC2_first_decision_is_the_crossbow_swap(self):
        bolts, sling, outcomes = classC2_public_board_decisions()
        self.assertEqual(bolts, [(99, 3)])
        # The current optimizer (supplement entry) also wields the Spear
        # alone, so the sub-hand weapon is shelved in the same transaction.
        for key, reason, loadout, actions, catalog in outcomes:
            self.assertEqual((key, reason), (SWAP_KEY, SWAP_REASON))
            self.assert_crossbow_swap(sling, loadout, actions, catalog,
                                      also_emptied=("sub_hand",))

    def test_live27_first_divergence_is_the_crossbow_target(self):
        # The first changed decision is a step of the new target loadout, not
        # yet its Home transaction: the target holds the Home Light Crossbow,
        # and the current optimizer (supplement entry) wields the War Hammer
        # alone, so the random-teleport suppression inscribes it (g) instead
        # of the live target's Mace (f).
        (index, live_key, live_reason, key, reason, bolts, sling, board,
         loadout, actions, _catalog) = live27_unwalled_first_divergence()
        print("LIVE27 XBOW FIRST DIVERGENCE", index, "live", repr(live_key),
              live_reason, "new", repr(key), reason)
        self.assertEqual(bolts, [(98, 3)])
        self.assertEqual(index, 11)
        self.assertEqual((live_key, live_reason),
                         ("{f.\r", "equipment:suppress-random-teleport"))
        self.assertEqual((key, reason),
                         ("{g.\r", "equipment:suppress-random-teleport"))
        self.assert_crossbow_target(sling, loadout)
        hammer = next(item for item in board.inventory if item.slot == "g")
        self.assertEqual(loadout.item_at("main_hand").item.name, hammer.name)
        self.assertIsNone(loadout.item_at("sub_hand"))
        self.assertIsNone(actions)

if __name__ == "__main__":
    unittest.main()
