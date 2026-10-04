"""Run one explicitly selected module, retaining per-identity triage evidence."""
import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "validation" / "suitefix3"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("revision")
    parser.add_argument("module")
    parser.add_argument("identities", nargs="*")
    args = parser.parse_args()
    if args.module == "test_policy_town":
        now = time.localtime()
        if (now.tm_hour, now.tm_min) < (19, 40):
            raise SystemExit("test_policy_town must wait until 19:40 JST")
    root = ROOT
    if args.revision != "working":
        root = OUT / ("source-" + args.revision)
        if not root.exists():
            archive = subprocess.check_output([
                "git", "archive", "--format=zip", args.revision,
                "src", "tests", "strategy", "pyproject.toml", "USER-CONTRACT.md",
            ], cwd=ROOT)
            root.mkdir(parents=True)
            with zipfile.ZipFile(io.BytesIO(archive)) as stream:
                stream.extractall(root)
    sys.path[:0] = [str(root / "src"), str(root / "tests"), str(root)]
    os.chdir(root)
    import tests  # runtime write guards and temporary overrides
    # An archive has no linked-worktree marker. Extend its audit guard to the
    # explicitly protected live runtime without opening any of its files.
    tests._RUNTIME_DIRS += (Path("C:/hengband/bot-client/jsonlog"),)
    names = [args.module + "." + name for name in args.identities] or [args.module]
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    if args.module == "test_unaffordable_claim_tour_recorded":
        module = sys.modules[args.module]
        original_claim_row = module._claim_row
        def claim_row(policy, snapshot, key, index):
            row = original_claim_row(policy, snapshot, key, index)
            if index % 500 == 0 or index >= 4229:
                print("replay", index, str(key).__repr__(), policy.last_reason, flush=True)
            return row
        module._claim_row = claim_row
    class Result(unittest.TextTestResult):
        def startTest(self, test):
            super().startTest(test)
            self.identities[test.id()] = "PASS"
        def addFailure(self, test, err):
            super().addFailure(test, err)
            self.identities[test.id()] = "FAIL"
        def addError(self, test, err):
            super().addError(test, err)
            self.identities[test.id()] = "ERROR"
        def addSubTest(self, test, subtest, err):
            super().addSubTest(test, subtest, err)
            if err:
                self.identities[test.id()] = "FAIL"
        def addSkip(self, test, reason):
            super().addSkip(test, reason)
            self.identities[test.id()] = "SKIP"
        identities = {}
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    started = time.monotonic()
    stem = args.revision + "-" + args.module + ("-targeted" if args.identities else "")
    with (OUT / (stem + ".txt")).open("w", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Result).run(suite)
    receipt = dict(revision=args.revision, module=args.module, started_at=started_at,
                   tests=result.testsRun,
                   failures=len(result.failures), errors=len(result.errors),
                   skipped=len(result.skipped), expected_failures=len(result.expectedFailures),
                   unexpected_successes=len(result.unexpectedSuccesses),
                   elapsed=round(time.monotonic()-started, 3),
                   identities=result.identities)
    (OUT / (stem + ".json")).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    if args.module == "test_unaffordable_claim_tour_recorded":
        replay = sys.modules[args.module].UnaffordableClaimTourRecordedTest.replay
        if replay is not None:
            (OUT / (stem + "-replay.json")).write_text(
                json.dumps(dict(decisions=replay[0], decision=replay[1],
                                follow_up=replay[3]), indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in receipt.items() if key != "identities"}))
    for identity, outcome in receipt["identities"].items():
        if outcome in {"FAIL", "ERROR"}:
            print(outcome, identity)
    raise SystemExit(not result.wasSuccessful())


if __name__ == "__main__":
    main()
