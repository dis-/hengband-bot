"""The safe-now gates' table and their record-only watcher (owner 2026-11-15, review Q9).

Owner 「差は残し表で説明する」: the gates keep their differences; safety_watch ``GATES`` says what
each reads beyond the strictest reading (safety_facts ``strict_quiet``) and why, and its watcher
records each answer beside the board's facts.  It decides nothing.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import ast
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import junk_destroy_now, safety_facts, safety_watch
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

SRC = Path(__file__).resolve().parents[1] / "src" / "hengbot"
FIXTURE = Path(__file__).with_name("fixtures") / "abilities-depth34-landed-dungeon.json"


class GatesTableTest(unittest.TestCase):
    def test_every_gate_of_the_table_is_watched_once(self):
        watched = []
        for path in SRC.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for decorator in node.decorator_list:
                        if (isinstance(decorator, ast.Call)
                                and ast.unparse(decorator.func) == "safety_watch.watched"):
                            watched.append(decorator.args[0].value)
        self.assertEqual(sorted(watched), sorted(safety_watch.GATES))

    def test_the_strict_reading_is_the_junk_gate(self):
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        with TemporaryDirectory() as directory:
            policy = _policy(Path(directory), monrace)
            board = parse_snapshot(copy.deepcopy(raw), monrace)
            safety_watch.begin(policy)
            answer = junk_destroy_now.safe(policy, board)
            self.assertEqual(answer, safety_facts.strict_quiet(safety_facts.of(policy, board)))
            name, recorded, strict, _facts = safety_watch.report()[-1]
            self.assertEqual((name, recorded, strict), ("junk_destroy_now.safe", answer, answer))
            safety_watch.begin(policy)
            self.assertEqual(safety_watch.report(), [])

    def test_a_gate_answers_as_before(self):
        """The watcher returns the gate's own answer (and records nothing without a board)."""
        @safety_watch.watched("sealed_loot._safe")
        def gate(snapshot):
            return "answer"

        self.assertEqual(gate(object()), "answer")


if __name__ == "__main__":
    unittest.main()
