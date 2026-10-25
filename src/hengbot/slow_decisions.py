"""Optional, bounded in-process stack samples around a single policy decision.

Python stacks only: samples in a Python caller may include time in native code.
No frame objects, locals, or policy objects are retained by the worker.
"""
from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
import sys
import threading
import time

INTERVAL = 0.010
MAX_DEPTH = 48
MAX_FUNCTIONS = 512
MAX_STACKS = 128
MAX_LOG_BYTES = 2 * 1024 * 1024


def _main_stack(thread_id):
    frame = sys._current_frames().get(thread_id)
    stack = []
    try:
        while frame is not None and len(stack) < MAX_DEPTH:
            code = frame.f_code
            stack.append((code.co_name[:128], code.co_filename[-240:],
                          code.co_firstlineno, frame.f_lineno))
            frame = frame.f_back
        return tuple(stack)  # leaf first, including its current source line
    finally:
        del frame


class _Samples:
    def __init__(self, thread_id, *, clock, stack_reader=_main_stack):
        self.thread_id = thread_id
        self.clock = clock
        self.stack_reader = stack_reader
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True,
                                       name="slow-decision-sampler")
        self.functions = {}
        self.stacks = Counter()
        self.count = 0
        self.dropped_stacks = 0
        self.tick_seconds = 0.0

    def start(self):
        self.thread.start()

    def tick(self):
        started = self.clock()
        stack = self.stack_reader(self.thread_id)
        if stack:
            self.count += 1
            # Recursive functions count at most once cumulatively per tick.
            seen = set()
            for index, (name, file, definition_line, line) in enumerate(stack):
                key = (name, file, definition_line)
                if key not in self.functions and len(self.functions) < MAX_FUNCTIONS:
                    self.functions[key] = [0, 0]
                counts = self.functions.get(key)
                if counts is not None:
                    counts[0] += index == 0
                    counts[1] += key not in seen
                seen.add(key)
            if stack in self.stacks or len(self.stacks) < MAX_STACKS:
                self.stacks[stack] += 1
            else:
                self.dropped_stacks += 1
        self.tick_seconds += max(0.0, self.clock() - started)

    def _run(self):
        try:
            while not self.stop.wait(INTERVAL):
                self.tick()
        except Exception:
            # Diagnostics must never interfere with decision execution.
            pass

    def finish(self):
        self.stop.set()
        self.thread.join(timeout=0.05)
        return not self.thread.is_alive()

    def aggregate(self):
        functions = sorted(self.functions.items(),
                           key=lambda item: (-item[1][1], -item[1][0], item[0]))[:40]
        return {
            "interval_ms": INTERVAL * 1000,
            "max_depth": MAX_DEPTH,
            "sample_count": self.count,
            "sampling_work_ms": round(self.tick_seconds * 1000, 3),
            "functions": [dict(function=k[0], file=k[1], line=k[2],
                               self_samples=v[0], cumulative_samples=v[1])
                          for k, v in functions],
            "stacks": [dict(samples=count, frames=[
                dict(function=f[0], file=f[1], line=f[3]) for f in stack])
                       for stack, count in self.stacks.most_common(5)],
            "dropped_stacks": self.dropped_stacks,
            "function_limit_reached": len(self.functions) == MAX_FUNCTIONS,
        }


class SlowDecisionRecorder:
    def __init__(self, seconds=0, decision_log=None, *, clock=None,
                 sampler_factory=None, max_bytes=MAX_LOG_BYTES):
        self.seconds = seconds
        self.path = (Path(decision_log).with_name("slow-decisions.jsonl")
                     if decision_log is not None else None)
        self.clock = clock or time.perf_counter
        self.sampler_factory = sampler_factory or _Samples
        self.max_bytes = max_bytes

    def choose_key(self, policy, snapshot):
        if self.seconds <= 0 or not math.isfinite(self.seconds) or self.path is None:
            return policy.choose_key(snapshot)
        samples = None
        try:
            samples = self.sampler_factory(threading.get_ident(), clock=self.clock)
            samples.start()
            started = self.clock()
        except Exception:
            self._finish(samples)
            return policy.choose_key(snapshot)
        try:
            key = policy.choose_key(snapshot)
        except BaseException:
            self._finish(samples)
            raise
        try:
            elapsed = self.clock() - started
            if self._finish(samples) and elapsed > self.seconds:
                self._append({
                    "decision_sequence": getattr(policy, "_decision_sequence", None),
                    "reason": policy.last_reason,
                    "choose_key_ms": round(elapsed * 1000, 3),
                    "aggregate": samples.aggregate(),
                })
        except Exception:
            pass
        return key

    @staticmethod
    def _finish(samples):
        try:
            return samples is not None and samples.finish()
        except Exception:
            return False

    def _append(self, record):
        payload = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        if len(payload) > self.max_bytes:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size + len(payload) > self.max_bytes:
            # One backup generation; both files are bounded by max_bytes.
            self.path.replace(self.path.with_name(self.path.name + ".1"))
        with self.path.open("ab") as stream:
            stream.write(payload)
