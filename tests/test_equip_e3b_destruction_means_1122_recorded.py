"""Equipment review E3b: a *Destruction* means gained mid-visit decides the visit's target again.

Owner 2026-11-22, on the E3 report's question 4 (verbatim choice): 「決め直す」 -- when the 50F+
*Destruction* means becomes satisfied during a town visit (a staff bought or withdrawn from the
Home, or any change that newly satisfies destruction_means), the target loadout and its depth band
are decided again in that visit (equipment_target ``destruction-means-gained``).  E3 held the
visit's first target there.

Recorded: n1-b life-413's town visit of 2026-11-22 00:17:35 (tests/fixtures/n1b-413-launcher-flip-1122,
its town-arrival checkpoint), the visit's first search on its first board.

DECLARED CONSTRUCTED: the *Destruction* staff the game sent at 00:13:50 put in the pack (as
tests/test_n1b_413_launcher_flip_1122_recorded) with no swap under way (the visit's first search
started one; at 00:13:49 the staff was bought before the swap).  For the means gained, the town's
absorption read (destruction_means ``Means.town_absorbs``) answers False: the staff is a staff the
town does not absorb (a warrior's, say), so the search's staff gate opens.  Without that, the staff
the Magic-Eater's town absorbs is no means and nothing is decided again (the life-413 launcher flip
stays fixed).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import equipment_target
from hengbot.equipment_optimizer import equipment_move_identity
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-launcher-flip-1122"


def _prepare(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        return policy._prepare_equipment_optimization(policy._with_cached_skill_exp(board))


def _searches(policy):
    return [row for row in policy._equipment_visit_journal["rows"] if row["kind"] == "search"]


def _target(policy):
    loadout = equipment_target.loadout_target_result(policy).best.loadout
    return tuple((slot, equipment_move_identity(owned.item)) for slot, owned in loadout.slots)


class DestructionMeansGainedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, journal, steps = load(FIXTURE, Path(scratch.name))
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)
        board = steps[0][1]()
        with contextlib.redirect_stdout(io.StringIO()):
            self.policy.choose_key(board)
        _prepare(self.policy, board)
        self.assertEqual(len(_searches(self.policy)), 1)
        self.decided = _target(self.policy)
        self.band = equipment_target.loadout_target_result(self.policy).chosen_decision.band
        raw = json.loads(journal[0]["line"] if journal[0]["line"] is not None
                         else journal[0]["inputs"][-1])
        staff = json.loads(lzma.decompress((FIXTURE / "staff.json.xz").read_bytes()))
        inventory = raw["inventory"]
        for item in inventory[7:]:
            item["slot"] = chr(ord(item["slot"]) + 1)
        raw["inventory"] = [*inventory[:7], {**staff, "slot": "h"}, *inventory[7:]]
        self.bought = parse_snapshot(raw, self.policy._monrace_knowledge)
        self.policy._set_equipment_transaction_session(None)  # DECLARED: no swap under way

    def means(self):
        return self.policy._optimizer_destruction_means(
            self.bought, self.policy._equipment_catalog.items,
            self.policy._validated_character_calibration(self.bought))

    def test_a_staff_the_search_reads_as_a_means_decides_again_once(self):
        with mock.patch("hengbot.destruction_means.Means.town_absorbs", return_value=False):
            self.assertIsNotNone(self.means()[1])        # the staff gate: a 50F+ means
            _prepare(self.policy, self.bought)
            # E3 held the visit's first target here: one search.
            searches = _searches(self.policy)
            self.assertEqual(len(searches), 2)
            self.assertEqual(searches[-1].get("events"), ["destruction-means-gained"])
            result = equipment_target.loadout_target_result(self.policy)
            self.assertGreater(result.chosen_decision.band, self.band)   # the deep band
            decided_again = _target(self.policy)
            # Once: the same board again with the memo forced (the worn set applied, say)
            # decides nothing more.
            equipment_target.invalidate_loadout_search(self.policy)
            _prepare(self.policy, self.bought)
            self.assertEqual(len(_searches(self.policy)), 2)
            self.assertEqual(_target(self.policy), decided_again)

    def test_a_staff_the_town_absorbs_decides_nothing(self):
        # The Magic-Eater's staff to absorb: no means (the life-413 launcher flip stays fixed).
        self.assertEqual(self.means(), (False, None))
        _prepare(self.policy, self.bought)
        self.assertEqual(len(_searches(self.policy)), 1)
        self.assertEqual(_target(self.policy), self.decided)


if __name__ == "__main__":
    unittest.main()
