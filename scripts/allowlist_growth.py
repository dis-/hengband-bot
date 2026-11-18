#!/usr/bin/env python3
"""Report (never block) commits that grow a lint's allow-list or baseline.

2026-11-17 owner (whole-bot maintainability review Q9, N5): a branch can make a red
lint pass by adding to its allow-list in the same commit.  The merge gate does not
stop that; it records it.  Given a base and a head commit, this prints one line per
allow-list that gained lines::

    ALLOWLIST +N lines in <file>
    ALLOWLIST +N lines in <file> (<CONSTANT>)

and always exits 0.  N counts added lines only (a rewritten line is +1), so a
shrink prints nothing.

Usage: python scripts/allowlist_growth.py BASE HEAD    (or BASE..HEAD)
"""
from __future__ import annotations

import ast
import difflib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

# Files that are allow-lists or recorded baselines as a whole.
ALLOWLIST_FILES = (
    'scripts/cross_rule_baseline.json',
    'scripts/item_intent_baseline.json',
    'scripts/item_sink_adapters.json',
    'scripts/item_sink_lint_baseline.json',
    'scripts/melee_site_lint_baseline.json',
    'scripts/ownership_claim_exceptions.txt',
    'scripts/test_fakery_lint_baseline.json',
    'scripts/town_structure_lint_baseline.json',
)
# Allow-lists written as a module-level constant inside a lint.
ALLOWLIST_CONSTANTS = (
    ('scripts/destruction_means_lint.py', 'ALLOWED'),
    ('scripts/item_sink_lint.py', 'NON_ITEM_COMPOSITIONS'),
    ('scripts/item_sink_lint.py', 'STANDALONE_ADAPTERS'),
    ('scripts/melee_site_lint.py', 'GUARDED_ELSEWHERE'),
    ('scripts/step_gate_lint.py', 'MOVEMENT_BYPASSES'),
    ('scripts/step_gate_lint.py', 'WARNING_READ_BYPASSES'),
    ('scripts/tier_reading_lint.py', 'BASELINE'),
    ('scripts/verify_scope.py', 'EXCLUDED_TESTS'),
    ('scripts/verify_scope.py', 'KNOWN_FAILURES'),
    ('scripts/verify_scope.py', 'KNOWN_LINT_FAILURES'),
)
# Inline allowances: an added line carrying the marker, anywhere under the directory.
ALLOWLIST_MARKERS = (
    ('tests/', 'TEST_FAKERY_LINT_ALLOW:'),
)


def _git(*args: str, repo: Path = ROOT) -> str | None:
    result = subprocess.run(['git', *args], cwd=repo, capture_output=True,
                            text=True, encoding='utf-8', errors='replace')
    return result.stdout if result.returncode == 0 else None


def _added(old: str, new: str) -> int:
    return sum(1 for line in difflib.ndiff(old.splitlines(), new.splitlines()) if line.startswith('+ '))


def _constant(source: str | None, name: str) -> str:
    if not source:
        return ''
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ''
    for node in tree.body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            return ast.get_source_segment(source, node) or ''
    return ''


def growth(base: str, head: str, repo: Path = ROOT) -> list[str]:
    lines = []
    for path in ALLOWLIST_FILES:
        added = _added(_git('show', f'{base}:{path}', repo=repo) or '',
                       _git('show', f'{head}:{path}', repo=repo) or '')
        if added:
            lines.append(f'ALLOWLIST +{added} lines in {path}')
    for path, name in ALLOWLIST_CONSTANTS:
        added = _added(_constant(_git('show', f'{base}:{path}', repo=repo), name),
                       _constant(_git('show', f'{head}:{path}', repo=repo), name))
        if added:
            lines.append(f'ALLOWLIST +{added} lines in {path} ({name})')
    for directory, marker in ALLOWLIST_MARKERS:
        diff = _git('diff', '-U0', '--no-color', base, head, '--', directory, repo=repo) or ''
        counts: dict[str, int] = {}
        current = None
        for line in diff.splitlines():
            if line.startswith('+++ '):
                current = line[6:] if line.startswith('+++ b/') else None
            elif line.startswith('+') and current and marker in line:
                counts[current] = counts.get(current, 0) + 1
        lines.extend(f'ALLOWLIST +{count} lines in {path} ({marker.rstrip(":")})'
                     for path, count in sorted(counts.items()))
    return lines


def main(argv: list[str]) -> int:
    revisions = argv[0].split('..', 1) if len(argv) == 1 and '..' in argv[0] else argv
    if len(revisions) != 2 or not all(revisions):
        print('ALLOWLIST error: usage: allowlist_growth.py BASE HEAD (or BASE..HEAD)')
        return 0
    base, head = revisions
    for revision in (base, head):
        if _git('rev-parse', '--verify', '--quiet', f'{revision}^{{commit}}') is None:
            print(f'ALLOWLIST error: unknown revision {revision}')
            return 0
    for line in growth(base, head):
        print(line)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
