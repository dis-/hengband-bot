"""Recorded pins: the Identify-staff swap buys the fuller staff (town, 2026-10-03 07:46-07:48).

USER DECISION 2026-10-03 (verbatim): 「鑑定の杖の所持数を4本以内にしたい」;
「4本を超えた分は回数の少ない杖から売る（売れなければ自宅に預ける）。20回分に
届かない時は、回数の一番少ない杖を手放して店の回数の多い杖に買い替える。20回分
の必須はそのまま。」

Live stop 2026-10-03 07:48: one town stay, 37 store entries, no purchase.
Bot process 07:35:33 (commit 31a1d944, both enforcement switches off), frozen
whole by tests/extract_identify_staff_swap_churn_fixture.py (2919 decisions;
indices below are decision indices of that process):

- 2846-2849: Magic shop shelf holds 「鑑定の杖 (4x 12回分)」 (745 gold); the
  cap/swap release plan releases one 3-charge staff and sells it ($262):
  carried 「鑑定の杖 (2x 6回分)」 + 「(3回分)」 = 3 staves, 15 charges.
- 2854: the outside one-shot composition wants the 12-charge staff, but
  ``_shop_core`` refuses ``shop:sell-rebuy-churn-defect`` because the guard
  keyed on (tval, sval) only; the bot probes ('7') instead of buying.
- 2874: Home shows a 3-charge staff; ``_identify_staff_acquisition_worthwhile``
  returned True below the cap, so it was queued and withdrawn (2883) and the
  swap sold it again (2889).  The stay repeated until the stop.

Fix 1 (policy_shop): an Identify staff with MORE charges than every Identify
staff sold this visit is the swap's replacement, not sell-then-rebuy churn;
equal or emptier is still refused.  Fix 2 (policy_supply): a Home staff the
swap would release again at once (kept charges do not rise after the release
plan) is not worth withdrawing.

The main replay stops at its declared #35 divergence at index 4: the board
has 22 carried charges and selling the selected 3-charge staff would break
the reserve. Decisions 0-3 stay strict. Later swap pins use DECLARED
CONSTRUCTED independent 3b12a514 substrates
at 2817 (the existing live-key wall) and 2846 (the unchanged sell prefix),
frozen by extract_suitefix4_checkpoints.py. These are baseline-policy states,
not effects of the new Home trip. Each pin continues from a deep copy.
Declared walls in ``_step``/``_dump_wall`` and the
independent swap continuation (S3.3: it stops at 2870; the Home
staff site is a DECLARED CONSTRUCTED fresh observer of frozen shelves, not
its later effect):

- DUMP WALL: the C-sheet dump file is not in the capture, so at each posted
  dump's completion the frozen record matching the board's printed stat key
  is installed (the drained-Strength record
  tests/fixtures/lethal-unseen-caster-20261003.character-calibration.json
  while Strength is drained, else the 07:47 record this process wrote).
- CLI TIMER WALL: the periodic dump/save requests come from the CLI wall
  clock, which the capture does not hold; each is delivered on the board
  where the live process posted it.
- LIVE-KEY WALL 2817-2845: at 2817 the replay defers the Alchemist
  *Identify* errand for the (聖戦者)タルワール (``_defer_identification_for_conquest``,
  replay '8' probe) where the live process kept it ('2' shop:approach); the
  cause was not found, so the historical baseline posts the live keys there.
  The independent 2846-2853 replay reproduces the recorded keys exactly;
  the 2817 difference is checked on its independent substrate.
- COMBAT DECISION WALL: the pending emergency escape uses the recorded
  escape-first rule, pre-teleport unseen-hit memory, pre-Speed-filter rule
  and pre-unseen-scratch-bound rule
  (tests/combat_decision_walls.py), preserving the teleport at 1785 and
  ordinary healing at 1786 under unchanged recorded expectations.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import copy
import gzip
import hashlib
import json
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.model import SV_STAFF_IDENTIFY, STORE_HOME, STORE_MAGIC, TVAL_STAFF
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.warrior_optimization import load_character_calibration

from test_esp_threat_rest_recorded import EDIT, _policy
from combat_decision_walls import pre_combat_decisions_rule
from suitefix4_checkpoints import restore as restore_independent

FIXTURES = Path(__file__).parent / "fixtures"
STEM = "identify-staff-swap-churn-20261003"
FIXTURE = FIXTURES / f"{STEM}.jsonl.gz"
BOUNDARIES = FIXTURES / f"{STEM}.boundaries.json"
CALIBRATION = FIXTURES / f"{STEM}.character-calibration.json"
DRAINED_CALIBRATION = FIXTURES / "lethal-unseen-caster-20261003.character-calibration.json"
# R9: digests of the bytes with CRLF normalized to LF.
SHA256 = {
    FIXTURE: "87aae9df8fefd08911bb5a36afeeb3633a74689cc9127aa8e77d86f46f469826",
    BOUNDARIES: "ae2d1fe38d8bc572246170671de985d158ce1c350beb50302002e2dc00fd04ff",
    CALIBRATION: "5ce8f502589e2d96662f96819b5ec034762a9ee8ba6b1d4e9746ad3824235cbc",
    DRAINED_CALIBRATION: "89681faaab50a350d0994cd790788bb424bd4f8a12f1f7801767c327c7773f4c",
}
LIVE_KEY_WALL = range(2817, 2846)
CHECKPOINT = 2853
RESERVE_DIVERGENCE = 4
INDEPENDENT = FIXTURES / "staff.suitefix4-independent-checkpoints.json.gz"
INDEPENDENT_SHA256 = "5c028f838663935a0da61d04ea35e5f16b66a6f7f87d67bd2e635dc9d08f6f77"
BUY = 2854
HOME_WITHDRAW = 2874
S33_FIRST_CHANGED = 2870
PERIODIC_REQUESTS = {
    "periodic:character-dump": "request_character_dump",
    "periodic:game-save": "request_game_save",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


_RECORDS = ()


def _recorded_dump(self, pending, character, envelope, board=None):
    """DECLARED WALL (dump): the frozen record for the board's printed stats.

    The dump file the live process read is not in the capture; the record
    whose visible stat key matches the board is what that process derived
    (the drained-Strength record before the 6084705 restore, then 07:47).
    """
    key = board.player.printed_stat_cur_key
    matches = [record for record in _RECORDS if record.visible_stat_key == key]
    if len(matches) != 1:
        raise AssertionError(f"no frozen calibration for printed stats {key}")
    self._character_calibration = matches[0]
    self._character_calibration_loaded = True
    self._calibration_unavailable_reason = None
    self._calibration_rejection = None
    self._equipment_optimization_signature = None
    self._confirmed_loadout = None
    self._confirmed_loadout_loaded = True


@contextmanager
def _dump_wall():
    with patch.object(HengbotPolicy, "_publish_character_dump", _recorded_dump):
        yield


class IdentifyStaffSwapChurnRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _RECORDS
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        _RECORDS = (load_character_calibration(CALIBRATION),
                    load_character_calibration(DRAINED_CALIBRATION))
        boundaries = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
        cls.boundaries = boundaries
        fields = boundaries["recorded_fields"]
        cls.recorded = [dict(zip(fields, row)) for row in boundaries["recorded"]]
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            lines = stream.read().splitlines(keepends=True)
        assert len(lines) == sum(boundaries["input_rows"])
        cls.segments = []
        start = 0
        for count in boundaries["input_rows"]:
            cls.segments.append(lines[start:start + count])
            start += count
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls._tmp = TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        policy = _policy(cls.directory, cls.monrace)
        policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
        # The CLI sets the dump path; the dump wall supplies its contents.
        policy._character_dump_path = cls.directory / "character-dump.txt"
        cls.prefix = []
        with _dump_wall(), pre_combat_decisions_rule():
            for index in range(RESERVE_DIVERGENCE + 1):
                result = cls._step(policy, index)
                row = result[:2]
                cls.prefix.append(row)
                if index < RESERVE_DIVERGENCE:
                    assert row == (cls.recorded[index]["key"], cls.recorded[index]["reason"]), index
                elif index == RESERVE_DIVERGENCE:
                    # DECLARED DIVERGENCE (#35): the board carries 22 Identify
                    # charges; selling the nominated 3-charge staff would
                    # leave 19, so the reserve-aware selector travels to a
                    # different store instead of following the captured route.
                    assert row == ("\x1b`n%.", "shop:travel"), index
                    cls.reserve_divergence_charges = policy._total_identify_staff_charges(result[2])
                    cls.reserve_sale_charges = policy._find_surplus_identify_staff(result[2]).charges
        assert hashlib.sha256(INDEPENDENT.read_bytes()).hexdigest() == INDEPENDENT_SHA256
        substrates = json.loads(gzip.decompress(INDEPENDENT.read_bytes()))
        assert substrates["source_revision"] == "3b12a514"
        assert substrates["input_sha256"] == SHA256[FIXTURE]
        assert set(substrates["checkpoints"]) == {"2817", "2846"}
        with _dump_wall():
            observer = restore_independent(substrates["checkpoints"]["2817"], cls.monrace, cls.directory)
            cls.live_wall_result = cls._step(observer, 2817)[:2]
            policy = restore_independent(substrates["checkpoints"]["2846"], cls.monrace, cls.directory)
            cls.independent_prefix = []
            for index in range(2846, CHECKPOINT + 1):
                row = cls._step(policy, index)[:2]
                assert row == (cls.recorded[index]["key"], cls.recorded[index]["reason"]), index
                cls.independent_prefix.append(row)
        cls.files = {path: path.read_bytes()
                     for path in cls.directory.rglob("*") if path.is_file()}
        cls.checkpoint = copy.deepcopy(policy, {id(cls.monrace): cls.monrace})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    @classmethod
    def _step(cls, policy, index):
        _decoded, snapshots = _consume_response_sequence(
            cls.segments[index], policy, lambda _key: True, cls.monrace,
            knowledge_ledger_path=cls.directory / "knowledge.jsonl",
        )
        board = snapshots[-1]
        live = cls.recorded[index]
        request = PERIODIC_REQUESTS.get(live["reason"])
        if request is not None:
            # DECLARED WALL (CLI timer): the wall-clock request is delivered on
            # the board where the live process posted it.
            getattr(policy, request)()
        key = str(policy.choose_key(board))
        reason = policy.last_reason
        # DECLARED WALL (live keys 2817-2845): the unexplained Alchemist
        # *Identify* deferral at 2817 (module docstring); post what live posted.
        posted = live["key"] if index in LIVE_KEY_WALL else key
        policy.confirm_key_posted(posted)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, posted):
            policy.commit_staged_prompt_chain(
                {"outcome": "released", "posted": str(posted)})
        return key, reason, board

    def _resume(self):
        """A fresh copy of the policy (and its files) after ``CHECKPOINT``."""
        for path in self.directory.rglob("*"):
            if path.is_file() and path not in self.files:
                path.unlink()
        for path, data in self.files.items():
            path.write_bytes(data)
        return copy.deepcopy(self.checkpoint, {id(self.monrace): self.monrace})

    def _live(self, index):
        row = self.recorded[index]
        return row["key"], row["reason"]

    # ------------------------------------------------------------ recorded
    def test_recorded_stay_is_the_incident(self):
        self.assertEqual(self._live(2849), ("d01\ry\x1b", "shop:one-shot-sell"))
        self.assertEqual(self._live(BUY), ("7", "probe"))
        selector = self.boundaries["stay"][str(BUY)]["shop_selector"]
        self.assertEqual(selector["composition_refusal"], "shop:sell-rebuy-churn-defect")
        self.assertEqual(
            {name: selector["wanted_purchase"][name]
             for name in ("category", "letter", "price", "charges")},
            {"category": "identify-staff", "letter": "i", "price": 745, "charges": 12})
        self.assertEqual(
            self.boundaries["stay"][str(BUY)]["procurement_requirements"],
            [{"item": "Identify staff charges", "current": 15, "target": 20,
              "missing": 5}])
        self.assertEqual(self._live(HOME_WITHDRAW),
                         ("\x1b", "home:queue-withdraw-identify-staff-reserve"))
        self.assertEqual(self._live(2883), ("5pU1\r\x1b", "home:atomic-withdraw"))
        self.assertEqual(self._live(2889), ("d01\ry\x1b", "shop:one-shot-sell"))

    def test_walled_replay_reproduces_the_recorded_keys(self):
        self.assertEqual(len(self.prefix), RESERVE_DIVERGENCE + 1)
        for index, row in enumerate(self.prefix):
            if index == RESERVE_DIVERGENCE:
                self.assertEqual(row, ("\x1b`n%.", "shop:travel"))
                self.assertEqual(self._live(index), ("\x1b`n&.", "shop:travel"))
                self.assertEqual(self.reserve_divergence_charges, 22)
                self.assertEqual(self.reserve_sale_charges, 3)
            elif index not in LIVE_KEY_WALL:
                self.assertEqual(row, self._live(index), index)
        for index, row in enumerate(self.independent_prefix, 2846):
            self.assertEqual(row, self._live(index), index)
        # The live-key wall is load-bearing: the replay's own 2817 differs.
        self.assertEqual(self._live(LIVE_KEY_WALL[0]), ("2", "shop:approach"))
        self.assertNotEqual(self.live_wall_result, self._live(LIVE_KEY_WALL[0]))

    # ------------------------------------------------------------ fix 1
    def test_swap_buys_the_fuller_staff(self):
        policy = self._resume()
        with _dump_wall():
            key, reason, board = self._step(policy, BUY)
        self.assertEqual(policy._town_visit_sale_identify_charges, 3)
        self.assertEqual(
            [(item.slot, item.count, item.charges)
             for item in policy._carried_identify_staves(board)],
            [("i", 2, 6), ("j", 1, 3)])
        self.assertEqual(policy._total_identify_staff_charges(board), 15)
        # First changed key versus live ('7' probe): stop here (R4).
        self.assertEqual((key, reason), ("5", "shop:one-shot-buy"))
        visit = policy._store_visit
        self.assertEqual(
            (visit.store_type, visit.operation_key, visit.operation_producer_family),
            (STORE_MAGIC, "pi1\r\r\x1b", "shop-buy"))
        diagnostics = policy._shop_selector_diagnostics
        self.assertNotIn("composition_refusal", diagnostics)
        self.assertEqual(
            {name: diagnostics["wanted_purchase"][name]
             for name in ("category", "letter", "price", "charges")},
            {"category": "identify-staff", "letter": "i", "price": 745, "charges": 12})
        self.assertIsNone(policy.town_visit_report)

    def test_equal_charge_sale_is_still_churn(self):
        """Counterfactual: had this visit sold a 12-charge staff, no rebuy."""
        for sold in (12, 13):
            with self.subTest(sold=sold):
                policy = self._resume()
                # DECLARED COUNTERFACTUAL: only the charges of the staff sold
                # at 2849 change (recorded 3); every board is recorded.
                policy._town_visit_sale_identify_charges = sold
                with _dump_wall():
                    key, reason, _board = self._step(policy, BUY)
                self.assertEqual((key, reason), self._live(BUY))
                self.assertEqual(
                    policy._shop_selector_diagnostics["composition_refusal"],
                    "shop:sell-rebuy-churn-defect")
                self.assertEqual(policy.town_visit_report,
                                 f"town-visit:sell-rebuy-churn:{TVAL_STAFF}:"
                                 f"{SV_STAFF_IDENTIFY}")

    # ------------------------------------------------------------ fix 2
    def test_home_staff_the_swap_would_release_is_not_withdrawn(self):
        policy = self._resume()
        rows = []
        # DECLARED WALL (churn fix off): follow the recorded refusal of the
        # purchase, only until the first changed approach key at 2870.
        with _dump_wall(), patch.object(
                HengbotPolicy, "_identify_staff_swap_purchase",
                lambda _self, _item: False):
            for index in range(BUY, S33_FIRST_CHANGED + 1):
                key, reason, board = self._step(policy, index)
                rows.append((key, reason))
        for offset, row in enumerate(rows[:-1]):
            self.assertEqual(row, self._live(BUY + offset), BUY + offset)
        # Current and baseline both wait on the existing travel work at
        # 2870. Stop here: old Home boards are not its observed effects.
        self.assertEqual(rows[-1], ("5", "shop:travel:await-entry"))
        self.assertIsNone(policy.decision_claim["declaration_mismatch"])
        self.assertIsNone(policy.decision_claim["claim_verdict_conflict"])
        self.assertIsNone(policy._s33_shadow_verdict(board, key)["would_stop"])
        # DECLARED CONSTRUCTED fresh observer: independent Magic/Home shelf
        # facts, no inferred route or command effects from the stopped prefix.
        # This also avoids the baseline's pre-existing first difference at
        # 2870 (verified on 0d2ef6d6), which is not a new S3.3 regression.
        with TemporaryDirectory() as raw:
            independent_directory = Path(raw)
            policy = _policy(independent_directory, self.monrace)
            policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
            for observed_index in (HOME_WITHDRAW,):
                _decoded, snapshots = _consume_response_sequence(
                    self.segments[observed_index], policy, lambda _key: True, self.monrace,
                    knowledge_ledger_path=independent_directory / "knowledge.jsonl")
                board = snapshots[-1]
                policy.prime(board)
            # Prime first: arrival correctly clears previous-town observations.
            # Then supply only the same-town observed pages from the faithful
            # prefix, never an owner or substituted readiness result.
            policy._town_supplier_stock = copy.deepcopy(self.checkpoint._town_supplier_stock)
            policy._town_supplier_stock_observations = copy.deepcopy(
                self.checkpoint._town_supplier_stock_observations)
            with _dump_wall():
                key = str(policy.choose_key(board))
        self.assertEqual(board.store.store_type, STORE_HOME)
        self.assertIn(3, [item.charges for item in board.store.items
                          if (item.tval, item.sval) == (TVAL_STAFF, SV_STAFF_IDENTIFY)])
        self.assertEqual(
            [(item.slot, item.count, item.charges)
             for item in policy._carried_identify_staves(board)],
            [("i", 2, 6), ("j", 1, 3)])
        # First changed key versus live (queue the withdraw): stop here (R4).
        self.assertNotEqual(policy.last_reason, "home:queue-withdraw-identify-staff-reserve")
        self.assertNotEqual(policy.last_reason, "home:atomic-withdraw")
        self.assertIsNone(policy._home_pending_item)
        # A fourth staff of 3 charges fills the cap below 20, so the swap
        # would release it (emptiest) for the 12-charge shelf staff at once.
        self.assertEqual(policy._identify_staff_store_offer_charges(board), 12)
        self.assertFalse(policy._identify_staff_acquisition_worthwhile(board, 3))


if __name__ == "__main__":
    unittest.main()
