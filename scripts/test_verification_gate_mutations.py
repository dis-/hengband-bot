#!/usr/bin/env python3
"""Prove the round-6 verification-gate guards turn red under sabotage."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent

MUTATIONS = {
    "failed-test-filter-deleted": (
        "            if not test_id.startswith(\"unittest.loader._FailedTest.\")\n            and \"._FailedTest.\" not in test_id\n",
        "            if True\n",
    ),
    "inline-answer-key-denylist": (
        "    sections = _failure_sections(stderr)\n",
        "    if any(name in stderr for name in (\"NameError\", \"AttributeError\", \"ImportError\")):\n        return set()\n    sections = _failure_sections(stderr)\n",
    ),
    "inline-literal-answer-key": (
        "                        new_failures = failures - baseline[module]\n",
        "                        new_failures = failures - {'test_demo.T.test_pin'}\n",
    ),
    "docstring-prose-fallback-removed": (
        "            return \"nonbehavioral-docstring-prose\"\n",
        "            return \"behavioral\"\n",
    ),
    "dead-stalled-capture-pattern": (
        '        "pattern": "stalled_capture",\n',
        '        "pattern": "stalled-capture",\n',
    ),
    "git-remover-before-inspected-removal": (
        '        shutil.rmtree(path)\n    git(root, "worktree", "remove", "--force", str(path), check=False)\n',
        '        git(root, "worktree", "remove", "--force", str(path), check=False)\n        shutil.rmtree(path)\n',
    ),
    "lint-allowance-count-disabled": (
        '        if lint_allowance and len(undeclared_lint_findings) == lint_allowance["count"]:\n',
        '        if lint_allowance:\n',
    ),
    "excluded-test-prefix-wrong": (
        "test.id().startswith(prefix + '.')",
        "test.id().startswith('tests.' + prefix + '.')",
    ),
    "known-failure-matcher-disabled": (
        '    return matches if len(matches) == 1 and len(failure_ids) == matches[0]["count"] else []\n',
        '    return [] if matches else []\n',
    ),
}

PINS = {
    "failed-test-filter-deleted": "test_failed_loader_is_never_a_protector_even_for_structural_changes",
    "inline-answer-key-denylist": "test_inline_blanket_exception_denylist_cannot_void_assertion_pin",
    "inline-literal-answer-key": "test_inline_literal_answer_key_cannot_filter_new_failures",
    "docstring-prose-fallback-removed": "test_zero_context_docstring_prose_fallback_is_nonbehavioral",
    "dead-stalled-capture-pattern": "test_stalled_capture_allowance_matches_real_failure_text",
    "git-remover-before-inspected-removal": "test_cleanup_removes_inspected_directory_before_unregistering",
    "lint-allowance-count-disabled": "test_failed_skipped_and_lint_excess_are_measured",
    "excluded-test-prefix-wrong": "test_excluded_test_prefix_is_exact",
    "known-failure-matcher-disabled": "test_stalled_capture_allowance_matches_real_failure_text",
}


def main() -> int:
    results = {}
    for name, (old, new) in MUTATIONS.items():
        with tempfile.TemporaryDirectory(prefix="vgate-mutation-") as temporary:
            scripts = Path(temporary) / "scripts"; scripts.mkdir()
            for filename in ("hunk_guard.py", "verify_scope.py", "test_verification_gates.py"):
                shutil.copy2(HERE / filename, scripts / filename)
            target = scripts / ("hunk_guard.py" if old in (scripts / "hunk_guard.py").read_text(encoding="utf-8")
                                else "verify_scope.py")
            source = target.read_text(encoding="utf-8")
            if source.count(old) != 1:
                raise RuntimeError(f"{name}: mutation anchor count was {source.count(old)}")
            target.write_text(source.replace(old, new), encoding="utf-8")
            pin = f"VerificationGateSelfTest.{PINS[name]}"
            run = subprocess.run([sys.executable, str(scripts / "test_verification_gates.py"), pin],
                                 cwd=temporary, text=True, encoding="utf-8", errors="replace",
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            results[name] = "RED" if run.returncode else "SURVIVED"
    payload = {"mutations": results, "red": sum(value == "RED" for value in results.values()),
               "total": len(results)}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return int(payload["red"] != payload["total"])


if __name__ == "__main__":
    raise SystemExit(main())
