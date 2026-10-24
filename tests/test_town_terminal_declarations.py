"""ROOT-FIX S1 structural checks of the terminal declarations (design 3.7).

1. Every ``_town_producer_entry("<rung>", ...)`` name in src (collected by AST)
   is a ``TERMINALS`` key, and no key is extra.
2. Modes: ENFORCE only for the two quest rungs; EXEMPT_SURVIVAL only for the
   survival/detectors/bookkeeping families; SHADOW only for the fixed S1->S2
   list (its census is pinned and may only shrink).
3. A producer of the manifest called by ``_decide`` outside the entry is in
   the fixed S1->S2 list ``DIRECT_PRODUCERS_S1``.
4. ``REFUSAL_SERVERS`` keys equal the declared codes; every code literal the
   verdict and the refusal-code namer return is declared.
5. A server's family is a town arbiter owner family; its category is a name
   of ``_town_need_registry``.
6. ``intended_terminal`` and the per-decision admission do not write on a
   second call.
"""

import tests  # noqa: F401

import ast
import gzip
import json
import unittest
from pathlib import Path

from hengbot import town_terminal
from hengbot.claim_ladder import rung_named
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.town_arbiter import owner_families
from hengbot.town_terminal import (
    ENFORCE,
    EXEMPT_FAMILIES,
    EXEMPT_SURVIVAL,
    QUEST_ENTRY_CODES,
    REFUSAL_SERVERS,
    SHADOW,
    TERMINALS,
    declared_code,
)


SRC = Path(__file__).resolve().parents[1] / "src" / "hengbot"
FIXTURE = Path(__file__).parent / "fixtures" / "n1a-townalt-20261023.jsonl.gz"
S1_SHADOW_CENSUS = 109
S1_DIRECT_CENSUS = 0


def _entry_calls():
    """(rung name, family keyword) of every _town_producer_entry call."""
    rows = []
    for path in sorted(SRC.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "_town_producer_entry"):
                continue
            family = next((keyword.value.value for keyword in node.keywords
                           if keyword.arg == "family"
                           and isinstance(keyword.value, ast.Constant)), None)
            name = node.args[0]
            for choice in ((name,) if isinstance(name, ast.Constant)
                           else (name.body, name.orelse)):
                assert isinstance(choice, ast.Constant), ast.dump(name)
                rows.append((choice.value, family))
    return rows


def _function(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == name)


class TerminalDeclarationTest(unittest.TestCase):
    def test_self_check_collects_the_known_entries(self):
        names = {name for name, _family in _entry_calls()}
        self.assertIn("_fixed_quest_key#2", names)
        self.assertIn("town-teleport", names)
        self.assertIn("verified-disposal", names)

    def test_1_every_entry_rung_is_declared(self):
        self.assertEqual({name for name, _family in _entry_calls()}, set(TERMINALS))

    def test_2_modes(self):
        families = {}
        for name, family in _entry_calls():
            rung = rung_named(name)
            families[name] = family or (rung.family if rung is not None else None)
        enforce = {name for name, decl in TERMINALS.items() if decl.mode == ENFORCE}
        self.assertEqual(enforce, {"_fixed_quest_key#1", "_fixed_quest_key#2"})
        for name, decl in TERMINALS.items():
            self.assertIn(decl.mode, {ENFORCE, SHADOW, EXEMPT_SURVIVAL}, name)
            if decl.mode == EXEMPT_SURVIVAL:
                self.assertIn(families[name], EXEMPT_FAMILIES, name)
            if decl.mode == SHADOW:
                self.assertIn(name, town_terminal.SHADOW_RUNGS, name)
                self.assertNotIn(families[name], EXEMPT_FAMILIES, name)
            if decl.mode == ENFORCE:
                self.assertIsNotNone(decl.intended_terminal, name)
        # The S1->S2 list may only shrink (empty at the S2 exit).
        self.assertLessEqual(len(town_terminal.SHADOW_RUNGS), S1_SHADOW_CENSUS)

    def test_3_direct_producers_are_listed(self):
        manifest = json.loads((SRC / "town_work_sites.json").read_text(encoding="utf-8"))
        producers = {key.rsplit(".", 1)[-1] for key, row in manifest.items()
                     if row.get("classification") == "producer"}
        decide = _function(SRC / "policy.py", "_decide")
        wrapped = set()
        for node in ast.walk(decide):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "_town_producer_entry"):
                for argument in node.args[1:]:
                    wrapped.update(id(inner) for inner in ast.walk(argument))
        direct = {
            node.func.attr for node in ast.walk(decide)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "self"
            and node.func.attr in producers and id(node) not in wrapped
        }
        self.assertEqual(direct, set())
        self.assertEqual(town_terminal.DIRECT_PRODUCERS_S1, frozenset())
        self.assertLessEqual(len(town_terminal.DIRECT_PRODUCERS_S1), S1_DIRECT_CENSUS)

    def test_4_codes_and_table_agree(self):
        # S2 (supervisor decision 2026-10-23 (1)): the keys are the union of
        # every terminal's declared codes; every verdict_* function is scanned.
        self.assertLessEqual(set(QUEST_ENTRY_CODES), set(town_terminal.TERMINAL_CODES))
        self.assertEqual(set(REFUSAL_SERVERS), set(town_terminal.TERMINAL_CODES))
        verdicts = sorted(
            node.name for node in ast.parse(
                (SRC / "town_terminal.py").read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef) and node.name.startswith("verdict_"))
        self.assertIn("verdict_store_buy", verdicts)
        literals = set()
        for path, name in ((*((SRC / "town_terminal.py", verdict) for verdict in verdicts),
                            (SRC / "policy_equipment.py",
                             "_equipment_departure_refusal_codes"))):
            for node in ast.walk(_function(path, name)):
                if isinstance(node, ast.Return) and node.value is not None:
                    emitted = node.value
                elif (isinstance(node, ast.Call)
                      and (isinstance(node.func, ast.Name) and node.func.id == "refused"
                           or isinstance(node.func, ast.Attribute)
                           and node.func.attr in {"append", "extend"})):
                    emitted = ast.Tuple(elts=node.args)
                else:
                    continue
                for inner in ast.walk(emitted):
                    if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                        literals.add(inner.value)
                    if isinstance(inner, ast.JoinedStr):
                        literals.add(inner.values[0].value + "detail")
        self.assertIn("identification-flow", literals)
        self.assertIn("missing-ability:detail", literals)
        for literal in sorted(literals):
            self.assertIsNotNone(declared_code(literal), literal)
        self.assertIsNone(declared_code("no-such-code"))
        self.assertEqual(declared_code("pack-space-required:2"), "pack-space-required:*")

    def test_5_servers_name_registered_owners_and_needs(self):
        families = set(owner_families())
        categories = {spec.category for spec in HengbotPolicy()._town_need_registry()}
        for code, servers in REFUSAL_SERVERS.items():
            for server in servers:
                self.assertIn(server.family, families, code)
                if server.category is not None:
                    self.assertIn(server.category, categories, code)

    def test_6_second_reads_do_not_write(self):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            board = parse_snapshot(json.loads(stream.readline()), {})
        policy = HengbotPolicy()
        policy._build_grid_index(board)
        policy._map_predicate_snapshot = board
        policy._decision_sequence = 1
        first = town_terminal.fixed_quest_intended_terminal(policy, board)
        town_terminal.terminal_admission(policy, board, first)
        watched = ("_town_blocked_reason", "_departure_block", "_fixed_quest_readiness",
                   "_equipment_departure_cache_token", "last_reason",
                   "_equipment_transaction_visit_closure",
                   "_equipment_optional_failure_pending", "_terminal_admission_memo")
        before = {name: repr(getattr(policy, name, None)) for name in watched}
        keys = set(vars(policy))
        self.assertEqual(town_terminal.fixed_quest_intended_terminal(policy, board), first)
        town_terminal.terminal_admission(policy, board, first)
        self.assertEqual({name: repr(getattr(policy, name, None)) for name in watched}, before)
        self.assertEqual(set(vars(policy)), keys)


if __name__ == "__main__":
    unittest.main()
