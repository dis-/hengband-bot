"""tests/support/extraction.py: the shared readers match the copies they replace."""

import tests  # noqa: F401 -- isolate live runtime files
import ast
import gzip
import hashlib
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.support.extraction import decision_rows, input_ends, lines, rows, sha, write_xz

TESTS = Path(__file__).resolve().parent


def _copy_of(script: str, name: str):
    """The helper ``name`` as defined in an existing extraction script."""
    tree = ast.parse((TESTS / script).read_text(encoding="utf-8"))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == name)
    namespace = {"gzip": gzip, "json": json, "Path": Path}
    exec(compile(ast.Module(body=[function], type_ignores=[]), script, "exec"), namespace)
    return namespace[name]


class SupportExtractionTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_lines_keep_crlf_for_gzip_and_plain_files(self):
        text = '{"a": 1}\r\n{"b": 2}\n'
        plain = self.root / "state.jsonl"
        plain.write_bytes(text.encode("utf-8"))
        packed = self.root / "state.jsonl.gz"
        packed.write_bytes(gzip.compress(text.encode("utf-8")))
        self.assertEqual(lines(plain), ['{"a": 1}\r\n', '{"b": 2}\n'])
        self.assertEqual(lines(packed), lines(plain))
        self.assertEqual(lines(packed), _copy_of(
            "extract_castle_top_floor_exit_fixture.py", "_lines")(packed))

    def test_rows_and_decision_rows(self):
        path = self.root / "decisions.jsonl"
        path.write_text('{"decision_sequence": 1, "turn": 5}\n\n{"type": "x"}\n'
                        '{"decision_sequence": 2, "turn": 9}\n', encoding="utf-8")
        self.assertEqual(len(rows(path)), 3)
        self.assertEqual([row["turn"] for row in decision_rows(path)], [5, 9])

    def test_input_ends_matches_the_extractor_copy(self):
        decisions = [
            {"turn": 10, "timing": {"jsonl_drain_records": 1}},
            {"turn": 20, "timing": {"jsonl_drain_records": 2}},
            {"turn": 30, "timing": {}},
        ]
        state = [{"turn": turn} for turn in (5, 10, 15, 20, 25, 30, 30, 31)]
        expected = _copy_of("extract_town_approach_retired_fixture.py", "_input_ends")(decisions, state)
        self.assertEqual(input_ends(decisions, state), expected)
        self.assertEqual(expected, [1, 3, 6])

    def test_sha_and_write_xz(self):
        path = self.root / "fixture.bin"
        path.write_bytes(b"a\r\nb\n")
        self.assertEqual(sha(path), hashlib.sha256(b"a\r\nb\n").hexdigest())
        self.assertEqual(sha(path, normalize_newlines=True), hashlib.sha256(b"a\nb\n").hexdigest())
        written = write_xz(self.root / "out" / "rows.json.xz", [{"名": 1}])
        self.assertEqual(json.loads(lzma.decompress(written.read_bytes())), [{"名": 1}])
        self.assertEqual(lzma.decompress(write_xz(self.root / "t.xz", "ü").read_bytes()), "ü".encode())


if __name__ == "__main__":
    unittest.main()
