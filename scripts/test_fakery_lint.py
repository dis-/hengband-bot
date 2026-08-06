#!/usr/bin/env python3
"""Find behavioural tests which replace the mechanism they claim to exercise."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
ALLOW_MARKER = "TEST_FAKERY_LINT_ALLOW:"
_ALLOW_RE = re.compile(r"#\s*" + re.escape(ALLOW_MARKER) + r"\s*(\S.*)$")
_PUBLIC_METHODS = frozenset({"choose_key", "_decide"})
_PATH_METHODS = frozenset({"_decide", "_shop", "_observe"})
_DRIVE_WORDS = ("drive", "histogram", "decisions", "interleaved")

# This is deliberately an inventory, not a silent ignore list.  The command-line
# report prints every resulting finding and its reason.  Entries are keyed by
# test name so line movement cannot silently detach a declaration.
DECLARED_EXCEPTIONS = {
    # TEST_FAKERY_LINT_ALLOW: adjacent positive scavenge pin preserves the sanctioned exception; this case is the normal-mode control.
    "test_incomplete_optimizer_blocks_normal_direct_entrance": "adjacent positive scavenge pin preserves the exception; this is the normal-mode control",
    # TEST_FAKERY_LINT_ALLOW: CLI unit isolates serialization of an already-latched capture.
    "test_naked_capture_characteristics_are_recorded_only_when_latched": "CLI unit isolates serialization of an already-latched capture",
    # TEST_FAKERY_LINT_ALLOW: Home scanner unit isolates leave-barrier observation from routing.
    "test_real_capture_leave_barrier_clears_before_request_is_posted": "Home scanner unit isolates leave-barrier observation from routing",
    # TEST_FAKERY_LINT_ALLOW: Home scanner unit isolates interleaved-page observation from routing.
    "test_real_capture_interleaved_surface_page_does_not_request_scan": "Home scanner unit isolates interleaved-page observation from routing",
    # TEST_FAKERY_LINT_ALLOW: Home scanner unit exercises the wrapper's unconfirmed-context guard.
    "test_visit_without_confirmed_outside_context_never_waits_for_scan": "Home scanner unit exercises the wrapper's unconfirmed-context guard",
    # TEST_FAKERY_LINT_ALLOW: Look-probe unit starts from the protocol's posted-request state.
    "test_requested_look_is_consumed_and_probe_is_lazy": "Look-probe unit starts from the protocol's posted-request state",
    # TEST_FAKERY_LINT_ALLOW: Replay deliberately supplies incident WAITs while applying returned movement.
    "test_incident_wait_cycle_replay_leaves_six_cell_set": "replay deliberately supplies incident WAITs while applying returned movement",
    # TEST_FAKERY_LINT_ALLOW: Store-leave tests isolate the choose_key stale-context wrapper.
    "test_captured_home_leave_stale_snapshot_cannot_drop_deposit": "isolates the choose_key stale-context wrapper",
    # TEST_FAKERY_LINT_ALLOW: Store-leave tests isolate every stale item-command family.
    "test_stale_store_after_leave_blocks_every_item_command_family": "isolates every stale item-command family",
    # TEST_FAKERY_LINT_ALLOW: Purchase-watch test isolates observation after a known posted command.
    "test_purchase_wait_clears_on_carried_item_progress": "isolates observation after a known posted purchase",
    # TEST_FAKERY_LINT_ALLOW: Failed-withdraw test isolates public cleanup after a known failed post.
    "test_failed_digger_withdrawal_is_not_retried_after_home_ejects_to_town": "isolates public cleanup after a known failed withdrawal post",
    # TEST_FAKERY_LINT_ALLOW: Home wrapper tests supply the command whose interception is their subject.
    "test_home_receives_equipment_before_other_town_work": "supplies the deposit command whose Home interception is under test",
    # TEST_FAKERY_LINT_ALLOW: Home wrapper test supplies a repeated deposit to test scan preservation.
    "test_home_deposit_does_not_restart_batch_scan_at_same_turn": "supplies a repeated deposit to test scan preservation",
    # TEST_FAKERY_LINT_ALLOW: Catalog invalidation unit supplies a withdrawal command, not its selection.
    "test_home_equipment_withdrawal_preserves_completed_scan": "supplies a withdrawal command to test catalog invalidation",
    # TEST_FAKERY_LINT_ALLOW: Catalog invalidation unit supplies unsafe withdrawal commands, not selection.
    "test_home_unsafe_or_unresolved_withdrawal_invalidates_scan": "supplies unsafe withdrawal commands to test catalog invalidation",
    # TEST_FAKERY_LINT_ALLOW: Arbitration unit controls unrelated town claims around the branch under test.
    "test_cross_town_identify_capture_starts_travel_instead_of_visible_stop": "controls unrelated town claims around cross-town arbitration",
    # TEST_FAKERY_LINT_ALLOW: Emergency wrapper unit seeds WAIT then tests its independent attack override.
    "test_choose_key_death_shape_attacks_instead_of_ping_ponging": "seeds WAIT and controls geometry collaborators to test the attack override",
    # TEST_FAKERY_LINT_ALLOW: Emergency wrapper unit supplies WAIT to test rejected-step handling.
    "test_choose_key_no_wait_does_not_reemit_emergency_refused_step": "supplies emergency WAIT to test rejected-step handling",
    # TEST_FAKERY_LINT_ALLOW: Reserve protocol unit begins after a previously posted buy.
    "test_star_remove_curse_reserve_buy_waits_for_inventory_delta": "begins after a previously posted reserve buy",
    # TEST_FAKERY_LINT_ALLOW: Reserve protocol unit begins after a previously posted deposit.
    "test_star_remove_curse_reserve_deposit_waits_for_inventory_delta": "begins after a previously posted reserve deposit",
    # TEST_FAKERY_LINT_ALLOW: Escape wrapper unit supplies disengage WAIT to test under-fire override.
    "test_ranged_disengage_wait_under_fire_uses_escape_scroll": "supplies disengage WAIT to test the under-fire escape override",
    # TEST_FAKERY_LINT_ALLOW: Tactical unit controls alternative exits to isolate adjacent-target choice.
    "test_cornered_disengage_melees_weakest_adjacent_instead_of_waiting": "controls alternative exits to isolate adjacent-target choice",
    # TEST_FAKERY_LINT_ALLOW: Recall arbitration unit controls independent readiness authorities.
    "test_sanctioned_repetition_recall_ignores_readiness_cancel": "controls independent readiness authorities around recall arbitration",
    # TEST_FAKERY_LINT_ALLOW: Recall arbitration unit controls route providers to isolate stalled entrance ownership.
    "test_blocked_repetition_stalled_entrance_leg_yields_to_recall": "controls route providers to isolate stalled entrance ownership",
    # TEST_FAKERY_LINT_ALLOW: None-decision test is explicitly the choose_key defensive wrapper contract.
    "test_choose_key_defensively_exits_store_on_none_decision": "explicitly tests the choose_key defensive wrapper contract",
    # TEST_FAKERY_LINT_ALLOW: Purchase-watch unit supplies decisions to test recording, not shopping selection.
    "test_choose_key_purchase_watch_records_only_confirmed_buy": "supplies decisions to test purchase-watch recording",
    # TEST_FAKERY_LINT_ALLOW: Leave-latch unit reconstructs emitter-observable inflight protocol state.
    "test_recorded_free_action_withdrawals_survive_live_leave_latch": "reconstructs emitter-observable leave-inflight protocol state",
    # TEST_FAKERY_LINT_ALLOW: Context guard unit reconstructs an emitter-observable stale store page.
    "test_unconfirmed_store_context_never_plans_item_command": "reconstructs an emitter-observable stale store page",
    # TEST_FAKERY_LINT_ALLOW: Depth fallback units control unrelated procurement and routing authorities.
    "test_no_valid_21f_loadout_equips_owned_20f_kit_and_keeps_angband": "controls unrelated procurement and routing authorities",
    # TEST_FAKERY_LINT_ALLOW: Depth fallback units control unrelated procurement and routing authorities.
    "test_no_valid_20f_loadout_equips_owned_19f_kit_and_keeps_angband": "controls unrelated procurement and routing authorities",
    # TEST_FAKERY_LINT_ALLOW: Quest fallback unit controls unrelated procurement and routing authorities.
    "test_pending_quest_procurement_does_not_create_dungeon_fallback": "controls unrelated procurement and routing authorities",
    # TEST_FAKERY_LINT_ALLOW: Atomic protocol test supplies the outside decision after a real posted withdrawal.
    "test_failed_atomic_withdrawal_is_reported_and_never_reposted": "supplies the outside decision after a real posted withdrawal",
    # TEST_FAKERY_LINT_ALLOW: Deposit wrapper tests supply commands and exercise atomic composition around them.
    "test_real_capture_escape_then_posts_stay_deposit_exit_in_one_decision": "supplies a deposit command to exercise atomic wrapping",
    # TEST_FAKERY_LINT_ALLOW: Deposit wrapper tests supply commands and exercise one-operation ownership.
    "test_pending_home_operation_never_waits_inside": "supplies a deposit command to exercise one-operation ownership",
    # TEST_FAKERY_LINT_ALLOW: Deposit wrapper tests supply commands and exercise already-inside refusal.
    "test_already_inside_without_posted_operation_leaves_not_deposits": "supplies a deposit command to exercise already-inside refusal",
    # TEST_FAKERY_LINT_ALLOW: Deposit wrapper tests supply commands and check side-effect slot safety.
    "test_real_pack_teleport_and_recall_slots_cannot_be_side_effect_deposits": "supplies a deposit command to check side-effect slot safety",
    # TEST_FAKERY_LINT_ALLOW: Atomic protocol test supplies the unrelated outside decision after a real post.
    "test_atomic_post_is_followed_directly_by_outside_observation": "supplies an unrelated outside decision after a real atomic post",
    # TEST_FAKERY_LINT_ALLOW: Atomic protocol test supplies an interleaved decision after a real post.
    "test_atomic_latch_survives_interleaved_outside_snapshot_until_confirmed": "supplies an interleaved decision after a real atomic post",
    # TEST_FAKERY_LINT_ALLOW: Atomic protocol test reconstructs the emitter's leave-inflight observation.
    "test_atomic_latch_clears_when_home_leave_is_observed": "reconstructs the emitter's leave-inflight observation",
    # TEST_FAKERY_LINT_ALLOW: Transaction routing unit controls error-reporting collaborators around target validation.
    "test_transaction_home_route_rejects_non_home_approach_target": "controls error-reporting collaborators around target validation",
    # TEST_FAKERY_LINT_ALLOW: Multi-entry protocol test supplies each known deposit after real entry composition.
    "test_three_deposits_use_three_entries_and_finish": "supplies each known deposit after real entry composition",
    # TEST_FAKERY_LINT_ALLOW: Entrance wrapper test supplies terminal reasons to verify they remain visible.
    "test_entrance_guard_preserves_visible_terminal_and_blocked_fuse": "supplies terminal reasons to test the entrance wrapper's preservation contract",
    # TEST_FAKERY_LINT_ALLOW: Entrance memory test supplies movement/WAIT while testing remembered terrain only.
    "test_remembered_store_position_covers_missing_current_grid": "supplies movement and WAIT while testing remembered entrance terrain",
    # TEST_FAKERY_LINT_ALLOW: Entrance wrapper test supplies WAIT while testing non-town building scope.
    "test_non_town_building_wait_is_also_guarded": "supplies WAIT while testing non-town building scope",
    # TEST_FAKERY_LINT_ALLOW: Page-wait state-machine units intentionally replace observation and downstream decision.
    "test_policy_bounds_home_page_wait_on_consecutive_town_snapshots": "isolates the page-wait state machine from observation and routing",
    # TEST_FAKERY_LINT_ALLOW: Page-wait state-machine units intentionally replace observation and downstream decision.
    "test_policy_clears_home_page_wait_on_interleaved_alchemist_snapshot": "isolates interleaved page-wait clearing from observation and routing",
    # TEST_FAKERY_LINT_ALLOW: Page-wait state-machine units intentionally replace observation and downstream decision.
    "test_policy_home_snapshot_still_clears_page_advance_pending": "isolates page-advance clearing from observation and routing",
}


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    rule: str
    message: str
    test: str
    allowed_reason: str | None = None

    def render(self) -> str:
        suffix = f" [DECLARED: {self.allowed_reason}]" if self.allowed_reason else ""
        return f"{self.path.as_posix()}:{self.line}: {self.rule}: {self.message}{suffix}"


def _call_name(node: ast.AST) -> str | None:
    func = node.func if isinstance(node, ast.Call) else node
    return func.attr if isinstance(func, ast.Attribute) else (
        func.id if isinstance(func, ast.Name) else None
    )


def _string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _patch_target(call: ast.Call) -> tuple[str | None, str | None]:
    """Return receiver/name for patch.object(receiver, name, ...)."""
    if not (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "object"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "patch"
        and len(call.args) >= 2
    ):
        return None, None
    receiver = call.args[0].id if isinstance(call.args[0], ast.Name) else None
    return receiver, _string(call.args[1])


def _assignment_targets(node: ast.AST) -> Iterable[ast.Attribute]:
    targets: list[ast.AST] = []
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        targets = list(node.targets) if isinstance(node, ast.Assign) else [node.target]
    for target in targets:
        if isinstance(target, ast.Attribute):
            yield target


def _assert_calls(function: ast.AST) -> list[ast.Call]:
    return [
        node for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and (_call_name(node) or "").startswith("assert")
    ]


def _attribute_names(nodes: Iterable[ast.AST]) -> set[str]:
    return {
        node.attr for root in nodes for node in ast.walk(root)
        if isinstance(node, ast.Attribute)
    }


def _allowances(lines: list[str], start: int, end: int) -> list[tuple[int, str]]:
    found = []
    for lineno in range(start, min(end, len(lines)) + 1):
        match = _ALLOW_RE.search(lines[lineno - 1])
        if match:
            found.append((lineno, match.group(1).strip()))
    return found


def analyze_source(source: str, path: Path = Path("fixture.py")) -> list[Finding]:
    tree = ast.parse(source, filename=str(path))
    lines = source.splitlines()
    findings: list[Finding] = []
    for function in (
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test")
    ):
        asserts = _assert_calls(function)
        if not asserts:
            continue
        assert_attrs = _attribute_names(asserts)
        calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
        public_calls = [call for call in calls if _call_name(call) in _PUBLIC_METHODS]
        patches: list[tuple[int, str | None, str]] = []
        assignments: list[tuple[int, str | None, str]] = []
        for node in ast.walk(function):
            if isinstance(node, ast.Call):
                receiver, name = _patch_target(node)
                if name and name.startswith("_"):
                    patches.append((node.lineno, receiver, name))
            for target in _assignment_targets(node):
                if target.attr.startswith("_"):
                    receiver = target.value.id if isinstance(target.value, ast.Name) else None
                    assignments.append((target.lineno, receiver, target.attr))

        if public_calls:
            for call in calls:
                name = _call_name(call) or ""
                if (
                    name.startswith("set_completed_equipment_optimization")
                    and "mining_walk_in_is_the_only" in function.name
                ):
                    findings.append(Finding(
                        path, call.lineno, "subject-precompleted",
                        f"{function.name} pre-completes equipment optimization before a public assertion",
                        function.name,
                    ))
            for line, _receiver, name in patches + assignments:
                if name in _PATH_METHODS:
                    findings.append(Finding(
                        path, line, "public-path-replaced",
                        f"{function.name} calls a public decision path after replacing {name}",
                        function.name,
                    ))

        # Directly manufacturing private state is suspicious only when an assertion
        # reads that exact state (or a public decision result is asserted). Ordinary
        # Snapshot construction therefore remains outside this rule.
        for line, _receiver, name in assignments:
            state_like = any(token in name for token in (
                "_pages", "_catalog", "_input_key", "_inflight"
            ))
            if state_like and (name in assert_attrs or public_calls):
                findings.append(Finding(
                    path, line, "private-state-injected",
                    f"{function.name} assigns derived state {name} before asserting its effect",
                    function.name,
                ))

        for node in ast.walk(function):
            for target in _assignment_targets(node):
                if target.attr == "loadout" and isinstance(target.value, ast.Attribute):
                    findings.append(Finding(
                        path, target.lineno, "pipeline-result-injected",
                        f"{function.name} hand-assigns a best/loadout pipeline result",
                        function.name,
                    ))

        lower_name = function.name.lower()
        if "incomplete_optimizer_blocks" in lower_name:
            for line, _receiver, name in assignments:
                if name == "_fundraising_mode":
                    findings.append(Finding(
                        path, line, "invariant-input-overwritten",
                        f"{function.name} directly selects the fundraising mode named by its invariant",
                        function.name,
                    ))

        collaborator_patches = {
            (receiver, name) for _line, receiver, name in patches
            if name not in _PATH_METHODS
        }
        by_receiver: dict[str | None, set[str]] = {}
        for receiver, name in collaborator_patches:
            by_receiver.setdefault(receiver, set()).add(name)
        for receiver, names in by_receiver.items():
            if len(names) >= 4:
                line = min(line for line, rec, name in patches if rec == receiver and name in names)
                findings.append(Finding(
                    path, line, "collaborator-wall",
                    f"{function.name} replaces {len(names)} collaborators of one object: "
                    + ", ".join(sorted(names)), function.name,
                ))

        if any(word in function.name.lower() for word in _DRIVE_WORDS):
            choose_results = {
                target.id
                for node in ast.walk(function)
                if isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and _call_name(node.value) == "choose_key"
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            for node in ast.walk(function):
                if not isinstance(node, ast.Compare):
                    continue
                compared_names = {
                    part.id for part in (node.left, *node.comparators)
                    if isinstance(part, ast.Name)
                }
                literals = [
                    value for part in (node.left, *node.comparators)
                    if (value := _string(part)) is not None
                ]
                if choose_results & compared_names and literals:
                    findings.append(Finding(
                        path, node.lineno, "literal-success-predicate",
                        f"{function.name} treats literal key {literals[0]!r} as drive success",
                        function.name,
                    ))
            for loop in (node for node in ast.walk(function) if isinstance(node, ast.For)):
                long_drive = (
                    isinstance(loop.iter, ast.Call)
                    and _call_name(loop.iter) == "range"
                    and loop.iter.args
                    and isinstance(loop.iter.args[-1], ast.Constant)
                    and isinstance(loop.iter.args[-1].value, int)
                    and loop.iter.args[-1].value >= 100
                )
                if not long_drive:
                    continue
                loop_choose = [
                    call for call in ast.walk(loop)
                    if isinstance(call, ast.Call) and _call_name(call) == "choose_key"
                    and call.args and isinstance(call.args[0], ast.Name)
                ]
                for call in loop_choose:
                    snapshot_name = call.args[0].id
                    refreshed = any(
                        isinstance(target, ast.Name) and target.id == snapshot_name
                        for child in ast.walk(loop)
                        for target in (
                            list(child.targets) if isinstance(child, ast.Assign)
                            else [child.target] if isinstance(child, (ast.AnnAssign, ast.AugAssign))
                            else []
                        )
                    )
                    if not refreshed:
                        findings.append(Finding(
                            path, call.lineno, "frozen-drive-state",
                            f"{function.name} repeatedly drives choose_key with unchanged {snapshot_name}",
                            function.name,
                        ))

        allowances = _allowances(lines, function.lineno, function.end_lineno or function.lineno)
        if allowances:
            reason = "; ".join(reason for _line, reason in allowances)
            findings = [
                Finding(f.path, f.line, f.rule, f.message, f.test, reason)
                if f.test == function.name and f.allowed_reason is None else f
                for f in findings
            ]
        declared = DECLARED_EXCEPTIONS.get(function.name)
        if declared:
            findings = [
                Finding(f.path, f.line, f.rule, f.message, f.test, declared)
                if f.test == function.name and f.allowed_reason is None else f
                for f in findings
            ]
    return findings


def scan_tests(tests: Path = TESTS) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(tests.rglob("test*.py")):
        relative = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        findings.extend(analyze_source(path.read_text(encoding="utf-8"), relative))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=TESTS)
    args = parser.parse_args()
    findings = scan_tests(args.path) if args.path.is_dir() else analyze_source(
        args.path.read_text(encoding="utf-8"), args.path
    )
    for finding in findings:
        print(finding.render())
    undeclared = [finding for finding in findings if not finding.allowed_reason]
    declared = [finding for finding in findings if finding.allowed_reason]
    declared_tests = {finding.test for finding in declared}
    print(
        f"test-fakery-lint: {len(undeclared)} violation(s), "
        f"{len(declared)} declared finding(s) in {len(declared_tests)} test(s)"
    )
    return bool(undeclared)


if __name__ == "__main__":
    raise SystemExit(main())
