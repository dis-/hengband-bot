"""Recorded baselines for the lints that were red when they joined the merge gate.

2026-11-17 owner (whole-bot maintainability review Q9): 「基準を取り直して検査に足す」.
item_sink_lint, town_structure_lint, melee_site_lint and test_fakery_lint keep
printing every finding, but exit non-zero only for findings that are not in their
recorded baseline (``scripts/<lint>_baseline.json``).

A baseline key never contains a line number: ``<file>:<enclosing function>: <message>``
(the function is the innermost ``def`` around the reported line, qualified by its
classes and outer functions), so an edit that only moves code does not trip the
lint.  Keys are counted: a fifth identical finding in a function that had four is
new.  A baseline entry that no longer matches is reported and does not fail; shrink
the file with ``--write-baseline``.  Growing the file is reported at merge time by
``scripts/allowlist_growth.py``.
"""
from __future__ import annotations

import ast
from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
import re

SCRIPTS = Path(__file__).resolve().parent
WRITE_FLAG = '--write-baseline'
ALL_FLAG = '--no-baseline'

# "arena.py: line 224: msg" (item_sink_lint) and "arena.py:379: expr" (melee_site_lint).
_LINE_FINDING = re.compile(r'^(?P<file>[^\s:]+\.py):(?: line)? ?(?P<line>\d+): (?P<message>.*)$', re.S)


def baseline_path(lint: str) -> Path:
    return SCRIPTS / f'{lint}_baseline.json'


@lru_cache(maxsize=None)
def _function_spans(path: Path) -> tuple[tuple[int, int, int, str], ...]:
    try:
        tree = ast.parse(path.read_text(encoding='utf8'))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return ()
    spans = []

    def visit(node, prefix, depth):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f'{prefix}{child.name}'
                if not isinstance(child, ast.ClassDef):
                    start = min([child.lineno, *(d.lineno for d in child.decorator_list)])
                    spans.append((start, child.end_lineno or child.lineno, depth, name))
                visit(child, name + '.', depth + 1)
            else:
                visit(child, prefix, depth)

    visit(tree, '', 0)
    return tuple(spans)


def enclosing_function(path: Path, line: int) -> str:
    """Innermost qualified ``def`` containing *line*, or ``<module>``."""
    inside = [span for span in _function_spans(path) if span[0] <= line <= span[1]]
    return max(inside, key=lambda span: span[2])[3] if inside else '<module>'


def line_finding_key(finding: str, root: Path) -> str:
    """Replace the line number of a ``file:line: message`` finding by its function."""
    match = _LINE_FINDING.match(finding)
    if not match:
        return finding
    function = enclosing_function(root / match['file'], int(match['line']))
    return f"{match['file']}:{function}: {match['message']}"


def load(lint: str) -> Counter:
    path = baseline_path(lint)
    if not path.exists():
        return Counter()
    return Counter(json.loads(path.read_text(encoding='utf8'))['findings'])


def write(lint: str, keys) -> Path:
    path = baseline_path(lint)
    payload = {
        '_comment': ('Known findings recorded 2026-11-17 (maintainability review Q9). '
                     'Keys are <file>:<function>: <message> with counts, never line numbers. '
                     f'Regenerate only to shrink: python scripts/{lint}.py {WRITE_FLAG}'),
        'findings': dict(sorted(Counter(keys).items())),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    return path


def new_findings(lint: str, findings, key) -> tuple[list, list[str]]:
    """Findings beyond the baseline's count for their key, and unmatched baseline keys."""
    remaining = load(lint)
    new = []
    for finding in findings:
        k = key(finding)
        if remaining[k] > 0:
            remaining[k] -= 1
        else:
            new.append(finding)
    stale = sorted(k for k, count in remaining.items() if count > 0)
    return new, stale


def gate(lint: str, label: str, findings, key, render=str, argv=()) -> int:
    """Shared tail of the baselined lints' ``main``: report and return the exit code."""
    if WRITE_FLAG in argv:
        path = write(lint, [key(finding) for finding in findings])
        print(f'{label}: wrote {len(findings)} finding(s) to {path.name}')
        return 0
    if ALL_FLAG in argv:
        return 1 if findings else 0
    new, stale = new_findings(lint, findings, key)
    for finding in new:
        print(f'{label}: NEW (not in {baseline_path(lint).name}): {render(finding)}')
    for k in stale:
        print(f'{label}: baseline entry no longer found (shrink with {WRITE_FLAG}): {k}')
    print(f'{label}: {len(findings)} finding(s), {len(findings) - len(new)} baselined, '
          f'{len(new)} new, {len(stale)} stale baseline entr(ies)')
    return 1 if new else 0
