"""Junk is destroyed in town under weight pressure, never deposited (#95 step 1b).

Live stop (Linux soak C4-A life-014, Level 32, bot 51a0d8f6): capture
``20261020-221304-town-blocked-departure-unsatisfiable`` decision 51,
``town:blocked:departure-unsatisfiable`` with ``departure_block.failed ==
["inventory_weight_ready"]`` only.  The pack weighed 1809 against the limit
1750 (STR index from the board); the heaviest item was the identified
"金属製スケイル・メイル (-2) [13,-5] {呪われている}" (slot m, 250), whose
``_junk_class`` is "cursed".  The town weight relief only knew Home deposits
(``_weight_deposit_candidates`` put cursed gear first, i.e. into the Home)
and the Home-full surplus disposal, which the Home deposit candidate (the
armour) kept unarmed; with the Home closed no owner was left.

Owner decisions 2026-10-20: junk is destroyed in town and never deposited
(design step 1b); stone-to-mud wands, artifacts and the 3rd/4th realm books
are never junk.

Recorded input ``junk-town-weight-20261020.jsonl.gz``: line 0 the recorded
decision row's reason/key/departure_block; lines 1-4 the capture's
state.jsonl rows 55, 56 (the Home knowledge answer), 57 and 75 (the stop
board), read unchanged (state.jsonl.gz sha256 32b5f2be1e7ab68b...).

DECLARED CONSTRUCTED (the capture's state log starts at decision 15, so the
visit's earlier policy state is not recorded):
* the town ledger of the recorded ``departure_block.town_ledger`` (visits,
  need attempts, unsatisfied passes, Home blocked) plus the Home block's work
  signature, the weight-overload deposit of the armour (installed and
  already rearmed once).  With it the pre-fix policy ends in the sibling
  terminal ``town:blocked:overweight-home-unreachable`` (key '7', the live
  key) instead of ``departure-unsatisfiable``: both are the "no owner for
  inventory_weight_ready" terminal; the unrecorded Home-block owner decides
  which one is written;
* the effect board after the destroy (the stop board without slot m);
* control items replacing slot m: the same armour uncursed, a cursed
  artifact, and a third realm book.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import STORE_HOME
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "junk-town-weight-20261020.jsonl.gz"
SHA256 = "c02bda2459f6482244418d03125a50e185bc5cea8064304a51c1e038ae0335f7"
ARMOUR = "金属製スケイル・メイル (-2) [13,-5] {呪われている}"


class JunkTownWeightRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = FIXTURE.read_bytes()
        assert hashlib.sha256(data).hexdigest() == SHA256
        lines = gzip.decompress(data).decode("utf-8").splitlines()
        cls.header = json.loads(lines[0])
        cls.lines = lines[1:]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def _consume(self, policy, line):
        return _consume_response_sequence(
            [line], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )[1]

    def _home_census(self, policy):
        # The posted ~9 request whose answer is line 2 (as in the #70 pins).
        policy._home_knowledge_scan_inflight = True
        policy._home_knowledge_scan_epoch = None
        self._consume(policy, self.lines[1])
        self._consume(policy, self.lines[2])

    def _stop(self, *, closed_home=True, slot_m=None):
        """The recorded stop board on a policy that began the visit."""
        policy = _policy(self.directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        first = self._consume(policy, self.lines[0])[-1]
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy.choose_key(first)
        self.assertEqual(policy.last_reason, "home:request-knowledge-scan")
        self._home_census(policy)
        board = self._consume(policy, self.lines[3])[-1]
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        if slot_m is not None:
            board = replace(board, inventory=[
                slot_m if item.slot == "m" else item for item in board.inventory])
        if closed_home:
            # DECLARED CONSTRUCTED: the recorded town ledger (module docstring).
            ledger = policy._town_visit_ledger
            ledger.store_visits.update({7: 5, 4: 3})
            ledger.need_attempts.update({
                "weight-overload": 4, "equipment-catalog": 3,
                "identification-source": 2, "identification-withdrawal": 2,
                "fundraising-kit": 1, "fundraising-detection": 1})
            ledger.unsatisfied_passes.update({7: 3})
            ledger.blocked_stores.add(STORE_HOME)
            armour = next(item for item in board.inventory if item.slot == "m")
            signature = ("weight-overload", *policy._item_signature(armour))
            ledger.blocked_store_work_signatures[STORE_HOME] = signature
            ledger.rearmed_work_signatures.add(signature)
        return policy, board

    def test_recorded_stop_facts(self):
        self.assertEqual(self.header["reason"], "town:blocked:departure-unsatisfiable")
        self.assertEqual(self.header["key"], "7")
        block = self.header["departure_block"]
        self.assertEqual(block["failed"], ["inventory_weight_ready"])
        self.assertEqual(block["town_ledger"]["blocked_stores"], [STORE_HOME])
        policy, board = self._stop(closed_home=False)
        self.assertEqual(board.turn, self.header["turn"])
        self.assertEqual(
            (policy._inventory_weight(board), policy._inventory_weight_limit(board)),
            (1809, 1750))
        armour = next(item for item in board.inventory if item.slot == "m")
        self.assertEqual((armour.name, armour.weight), (ARMOUR, 250))
        self.assertEqual(policy._junk_class(board, armour), "cursed")
        # Stone-to-mud wands (slot j) are never junk (owner 2026-10-20).
        wand = next(item for item in board.inventory if item.slot == "j")
        self.assertIn("岩石溶解", wand.name)
        self.assertIsNone(policy._junk_class(board, wand))

    def test_closed_home_destroys_the_cursed_armour_then_departs(self):
        policy, board = self._stop()
        key = policy.choose_key(board)
        # Pre-fix: '7' town:blocked:overweight-home-unreachable.
        self.assertEqual((key, policy.last_reason),
                         ("01km", "inventory:destroy-worthless-junk"))
        self.assertIsNone(policy._town_blocked_reason)
        # DECLARED CONSTRUCTED effect board: the stop board without slot m.
        after = replace(board, inventory=[
            item for item in board.inventory if item.slot != "m"])
        self.assertFalse(policy._inventory_overweight(after))
        policy.choose_key(after)
        self.assertFalse(policy.last_reason.startswith("town:blocked:"),
                         policy.last_reason)
        self.assertNotEqual(policy.last_reason, "inventory:destroy-worthless-junk")

    def test_junk_is_never_a_home_deposit(self):
        policy, board = self._stop(closed_home=False)
        armour = next(item for item in board.inventory if item.slot == "m")
        # Pre-fix the weight relief chose the armour first (cursed gear first).
        self.assertNotIn(armour, policy._weight_deposit_candidates(board))
        self.assertFalse(policy._home_deposit_candidate(armour, board))
        self.assertIsNot(policy._find_home_deposit(board), armour)
        # With the Home open the junk is destroyed before any Home trip.
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         ("01km", "inventory:destroy-worthless-junk"))

    def test_unused_ammo_is_not_a_home_deposit_candidate(self):
        policy, board = self._stop(closed_home=False)
        armour = next(item for item in board.inventory if item.slot == "m")
        # DECLARED CONSTRUCTED: iron shots (sling ammunition) in slot m while
        # the recorded light crossbow is worn.
        shots = replace(armour, name="鉄の弾 (1d4) (+0,+0)", count=20, tval=16,
                        sval=1, weight=4, is_cursed=False, to_h=0, to_a=0, ac=0)
        policy, board = self._stop(closed_home=False, slot_m=shots)
        shots = next(item for item in board.inventory if item.slot == "m")
        self.assertEqual(policy._junk_class(board, shots), "unused-ammo")
        # Pre-fix the general Home deposit took the unused shots.
        self.assertFalse(policy._home_deposit_candidate(shots, board))

    def test_control_non_junk_heavy_item_keeps_the_home_relief(self):
        policy, board = self._stop(closed_home=False)
        armour = next(item for item in board.inventory if item.slot == "m")
        # DECLARED CONSTRUCTED: the same armour without its curse.
        plain = replace(armour, name="金属製スケイル・メイル (-2) [13,-5]",
                        is_cursed=False)
        policy, board = self._stop(closed_home=False, slot_m=plain)
        plain = next(item for item in board.inventory if item.slot == "m")
        self.assertIsNone(policy._junk_class(board, plain))
        self.assertIsNone(policy._find_worthless_junk(board))
        self.assertIs(policy._find_home_deposit(board), plain)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("\x1b`n(.", "shop:travel"))

    def test_control_closed_home_without_pressure_keeps_the_junk(self):
        # Round 2 (supervisor option a): only weight or pack-slot pressure
        # runs the junk-first step; a closed Home alone is not a reason.
        policy, board = self._stop()
        # DECLARED CONSTRUCTED: the stop board without its heavier non-junk
        # stacks (largest first) until the pack is within the weight limit.
        inventory = list(board.inventory)
        for heavy in sorted((item for item in board.inventory if item.slot != "m"),
                            key=lambda item: -item.weight):
            if not policy._inventory_overweight(replace(board, inventory=inventory)):
                break
            inventory.remove(heavy)
        board = replace(board, inventory=inventory)
        self.assertFalse(policy._inventory_overweight(board))
        self.assertFalse(policy._town_pack_space_shortage(board))
        self.assertEqual(policy._find_worthless_junk(board).name, ARMOUR)
        policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "inventory:destroy-worthless-junk")

    def test_control_protected_items_are_never_destroyed(self):
        policy, board = self._stop()
        armour = next(item for item in board.inventory if item.slot == "m")
        # DECLARED CONSTRUCTED: a cursed artifact and a third realm book.
        artifact = replace(armour, name="★呪われたスケイル・メイル", is_artifact=True)
        book = replace(armour, name="[魔術の第三巻]", tval=90, sval=2,
                       is_equipment=False, is_cursed=False, weight=30)
        for control in (artifact, book):
            with self.subTest(control=control.name):
                policy, board = self._stop(slot_m=control)
                carried = next(item for item in board.inventory if item.slot == "m")
                self.assertIsNone(policy._junk_class(board, carried))
                self.assertIsNone(policy._find_worthless_junk(board))
                policy.choose_key(board)
                self.assertNotEqual(policy.last_reason,
                                    "inventory:destroy-worthless-junk")


if __name__ == "__main__":
    unittest.main()
