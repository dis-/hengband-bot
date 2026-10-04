"""The decision-facts capture reuses supply-ledger results within one capture.

_capture_decision_facts evaluates the supply ledger hundreds of times per town
decision (equipment optimization -> town need candidates -> retention surplus
per item) with one board.  The memo must not change any captured fact, must
miss when the capture itself writes a ledger input, and must not outlive the
capture.
"""
import ast
from contextlib import nullcontext
from dataclasses import replace
import gzip
import inspect
import textwrap
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import tests  # noqa: F401 -- isolate runtime writes
from hengbot import cli, policy_supply
from hengbot.cli import _capture_decision_facts
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_supply import supply_ledger_observer_memo
from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURE = Path(__file__).parent / "fixtures" / "supply-ledger-memo-20261003.jsonl.gz"
# LF-normalized payload; producer: tests/extract_supply_ledger_memo_fixture.py
FIXTURE_SHA256 = "264b3a7278b69397d30dcff5a75af862eb1a1a3ff1c23df9a8b954833df13976"


def _board_snapshot(board, monrace):
    snapshot = parse_snapshot(board, monrace)
    player = snapshot.player
    if player.two_weapon_skill is None or player.shield_skill is None:
        # These captures predate the skill fields; the replay used the same
        # defaults for both the memoized and the unmemoized evaluation.
        snapshot = replace(snapshot, player=replace(
            player,
            two_weapon_skill=player.two_weapon_skill or 4000,
            shield_skill=player.shield_skill or 3000,
        ))
    return snapshot


def _canonical(facts) -> str:
    return json.dumps(facts, default=str, sort_keys=True, ensure_ascii=False)


class SupplyLedgerObserverMemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = gzip.decompress(FIXTURE.read_bytes()).replace(b"\r\n", b"\n")
        assert hashlib.sha256(payload).hexdigest() == FIXTURE_SHA256
        cls.rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _segment(self, name):
        return [
            _board_snapshot(row["board"], self.monrace)
            for row in self.rows
            if row["segment"] == name
        ]

    def test_memoized_facts_equal_unmemoized_facts_on_recorded_boards(self):
        for segment in ("town", "dungeon"):
            with self.subTest(segment=segment), TemporaryDirectory() as directory:
                snapshots = self._segment(segment)
                policy = _policy(Path(directory), self.monrace)
                policy.prime(snapshots[0])
                ledger_calls = 0
                computed = 0
                real_ledger = HengbotPolicy._supply_ledger
                real_compute = HengbotPolicy._compute_supply_ledger

                def ledger(self_, snapshot, depth):
                    nonlocal ledger_calls
                    ledger_calls += 1
                    return real_ledger(self_, snapshot, depth)

                def compute(self_, snapshot, depth):
                    nonlocal computed
                    computed += 1
                    return real_compute(self_, snapshot, depth)

                for index, snapshot in enumerate(snapshots):
                    key = policy.choose_key(snapshot)
                    with (
                        patch.object(HengbotPolicy, "_supply_ledger", ledger),
                        patch.object(HengbotPolicy, "_compute_supply_ledger", compute),
                    ):
                        memoized = _capture_decision_facts(snapshot, policy)
                    with patch.object(cli, "supply_ledger_observer_memo", nullcontext):
                        plain = _capture_decision_facts(snapshot, policy)
                    self.assertEqual(_canonical(memoized), _canonical(plain), index)
                    if key:
                        policy.confirm_key_posted(key)
                # The memo is exercised: repeated reads within one capture
                # were served without recomputing the ledger.
                self.assertGreater(ledger_calls, computed)
                self.assertGreater(computed, 0)

    def test_memo_is_dropped_when_the_capture_ends(self):
        snapshot = self._segment("town")[0]
        with TemporaryDirectory() as directory:
            policy = _policy(Path(directory), self.monrace)
            policy.prime(snapshot)
            policy.choose_key(snapshot)
            memos = []
            computed = 0
            real_compute = HengbotPolicy._compute_supply_ledger

            def compute(self_, board, depth):
                nonlocal computed
                computed += 1
                memos.append(policy_supply._SUPPLY_LEDGER_OBSERVER_MEMO.get())
                return real_compute(self_, board, depth)

            with patch.object(HengbotPolicy, "_compute_supply_ledger", compute):
                self.assertIsNone(policy_supply._SUPPLY_LEDGER_OBSERVER_MEMO.get())
                _capture_decision_facts(snapshot, policy)
                first = computed
                first_memo = memos[0]
                self.assertIsNotNone(first_memo)
                self.assertIsNone(policy_supply._SUPPLY_LEDGER_OBSERVER_MEMO.get())
                # A second capture of the same board starts from an empty memo.
                _capture_decision_facts(snapshot, policy)
                self.assertEqual(computed, 2 * first)
                self.assertIsNot(memos[first], first_memo)
                # Outside a capture every read recomputes.
                computed = 0
                depth = policy._planned_depth()
                policy._supply_ledger(snapshot, depth)
                policy._supply_ledger(snapshot, depth)
                self.assertEqual(computed, 2)
                # The memo is dropped even when the capture raises.
                with patch.object(
                    cli, "_capture_decision_facts_unchecked",
                    side_effect=ValueError("boom"),
                ):
                    with self.assertRaises(ValueError):
                        _capture_decision_facts(snapshot, policy)
                self.assertIsNone(policy_supply._SUPPLY_LEDGER_OBSERVER_MEMO.get())

    def test_memo_keys_on_board_identity_and_depth(self):
        snapshot = self._segment("dungeon")[0]
        with TemporaryDirectory() as directory:
            policy = _policy(Path(directory), self.monrace)
            policy.prime(snapshot)
            computed = []
            real_compute = HengbotPolicy._compute_supply_ledger

            def compute(self_, board, depth):
                computed.append((id(board), depth))
                return real_compute(self_, board, depth)

            twin = replace(snapshot)
            with (
                patch.object(HengbotPolicy, "_compute_supply_ledger", compute),
                supply_ledger_observer_memo(),
            ):
                first = policy._supply_ledger(snapshot, 3)
                first["recall"] = None  # a caller's edit stays in its copy
                again = policy._supply_ledger(snapshot, 3)
                policy._supply_ledger(snapshot, 4)
                policy._supply_ledger(twin, 3)
            self.assertEqual(
                computed,
                [(id(snapshot), 3), (id(snapshot), 4), (id(twin), 3)],
            )
            self.assertIsNotNone(again["recall"])

    def test_a_capture_write_to_a_ledger_input_is_a_miss(self):
        snapshot = self._segment("dungeon")[0]
        with TemporaryDirectory() as directory:
            policy = _policy(Path(directory), self.monrace)
            policy.prime(snapshot)
            computed = 0
            real_compute = HengbotPolicy._compute_supply_ledger

            def compute(self_, board, depth):
                nonlocal computed
                computed += 1
                return real_compute(self_, board, depth)

            mode = policy._fundraising_mode
            with (
                patch.object(HengbotPolicy, "_compute_supply_ledger", compute),
                supply_ledger_observer_memo(),
            ):
                plain = policy._supply_ledger(snapshot, 3)
                # _recall_stockout_persists swaps the mode around a ledger read.
                policy._fundraising_mode = "mine"
                mined = policy._supply_ledger(snapshot, 3)
                policy._fundraising_mode = mode
                restored = policy._supply_ledger(snapshot, 3)
                self.assertEqual(computed, 2)
                policy._equipment_optimization_last_depth = 30
                depth_changed = policy._supply_ledger(snapshot, 3)
                policy._deferred_home_items.add(("deferred", 1, 1))
                # Deferral leaves this board's counts unchanged, but it now
                # affects Home remove-curse procurement and must miss the memo.
                self.assertEqual(policy._supply_ledger(snapshot, 3), depth_changed)
                self.assertEqual(computed, 4)
                policy._supply_ledger(snapshot, 3)
                self.assertEqual(computed, 4)
                policy._deferred_home_items.clear()
                policy._supply_ledger(snapshot, 3)
            self.assertEqual(computed, 4)
            self.assertEqual(mined["recall"].required_return, 0)
            self.assertEqual(restored, plain)

    def test_memo_inputs_cover_every_ledger_input_the_capture_writes(self):
        """Static scan: what the facts evaluators can write vs what the ledger
        reads.  An attribute in both must be in the memo key, or be a memo of
        a pure computation whose rewrite cannot change a ledger result."""
        source = Path(cli.__file__).parent
        methods: dict[str, list[ast.FunctionDef]] = {}
        for path in source.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            methods.setdefault(item.name, []).append(item)
        info = {name: _self_access(defs) for name, defs in methods.items()}

        def closure(roots):
            seen, stack = set(), list(roots)
            while stack:
                name = stack.pop()
                if name in seen or name not in info:
                    continue
                seen.add(name)
                stack.extend(info[name][2])
            return seen

        roots = [
            "with_known_skill_exp", "fixed_quest_readiness_state",
            "retention_reservation_state", "procurement_requirements",
            "threat_prediction", "equipment_optimization_state", "loot_state",
            "departure_block_state", "cross_town_shopping_state",
            "approved_quest_strategy",
        ]
        cli_tree = ast.parse(Path(cli.__file__).read_text(encoding="utf-8"))
        for node in cli_tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in {
                "_capture_decision_facts_unchecked", "_over_extension_state",
                "_depth_safety", "_mining_state", "_fundraising_state",
                "_town_plan_state",
            }:
                roots.extend(
                    sub.attr for sub in ast.walk(node)
                    if isinstance(sub, ast.Attribute)
                    and isinstance(sub.value, ast.Name)
                    and sub.value.id == "policy"
                )
        ledger_reads = set().union(
            *(info[name][0] for name in closure(["_compute_supply_ledger"]))
        ) - set(methods)
        facts_writes = set().union(*(info[name][1] for name in closure(roots)))
        keyed = _self_attributes(HengbotPolicy._supply_ledger_observer_inputs)
        pure_memos = {"_aggregate_ranged_cache", "_threat_prediction_memo"}
        self.assertIn("_town_supplier_stock", ledger_reads)  # the scan sees reads
        self.assertIn("_fundraising_mode", facts_writes)  # and capture writes
        self.assertEqual((ledger_reads & facts_writes) - pure_memos, keyed)


_MUTATORS = {
    "add", "discard", "remove", "clear", "update", "pop", "popitem", "append",
    "extend", "insert", "setdefault", "appendleft", "popleft", "sort",
    "reverse", "difference_update", "intersection_update",
}


def _is_self(node) -> bool:
    return isinstance(node, ast.Name) and node.id == "self"


def _self_attribute_named(node):
    """``self.x`` or ``getattr(self, "x"...)`` -> "x", else None."""
    if isinstance(node, ast.Attribute) and _is_self(node.value):
        return node.attr
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) > 1
        and _is_self(node.args[0])
        and isinstance(node.args[1], ast.Constant)
    ):
        return node.args[1].value
    return None


def _self_access(defs):
    """(attributes read, attributes written, methods called) through self."""
    reads, writes, calls = set(), set(), set()
    for definition in defs:
        for node in ast.walk(definition):
            if isinstance(node, ast.Attribute) and _is_self(node.value):
                (writes if isinstance(node.ctx, (ast.Store, ast.Del)) else reads).add(
                    node.attr
                )
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and _is_self(func.value):
                    calls.add(func.attr)
                elif isinstance(func, ast.Attribute) and func.attr in _MUTATORS:
                    if (name := _self_attribute_named(func.value)) is not None:
                        writes.add(name)
                elif (
                    isinstance(func, ast.Name)
                    and func.id in {"getattr", "setattr", "hasattr"}
                    and len(node.args) > 1
                    and _is_self(node.args[0])
                    and isinstance(node.args[1], ast.Constant)
                ):
                    (writes if func.id == "setattr" else reads).add(node.args[1].value)
            elif isinstance(node, (ast.Assign, ast.AugAssign, ast.Delete)):
                targets = (
                    [node.target] if isinstance(node, ast.AugAssign) else node.targets
                )
                for target in targets:
                    while isinstance(target, ast.Subscript):
                        target = target.value
                    if (name := _self_attribute_named(target)) is not None:
                        writes.add(name)
    return reads, writes, calls


def _self_attributes(function) -> set[str]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    return {
        node.attr for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and _is_self(node.value)
    }


if __name__ == "__main__":
    unittest.main()
