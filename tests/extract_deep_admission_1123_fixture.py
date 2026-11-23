"""Write the 50F+ admission gates' answers of main 5fe531c0a (tests/fixtures/deep-admission-1123).

Whole-bot maintainability review 2026-11-23 K2: before the gates were routed through
deep_admission.verdict, every gate was asked over the table of tests/support/deep_admission_table
(its cells and its DECLARED CONSTRUCTED facts) and the answers were written here; the routed
gates must give the same answers (tests/test_deep_admission_1123.py).

    python tests/extract_deep_admission_1123_fixture.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests"), str(ROOT)]

import tests  # noqa: E402,F401 -- isolate runtime files
from support import deep_admission_table as table  # noqa: E402

OUT = Path(__file__).with_name("fixtures") / "deep-admission-1123"


def main() -> int:
    with TemporaryDirectory() as scratch:
        policy, town, board = table.load_recorded(Path(__file__).with_name("fixtures"), scratch)
        answers = table.answers(policy, town, board)
        policy._home_disposal.history_path.unlink(missing_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "answers.json").write_text(table.dumps(answers), encoding="utf-8", newline="\n")
    (OUT / "disagreements.json").write_text(
        table.dumps(table.disagreements(answers)), encoding="utf-8", newline="\n")
    print(f"{len(answers)} gates, {len(table.disagreements(answers))} disagreeing cells")
    return 0


if __name__ == "__main__":
    sys.exit(main())
