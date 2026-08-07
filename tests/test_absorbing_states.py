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
        self.assertEqual(len(SEEDED_STATES), 14)
        self.assertEqual(len({state.name for state in SEEDED_STATES}), 14)
        self.assertTrue(all(state.build for state in SEEDED_STATES))

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
        self.assertTrue(all(not result.passed for result in results))
