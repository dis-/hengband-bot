"""D39: town work records without the per-call profile hook.

town_work_decision recorded which hengbot frames returned the decided key
with a sys.setprofile hook. The hook ran a Python callback for every call and
return of every function, which made town decisions 2-4 times slower (n1-c
fixedquest:claim:approach 0.9-2.4 s). The observer now watches only returns
through sys.monitoring and disables the locations it can never record.

Each board goes through the public choose_key twice from the same recorded
start: once with the original hook (_profile_returns, the reference) and once
with the default observer. Key, reason, every receipt (with the policy-final
work record and its chain) and current_record must be identical. The cost
check counts observer callbacks, not wall time.

Boards: three pickled pre-decision checkpoints of the ownership replay
corpus, three 2026-10-29/30 viewing-bot boundaries of the lv7 and
Magic-Eater town stop fixtures, and four n1-c approach boards of 2026-10-30
extracted by tests/extract_town_work_observer.py.
"""
import tests  # noqa: F401

import base64
from contextlib import contextmanager
import gzip
import json
import os
from pathlib import Path
import pickle
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

from hengbot import town_work
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from ownership_on_corpus import FIXTURES, MANIFEST, enable_live_switches, read_json, read_rows
from tests import test_lv7_town_stop_recorded as lv7
from tests import test_me_town_stops_recorded as me
from test_town_work_contract import board as constructed_board


OBSERVER_FIXTURE = Path(__file__).with_name("fixtures") / "town-work-observer-20261031.json.gz"
CHECKPOINTS = (
    "town-restock-stall-hungry-checkpoints.jsonl.gz:2331",
    "food-store-unreachable-checkpoints.jsonl.gz:220",
    "device-purchase-preempted-checkpoint.jsonl.gz:253",
)
LV7_CASES = (0, 4)  # fixedquest:request:approach and shop:travel
ME_CASES = ("life-021", "life-023")
# The default observer runs at most this share of the hook's callbacks.
CALLBACK_RATIO = 10


def outcome(policy, key):
    return dict(key=key, reason=policy.last_reason, receipts=town_work.receipts(policy),
                record=town_work.current_record(policy, key))


class TownWorkObserverRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = town_work._monitoring_tool()
        lv7.Lv7TownStopRecordedTest.setUpClass()
        me.MagicEaterTownStopsRecordedTest.setUpClass()
        with gzip.open(OBSERVER_FIXTURE, "rt", encoding="utf-8") as stream:
            cls.observer_cases = json.load(stream)
        windows = {w["name"]: w for w in read_json(MANIFEST)["windows"]}
        cls.checkpoints = {}
        for name in CHECKPOINTS:
            window = windows[name]
            rows = read_rows(FIXTURES / window["checkpoint_source"])
            cls.checkpoints[name] = rows[window["checkpoint_line"] - 1]

    def boards(self):
        """(name, factory) for each recorded board; a factory builds a fresh start."""
        def checkpoint(name):
            captured = self.checkpoints[name]
            policy = restore_checkpoint(HengbotPolicy, captured["predecision_policy_checkpoint_pickle_b64"])
            enable_live_switches(policy)
            return policy, pickle.loads(base64.b64decode(captured["decision_snapshot_pickle_b64"]))

        def boundary(make):
            policy, raw = make()
            return policy, parse_snapshot(raw, policy._monrace_knowledge)

        found = [(f"checkpoint/{name}", lambda name=name: checkpoint(name)) for name in CHECKPOINTS]
        found += [(f"lv7/{index}", lambda index=index: boundary(
            lambda: lv7.Lv7TownStopRecordedTest().boundary(lv7.Lv7TownStopRecordedTest.cases[index])))
            for index in LV7_CASES]
        found += [(f"me/{life}", lambda life=life: boundary(
            lambda: me.MagicEaterTownStopsRecordedTest().boundary(life))) for life in ME_CASES]
        found += [(f"n1c/{case['id']}", lambda case=case: boundary(
            lambda: lv7.Lv7TownStopRecordedTest().boundary(case))) for case in self.observer_cases]
        return found

    def reference(self, policy, board):
        """The original hook; returns (outcome, profile events it handled)."""
        events = [0]

        def count(frame, event, value):
            events[0] += 1

        previous = sys.getprofile()
        sys.setprofile(count)
        try:
            # The hook chains the profiler it replaces, so count sees each event.
            with patch.object(town_work, "_collect_returns", town_work._profile_returns):
                key = policy.choose_key(board)
        finally:
            sys.setprofile(previous)
        return outcome(policy, key), events[0]

    def observed(self, policy, board):
        """The default observer; returns (outcome, callbacks it received)."""
        monitoring = sys.monitoring
        calls = [0]
        # A copy of the callback whose sys._getframe skips the counting frame.
        shim = types.SimpleNamespace(_getframe=lambda depth=0: sys._getframe(depth + 2))
        callback = types.FunctionType(town_work._on_return.__code__,
                                      dict(vars(town_work), sys=shim))

        def counting(code, offset, value):
            calls[0] += 1
            return callback(code, offset, value)

        events = (monitoring.events.PY_RETURN, monitoring.events.PY_YIELD)
        for event in events:
            monitoring.register_callback(self.tool, event, counting)
        try:
            key = policy.choose_key(board)
        finally:
            for event in events:
                monitoring.register_callback(self.tool, event, town_work._on_return)
        return outcome(policy, key), calls[0]

    def test_recorded_town_boards_keep_records_with_a_fraction_of_the_callbacks(self):
        self.assertIsNotNone(self.tool, "no free sys.monitoring tool id")
        self.assertIs(town_work._collect_returns, town_work._monitor_returns)
        rows = []
        chains = 0
        for name, make in self.boards():
            with self.subTest(board=name):
                policy, board = make()
                self.assertTrue(town_work.town_context(board))
                started = time.perf_counter()
                expected, hook_events = self.reference(policy, board)
                hook_ms = (time.perf_counter() - started) * 1000
                policy, board = make()
                started = time.perf_counter()
                actual, callbacks = self.observed(policy, board)
                observer_ms = (time.perf_counter() - started) * 1000
                self.assertEqual(actual, expected)
                self.assertEqual(sys.monitoring.get_events(self.tool), 0)
                final = expected["receipts"][-1]
                self.assertEqual(final["seam"], "policy-final")
                self.assertIsNone(final["reason"], final)
                chains += len(expected["record"]["chain"])
                self.assertLessEqual(callbacks * CALLBACK_RATIO, hook_events,
                                     (name, callbacks, hook_events))
                rows.append(dict(board=name, key=expected["key"], reason=expected["reason"],
                                 chain=len(expected["record"]["chain"]),
                                 hook_events=hook_events, observer_callbacks=callbacks,
                                 hook_ms=round(hook_ms), observer_ms=round(observer_ms)))
        self.assertEqual(len(rows), 11)
        self.assertGreater(chains, len(rows))
        destination = os.environ.get("TOWN_WORK_OBSERVER_RESULTS")
        if destination:
            Path(destination).write_text(json.dumps(dict(schema=1, boards=rows), indent=2) + "\n",
                                         encoding="utf-8", newline="\n")

    def test_other_threads_and_unreviewed_children_match_the_hook(self):
        # DECLARED CONSTRUCTED: an unreviewed policy child returns the key and
        # another thread returns it from a policy method meanwhile. The hook
        # saw only the deciding thread and marked the unreviewed child unmapped.
        code = compile("def new_town_work(self, snapshot):\n"
                       " helper = threading.Thread(target=lambda: self.other_thread_key())\n"
                       " helper.start()\n"
                       " helper.join()\n"
                       " return '5'\n"
                       "def other_thread_key(self):\n"
                       " return '5'\n",
                       str(Path(HengbotPolicy.choose_key.__code__.co_filename).with_name("policy.py")),
                       "exec")
        results = []
        for collect in (town_work._profile_returns, town_work._monitor_returns):
            namespace = {"__name__": "hengbot.policy", "threading": threading}
            exec(code, namespace)
            policy = HengbotPolicy()
            with patch.object(policy, "_choose_key", namespace["new_town_work"].__get__(policy)), \
                 patch.object(policy, "other_thread_key", namespace["other_thread_key"].__get__(policy),
                              create=True), \
                 patch.object(town_work, "_collect_returns", collect):
                key = policy.choose_key(constructed_board())
            results.append(outcome(policy, key))
        self.assertEqual(results[1], results[0])
        final = results[0]["receipts"][-1]
        self.assertEqual(final["reason"], town_work.UNMAPPED)
        self.assertEqual(final["producer"], "policy.py:new_town_work")

    def test_observer_is_off_after_a_failed_decision(self):
        def broken(policy, snapshot):
            raise RuntimeError("control")
        with self.assertRaises(RuntimeError):
            town_work.town_work_decision(broken)(HengbotPolicy(), constructed_board())
        self.assertEqual(town_work._observing, [])
        self.assertEqual(sys.monitoring.get_events(self.tool), 0)


if __name__ == "__main__":
    unittest.main()
