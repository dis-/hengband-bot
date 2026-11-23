"""The 50F+ admission gates answer through deep_admission.verdict as they did before (K2).

Whole-bot maintainability review 2026-11-23 K2: eleven gates of 「*破壊* なしで50F以降にいない」 asked
it with three predicates of their own.  tests/extract_deep_admission_1123_fixture.py asked every
gate over one table (dungeon x depth 44-52 x the means x the climb, tests/support
/deep_admission_table) on main 5fe531c0a and wrote the answers (tests/fixtures
/deep-admission-1123/answers.json); the gates routed through ``verdict`` give the same answers,
and where they disagree with each other (disagreements.json) is the owner's question, kept as
it is.

Recorded: n1-a life-535's town-arrival checkpoint (tests/fixtures/n1a-535-deep-arrival-1123):
its policy, the departure board of row 122 and the first Castle 48F board of the capture.

DECLARED CONSTRUCTED: the leaf facts of each cell (tests/support/deep_admission_table's
docstring: the means, the kit, the climb switch, the recall target, the floor, the loop's
streak, the loadout).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import deep_admission
from support import deep_admission_table as table

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import deep_admission_lint  # noqa: E402

FIXTURES = Path(__file__).with_name("fixtures")
RECORDED = FIXTURES / "deep-admission-1123"


def _verdict(cell, route, *, means=None, climbing=None):
    dungeon, depth, cell_means, cell_climbing = cell
    return deep_admission.verdict(dungeon, depth, route,
                                  cell_means if means is None else means,
                                  cell_climbing if climbing is None else climbing)


# The gates whose answer is ``verdict`` on the cell's own readings (the others add a context of
# their own: the trap door's landing guard on a recall or a fallback landing, the fall from the
# floor stood on, the standing hold that only the Castle and the Mountain have).
PROJECTIONS = {
    "policy_constants.destruction_dive_permitted": lambda c: _verdict(c, "intent").admitted,
    "policy_constants.permitted_dive_depth": lambda c: _verdict(c, "intent").admitted,
    "policy_observation._missing_required_abilities": lambda c: _verdict(c, "intent").admitted,
    "policy_supply._intended_dive_depth": lambda c: _verdict(c, "intent").admitted,
    "destruction_means.departure_carried": lambda c: _verdict(c, "recall").admitted,
    "deep_climb.departure_gaps": lambda c: _verdict(c, "recall").admitted,
    "policy._destination_depth_allowed": lambda c: _verdict(c, "recall").admitted,
    "policy._deep_stair_refused": lambda c: _verdict(c, "stairs").admitted,
    "deep_fall_guard.sanctioned": lambda c: _verdict(c, "trapdoor", means=False).admitted,
    "deep_climb.observe": lambda c: _verdict(c, "trapdoor").admitted,
    "destruction_use.means_spent": lambda c: _verdict(c, "stand").admitted,
    "deep_climb._standing_without_means@quest": lambda c: _verdict(c, "quest").admitted,
    "destruction_use.means_spent@quest": lambda c: _verdict(c, "quest").admitted,
    "deep_climb.observe@quest": lambda c: _verdict(c, "quest").admitted,
    # The inn reads the floor the intended dive's first descent reaches.
    "me_inn_refill.dive_reaches_deep":
        lambda c: _verdict((c[0], c[1] + 1, c[2], c[3]), "deep-descent").deep,
    "means_spent_loop.looping": lambda c: _verdict(c, "departure-loop").admitted,
    "equipment_optimizer.divable_depth": lambda c: _verdict(c, "loadout").admitted,
    "equipment_optimizer._meets_static_requirements":
        lambda c: _verdict(c, "loadout").admitted,
}


class DeepAdmissionTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, cls.town, cls.board = table.load_recorded(FIXTURES, cls.scratch.name)
        cls.answers = table.answers(cls.policy, cls.town, cls.board)

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_every_gate_keeps_its_answers_of_main(self):
        recorded = json.loads((RECORDED / "answers.json").read_text(encoding="utf-8"))
        self.assertEqual(set(recorded), set(table.GATES))
        for gate in table.GATES:
            with self.subTest(gate=gate):
                changed = sorted(cell for cell, answer in recorded[gate].items()
                                 if self.answers[gate][cell] != answer)
                self.assertEqual(changed, [])

    def test_the_gates_answer_the_verdict_of_their_route(self):
        for gate, projection in PROJECTIONS.items():
            with self.subTest(gate=gate):
                wrong = sorted(table.cell_name(cell) for cell in table.cells()
                               if projection(cell) != self.answers[gate][table.cell_name(cell)])
                self.assertEqual(wrong, [])

    def test_the_disagreements_are_the_owner_question_as_recorded(self):
        recorded = json.loads((RECORDED / "disagreements.json").read_text(encoding="utf-8"))
        self.assertEqual(table.disagreements(self.answers), recorded)

    def test_a_callable_reading_is_asked_only_where_the_answer_needs_it(self):
        asked = []
        reading = lambda name: lambda: asked.append(name) or False
        deep_admission.verdict(12, 49, "recall", reading("means"), reading("climb"))
        self.assertEqual(asked, [])
        deep_admission.verdict(12, 51, "recall", reading("means"), reading("climb"))
        self.assertEqual(asked, ["means"])
        asked.clear()
        deep_admission.verdict(12, 50, "recall", lambda: True, reading("climb"))
        self.assertEqual(asked, [])

    def test_the_lint_finds_no_unregistered_deep_depth_reader(self):
        self.assertEqual(deep_admission_lint.findings(), [])


if __name__ == "__main__":
    unittest.main()
