"""The decision reason registry (hengbot.reasons) and what is derived from it.

Maintainability review 2026-11-09, step 1 (owner 「手順1から始める」): the escape sets of
policy_constants are derived from the registry with the membership they had as literals, frozen
here as they stood at 7e4d87ab2f (policy_constants.py:923-997)."""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import unittest

from hengbot import policy_constants, reasons

# policy_constants.EMERGENCY_ESCAPE_REASONS at 7e4d87ab2f.
OLD_EMERGENCY_ESCAPE_REASONS = frozenset({
    "emergency:teleport",
    "emergency:teleport:absorbed-power",
    "emergency:teleport-staff",
    "emergency:phase",
    "emergency:recall",
    "emergency:stairs",
    "emergency:seek-upstairs",
})
# policy_constants.STATUS_THREAT_RELOCATION_REASONS | the 11-09 literal set at 7e4d87ab2f.
OLD_RELOCATING_ESCAPE_REASONS = frozenset({
    "status-threat:scroll",
    "status-threat:stairs",
    "emergency:recall-quest-fail",
    "emergency:stairs-quest-fail",
    "emergency:stairs-down",
    "flee:scroll",
    "flee:stairs",
    "flee:stairs-quest-fail",
    "threat:scroll",
    "sensed-t1:teleport",
    "sensed-t1:teleport:absorbed-power",
    "sensed-t1:teleport-staff",
    "sensed-t1:phase",
    "sensed-t1:stairs",
    "sensed-t1:recall",
    "summoner:stairs",
    "summoner:stairs-quest-fail",
    "summoner:hold-teleport",
    "summons:leave-teleport",
    "summons:recall",
    "resist-potion:no-chance-teleport",
    "breeder-item-damage:stairs",
    "breeder-item-damage:teleport-level",
    "breeder-item-damage:teleport",
    "breeder-item-damage:recall",
    "combat:disengage-stairs",
    "combat:disengage-recall",
    "breeder-breakthrough:ascend",
    "breeder-breakthrough:recall",
})


class DerivedSetsTest(unittest.TestCase):
    def test_emergency_escape_reasons_are_the_old_literals(self):
        self.assertEqual(policy_constants.EMERGENCY_ESCAPE_REASONS, OLD_EMERGENCY_ESCAPE_REASONS)

    def test_relocating_escape_reasons_are_the_old_literals(self):
        self.assertEqual(policy_constants.RELOCATING_ESCAPE_REASONS, OLD_RELOCATING_ESCAPE_REASONS)

    def test_the_counted_kinds_do_not_overlap(self):
        self.assertFalse(policy_constants.EMERGENCY_ESCAPE_REASONS
                         & policy_constants.RELOCATING_ESCAPE_REASONS)

    def test_lookup_answers_every_counted_reason_with_its_kind(self):
        for reason in OLD_EMERGENCY_ESCAPE_REASONS:
            self.assertEqual(reasons.lookup(reason).kind, reasons.EMERGENCY, reason)
        for reason in OLD_RELOCATING_ESCAPE_REASONS:
            self.assertEqual(reasons.lookup(reason).kind, reasons.RELOCATING, reason)


class RegistryShapeTest(unittest.TestCase):
    def test_every_row_has_a_known_kind_producers_and_a_rule(self):
        for row in reasons.ROWS:
            self.assertIn(row.kind, reasons.KINDS, row)
            self.assertTrue(row.producers, row)
            self.assertTrue(row.rule, row)

    def test_no_pattern_is_declared_twice(self):
        patterns = [row.pattern for row in reasons.ROWS]
        self.assertEqual(sorted(p for p in set(patterns) if patterns.count(p) > 1), [])

    def test_counted_rows_are_exact_reasons(self):
        for row in reasons.ROWS:
            if row.kind in reasons.COUNTED:
                self.assertFalse(any(mark in row.pattern for mark in "*?["), row)

    def test_the_escape_vocabulary_covers_every_counted_reason(self):
        """ESCAPE_WORDS is the registry's own: every counted reason has one of its words, so the
        lint's shape test cannot miss a reason of a counted family."""
        for row in reasons.ROWS:
            if row.kind in reasons.COUNTED:
                self.assertTrue(reasons.escape_shaped(row.pattern), row.pattern)

    def test_a_pattern_row_answers_the_reasons_built_from_it(self):
        self.assertEqual(reasons.lookup("esp-threat:leave-recall").kind, reasons.EXCLUDED)
        self.assertEqual(reasons.lookup("emergency:destruction:disenchanter:absorbed-power").kind,
                         reasons.EXCLUDED)
        self.assertEqual(reasons.lookup("me-power:unbeatable-in-range:teleport-away").kind,
                         reasons.EXCLUDED)
        self.assertEqual(reasons.lookup("combat:disengage-new").kind, reasons.WALK)
        self.assertIsNone(reasons.lookup("explore:frontier"))
        self.assertIsNone(reasons.lookup(None))


if __name__ == "__main__":
    unittest.main()
