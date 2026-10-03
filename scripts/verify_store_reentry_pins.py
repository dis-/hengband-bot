"""Revert behavioral hunks, run recorded public-path pins, then restore bytes.

Run alone, with PYTHONPATH=src;tests;scripts. The recorded replay is performed
once. Its pre-decision checkpoints are shared with independent pin instances.
For each source mutation, compile the modified function from the actual file
and replace that function's code in the already loaded module. This avoids
replaying four minutes of unaffected prefix for every reverted downstream
hunk. No public policy path or selector is mocked by this harness.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), *(str(ROOT / path) for path in ("src", "tests", "scripts"))]

from hengbot import cli, input_executor, policy_instore
import test_store_reentry_recorded as pins


def recompile(module, owner, name, source):
    tree = ast.parse(source)
    nodes = tree.body if owner is None else next(
        node.body for node in tree.body if isinstance(node, ast.ClassDef)
        and node.name == owner.__name__)
    node = next(node for node in nodes if isinstance(node, ast.FunctionDef) and node.name == name)
    node.decorator_list = []
    namespace = dict(vars(module))
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(module.__file__), "exec"), namespace)
    original = getattr(owner or module, name)
    old_code = original.__code__
    original.__code__ = namespace[name].__code__
    return original, old_code


def run_pin(cls, name):
    result = unittest.TestResult()
    cls(name).run(result)
    return result


def main():
    cls = pins.StoreReentryRecordedTest
    print("Build the recorded replay once (847 decisions)", flush=True)
    cls.setUpClass()
    records = []
    try:
        for case in (cls, pins.InStoreExecutorTest):
            for name in unittest.defaultTestLoader.getTestCaseNames(case):
                result = run_pin(case, name)
                if not result.wasSuccessful():
                    for failure in result.failures + result.errors:
                        print(failure[1], file=sys.stderr)
                    raise RuntimeError("baseline pin failed: " + name)
        print("All baseline pins passed", flush=True)
        mixin = policy_instore.InStoreMixin
        mutations = [
            ("P0 flag-off", policy_instore, mixin, "_in_store_ops_active",
             'bool(getattr(self, "_in_store_ops_enabled", False))', 'True',
             "test_p0_switch_off_replay_reproduces_every_recorded_key"),
            ("P1 activation / P11 progress", policy_instore, mixin, "_in_store_try_start",
             'if not self._in_store_ops_active():', 'if True:',
             "test_p1_in_store_operation_is_the_recorded_release_body"),
            ("P2 exact total", cli, None, "_in_store_buy_continuations",
             'total = row.price * quantity', 'total = row.price',
             "test_p2_confirmation_gate_is_the_exact_total"),
            ("P2 wand rounding", cli, None, "_in_store_buy_continuations",
             'if row.tval == TVAL_WAND and row.count > 1:', 'if False:',
             "test_p2_wand_stack_keeps_the_generic_price_gate"),
            ("P2 mismatch breaker", policy_instore, mixin, "_in_store_reconcile",
             '"failed:price-mismatch": "price-mismatch",', '',
             "test_p2_price_mismatch_declines_and_trips_the_breaker"),
            ("P3 re-address", policy_instore, mixin, "_in_store_entry_key",
             'ledger = getattr(self, "_in_store_entry_ledger", None)', 'ledger = None',
             "test_p3_sale_then_buy_are_addressed_from_each_observed_page"),
            ("P4 screen", policy_instore, mixin, "_in_store_preconditions",
             'getattr(self, "_in_store_screen_verified", None) is True', 'True',
             "test_p4_unverified_page_falls_back_to_observe_and_leave"),
            ("P4 page", policy_instore, mixin, "_in_store_preconditions",
             '"page_one": store.page_top == 0', '"page_one": True',
             "test_p4_unverified_page_falls_back_to_observe_and_leave"),
            ("P4 double purchase", policy_instore, mixin, "_in_store_emit",
             'self._shop_observation = None', 'pass',
             "test_p4_in_store_operation_clears_an_earlier_observation_of_the_shelf"),
            ("P5 skip", policy_instore, mixin, "_shelf_evidence_skips_need",
             '            return True', '            return False',
             "test_p5_shelf_proven_fruitless_stops_are_skipped"),
            ("P6 present", policy_instore, mixin, "_shelf_evidence_skips_need",
             'entry is None or not entry["absent"]', 'entry is None',
             "test_p6_stops_are_kept_when_the_shelf_can_supply_or_evidence_expired"),
            ("P6 expired", policy_instore, mixin, "_shelf_evidence_entry",
             'record is None or not self._shelf_evidence_valid(record, snapshot.turn)', 'record is None',
             "test_p6_stops_are_kept_when_the_shelf_can_supply_or_evidence_expired"),
            ("P7 owner change", policy_instore, None, "shelf_item_name",
             'return _INSCRIPTION.sub("", name).strip()', 'return name.strip()',
             "test_p7_restock_is_known_from_observations_only"),
            ("P7 hard window", policy_instore, mixin, "_observe_shelf_evidence",
             'if entering and snapshot.turn - previous["turn"] >= STORE_MAINTENANCE_INTERVAL_TURNS:',
             'if False:', "test_p7_restock_is_known_from_observations_only"),
            ("P8 restart", policy_instore, mixin, "load_in_store_breaker",
             'if path is None or not path.exists():', 'if True:',
             "test_p8_store_command_refusal_trips_a_breaker_that_survives_restart"),
            ("P9 lifecycle", policy_instore, mixin, "_in_store_effect_confirmed",
             'ledger["ops"] += 1', 'ledger["ops"] += 0',
             "test_p9_visit_operates_in_store_and_closes_outside"),
            ("P12 refusal", policy_instore, mixin, "_in_store_reconcile",
             'if owner == IN_STORE_BUY_REASON and business_outcome == "failed:purchase-refused":',
             'if False:', "test_p12_refused_purchase_closes_the_visit"),
            ("P11 operation reason", policy_instore, mixin, "_in_store_emit",
             'IN_STORE_BUY_REASON if key.startswith(BUY_KEY)',
             '"shop:one-shot-buy" if key.startswith(BUY_KEY)',
             "test_p1_in_store_operation_is_the_recorded_release_body"),
            ("Entry bound", policy_instore, mixin, "_in_store_entry_key",
             'ledger["ops"] >= STORE_STUCK_LIMIT', 'False',
             "test_per_entry_bound_ends_the_entry"),
            ("No-effect exit", policy_instore, mixin, "_in_store_leave",
             'visit.operation_posted = False', 'pass',
             "test_unconfirmed_operation_leaves_without_retry"),
            ("Home-first fallback", policy_instore, mixin, "_in_store_selection",
             'home_gate = self._evaluate_purchase_home_gate(snapshot, item)',
             'home_gate = ProcurementHomeGate.ALLOW_PURCHASE',
             "test_home_first_keeps_the_existing_detour"),
            ("P13 pure shadow", policy_instore, mixin, "_in_store_shadow",
             'selection = self._in_store_selection(snapshot)',
             'self._shop(snapshot)\n        selection = self._in_store_selection(snapshot)',
             "test_p13_shadow_changes_no_policy_state"),
        ]
        for label, module, owner, function, before, after, test in mutations:
            path = Path(module.__file__)
            original_bytes = path.read_bytes()
            source = original_bytes.decode("utf-8")
            tree = ast.parse(source)
            functions = tree.body if owner is None else next(
                node.body for node in tree.body if isinstance(node, ast.ClassDef)
                and node.name == owner.__name__)
            node = next(node for node in functions if isinstance(node, ast.FunctionDef) and node.name == function)
            lines = source.splitlines(keepends=True)
            body = "".join(lines[node.lineno - 1:node.end_lineno])
            assert body.count(before) == 1, (label, before)
            modified = body.replace(before, after)
            lines[node.lineno - 1:node.end_lineno] = [modified]
            mutated = "".join(lines)
            loaded = None
            try:
                path.write_bytes(mutated.encode("utf-8"))
                loaded = recompile(module, owner, function, mutated)
                # P0 also removes the independent flag precondition. Both
                # guards protect activation; reverting only one cannot act.
                extra = None
                if label.startswith("P0"):
                    extra_source = mutated.replace(
                        '"flag": bool(getattr(self, "_in_store_ops_enabled", False))', '"flag": True')
                    path.write_bytes(extra_source.encode("utf-8"))
                    extra = recompile(module, mixin, "_in_store_preconditions", extra_source)
                try:
                    result = run_pin(cls, test)
                finally:
                    if extra:
                        extra[0].__code__ = extra[1]
                failed = not result.wasSuccessful()
                diff = subprocess.check_output(["git", "diff", "--", str(path)], cwd=ROOT, text=True, encoding="utf-8")
                records.append({"pin": label, "test": test, "source": str(path.relative_to(ROOT)),
                                "function": function, "reverted": before, "replacement": after,
                                "failed": failed, "failures": [text for _, text in result.failures + result.errors],
                                "diff_sha256": hashlib.sha256(diff.encode()).hexdigest()})
                print(label, "FAIL detected" if failed else "UNDETECTED", flush=True)
            finally:
                if loaded:
                    loaded[0].__code__ = loaded[1]
                path.write_bytes(original_bytes)
                assert path.read_bytes() == original_bytes
            restored = run_pin(cls, test)
            records[-1]["restored_pass"] = restored.wasSuccessful()
            if not failed or not restored.wasSuccessful():
                raise RuntimeError("revert proof incomplete: " + label)
    finally:
        cls.tearDownClass()
        (ROOT / "SOL-REVERT-PROOFS-instore.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
    print(f"{len(records)} revert proofs passed; all source bytes restored", flush=True)


if __name__ == "__main__":
    main()
