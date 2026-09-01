from __future__ import annotations

import unittest

import town_acquire_bypass_recorded as recorded


class TownAcquireBypassRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decisions = list(recorded._rows(recorded.DECISIONS))
        cls.raw_ledger = list(recorded._rows(recorded.LEDGER))
        cls.posted = list(recorded._rows(recorded.POSTED))
        cls.clean_ledger = recorded.filter_synthetic_ledger(cls.decisions, cls.raw_ledger)
        cls.raw = recorded.measure(cls.decisions, cls.raw_ledger, cls.posted)
        cls.result = recorded.measure(cls.decisions, cls.clean_ledger, cls.posted)

    def test_recorded_values_are_pinned_not_only_fixture_shape(self):
        raw, totals = self.raw["totals"], self.result["totals"]
        self.assertEqual((15161, 14725, 436, 248), tuple(raw[key] for key in (
            "ledger_posts", "ledger_posts_with_decision", "ledger_posts_without_decision",
            "ledger_posts_without_decision_while_visit_open")))
        self.assertEqual((14727, 14725, 2, 0), tuple(totals[key] for key in (
            "ledger_posts", "ledger_posts_with_decision", "ledger_posts_without_decision",
            "ledger_posts_without_decision_while_visit_open")))
        self.assertEqual((16068, 14740, 1328, 1343, 13), (
            totals["decisions_in_forward_denominator"], totals["posts_with_decision"],
            totals["decisions_in_forward_denominator"] - totals["posts_with_decision"],
            totals["decisions_without_ledger_match"], totals["posts_with_decision_without_ledger_row"]))
        self.assertEqual((15101, 361, 341, 20, 119, 7), (
            totals["posts_in_window"], totals["posts_without_decision"],
            totals["decisionless_key:\x1b"], totals["decisionless_key:l\x1b"],
            totals["decisionless_while_visit_open"], totals["decisionless_while_store_page_open"]))
        self.assertEqual((1870, 222, 222, 0), tuple(totals[key] for key in (
            "non_opener_posts_proxy", "non_opener_target_derivable",
            "non_opener_target_same", "non_opener_target_different")))
        self.assertEqual((227, 149, 46), tuple(self.result["origins"][key] for key in (
            "shop-one-shot", "shop-handler-recovery", "recovered-store-context")))

    def test_pollution_discriminator_and_magnitude_controls_are_exact(self):
        pollution = recorded.ledger_pollution(self.decisions, self.raw_ledger)
        self.assertEqual(3044, pollution["rows"])
        self.assertEqual(933, pollution["with_posted_key"])
        self.assertEqual("2026-08-15T05:36:04.979046", pollution["first"])
        self.assertEqual("2026-09-01T08:43:32.186235", pollution["last"])
        self.assertEqual((436, 2), (self.raw["totals"]["ledger_posts_without_decision"],
                                    self.result["totals"]["ledger_posts_without_decision"]))
        self.assertEqual((248, 0), (self.raw["totals"]["ledger_posts_without_decision_while_visit_open"],
                                    self.result["totals"]["ledger_posts_without_decision_while_visit_open"]))
        self.assertEqual((0, 222), (self.result["totals"]["non_opener_target_different"],
                                    self.result["totals"]["non_opener_target_derivable"]))
        controls = recorded.magnitude_controls(
            self.decisions, self.raw_ledger, self.clean_ledger, self.posted, self.result)
        self.assertEqual({"filter_reverse": (436, 2), "filter_open_visit": (248, 0),
                          "remove_decisionless": (15101, 14740, 361, 0),
                          "remove_decision_posts": (14740, 0), "clear_visits": (119, 0, 7, 0, 2818, 0),
                          "equalize_openers": (1870, 0), "force_different": (0, 222)}, controls)


if __name__ == "__main__":
    unittest.main()
