"""Freeze where the bot infers the game's input wait (design section 6.4, S0).

plans/DESIGN-control-context-1022.md: the one reader is hengbot.input_context.
This slice freezes today's places by file and function (never by count, so a
small tidy-up inside a function does not fail); a new place fails here and
later slices shrink the lists.

1. ``classify_screen`` is called only by the reader (and, during S0, by the
   executor's ``_classify``).
2. ``input_context`` is read only by the reader.
3. A screen reply's ``"lines"`` is read (``x["lines"]`` or ``x.get("lines", ...)``)
   only by the eight functions of 17b8907c and the reader.
4. The prompt literals ("[y/n]", "[Y/n]", "-more-", "-続く-") and the
   ``*_PROMPT_MESSAGE_PREFIXES`` tables are referenced only where they are today.
"""

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import ast
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "src" / "hengbot"
READER = "input_context.py"

CLASSIFY_SCREEN_CALLERS = {
    ("input_executor.py", "OperationExecutor._classify"),
}
LINES_READERS = {
    ("input_executor.py", "classify_screen"),
    ("input_executor.py", "_operation_messages"),
    ("input_executor.py", "_store_page_is_on_screen"),
    ("input_executor.py", "compose_barrier_board"),
    ("input_executor.py", "OperationExecutor._after_post"),
    ("cli.py", "_release_prompt_gated_tail"),
    ("observed_input.py", "compile_observed_input"),
}
PROMPT_LITERALS = ("[y/n]", "[Y/n]", "-more-", "-続く-")
PROMPT_TEXT_SITES = {
    ("cli.py", "<module>"),
    ("cli.py", "_dungeon_entrance_continuation"),
    ("cli.py", "_open_game_prompt"),
    ("input_executor.py", "classify_screen"),
    ("item_reservation.py", "store_item_key"),
    ("policy_instore.py", "expected_buy_confirmation"),
    ("input_executor.py", "OperationExecutor._is_recall_depth_confirm"),
    ("input_executor.py", "OperationExecutor._is_warning_confirm"),
    ("policy.py", "<module>"),
    ("policy.py", "HengbotPolicy._skill_exp_request_key"),
    ("policy.py", "HengbotPolicy._warning_prompt_response_key"),
    ("policy.py", "HengbotPolicy.choose_key"),
}


def _is_constant(node, value):
    return isinstance(node, ast.Constant) and node.value == value


def input_inference_sites(name: str, text: str) -> dict[str, set[tuple[str, str]]]:
    """(rule -> {(file, qualified function)}) for one module's source."""
    sites: dict[str, set[tuple[str, str]]] = {
        "classify_screen": set(), "input_context": set(), "lines": set(), "prompt_text": set(),
    }

    def visit(node, scope):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                visit(child, scope + [child.name])
                continue
            where = (name, ".".join(scope) or "<module>")
            if isinstance(child, ast.Call):
                function = child.func
                called = function.id if isinstance(function, ast.Name) else (
                    function.attr if isinstance(function, ast.Attribute) else None)
                if called == "classify_screen":
                    sites["classify_screen"].add(where)
                if isinstance(function, ast.Attribute) and function.attr == "get" and child.args:
                    if _is_constant(child.args[0], "lines"):
                        sites["lines"].add(where)
                    if _is_constant(child.args[0], "input_context"):
                        sites["input_context"].add(where)
            elif isinstance(child, ast.Subscript):
                if _is_constant(child.slice, "lines"):
                    sites["lines"].add(where)
                if _is_constant(child.slice, "input_context"):
                    sites["input_context"].add(where)
            elif isinstance(child, ast.Compare) and _is_constant(child.left, "input_context"):
                sites["input_context"].add(where)
            elif isinstance(child, ast.Constant) and isinstance(child.value, str) \
                    and any(literal in child.value for literal in PROMPT_LITERALS):
                sites["prompt_text"].add(where)
            elif isinstance(child, ast.Name) and child.id.endswith("_PROMPT_MESSAGE_PREFIXES"):
                sites["prompt_text"].add(where)
            elif isinstance(child, ast.Attribute) and child.attr.endswith("_PROMPT_MESSAGE_PREFIXES"):
                sites["prompt_text"].add(where)
            elif isinstance(child, ast.alias) \
                    and (child.asname or child.name).endswith("_PROMPT_MESSAGE_PREFIXES"):
                sites["prompt_text"].add(where)
            visit(child, scope)

    visit(ast.parse(text), [])
    return sites


def bot_sites() -> dict[str, set[tuple[str, str]]]:
    merged: dict[str, set[tuple[str, str]]] = {}
    for path in sorted(SOURCE.rglob("*.py")):
        name = path.relative_to(SOURCE).as_posix()
        for rule, found in input_inference_sites(name, path.read_text(encoding="utf-8")).items():
            merged.setdefault(rule, set()).update(found)
    return merged


class InputInferenceSitesAreFrozen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sites = bot_sites()

    @staticmethod
    def outside_reader(found):
        return {site for site in found if site[0] != READER}

    def test_classify_screen_is_called_only_by_the_reader(self):
        self.assertLessEqual(self.outside_reader(self.sites["classify_screen"]),
                             CLASSIFY_SCREEN_CALLERS)
        self.assertIn((READER, "current_input_state"), self.sites["classify_screen"])

    def test_input_context_is_read_only_by_the_reader(self):
        self.assertEqual(self.outside_reader(self.sites["input_context"]), set())
        self.assertIn((READER, "read_input_context"), self.sites["input_context"])

    def test_screen_lines_are_read_only_where_they_are_today(self):
        self.assertEqual(self.outside_reader(self.sites["lines"]), LINES_READERS)

    def test_prompt_text_is_referenced_only_where_it_is_today(self):
        self.assertEqual(self.outside_reader(self.sites["prompt_text"]), PROMPT_TEXT_SITES)

    def test_a_new_reader_in_another_function_is_found(self):
        # Revert-proof for the scanner itself: both spellings and a nested
        # method are found, attributed to the enclosing function.
        found = input_inference_sites("policy.py", (
            "class P:\n"
            "    def choose(self, screen, reply):\n"
            "        top = screen['lines'][0]\n"
            "        rows = screen.get('lines', ())\n"
            "        kind = reply.get('input_context')\n"
            "        if top.endswith('-more-'):\n"
            "            return classify_screen(screen)\n"))
        self.assertEqual(found["lines"], {("policy.py", "P.choose")})
        self.assertEqual(found["input_context"], {("policy.py", "P.choose")})
        self.assertEqual(found["prompt_text"], {("policy.py", "P.choose")})
        self.assertEqual(found["classify_screen"], {("policy.py", "P.choose")})
        self.assertFalse(found["lines"] <= LINES_READERS)


if __name__ == "__main__":
    unittest.main()
