import unittest
import unittest.mock
from dataclasses import replace
from types import SimpleNamespace

import absorbing_state_catalog as cat
from absorbing_state_catalog import SEEDED_STATES, TownWorld
from absorbing_state_harness import AbsorbingState, drive
from hengbot.model import TVAL_POTION
import test_policy as fixture


class _ScriptedPolicy:
    def __init__(self, key="5", reason="wait"):
        self.key = key
        self.last_reason = reason

    def choose_key(self, _snapshot):
        return self.key


class _EveryThirdPurchasePolicy(_ScriptedPolicy):
    def __init__(self):
        super().__init__()
        self.decisions = 0

    def choose_key(self, _snapshot):
        self.decisions += 1
        self.last_reason = "shop:purchase" if self.decisions % 3 == 0 else "wait"
        return "pa" if self.decisions % 3 == 0 else "5"


class _FinalRecoveryPolicy(_ScriptedPolicy):
    def __init__(self):
        super().__init__()
        self.decisions = 0

    def choose_key(self, _snapshot):
        self.decisions += 1
        if self.decisions == 200:
            self.last_reason = "town:recover"
            return "R&\r"
        self.last_reason = "wait"
        return "5"


class _StubWorld:
    entries = 0
    exits = 0

    def __init__(self, *, progressing=False, unmodelled=False):
        self.progressing = progressing
        self.unmodelled = unmodelled
        self.value = 0

    def snapshot(self, _decision):
        return SimpleNamespace()

    def apply(self, _key):
        if self.progressing:
            self.value += 1

    def deliver_events(self, _policy):
        pass

    def durable_fingerprint(self):
        return self.value

    def visible_terminal(self, _reason):
        return None

    def terminal_ends_drive(self, _reason, _key):
        return False

    def unmodelled_release(self, _reason):
        return self.unmodelled


class _FinalTwitchWorld(_StubWorld):
    def __init__(self, twitch_at):
        super().__init__()
        self.calls = 0
        self.twitch_at = twitch_at

    def apply(self, _key):
        self.calls += 1
        if self.calls == self.twitch_at:
            self.value += 1


class AbsorbingStateHarnessTest(unittest.TestCase):
    def test_catalogue_is_cheap_and_grows_by_data(self):
        # Five seeds modelled the deleted in-store Home scan/selection paths.
        self.assertEqual(len(SEEDED_STATES), 26)
        self.assertEqual(len({state.name for state in SEEDED_STATES}), 26)
        self.assertEqual(len({state.build for state in SEEDED_STATES}), 26)
        self.assertTrue(all(state.build for state in SEEDED_STATES))

    def test_home_suppression_cycle_releases_by_atomic_withdrawal(self):
        state = next(
            state for state in SEEDED_STATES
            if state.name == "home-random-teleport-suppression-one-shot"
        )

        result = drive(state)

        self.assertTrue(result.passed, result.report())
        self.assertEqual(result.decisions, 2)
        self.assertEqual(result.entries, 1)
        self.assertEqual(result.exits, 1)
        self.assertEqual(result.keys["5 pa\x1b"], 1)
        self.assertEqual(result.reasons["home:atomic-withdraw"], 1)
        self.assertEqual(result.keys["{A.\r"], 1)
        self.assertEqual(
            result.reasons["equipment:suppress-random-teleport"], 1
        )

    def test_refused_home_suppression_take_defers_once_and_does_not_rearm(self):
        policy, world = cat._home_suppression_one_shot(
            purchases_succeed=False
        )
        reasons = []
        keys = []

        for decision in range(1, 9):
            world.deliver_events(policy)
            snapshot = world.snapshot(decision)
            key = policy.choose_key(snapshot)
            reasons.append(policy.last_reason)
            keys.append(key)
            policy.confirm_key_posted(key)
            world.apply(key)

        signature = policy._item_signature(world.stock[-1])
        preparation = policy._prepare_equipment_optimization(world.snapshot(9))
        self.assertGreater(len(reasons), 3)
        self.assertEqual(
            reasons.count("home:atomic-withdraw"),
            1,
            "without the deferred guard the public drive is unbounded: "
            "{('home:atomic-withdraw-target-unobserved', '\\x1b'): 30}",
        )
        self.assertEqual(keys.count("5 pa\x1b"), 1)
        self.assertLessEqual(
            reasons.count("home:atomic-withdraw-target-unobserved"),
            1,
            "the refused withdrawal must not spin on an unobserved target",
        )
        self.assertIn(signature, policy._deferred_home_items)
        self.assertIsNone(policy._home_pending_item)
        self.assertFalse(
            policy._random_teleport_suppression_actionable(
                world.snapshot(9), preparation
            )
        )

    def test_public_choose_key_refuses_all_four_live_store_cycles(self):
        names = {
            "visit-scan-address-burst",
            "visit-abandon-blocked-home",
            "visit-approach-entrance-stepoff",
            "visit-live-shop-entry-exit-531",
        }
        selected = [state for state in SEEDED_STATES if state.name in names]
        self.assertEqual({state.name for state in selected}, names)
        results = [drive(state) for state in selected]
        self.assertTrue(all(result.passed for result in results), [
            result.report() for result in results
        ])

    def test_frozen_owned_home_approach_reaches_existing_ceiling_publicly(self):
        """Review probe: 1248168 approached 200 times without accounting."""
        policy, world = cat._approach_refused_optimizer_transaction()
        base_apply = type(world).apply

        def frozen_apply(self, key):
            if key and all(ch in "12346789" for ch in key):
                return                       # the approach never arrives
            base_apply(self, key)

        type(world).apply = frozen_apply
        terminal_decision = None
        for i in range(200):
            world.apply(policy.choose_key(world.snapshot(i)))
            if policy._town_blocked_reason is not None:
                terminal_decision = i + 1
                break

        self.assertEqual(
            policy._town_blocked_reason,
            "equipment-work-home-route-exhausted",
            "1248168 exhausted 200 decisions without a named terminal; historical "
            "Counter({'equipment-transaction:approach-home': 200})",
        )
        self.assertIn(cat.STORE_HOME, policy._town_visit_ledger.blocked_stores)
        self.assertEqual(
            policy._town_visit_ledger.unsatisfied_passes[cat.STORE_HOME],
            policy._town_store_visit_limit(cat.STORE_HOME),
        )
        self.assertLessEqual(terminal_decision, 200)

    def test_progress_limb_distinguishes_progress_from_freeze(self):
        def state(progressing):
            return AbsorbingState(
                "stub", 3,
                lambda: (_ScriptedPolicy(), _StubWorld(progressing=progressing)),
            )
        self.assertTrue(drive(state(True)).passed)
        self.assertFalse(drive(state(False)).passed)

    def test_named_infinite_wait_is_not_a_drive_ending_terminal(self):
        class NamedWaitWorld(_StubWorld):
            def visible_terminal(self, reason):
                return reason if reason == "named-terminal" else None

        state = AbsorbingState(
            "named-wait", 10,
            lambda: (
                _ScriptedPolicy(reason="named-terminal"), NamedWaitWorld()
            ),
        )
        result = drive(state)
        self.assertFalse(result.passed)
        self.assertIn("repeated without ending drive", result.outcome)
        self.assertEqual(result.decisions, 4)

    def test_coordinate_drift_and_closed_patrol_are_not_progress(self):
        _, template = SEEDED_STATES[0].build()

        def movement_state(name, keys):
            class Policy(_ScriptedPolicy):
                def __init__(self):
                    super().__init__(reason="explore")
                    self.index = 0

                def choose_key(self, _snapshot):
                    key = keys[self.index % len(keys)]
                    self.index += 1
                    return key

            return AbsorbingState(name, 200, lambda: (Policy(), TownWorld(template.base)))

        self.assertFalse(drive(movement_state("drift", ("6",))).passed)
        self.assertFalse(drive(movement_state("patrol", ("6", "2", "4", "8"))).passed)

    def test_final_twitch_fails_independently_of_adjacent_bound(self):
        def state(bound):
            return AbsorbingState(
                f"twitch-{bound}", bound,
                lambda: (_ScriptedPolicy(), _FinalTwitchWorld(300)),
            )

        self.assertFalse(drive(state(300)).passed)
        self.assertFalse(drive(state(301)).passed)

    def test_unmodelled_release_is_not_an_absorbing_state(self):
        state = AbsorbingState(
            "unmodelled", 2,
            lambda: (_ScriptedPolicy(reason="await:external"),
                     _StubWorld(unmodelled=True)),
        )
        result = drive(state)
        self.assertFalse(result.passed)
        self.assertEqual(result.outcome, "unmodelled release: await:external")

    def test_ordinary_freeze_is_not_labelled_unmodelled(self):
        state = AbsorbingState(
            "freeze", 2,
            lambda: (_ScriptedPolicy(reason="explore"), _StubWorld()),
        )
        result = drive(state)
        self.assertFalse(result.passed)
        self.assertEqual(
            result.outcome,
            "decision bound exhausted without durable progress or named terminal",
        )

    def test_indefinite_recovery_rest_is_a_real_unmodelled_release(self):
        _, template = SEEDED_STATES[0].build()
        damaged = replace(
            template.base,
            player=replace(template.base.player, hp=template.base.player.max_hp - 1),
        )
        state = AbsorbingState(
            "recover", 2,
            lambda: (_ScriptedPolicy(key="R&\r", reason="town:recover"),
                     TownWorld(damaged)),
        )
        result = drive(state)
        self.assertFalse(result.passed)
        self.assertEqual(result.outcome, "unmodelled release: town:recover")

    def test_final_recovery_rest_label_is_fail_closed(self):
        _, template = SEEDED_STATES[0].build()
        state = AbsorbingState(
            "final-recover", 200,
            lambda: (_FinalRecoveryPolicy(), TownWorld(template.base)),
        )
        result = drive(state)
        self.assertFalse(result.passed)
        self.assertEqual(result.outcome, "unmodelled release: town:recover")

    def test_failed_repeat_posts_do_not_score_as_progress(self):
        _, template = SEEDED_STATES[0].build()
        stock = [fixture.store_item("a", TVAL_POTION, 9999, name="unbought")]
        state = AbsorbingState(
            "repeat-post", 300,
            lambda: (_EveryThirdPurchasePolicy(),
                     TownWorld(template.base, stock=stock, purchases_succeed=False)),
        )
        result = drive(state)
        self.assertFalse(result.passed)
        self.assertEqual(result.keys["pa"], 100)

    def test_turn_physics_uses_emitted_game_turns(self):
        _, template = SEEDED_STATES[0].build()
        world = TownWorld(template.base)
        start = world.turn
        world.apply("R300\r")
        self.assertEqual(world.turn, start + 3000)
        self.assertGreaterEqual(world.turn, start + 1000)

        world = TownWorld(template.base)
        start = world.turn
        world.apply("5")
        self.assertEqual(world.turn, start + 10)


class SeededAbsorbingStateTest(unittest.TestCase):
    def test_six_seeded_states_reach_progress_or_visible_terminal(self):
        self.assertNotIn("arrived", AbsorbingState.__dataclass_fields__)
        results = [drive(state) for state in SEEDED_STATES]
        failures = [result.report() for result in results if not result.passed]
        self.assertEqual(failures, [], "\n" + "\n".join(failures))

    def test_seed_verdicts_depend_on_visible_bot_terminals(self):
        with unittest.mock.patch.object(
            TownWorld, "visible_terminal", return_value=None
        ):
            results = [drive(state) for state in SEEDED_STATES]
        # Store entry/page state is real town-workflow progress, independent of
        # the visible-terminal catalogue. The narrowed entrance guard also
        # preserves the equipment owner's drive-ending terminal verbatim.
        passed = [result for result in results if result.passed]
        self.assertEqual(
            [result.state for result in passed],
            [
                "doubled-store-entry-cycle",
                "lagged-successful-store-entry",
                "transaction-abandoned-mid-strip",
                "movement-opens-store-before-surface-observation",
            ],
        )
        self.assertEqual(
            [result.outcome for result in passed],
            [
                "durable progress within decision bound",
                "durable progress within decision bound",
                "drive-ending terminal equipment transaction owns ten-item restoration",
                "durable progress within decision bound",
            ],
        )
