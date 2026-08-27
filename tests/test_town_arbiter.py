import ast
import copy
from dataclasses import replace
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from hengbot.cli import _write_decision
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit, StoreVisitPhase
from store_visit_alternation_gate import measure as measure_visit_alternation


FIXTURES = Path(__file__).parent / "fixtures"
DECISION_CAPTURES = (
    "incident-equipment-abandon-loop-20260822.jsonl",
    "incident-alchemist-repetition-20260823.jsonl",
    "incident-launcher-repetition-20260823.jsonl",
    "incident-calibration-entry-await-20260823.jsonl",
    "incident-magic-abandon-cycle-20260823.jsonl",
)

# These namespaces are emitted only after the policy has left town.  The census
# otherwise defaults to inclusion: a new namespace is therefore treated as town
# reachable until it is deliberately classified here.  Mixed namespaces such as
# quest:, fundraise:, return:, and wilderness: stay included because at least one
# of their producers can run during town/departure handling.
DUNGEON_ONLY_REASON_PREFIXES = (
    "breeder-breakthrough:", "chest:", "combat:", "conquest:", "detected:",
    "emergency:", "flee:", "guardian:", "loot:", "melee:", "paralyzer-guard:",
    "quest-strategy:", "ranged:", "summoner:", "threat:", "unique:",
    "unseen:", "unseen-recall:", "victory:",
)
DUNGEON_ONLY_BARE_REASONS = {
    "approach-descent", "clear-descent", "descend", "flee", "probe", "search",
    "seek-downstairs", "seek-secret-wall",
}


def _literal_last_reasons():
    """Return complete static literals assigned to last_reason in production.

    Constants and conditional branches are complete emitted values.  Formatted
    strings and concatenations are intentionally excluded because their constant
    fragments are not independently emitted reasons.
    """
    def complete_literals(value):
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            yield value.value
        elif isinstance(value, ast.IfExp):
            yield from complete_literals(value.body)
            yield from complete_literals(value.orelse)

    root = Path(__file__).parents[1] / "src" / "hengbot"
    reasons = set()
    trees = []
    reason_parameters = {}
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        trees.append(tree)
        for function in (
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            parameters = [argument.arg for argument in function.args.args]
            for node in ast.walk(function):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if (
                    any(isinstance(target, ast.Attribute) and target.attr == "last_reason"
                        for target in targets)
                    and isinstance(node.value, ast.Name)
                    and node.value.id in parameters
                ):
                    position = parameters.index(node.value.id)
                    if parameters and parameters[0] in {"self", "cls"}:
                        position -= 1
                    reason_parameters[function.name] = (position, node.value.id)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(
                isinstance(target, ast.Attribute) and target.attr == "last_reason"
                for target in targets
            ):
                reasons.update(complete_literals(node.value))
    # Include literals passed to helper parameters which are assigned directly
    # to last_reason (for example the shared sale composer).  This is a bounded
    # static data-flow step, not a capture-derived list.
    for tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function_name = (
                node.func.attr if isinstance(node.func, ast.Attribute)
                else node.func.id if isinstance(node.func, ast.Name)
                else None
            )
            if function_name not in reason_parameters:
                continue
            position, parameter = reason_parameters[function_name]
            if position < len(node.args):
                reasons.update(complete_literals(node.args[position]))
            for keyword in node.keywords:
                if keyword.arg == parameter:
                    reasons.update(complete_literals(keyword.value))
    return reasons


def _town_reachable_literal_reasons():
    return {
        reason for reason in _literal_last_reasons()
        if reason not in DUNGEON_ONLY_BARE_REASONS
        and not reason.startswith(DUNGEON_ONLY_REASON_PREFIXES)
    }


class TownTurnArbiterAcceptanceTest(unittest.TestCase):
    @staticmethod
    def _postlevel_snapshot():
        fixture = FIXTURES / "incident-postlevel-repetition-turn-1006064.jsonl.gz"
        with gzip.open(fixture, "rt", encoding="utf-8-sig") as stream:
            return parse_snapshot(json.loads(next(stream)), {})

    def test_pin_vacuity_postlevel_public_choose_key_consumes_retirement_budget(self):
        snapshot = self._postlevel_snapshot()
        policy = HengbotPolicy()
        budget = policy._town_turn_arbiter.registry["home-scan"].budget
        decisions = []
        for _ in range(budget + 1):
            key = policy.choose_key(snapshot)
            decisions.append((key, policy.last_reason, copy.deepcopy(policy)))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            for key, reason, decided_policy in decisions:
                _write_decision(path, snapshot, key, reason, decided_policy)
            rows = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertTrue(rows)
        for row in rows:
            with self.subTest(sequence=row["decision_sequence"]):
                self.assertIsNotNone(row["arbiter"]["owner"])
                self.assertEqual(
                    {
                        "owner", "tenure", "progress",
                        "budget_remaining_estimate", "would_retire",
                        "retired", "retirement_set", "decision_attribution",
                        "_owner", "_tenure", "_no_progress_by_owner",
                        "_vector_by_owner", "_retired", "_recurrences",
                        "_visit_vector", "_last_pair",
                        "_visit_transfers",
                        "_last_transfer_sequence",
                        "_last_transfer_pair",
                        "_pending_transfer", "_transfer_exhausted",
                        "_transferred_visit",
                    },
                    set(row["arbiter"]),
                )
        self.assertFalse(rows[0]["arbiter"]["would_retire"])
        self.assertTrue(any(row["arbiter"]["would_retire"] for row in rows[:budget + 1]))

    def test_completed_attribution_obeys_composed_reason_structure(self):
        arbiter = HengbotPolicy()._town_turn_arbiter
        expected = {
            (
                "town-progress-invariant:defect:equipment-transaction:"
                "await-confirmation=>town-progress-invariant:approach"
            ): "detectors",
            "town:blocked:equipment-transaction:home-route-unavailable": "town-plan",
            (
                "town:entrance-step-off:home:"
                "atomic-withdraw-target-unobserved"
            ): "home-visit",
            "town:entrance-step-off:home:scan-step-off": "home-scan",
            (
                "town:entrance-step-off:town:entrance-step-off:"
                "home:scan-step-off"
            ): "home-scan",
            (
                "town-progress-invariant:defect:town:entrance-step-off:"
                "home:scan-step-off=>next"
            ): "detectors",
            (
                "town:entrance-step-off:town-progress-invariant:"
                "defect:X=>Y"
            ): "detectors",
        }
        for reason, owner in expected.items():
            with self.subTest(reason=reason):
                self.assertEqual(arbiter.decision_owner_for_reason(reason), owner)

    def test_empty_completed_reason_is_not_given_a_decision_owner(self):
        arbiter = HengbotPolicy()._town_turn_arbiter
        self.assertEqual(arbiter.decision_owner_for_reason(""), "misc")

    def test_pin_vacuity_registered_owner_consumes_static_reason_census(self):
        policy = HengbotPolicy()
        arbiter = policy._town_turn_arbiter
        registered = set(arbiter.registry)
        reasons = _town_reachable_literal_reasons()
        unregistered = sorted(
            reason for reason in reasons
            if arbiter.owner_for_reason(reason) not in registered
        )

        self.assertGreater(len(reasons), 300)
        self.assertEqual(unregistered, [])

    def test_capture_and_golden_reason_census_remains_registered(self):
        from test_golden_trajectory import GoldenOpeningTrajectoryTest

        policy = HengbotPolicy()
        arbiter = policy._town_turn_arbiter
        registered = set(arbiter.registry)
        self.assertNotIn("unregistered", registered)
        self.assertEqual(
            arbiter.owner_for_reason("invented:unattributed-family"),
            "unregistered",
        )
        reasons = []
        for name in DECISION_CAPTURES:
            with (FIXTURES / name).open(encoding="utf-8-sig") as stream:
                reasons.extend(
                    json.loads(line).get("reason", "")
                    for line in stream if line.strip()
                )

        golden_policy, world = GoldenOpeningTrajectoryTest().build()
        for decision in range(1, 21):
            world.deliver_events(golden_policy)
            key = golden_policy.choose_key(world.snapshot(decision))
            reasons.append(golden_policy.last_reason)
            golden_policy.confirm_key_posted(key)
            world.apply(key)

        self.assertTrue(reasons)
        owners = [arbiter.owner_for_reason(reason) for reason in reasons]
        self.assertTrue(all(owner in registered for owner in owners))
        self.assertNotIn(None, owners)
        self.assertNotIn("unregistered", owners)

    def test_owner_switch_does_not_reset_each_owners_stall_budget(self):
        policy = HengbotPolicy()
        arbiter = policy._town_turn_arbiter
        budgets = {
            owner: arbiter.registry[owner].budget
            for owner in ("shop-buy", "shop-sell")
        }
        retired = set()
        for turn in range(2 * max(budgets.values()) + 4):
            owner = "shop-buy" if turn % 2 == 0 else "shop-sell"
            reason = "shop:buy" if owner == "shop-buy" else "shop:sale"
            row = arbiter.observe(in_town=True, reason=reason, progress_vector=(1,))
            if row["would_retire"]:
                retired.add(owner)
        self.assertEqual(retired, set(budgets))

    def test_formerly_unregistered_remove_curse_retires_within_200_decisions(self):
        arbiter = HengbotPolicy()._town_turn_arbiter
        registration = arbiter.registry["curse-enchant"]
        rows = [
            arbiter.observe(
                in_town=True,
                reason="town:remove-curse",
                progress_vector=("frozen",),
            )
            for _ in range(200)
        ]

        self.assertEqual({row["owner"] for row in rows}, {"curse-enchant"})
        self.assertEqual(rows[0]["budget_remaining_estimate"], registration.budget)
        self.assertTrue(any(row["would_retire"] for row in rows))

    def test_interleaved_owner_does_not_refill_remaining_budget(self):
        policy = HengbotPolicy()
        arbiter = policy._town_turn_arbiter
        first = None
        for _ in range(7):
            first = arbiter.observe(
                in_town=True, reason="shop:buy", progress_vector=(1,)
            )
            arbiter.observe(in_town=True, reason="shop:sale", progress_vector=(1,))
        resumed = arbiter.observe(
            in_town=True, reason="shop:buy", progress_vector=(1,)
        )
        self.assertEqual(
            resumed["budget_remaining_estimate"],
            max(0, first["budget_remaining_estimate"] - 1),
        )

    def test_enforcement_retires_and_state_change_rearms_owner(self):
        arbiter = HengbotPolicy()._town_turn_arbiter
        budget = arbiter.registry["detectors"].budget
        row = None
        for _ in range(budget + 1):
            row = arbiter.observe(
                in_town=True,
                reason="town:cycle-break",
                progress_vector=("same",),
            )
        self.assertTrue(row["retired"])
        self.assertFalse(
            arbiter.may_select("town:cycle-break", ("same",))
        )
        self.assertTrue(
            arbiter.may_select("town:cycle-break", ("equipment-slot-delta",))
        )

    def test_state_rearm_clears_prior_vector_class_recurrences(self):
        arbiter = HengbotPolicy()._town_turn_arbiter
        limit = arbiter.registry["detectors"].budget
        for index in range(limit):
            vector = ("stale", index % 2)
            arbiter.observe(in_town=True, reason="shop:approach", progress_vector=vector)
        arbiter._retired["store-router"] = ("stale", 1)
        self.assertTrue(arbiter.may_select("shop:approach", ("advanced", 3)))
        self.assertFalse(any(owner == "store-router" for owner, _ in arbiter._recurrences))

    def test_locomotion_distance_changes_progress_without_position_in_durable_core(self):
        policy = HengbotPolicy()
        snapshot = self._postlevel_snapshot()
        goal = snapshot.player.position.__class__(
            snapshot.player.position.y, snapshot.player.position.x + 26
        )
        policy._store_visit = StoreVisit(
            owner="store-router", purpose="distance-pin", store_type=0, goal=goal
        )
        vectors = []
        for offset in range(27):
            moved = replace(
                snapshot,
                player=replace(
                    snapshot.player,
                    position=replace(snapshot.player.position, x=snapshot.player.position.x + offset),
                ),
            )
            vectors.append(policy._town_arbiter_progress_vector(moved, "shop:approach"))
        self.assertEqual(len(set(vectors)), 27)
        for vector in vectors:
            row = policy._town_turn_arbiter.observe(
                in_town=True, reason="shop:approach", progress_vector=vector
            )
            self.assertFalse(row["retired"])

    def test_hundred_tile_departure_leg_does_not_retire(self):
        policy = HengbotPolicy()
        snapshot = self._postlevel_snapshot()
        start = snapshot.player.position
        goal = replace(start, x=start.x + 100)
        policy._remembered_downstairs = {goal}
        for offset in range(101):
            moved = replace(
                snapshot,
                player=replace(snapshot.player, position=replace(start, x=start.x + offset)),
            )
            vector = policy._town_arbiter_progress_vector(moved, "descend:approach")
            row = policy._town_turn_arbiter.observe(
                in_town=True, reason="descend:approach", progress_vector=vector
            )
            self.assertFalse(row["retired"])

    def test_nonconverging_store_walk_retires_within_recurrence_budget(self):
        policy = HengbotPolicy()
        snapshot = self._postlevel_snapshot()
        start = snapshot.player.position
        goal = replace(start, x=start.x + 26)
        policy._store_visit = StoreVisit(
            owner="store-router", purpose="oscillation-pin", store_type=0, goal=goal
        )
        retired_at = None
        limit = policy._town_turn_arbiter.registry["detectors"].budget
        for index in range(limit * 2 + 1):
            moved = replace(
                snapshot,
                player=replace(snapshot.player, position=replace(start, x=start.x + index % 2)),
            )
            vector = policy._town_arbiter_progress_vector(moved, "shop:approach")
            row = policy._town_turn_arbiter.observe(
                in_town=True, reason="shop:approach", progress_vector=vector
            )
            if row["retired"]:
                retired_at = index + 1
                break
        self.assertIsNotNone(retired_at)
        self.assertLessEqual(retired_at, limit * 2 + 1)

    def test_foreign_visit_transfers_unless_operation_is_unreleased(self):
        policy = HengbotPolicy()
        old = StoreVisit(
            owner="shop-buy", purpose="old", store_type=0,
            operation_posted=False,
        )
        policy._store_visit = old
        policy._town_turn_arbiter._owner = "equipment-txn"
        acquired = policy._town_turn_arbiter.acquire_store_visit(
            store_type=7,
            owner="equipment-transaction",
            purpose="equipment-work",
            opened_sequence=3,
            close_visit=policy._close_store_visit,
        )
        self.assertEqual(old.phase, StoreVisitPhase.CLOSED)
        self.assertEqual(old.outcome, "arbiter-retired")
        self.assertIs(acquired, policy._store_visit)
        self.assertEqual(acquired.store_type, 7)

        protected = StoreVisit(
            owner="shop-buy", purpose="posted", store_type=0,
            operation_posted=True, operation_released=False,
            posted_sequence=4,
        )
        policy._store_visit = protected
        refused = policy._town_turn_arbiter.acquire_store_visit(
            store_type=7,
            owner="equipment-transaction",
            purpose="equipment-work",
            opened_sequence=5,
            close_visit=policy._close_store_visit,
        )
        self.assertIsNone(refused)
        self.assertIs(policy._store_visit, protected)

        protected.operation_released = True
        acquired = policy._town_turn_arbiter.acquire_store_visit(
            store_type=7,
            owner="equipment-transaction",
            purpose="equipment-work",
            opened_sequence=6,
            close_visit=policy._close_store_visit,
        )
        self.assertIsNone(acquired)
        self.assertIs(policy._store_visit, protected)

        protected.operation_effect_observed = True
        acquired = policy._town_turn_arbiter.acquire_store_visit(
            store_type=7,
            owner="equipment-transaction",
            purpose="equipment-work",
            opened_sequence=7,
            close_visit=policy._close_store_visit,
        )
        self.assertEqual(protected.outcome, "arbiter-retired")
        self.assertEqual(acquired.store_type, 7)

    def test_posted_entry_and_leave_contexts_cannot_transfer(self):
        for phase, posted_sequence, posted_turn in (
            (StoreVisitPhase.ENTERING, 4, None),
            (StoreVisitPhase.LEAVING, 4, None),
            (StoreVisitPhase.LEAVING, None, 100),
        ):
            with self.subTest(
                phase=phase,
                posted_sequence=posted_sequence,
                posted_turn=posted_turn,
            ):
                policy = HengbotPolicy()
                protected = StoreVisit(
                    owner="shop-buy",
                    purpose="posted-command",
                    store_type=0,
                    phase=phase,
                    posted_sequence=posted_sequence,
                    posted_turn=posted_turn,
                )
                policy._store_visit = protected
                acquired = policy._town_turn_arbiter.acquire_store_visit(
                    store_type=7,
                    owner="equipment-transaction",
                    purpose="equipment-work",
                    opened_sequence=5,
                    close_visit=policy._close_store_visit,
                )
                self.assertIsNone(acquired)
                self.assertIs(policy._store_visit, protected)
                self.assertEqual(protected.phase, phase)

    def test_unobserved_owner_does_not_restore_first_opened_authority(self):
        policy = HengbotPolicy()
        old = StoreVisit(owner="shop-buy", purpose="old", store_type=0)
        policy._store_visit = old
        self.assertIsNone(policy._town_turn_arbiter._owner)

        acquired = policy._town_turn_arbiter.acquire_store_visit(
            store_type=7,
            owner="equipment-transaction",
            purpose="equipment-work",
            opened_sequence=3,
            close_visit=policy._close_store_visit,
        )

        self.assertEqual(old.outcome, "arbiter-retired")
        self.assertEqual(acquired.store_type, 7)

    def test_store_visit_alternation_reaches_named_terminal_within_bound(self):
        reason, acquisitions, bound = measure_visit_alternation()
        self.assertEqual(reason, "town:blocked:owner-retired")
        self.assertLessEqual(acquisitions, bound)

    def test_terminal_is_never_scored_as_owner_progress(self):
        arbiter = HengbotPolicy()._town_turn_arbiter
        row = arbiter.observe(
            in_town=True,
            reason="town:blocked:departure-unsatisfiable",
            progress_vector=("new-terminal-vector",),
            terminal=True,
        )
        self.assertFalse(row["progress"])

    def test_probe_does_not_consume_tenure_or_budget(self):
        arbiter = HengbotPolicy()._town_turn_arbiter
        before = arbiter.observe(
            in_town=True, reason="shop:buy", progress_vector=("same",)
        )
        probe = arbiter.observe(
            in_town=True,
            reason="shop:buy",
            progress_vector=("same",),
            probe=True,
        )
        after = arbiter.observe(
            in_town=True, reason="shop:buy", progress_vector=("same",)
        )
        self.assertEqual(probe, before)
        self.assertEqual(after["tenure"], before["tenure"] + 1)
        self.assertEqual(
            after["budget_remaining_estimate"],
            before["budget_remaining_estimate"] - 1,
        )

    def test_town_vector_excludes_position_and_turn_but_tracks_home_and_slots(self):
        snapshot = self._postlevel_snapshot()
        policy = HengbotPolicy()
        first = policy._town_arbiter_progress_vector(snapshot)
        moved = replace(
            snapshot,
            turn=snapshot.turn + 99,
            player=replace(
                snapshot.player,
                position=snapshot.player.position.__class__(1, 1),
            ),
        )
        self.assertEqual(first, policy._town_arbiter_progress_vector(moved))
        policy._home_knowledge_current = not policy._home_knowledge_current
        self.assertNotEqual(first, policy._town_arbiter_progress_vector(moved))


if __name__ == "__main__":
    unittest.main()
