"""class_literal_lint: a branch on a literal class / race / personality id or on an instance name
is a finding (MAINTAINABILITY.md rule 1, 2026-11-27)."""

import tests  # noqa: F401
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import class_literal_lint as lint  # noqa: E402

SOURCE = '''
PLAYER_CLASS_MAGIC_EATER = 16


def warrior_only(snapshot):
    if snapshot.player.class_id == 0:
        return 1
    if snapshot.player.class_id in (0, 16):
        return 2
    return 3


def magic_eater(player):
    return getattr(player, "class_id", None) != PLAYER_CLASS_MAGIC_EATER


def known(snapshot):
    return snapshot.player.class_id >= 0 and snapshot.player.class_id != -1


def monster(monster, snapshot):
    return monster.race_id == 202 or snapshot.player.race_id == 7


def instance(name):
    """Prose about n1-a in a docstring is fine."""
    note = "n1-c life-209: a walk-out (prose)"
    return name == "n1-b" or note
'''


class ClassLiteralLintTest(unittest.TestCase):
    def findings(self, source=SOURCE, filename='mutant.py'):
        return [(f.function, f.kind, f.expression) for f in lint.findings_in(source, filename)]

    def test_literal_and_constant_branches_are_found(self):
        found = self.findings()
        self.assertIn(('warrior_only', 'class-literal', 'snapshot.player.class_id == 0'), found)
        self.assertIn(('warrior_only', 'class-literal', 'snapshot.player.class_id in (0, 16)'), found)
        self.assertIn(('magic_eater', 'class-constant',
                       "getattr(player, 'class_id', None) != PLAYER_CLASS_MAGIC_EATER"), found)
        self.assertIn(('<module>', 'constant-definition', 'PLAYER_CLASS_MAGIC_EATER = 16'), found)

    def test_the_players_race_counts_and_a_monsters_does_not(self):
        found = self.findings()
        self.assertIn(('monster', 'race-literal', 'snapshot.player.race_id == 7'), found)
        self.assertFalse(any('monster.race_id' in expression for _, _, expression in found))

    def test_known_checks_are_not_branches(self):
        self.assertFalse(any(function == 'known' for function, _, _ in self.findings()))

    def test_instance_name_compared_is_found_and_prose_is_not(self):
        found = [entry for entry in self.findings() if entry[1] == 'instance-name']
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0], 'instance')
        self.assertTrue(found[0][2].startswith('n1-b'))

    def test_allowed_modules_may_define_and_compare(self):
        found = self.findings(filename='class_roles.py')
        self.assertEqual([entry for entry in found if entry[1] != 'instance-name'], [])

    def test_key_has_no_line_number_and_summary_counts_the_magic_eater(self):
        findings = lint.findings_in(SOURCE, 'mutant.py')
        moved = lint.findings_in('\n\n\n' + SOURCE, 'mutant.py')
        self.assertEqual([lint.finding_key(f) for f in findings], [lint.finding_key(f) for f in moved])
        self.assertIn('PLAYER_CLASS_MAGIC_EATER checks: 1', lint.summary(findings))

    def test_repository_is_within_its_baseline(self):
        import lint_baseline
        findings = lint.repository_findings()
        new, _stale = lint_baseline.new_findings(lint.LINT, findings, lint.finding_key)
        self.assertEqual([lint.render(finding) for finding in new], [])


if __name__ == '__main__':
    unittest.main()
