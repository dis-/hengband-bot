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
        "test_home_entry_capture.HomeEntryCaptureTest.test_gate1_substrate_replays_fixed_digger_arming_and_composed_key",
        "test_policy.TownAndFundraisingPolicyTest.test_recovered_home_entry_charges_an_evaporated_route_claim",
        "test_policy.TownAndFundraisingPolicyTest.test_recovered_home_entry_arms_standing_digger_withdrawal_after_restart",
        "test_policy.TownAndFundraisingPolicyTest.test_queued_digger_withdrawal_blocks_departure_without_home_route",
        "test_policy.TownAndFundraisingPolicyTest.test_failed_digger_withdraw_retries_only_after_fresh_home_observation",
        "test_policy.TownAndFundraisingPolicyTest.test_second_failed_digger_withdrawal_releases_to_visible_fallback",
        "test_policy.TownAndFundraisingPolicyTest.test_second_digger_queue_survives_surface_item_processing_until_post",
        "test_policy.TownAndFundraisingPolicyTest.test_pending_home_digger_is_additional_mining_walk_in_conjunct",
        "test_policy.TownAndFundraisingPolicyTest.test_scavenge_plan_routes_unaddressed_home_digger_latch_and_clears_queue",
        "test_navigation.StairRejectionInvalidationTest.test_interleaved_refusal_probe_releases_older_stair_watch",
        "test_navigation.StairRejectionInvalidationTest.test_quiet_same_turn_stair_watch_has_visible_bounded_probe",
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
        "rearm-only-in-mine-mode",
        True,
        "Restore the circular mode gate that starved Home digger arming.",
        (replacement(
            "policy.py",
            "            store is None\n"
            "            or store.store_type != STORE_HOME\n"
            "            or self._digging_tool_count(snapshot) >= 2\n"
            "        ):\n",
            "            store is None\n"
            "            or store.store_type != STORE_HOME\n"
            "            or self._digging_tool_count(snapshot) >= 2\n"
            "            or self._fundraising_mode == \"scavenge\"\n"
            "        ):\n",
        ),),
    ),
    Mutation(
        "drop-recovered-home-digger-binding",
        True,
        "Remove the recovered open-Home production binding.",
        (replacement(
            "policy.py",
            "            elif (\n"
            "                not self._calibration_active()\n"
            "                and self._home_atomic_deposit_pending is None\n"
            "                and self._equipment_transaction_session is None\n"
            "                and (\n"
            "                    standing_digger := self._queue_standing_home_digger(snapshot)\n"
            "                ) is not None\n"
            "            ):\n"
            "                # The open page is authoritative Home-stock evidence even when\n"
            "                # entry ownership was recovered after a restart or lagged post.\n"
            "                # Selection is bound here; the outside decision composes it.\n"
            "                key = standing_digger\n",
            "",
        ),),
    ),
    Mutation(
        "drop-evaporated-home-claim-charge",
        True,
        "Stop cooling an unfulfilled recovered Home route for the town visit.",
        (replacement(
            "policy.py",
            "                self._town_store_attempted[STORE_HOME] = snapshot.turn\n"
            "                self.last_reason = \"home:route-claim-unfulfilled\"\n",
            "                self.last_reason = \"home:route-claim-unfulfilled\"\n",
        ),),
    ),
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
    Mutation(
        "withdraw-gate-depends-on-home-route",
        True,
        "Restore the departure race by making the pending take conditional on Home routing.",
        (replacement(
            "policy.py",
            "            \"home_atomic_withdraw_clear\": (\n"
            "                self._home_atomic_withdraw_pending is None\n"
            "            ),\n",
            "            \"home_atomic_withdraw_clear\": (\n"
            "                not home_required or self._home_atomic_withdraw_pending is None\n"
            "            ),\n",
        ),),
    ),
    Mutation(
        "drop-queued-digger-departure-leaf",
        True,
        "Remove the state-based queued digger departure premise.",
        (replacement(
            "policy.py",
            "            \"digger_withdrawal_resolved\": (\n"
            "                not self._home_digger_withdraw_pending\n"
            "                or self._digger_fallback_bought_this_visit\n"
            "            ),\n",
            "",
        ),),
    ),
    Mutation(
        "keep-stair-watch-across-refusal-probe",
        True,
        "Retain the older stair watch across the identity-breaking probe.",
        (replacement(
            "policy.py",
            "                if self._pending_stair_command is not None:\n"
            "                    self._pending_stair_command = None\n"
            "                    self._owner_expectations.release(\"stair-command\")\n",
            "",
        ),),
    ),
    Mutation(
        "defer-first-failed-digger-address",
        True,
        "Consume the first failed take instead of requiring a fresh Home observation.",
        (replacement(
            "policy.py",
            "                retry_digger = (\n"
            "                    withdrawn.is_digging_tool\n"
            "                    and self._digger_home_withdraw_failures < 1\n"
            "                )\n",
            "                retry_digger = False\n",
        ),),
    ),
    Mutation(
        "drop-standing-digger-prepost-attribution",
        True,
        "Clear the queued attribution bit set by standing Home digger selection.",
        (replacement(
            "policy.py",
            "        self._home_withdrawal_queued = True\n"
            "        self.last_reason = \"home:queue-digging-tool-withdraw\"\n",
            "        self._home_withdrawal_queued = False\n"
            "        self.last_reason = \"home:queue-digging-tool-withdraw\"\n",
        ),),
    ),
    Mutation(
        "move-digger-entry-guard-after-mining-exemption",
        True,
        "Restore the mining walk-in early return ahead of the pending withdrawal guard.",
        (replacement(
            "policy.py",
            "        if (\n"
            "            self._home_digger_withdraw_pending\n"
            "            and not self._digger_fallback_bought_this_visit\n"
            "        ):\n"
            "            self._town_blocked_reason = \"home-digger-withdraw-pending\"\n"
            "            return False\n",
            "",
        ),),
    ),
    Mutation(
        "route-only-addressed-digger-withdrawal",
        True,
        "Require the transient Home item address before routing the durable latch.",
        (replacement(
            "policy.py",
            "        if snapshot.in_town and self._home_digger_withdraw_pending:\n",
            "        if (\n"
            "            snapshot.in_town\n"
            "            and self._home_digger_withdraw_pending\n"
            "            and self._home_pending_item is not None\n"
            "        ):\n",
        ),),
    ),
    Mutation(
        "remove-quiet-stair-observation-bound",
        True,
        "Keep quiet accepted stair observations in the empty-key wait forever.",
        (replacement(
            "policy.py",
            "            if self._stair_observation_waits >= STAIR_OBSERVATION_WAIT_LIMIT:\n",
            "            if False and self._stair_observation_waits >= STAIR_OBSERVATION_WAIT_LIMIT:\n",
        ),),
    ),
)


def repo_fingerprint() -> str:
    """Fingerprint checkout state without writing into it."""
    proc = subprocess.run(
        # The supervisor-owned JSONL recorder rotates untracked files while
        # this read-only battery runs.  Track checkout mutations through Git's
        # tracked index/worktree state; package bytes are hashed separately.
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=no"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    )
    digest = hashlib.sha256(proc.stdout)
    for path in sorted(PACKAGE.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
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
