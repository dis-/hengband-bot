"""Count S3 town producer deferrals during one recorded ownership test.

Run one case per process with PYTHONPATH=src;tests;scripts, for example:
python scripts/measure_s3_errand_deferred.py tour
"""

from collections import Counter
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tests  # noqa: F401 -- isolate runtime files as the recorded tests do
from hengbot.policy import HengbotPolicy


CASES = {
    "tour": "test_unaffordable_claim_tour_recorded.UnaffordableClaimTourRecordedTest.test_s3_new_code_replay_names_remaining_violations",
    "town-approach": "test_town_approach_retired_recorded.TownApproachRetiredRecordedTest.test_s3_new_code_replay_names_remaining_violations",
    "overweight-home": "test_overweight_home_unreachable_recorded.OverweightHomeUnreachableRecordedTest.test_replay_reproduces_every_recorded_decision_before_the_stop",
    "home-withdraw": "test_home_withdraw_failed_stock_present_recorded.HomeWithdrawFailedStockPresentRecordedTest.test_replay_reproduces_the_process_before_equipment_choice",
    "recall-cancel": "test_recall_read_cancel_pingpong_recorded.RecallReadCancelPingPongRecordedTest.test_replay_reproduces_each_recorded_read",
    "stuck-prompt": "test_stuck_prompt_staged_tail_recorded.StuckPromptStagedTailRecordedTest.test_replay_reproduces_the_window_decisions",
}


def main(case: str) -> int:
    counts = Counter()
    key_reasons = []
    original = getattr(HengbotPolicy, "_defer_town_errand", None)
    original_choose_key = HengbotPolicy.choose_key

    def measure(self, family, reason):
        before = len(getattr(self, "_decision_errand_deferred", ()))
        barred = original(self, family, reason)
        rows = getattr(self, "_decision_errand_deferred", ())
        for row in rows[before:]:
            counts[(row["holder_family"], row["deferred_family"])] += 1
        return barred

    def capture_key_reason(self, snapshot):
        key = original_choose_key(self, snapshot)
        key_reasons.append((str(key), self.last_reason))
        return key

    if original is not None:
        HengbotPolicy._defer_town_errand = measure
    HengbotPolicy.choose_key = capture_key_reason
    suite = unittest.defaultTestLoader.loadTestsFromName(CASES[case])
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=0).run(suite)
    print(json.dumps({
        "replay": case,
        "errand_deferred": sum(counts.values()),
        "by_holder_and_deferred": [
            {"holder_family": holder, "deferred_family": deferred, "count": count}
            for (holder, deferred), count in sorted(counts.items())
        ],
        "tests_run": result.testsRun,
        "passed": result.wasSuccessful(),
        "decisions": len(key_reasons),
        "key_reason_sha256": hashlib.sha256(
            json.dumps(key_reasons, ensure_ascii=False, separators=(",", ":"))
            .encode("utf-8")
        ).hexdigest(),
    }, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in CASES:
        raise SystemExit("Choose one replay: " + ", ".join(CASES))
    raise SystemExit(main(sys.argv[1]))
