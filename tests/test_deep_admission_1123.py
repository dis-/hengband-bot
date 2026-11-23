"""The 50F+ admission gates answer the owner's one rule through deep_admission.verdict (K2).

Whole-bot maintainability review 2026-11-23 K2: eleven gates of 「*破壊* なしで50F以降にいない」 asked
it with three predicates of their own.  tests/extract_deep_admission_1123_fixture.py asks every
gate over one table (dungeon x depth 44-52 x the means x the climb, tests/support
/deep_admission_table) and writes the answers (tests/fixtures/deep-admission-1123/answers.json);
the gates routed through ``verdict`` gave main 5fe531c0a's answers, 37 cells disagreeing.

Owner 2026-11-23 (b)-2 「入らない・着いたら登る側にそろえる」: without the means no route enters 50F+,
a 50F+ floor stood on anyway is climbed from, only the climb's 50F landing is arrived on.
Every gate now gives that rule's answer (deep_admission_table.owner_answer, the rule written out
per question); answers.json changed from main 57a80bc0a in 30 answers, all of them toward it:
the stairs' two gates one answer (an exposed 48F/49F refused by both, 50F+ without the means
refused by both), the trap door's landing admitted with the means, Angband's 50F+ floor stood on
without the means refused.  disagreements.json keeps where the routes answer different
questions of the rule (the climb's exception taken by the landing and the floor stood on, never
by the intent or a stair; the quest floor; the means-spent loop's net; the means-only parts of
the recall beside its landing gate).

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
# their own: the trap door's landing guard on a recall or a fallback landing and the stairs'
# ``exposed`` floor, the fall from the floor stood on).
PROJECTIONS = {
    "policy_constants.destruction_dive_permitted": lambda c: _verdict(c, "intent").admitted,
    "policy_constants.permitted_dive_depth": lambda c: _verdict(c, "intent").admitted,
    "policy_observation._missing_required_abilities": lambda c: _verdict(c, "intent").admitted,
    "policy_supply._intended_dive_depth": lambda c: _verdict(c, "intent").admitted,
    "destruction_means.departure_carried": lambda c: _verdict(c, "recall").admitted,
    "deep_climb.departure_gaps": lambda c: _verdict(c, "recall").admitted,
    "policy._destination_depth_allowed": lambda c: _verdict(c, "recall").admitted,
    "deep_fall_guard.sanctioned": lambda c: _verdict(c, "trapdoor").admitted,
    "deep_climb.observe": lambda c: _verdict(c, "trapdoor").admitted,
    "destruction_use.means_spent": lambda c: _verdict(c, "stand").admitted,
    "deep_climb._standing_without_means": lambda c: _verdict(c, "stand").admitted,
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

    def test_every_gate_keeps_its_recorded_answers(self):
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

    def test_every_gate_gives_the_owner_rule_answer(self):
        last = table.last_floors(self.policy)
        for gate in table.GATES:
            with self.subTest(gate=gate):
                wrong = sorted(table.cell_name(cell) for cell in table.cells()
                               if self.answers[gate][table.cell_name(cell)]
                               != table.owner_answer(last, gate, cell))
                self.assertEqual(wrong, [])

    def test_the_owner_rule_on_the_five_shapes(self):
        """The five shapes of main's 37 disagreeing cells, as the owner's rule answers them."""
        answers = lambda cell: {gate: self.answers[gate][cell] for gate in table.GATES}
        # 1. The climb's 50F landing: arrived on (recall, fallback, trap door) and stood on;
        #    never a dive's intent nor a stair.
        climb_50 = answers("castle:50:no-means:climbing")
        self.assertTrue(climb_50["policy._recall_destination_safe"])
        self.assertTrue(climb_50["deep_climb.observe"])
        self.assertTrue(climb_50["destruction_use.means_spent"])
        self.assertFalse(climb_50["policy._deep_stair_refused"])
        self.assertFalse(climb_50["deep_fall_guard.descent_refused"])
        self.assertFalse(climb_50["policy_constants.destruction_dive_permitted"])
        # 2. The climb's 51F/52F: no route arrives there, the floor stood on is climbed from.
        for cell in ("castle:51:no-means:climbing", "mountain:52:no-means:climbing"):
            climb_deep = answers(cell)
            self.assertFalse(climb_deep["deep_climb.observe"])
            self.assertFalse(climb_deep["deep_fall_guard.sanctioned"])
            self.assertFalse(climb_deep["policy._recall_destination_safe"])
            self.assertFalse(climb_deep["deep_fall_guard.descent_refused"])
            self.assertTrue(climb_deep["deep_climb._standing_without_means"])
            self.assertTrue(climb_deep["destruction_use.means_spent"])
        # 3. An exposed 48F/49F (its trap door onto 50F+, no detection): no landing, no stair.
        for cell in ("angband:49:no-means:no-climb", "castle:48:no-means:no-climb",
                     "mountain:49:no-means:no-climb"):
            exposed = answers(cell)
            for gate in ("policy._deep_stair_refused", "deep_fall_guard.descent_refused",
                         "policy._recall_destination_safe",
                         "policy_helpers._fallback_landing_allowed"):
                self.assertFalse(exposed[gate], (cell, gate))
        # 4. Angband 50F+ without the means: no climb, refused by every route; the floor stood
        #    on is left (the means-spent return; an arrival from above, the named stop).
        for depth in (50, 51, 52):
            angband = answers(f"angband:{depth}:no-means:no-climb")
            self.assertEqual(sorted(gate for gate, admitted in angband.items() if admitted),
                             ["deep_climb._standing_without_means@quest",
                              "deep_climb.observe@quest", "destruction_use.means_spent@quest",
                              "me_inn_refill.dive_reaches_deep"])
        # 5. With the means every route admits 50F+ but the means-spent loop's net.
        for cell in ("angband:51:means:no-climb", "castle:50:means:no-climb",
                     "mountain:52:means:climbing"):
            means = answers(cell)
            self.assertEqual(sorted(gate for gate, admitted in means.items() if not admitted),
                             ["means_spent_loop.looping"])

    def test_the_route_differences_are_as_recorded(self):
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
