#!/usr/bin/env python3
"""Run the standing Hengbot mutation experiments without touching the checkout.

The default selection is the five public ``choose_key`` pins plus the two
optimizer input-key unit pins named in ``DEFAULT_TESTS``.  Pass ``--full-suite``
to run normal unittest discovery for every mutation.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "hengbot"

PUBLIC_TESTS = frozenset(
    {
        "test_policy.HomeOneOperationPerEntryTest.test_public_page_three_withdrawal_posts_one_complete_sender_key",
        "test_policy.HomeOneOperationPerEntryTest.test_derived_withdrawal_uses_uppercase_and_live_page_three_arithmetic",
        "test_policy.HomeOneOperationPerEntryTest.test_descending_withdrawals_share_one_home_knowledge_read",
        "test_policy.HomeOneOperationPerEntryTest.test_derived_withdrawal_waits_when_page_size_was_never_observed",
        "test_policy.ConfirmedLoadoutPublicPathPinTest.test_home_upgrade_invalidates_confirmation_through_choose_key",
        "test_policy.ConfirmedLoadoutPublicPathPinTest.test_fuel_tick_reuses_confirmation_through_choose_key",
    }
)
DEFAULT_TESTS = (
    *sorted(PUBLIC_TESTS),
    "test_warrior_optimization.WarriorOptimizationTest.test_optimizer_input_key_covers_search_and_planner_inputs",
    "test_warrior_optimization.WarriorOptimizationTest.test_optimizer_input_key_ignores_transport_noise_and_catalog_order",
)


@dataclasses.dataclass(frozen=True)
class Replacement:
    relative_path: str
    old: str
    new: str


@dataclasses.dataclass(frozen=True)
class Mutation:
    name: str
    expected_to_bite: bool
    explanation: str
    replacements: tuple[Replacement, ...]


def replacement(path: str, old: str, new: str) -> Replacement:
    return Replacement(path, old, new)


MUTATIONS = (
    Mutation(
        "carried-half-only",
        True,
        "Build the optimizer input key from carried items only.",
        (replacement(
            "warrior_optimization.py",
            "(optimizer_item_projection(item) for item in items),",
            "(optimizer_item_projection(item) for item in items if item.origin != \"home\"),",
        ),),
    ),
    Mutation(
        "fuel-in-projection",
        True,
        "Include volatile fuel in the optimizer input projection.",
        (replacement(
            "equipment_optimizer.py",
            "        _catalog_signature(item),\n        item.weight,",
            "        _catalog_signature(item),\n        getattr(item, \"fuel\", None),\n        item.weight,",
        ),),
    ),
    Mutation(
        "guess-home-page-size",
        True,
        "Guess 52 columns when no Home page size was observed.",
        (replacement(
            "policy.py",
            "        if not self._home_page_size:\n            self.last_reason = \"home:await-page-size\"\n            return None\n",
            "        if not self._home_page_size:\n            self._home_page_size = 52  # mutant guesses geometry\n",
        ),),
    ),
    Mutation(
        "lowercase-past-z",
        True,
        "Continue lowercase address arithmetic past z.",
        (replacement(
            "policy.py",
            "            if page_pos < 26\n",
            "            if page_pos < 52\n",
        ),),
    ),
    Mutation(
        "invalidate-descending-frontier",
        True,
        "Invalidate the whole knowledge read after the first withdrawal.",
        (replacement(
            "policy.py",
            "        self._home_knowledge_valid_before = index\n",
            "        self._home_knowledge_current = False  # mutant loses descending batch\n",
        ),),
    ),
)


def repo_fingerprint() -> str:
    """Fingerprint checkout state without writing into it."""
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    )
    digest = hashlib.sha256(proc.stdout)
    for path in sorted(PACKAGE.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def apply_mutation(package: Path, mutation: Mutation) -> tuple[bool, str | None]:
    for edit in mutation.replacements:
        target = package / edit.relative_path
        text = target.read_text(encoding="utf-8")
        count = text.count(edit.old)
        if count != 1:
            return False, f"anchor in {edit.relative_path} matched {count} times (expected 1)"
        target.write_text(text.replace(edit.old, edit.new, 1), encoding="utf-8")
    return True, None


FAILURE_RE = re.compile(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)$", re.MULTILINE)
RAN_RE = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)
ASSERTION_RE = re.compile(r"^(?:AssertionError|[A-Za-z_.]+Error): (.+)$", re.MULTILINE)


def run_tests(package_parent: Path, full_suite: bool) -> dict:
    if full_suite:
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
    else:
        command = [
            sys.executable, "-m", "unittest", "discover", "-s", "tests",
            *sum((["-k", name.rsplit(".", 1)[-1]] for name in DEFAULT_TESTS), []),
        ]
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    old_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(package_parent), *(old_pythonpath.split(os.pathsep) if old_pythonpath else [])]
    )
    proc = subprocess.run(
        command, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
    )
    output = proc.stdout
    failures = []
    for match in FAILURE_RE.finditer(output):
        _method, container = match.groups()
        failures.append(container)
    ran = RAN_RE.search(output)
    assertion = ASSERTION_RE.search(output)
    return {
        "command": command,
        "tests_run": int(ran.group(1)) if ran else None,
        "failures": failures,
        "returncode": proc.returncode,
        "first_assertion": assertion.group(1) if assertion else None,
        "output": output,
    }


def execute(mutation: Mutation, full_suite: bool) -> dict:
    result = {
        "name": mutation.name,
        "expected_to_bite": mutation.expected_to_bite,
        "explanation": mutation.explanation,
        "applied": False,
        "tests_run": 0,
        "failures": [],
        "public_path_failure": False,
        "first_assertion": None,
        "expectation_met": False,
    }
    with tempfile.TemporaryDirectory(prefix="hengbot-mutation-") as directory:
        package_parent = Path(directory)
        copied_package = package_parent / "hengbot"
        shutil.copytree(PACKAGE, copied_package)
        applied, error = apply_mutation(copied_package, mutation)
        result["applied"] = applied
        if not applied:
            result["apply_error"] = error
            return result
        test_result = run_tests(package_parent, full_suite)
        result.update({key: test_result[key] for key in (
            "tests_run", "failures", "returncode", "first_assertion"
        )})
        result["public_path_failure"] = any(
            failure in PUBLIC_TESTS for failure in test_result["failures"]
        )
        bit = result["public_path_failure"]
        result["expectation_met"] = bit == mutation.expected_to_bite
    return result


def compact(value: object, width: int) -> str:
    text = "-" if value in (None, "", []) else str(value)
    return text if len(text) <= width else text[: width - 1] + "…"


def print_table(results: list[dict]) -> None:
    headers = ("mutation", "expect", "applied", "tests", "fail", "public", "result", "first assertion")
    rows = []
    for item in results:
        rows.append((
            item["name"], "bite" if item["expected_to_bite"] else "no-bite",
            "yes" if item["applied"] else "no", item["tests_run"],
            len(item["failures"]), "yes" if item["public_path_failure"] else "no",
            "PASS" if item["expectation_met"] else "FAIL",
            item.get("apply_error") or item["first_assertion"],
        ))
    widths = [max(len(headers[i]), *(len(compact(row[i], 72)) for row in rows)) for i in range(len(headers))]
    print("  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(compact(row[i], 72).ljust(widths[i]) for i in range(len(headers))))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=[item.name for item in MUTATIONS])
    parser.add_argument("--full-suite", action="store_true")
    args = parser.parse_args()
    selected = [item for item in MUTATIONS if args.only in (None, item.name)]
    before = repo_fingerprint()
    results = [execute(item, args.full_suite) for item in selected]
    after = repo_fingerprint()
    tree_untouched = before == after
    if not tree_untouched:
        for item in results:
            item["expectation_met"] = False
            item["repo_tree_error"] = "repository fingerprint changed during the run"
    print_table(results)
    summary = {
        "runtime": sys.executable,
        "selection": "full-suite" if args.full_suite else list(DEFAULT_TESTS),
        "repo_tree_untouched": tree_untouched,
        "results": results,
    }
    print("\nJSON_SUMMARY=" + json.dumps(summary, sort_keys=True))
    return 0 if tree_untouched and all(item["expectation_met"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
