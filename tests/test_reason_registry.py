"""The decision reason registry (hengbot.reasons) and what is derived from it.

Maintainability review 2026-11-09, step 1 (owner 「手順1から始める」): the escape sets of
policy_constants are derived from the registry with the membership they had as literals, frozen
here as they stood at 7e4d87ab2f (policy_constants.py:923-997)."""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import ast
from functools import lru_cache
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reason_registry_lint as lint  # noqa: E402
from hengbot import policy_constants, reasons  # noqa: E402


@lru_cache(maxsize=1)
def repository_shapes() -> dict:
    """Every reason shape the package sends (the lint's scan), computed once."""
    return lint.shapes()

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


class LintTest(unittest.TestCase):
    """scripts/reason_registry_lint.py on the repository and on edited sources."""

    @staticmethod
    def edited(module: str, old: str, new: str) -> list[str]:
        sources = lint.repository_sources()
        source = sources[module]
        assert old in source, old
        sources[module] = source.replace(old, new, 1)
        return lint.analyze(sources)

    def test_every_escape_shaped_reason_of_the_source_is_registered(self):
        self.assertEqual(lint.analyze(), [])

    def test_a_new_literal_escape_reason_fails(self):
        findings = self.edited(
            "threat_tiers", 'policy.last_reason = SENSED_LEAVE_PREFIX + "stairs"',
            'policy.last_reason = "sensed-t2:stairs"')
        self.assertTrue(any("'sensed-t2:stairs'" in finding for finding in findings), findings)

    def test_a_new_reason_built_from_a_prefix_constant_fails(self):
        """The sensed T1 leave's reasons are built from SENSED_LEAVE_PREFIX (threat_tiers ~1212):
        a new means under it is seen through the constant."""
        findings = self.edited(
            "threat_tiers", 'SENSED_LEAVE_PREFIX + "recall"', 'SENSED_LEAVE_PREFIX + "teleport-level"')
        self.assertTrue(any("'sensed-t1:teleport-level'" in finding for finding in findings), findings)

    def test_a_new_f_string_family_fails_on_its_fixed_part(self):
        findings = self.edited(
            "summon_response", 'LEAVE_REASON = "summons:leave-teleport"',
            'LEAVE_REASON = f"summons-new:leave-{FEW}"')
        self.assertTrue(any("'summons-new:leave-*'" in finding for finding in findings), findings)

    def test_a_reason_passed_to_a_reason_parameter_is_seen(self):
        """blind_teleport_key(policy, snapshot, reason) builds ``reason + CAST_SUFFIX``: the
        callers' values reach the assignment."""
        findings = self.edited(
            "threat_tiers", 'blind_teleport_key(policy, snapshot, SENSED_LEAVE_PREFIX + "teleport")',
            'blind_teleport_key(policy, snapshot, "sensed-t9:teleport")')
        self.assertTrue(any("'sensed-t9:teleport:absorbed-power'" in finding for finding in findings),
                        findings)

    def test_a_reason_rewritten_by_replace_is_seen(self):
        """policy._unprofitable_unique_disengage_key renames the fruitless fight's
        combat:disengage-* reasons with ``str.replace`` on ``self.last_reason``."""
        findings = self.edited(
            "policy", '"combat:avoid-unprofitable-unique-",\n                1,',
            '"combat:shun-unprofitable-unique-",\n                1,')
        self.assertTrue(any("'combat:shun-unprofitable-unique-stairs'" in finding for finding in findings),
                        findings)

    def test_every_counted_reason_is_sent_by_one_of_its_producers(self):
        """A counted row names the modules that send it; the scan finds it there."""
        shapes = repository_shapes()
        for row in reasons.ROWS:
            if row.kind not in reasons.COUNTED:
                continue
            modules = {module for module, _ in shapes.get(row.pattern, [])}
            self.assertTrue(modules & set(row.producers), (row.pattern, row.producers, sorted(modules)))


# breeder_stalemate's word guess as it stood at 7e4d87ab2f (breeder_stalemate.py:99-103, 129-133).
OLD_ATTACK_REASON_WORDS = ("ranged", "fire", "shot", "melee", "attack", "strike", "throw", "kill",
                           "magic-eater-device", "breeder-area", "aim-wand")
OLD_NOT_ATTACK_WORDS = ("hold", "approach", "reposition", "retreat", "recover", "survey", "unreachable",
                        "blocked", "disengage", "-point", "shop:", "periodic:", "immune:")


def old_is_attack_reason(reason):
    reason = reason or ""
    return (any(word in reason for word in OLD_ATTACK_REASON_WORDS)
            and not any(word in reason for word in OLD_NOT_ATTACK_WORDS))


def recorded_reasons() -> list[str]:
    path = Path(__file__).resolve().parent / "fixtures" / "reason-registry-recorded-reasons-1109.json"
    return json.loads(path.read_text(encoding="utf-8"))["reasons"]


def built_reasons() -> set[str]:
    """The reasons the source builds from values the scan leaves as ``*``, from their tables."""
    from hengbot import me_powers, policy_constants as constants
    out = set()
    for power in me_powers.POWERS:
        for trigger in power.triggers:
            base = f"{me_powers.REASON}:{trigger}:{power.effect}"
            out |= {base, base + me_powers.POWERFUL_SUFFIX}
    out |= {f"ranged:breeder-area:{kind}" for kind in ("wand", "rod", "staff", "read")}
    labels = sorted(set().union(*(constants.required_depth_gates(depth) for depth in range(128))))
    for mask in range(1, 1 << len(labels)):
        missing = ",".join(label for index, label in enumerate(labels) if mask >> index & 1)
        gate = f"depth-gate:destination-50:missing-{missing}"
        out |= {gate, f"fundraising:no-safe-destination:{gate}"}
    readiness = {"unready"}
    for node in ast.walk(ast.parse((lint.POLICY_ROOT / "policy_quest.py").read_text(encoding="utf-8"))):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "reject"
                and node.args and isinstance(node.args[0], ast.Constant)):
            readiness.add(node.args[0].value)
    out |= {f"quest:readiness:{label}" for label in readiness}
    out |= {f"esp-threat:hunt-{tier}" for tier in ("weak", "medium", "strong")}
    returns = [shape for shape in repository_shapes() if shape.startswith("return:") and "*" not in shape]
    out |= {"esp-threat:leave-" + shape[len("return:"):] for shape in returns}
    return out


class AttackAttributeTest(unittest.TestCase):
    """The registry's ``attack`` classifies every reason exactly as the word guess it replaced."""

    def assert_same(self, universe):
        differ = sorted(reason for reason in universe
                        if reasons.is_attack(reason) != old_is_attack_reason(reason))
        self.assertEqual(differ, [])

    def test_every_reason_the_source_sends(self):
        self.assert_same(repository_shapes())

    def test_every_reason_the_recordings_show(self):
        self.assert_same(recorded_reasons())

    def test_the_reasons_built_from_tables(self):
        self.assert_same(built_reasons())

    def test_breeder_stalemate_reads_the_registry(self):
        from hengbot import breeder_stalemate
        self.assertFalse(hasattr(breeder_stalemate, "ATTACK_REASON_WORDS"))
        self.assertTrue(breeder_stalemate.is_attack_reason("ranged:fire"))
        self.assertTrue(breeder_stalemate.is_attack_reason("quest25:shot"))
        self.assertFalse(breeder_stalemate.is_attack_reason("summoner:hold-choke"))
        self.assertFalse(breeder_stalemate.is_attack_reason(None))


if __name__ == "__main__":
    unittest.main()
