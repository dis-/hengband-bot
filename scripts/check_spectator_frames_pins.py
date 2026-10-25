"""Per-pin behavioural revert proofs in a disposable package copy.

The current checkout and existing tests are never modified. Every mutant must
fail its named regression test with an assertion (import failures do not count).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FOLLOW = "tests.test_spectator_frames.FramesFollowTest."
WRITER = "tests.test_spectator_frames.FramesWriterTest."
MUTANTS = [
    ("append", "cli.py", "                spectator.commit_frame()", "                pass",
     FOLLOW + "test_every_post_appends_in_order_without_snapshot_throttle"),
    ("number", "spectator.py", "number = self.last_frame + 1", "number = 1",
     FOLLOW + "test_every_post_appends_in_order_without_snapshot_throttle"),
    ("backlog_wait", "cli.py", 'maximum = getattr(args, "spectate_max_backlog", 0)', "maximum = 0",
     FOLLOW + "test_backlog_at_limit_waits_for_played_advance_outside_timing"),
    ("backlog_boundary", "spectator.py", "self.last_frame - frame >= maximum", "self.last_frame - frame > maximum",
     FOLLOW + "test_backlog_at_limit_waits_for_played_advance_outside_timing"),
    ("below_limit", "spectator.py", "self.last_frame - frame >= maximum", "self.last_frame - frame >= 1",
     FOLLOW + "test_backlog_below_limit_does_not_wait"),
    ("stale", "spectator.py", "age < 0 or age > SPECTATE_PLAYED_MAX_AGE_SECONDS", "age < 0",
     FOLLOW + "test_stale_missing_and_invalid_ack_do_not_wait"),
    ("missing_or_invalid", "spectator.py", "except (OSError, ValueError, KeyError, TypeError, OverflowError):\n            return False",
     "except (OSError, ValueError, KeyError, TypeError, OverflowError):\n            return True",
     FOLLOW + "test_stale_missing_and_invalid_ack_do_not_wait"),
    ("expire_during_wait", "spectator.py", "age < 0 or age > SPECTATE_PLAYED_MAX_AGE_SECONDS", "age < 0",
     FOLLOW + "test_server_stopping_during_wait_releases_bot"),
    ("zero_no_read", "spectator.py", "if maximum <= 0:", "if maximum < 0:",
     FOLLOW + "test_default_zero_never_reads_played_file"),
    ("feature_control", "cli.py", 'maximum = getattr(args, "spectate_max_backlog", 0)', "maximum = 0",
     FOLLOW + "test_keys_and_reasons_with_both_features_and_pacing"),
    ("retry", "cli.py", "(post_decision if args.min_action_seconds > 0 or spectator is not None\n                             else",
     "(post_decision if args.min_action_seconds > 0\n                             else",
     FOLLOW + "test_refused_post_has_no_frame_and_retry_is_backpressured"),
    ("deadline", "cli.py", 'post_kwargs["deadline"] = post_at + args.stall_timeout', "pass",
     FOLLOW + "test_backlog_at_limit_waits_for_played_advance_outside_timing"),
    ("timing", "cli.py", "decision_started_at += waited", "decision_started_at += 0",
     FOLLOW + "test_backlog_at_limit_waits_for_played_advance_outside_timing"),
    ("watchdog_cancel", "cli.py", "            faulthandler.cancel_dump_traceback_later()\n            try:\n                if remaining > 0:",
     "            pass\n            try:\n                if remaining > 0:",
     FOLLOW + "test_backlog_at_limit_waits_for_played_advance_outside_timing"),
    ("watchdog_rearm", "cli.py", "                _arm_decision_watchdog()\n        if spectator is not None:",
     "                pass\n        if spectator is not None:",
     FOLLOW + "test_backlog_at_limit_waits_for_played_advance_outside_timing"),
    ("frame_colours", "spectator.py", "if not snapshot_due and not append_frame:", "if not snapshot_due:",
     WRITER + "test_colours_every_frame_and_snapshot_stays_throttled"),
    ("follow_colours", "cli.py", "screen_client=executor.client if executor is not None else None,\n                policy=policy, append_frame=True",
     "screen_client=None,\n                policy=policy, append_frame=True",
     "tests.test_spectator_frames.FramesColourFollowTest.test_each_actual_post_requests_colours_through_executor"),
    ("rotation", "spectator.py", "if size + len(row) > SPECTATE_FRAMES_MAX_BYTES:", "if False:",
     WRITER + "test_rotation_keeps_complete_newest_rows_and_restart_number"),
    ("restart", "spectator.py", "self.last_frame = self._resume_frame()", "self.last_frame = 0",
     WRITER + "test_rotation_keeps_complete_newest_rows_and_restart_number"),
    ("ack_validation", "spectator.py", "if type(stamp) not in (int, float) or not math.isfinite(stamp):", "if type(stamp) not in (int, float):",
     WRITER + "test_bad_ack_values_fail_open"),
    ("torn_tail", "spectator.py", 'if stream.read(1) != b"\\n":', "if False:",
     WRITER + "test_torn_tail_is_repaired_before_next_append"),
    ("failed_rotation", "spectator.py", "            os.replace(temporary, self.frames_path)",
     '            with self.frames_path.open("ab") as stream:\n                stream.write(row)',
     WRITER + "test_failed_rotation_does_not_allow_file_to_grow"),
    ("isolated_outputs", "spectator.py", "                self.pending_frame = content", "                self.pending_frame = None",
     WRITER + "test_broken_output_never_raises_and_other_output_survives"),
]


def main():
    results = []
    with tempfile.TemporaryDirectory(prefix="spectate-revert-") as directory:
        copied = Path(directory) / "src/hengbot"
        shutil.copytree(ROOT / "src/hengbot", copied, ignore=shutil.ignore_patterns("__pycache__"))
        originals = {name: (copied / name).read_text(encoding="utf-8") for name in ("cli.py", "spectator.py")}
        env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(copied.parent), str(ROOT / "tests"), str(ROOT / "scripts"))),
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
        baseline = subprocess.run([sys.executable, "-m", "unittest", "tests.test_spectator_frames"],
                                  cwd=ROOT, env=env, capture_output=True, text=True,
                                  encoding="utf-8", timeout=120)
        if baseline.returncode:
            print(baseline.stderr)
            raise SystemExit("the unmodified pins must pass before mutation")
        for label, name, before, after, pin in MUTANTS:
            assert originals[name].count(before) == 1, (label, originals[name].count(before))
            (copied / name).write_text(originals[name].replace(before, after), encoding="utf-8", newline="\n")
            try:
                run = subprocess.run([sys.executable, "-m", "unittest", pin], cwd=ROOT,
                                     env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
                # An assertion or a torn-record JSON decoding failure is a behavioural detection.
                failures = re.findall(r"^(?:FAIL|ERROR): (.+)", run.stderr, re.M)
                caught = (run.returncode != 0 and bool(failures)
                          and "ImportError" not in run.stderr and "SyntaxError" not in run.stderr)
                results.append({"mutation": label, "pin": pin, "caught": caught,
                                "failures": failures})
                print(json.dumps(results[-1]), flush=True)
            finally:
                (copied / name).write_text(originals[name], encoding="utf-8", newline="\n")
    print(f"caught {sum(item['caught'] for item in results)}/{len(results)}")
    return int(not all(item["caught"] for item in results))


if __name__ == "__main__":
    raise SystemExit(main())
