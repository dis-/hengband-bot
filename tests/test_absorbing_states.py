import unittest
from types import SimpleNamespace

from absorbing_state_catalog import SEEDED_STATES
from absorbing_state_harness import AbsorbingState, drive


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


class _StubWorld:
    entries = 0
    exits = 0

    def __init__(self, *, progressing=False, modelled=True):
        self.progressing = progressing
        self.modelled = modelled
        self.value = 0

    def snapshot(self, _decision):
        return SimpleNamespace()

    def apply(self, _key):
        if self.progressing:
            self.value += 1

    def durable_fingerprint(self):
        return self.value

    def visible_terminal(self, _reason):
        return None

    def release_modelled(self, _reason):
        return self.modelled


class AbsorbingStateHarnessTest(unittest.TestCase):
    def test_catalogue_is_cheap_and_grows_by_data(self):
        self.assertEqual(len(SEEDED_STATES), 6)
        self.assertEqual(len({state.name for state in SEEDED_STATES}), 6)
        self.assertTrue(all(state.build and state.arrived for state in SEEDED_STATES))

    def test_progress_limb_distinguishes_progress_from_freeze(self):
        def state(progressing):
            return AbsorbingState(
                "stub", 3,
                lambda: (_ScriptedPolicy(), _StubWorld(progressing=progressing)),
                lambda _p, _w: None,
            )
        self.assertTrue(drive(state(True)).passed)
        self.assertFalse(drive(state(False)).passed)

    def test_unmodelled_release_is_not_an_absorbing_state(self):
        state = AbsorbingState(
            "unmodelled", 2,
            lambda: (_ScriptedPolicy(reason="await:external"),
                     _StubWorld(modelled=False)),
            lambda _p, _w: None,
        )
        result = drive(state)
        self.assertFalse(result.passed)
        self.assertEqual(result.outcome, "unmodelled release: await:external")

    def test_failed_repeat_posts_do_not_score_as_progress(self):
        state = AbsorbingState(
            "repeat-post", 300,
            lambda: (_EveryThirdPurchasePolicy(),
                     _StubWorld()),
            lambda _p, _w: None,
        )
        result = drive(state)
        self.assertFalse(result.passed)
        self.assertEqual(result.keys["pa"], 100)


class SeededAbsorbingStateTest(unittest.TestCase):
    def test_six_seeded_states_reach_progress_or_visible_terminal(self):
        failures = []
        for state in SEEDED_STATES:
            with self.subTest(state=state.name):
                result = drive(state)
                if not result.passed:
                    failures.append(result.report())
        self.assertEqual(failures, [], "\n" + "\n".join(failures))
