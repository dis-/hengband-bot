"""The town search's speed-row band does not turn on the gear it chooses (n1-c life-224).

n1-c life-224 (Zombie Magic-Eater CL44, build bot-9c671e415) stopped 2026-11-28 15:24:26 under
``town:blocked:equipment-slot-flipflop:main_hand``.  Its worn kit gave +16 (★フーリン王のビークド・アックス
(2d6) (+10,+12) [+2] (+3), 輝きの殺戮の指輪, スピードの指輪 (+10), スピードの軟革ブーツ (+2)); the 91F row asks
+25 (policy_constants SPEED_GATE_DEPTH), so the speed ceiling was 90 and the search's speed-row band
(depth_gap_gear ``gate_floor``) 91.  All three wears were the equipment transaction's, on three
searches of one visit:

* row 10 (gate 91): the 91F band adopted under the half-blows rule takes ★ハーゲンのスピア (1d6)
  (+11,+13) (+3加速) and スピードの指輪 (+6) for the 殺戮の指輪: +25, speed 135;
* row 55 (worn +25, the row met, gate None): the 90F band takes the axe and 『炎の鉄ゲタ』 (-1) for
  their blows: +19;
* row 76 (worn +19, gate 91 again, re-decided on ``destination-band-floor``): the spear and the
  boots again; row 90's board shows main_hand axe, spear, axe, spear and the guard stopped.

The fix: the gate is the shallowest row the worn kit does not meet, and when the worn kit meets
every row, the deepest row it meets only through its worn speed pieces (``gate_floor``): 91 on
every board of the visit.  And the guard no longer stops: the second round trip closes the visit's
equipment transaction and keeps the worn kit (equipment_visit_journal ``settle``).

Recorded (tests/extract_n1c_224_mainhand_flipflop_1128_fixture.py): the town-arrival checkpoint and
its 91 journal rows.  Every board is decided through ``choose_key`` and the recorded key is
acknowledged as posted (the boards are the recorded ones).  Rows 0-54 replay the record.  From row
56 the replay differs from the record with or without the fix: it asks the Home knowledge
('~9\\x1b', home-errand:request-knowledge) where the live process was in its transaction, and the
recorded boards do not answer it; ``town:blocked:owner-retired`` there is the owner budget the live
process forgave (cli ``_handle_owner_retirement`` under ``--owner-retired-log-only``).  The record
ends at the stop, so the departure itself is not on these boards.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import angband_cap, depth_gap_gear, equipment_target
from hengbot import equipment_visit_journal as journal
from hengbot.policy import staged_prompt_chain_matches
from hengbot.speed_valuation import permanent_player_speed
from hengbot.warrior_optimization import prepare_warrior_optimization
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-224-mainhand-flipflop-1128"
SPEAR_WORN_ROW = 29     # the spear and the +6 ring worn: speed 135, every row met
SEARCH_ROW = 45         # a decision that read the search's inputs
SEARCH_DECISION = 73318
SWAP_BACK_ROW = 55      # the record's transaction toward the axe
REPLAYED_ROWS = 55      # rows 0-54 replay the record
STOP_ROW = 90
GATE = 91
SPEAR = "★ハーゲンのスピア"
AXE = "★フーリン王のビークド・アックス"
FORGIVEN = "town:blocked:owner-retired"
RECORDED_STOP = "town:blocked:equipment-slot-flipflop:main_hand"


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def _old_gate_floor(policy, snapshot):
    """The gate before the fix (the worn kit's ceiling + 1, None when the worn kit meets it)."""
    ceiling = angband_cap.speed_ceiling(policy, snapshot)
    return None if ceiling is None else ceiling + 1


def replay(scratch: Path):
    policy, _journal, steps = load(FIXTURE, scratch)
    rows = []
    stash = None
    for recorded, supply in steps:
        board = supply()
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        target = equipment_target.loadout_target(policy)
        best = getattr(getattr(target, "result", None), "best", None)
        main = None if best is None else best.loadout.item_at("main_hand")
        rows.append({"recorded": recorded, "key": key, "reason": policy.last_reason,
                     "gate": depth_gap_gear.gate_floor(policy, board),
                     "speed": permanent_player_speed(board),
                     "target_main": None if main is None else main.item.name})
        if recorded["row"] == SEARCH_ROW:
            # The search's inputs this decision read (policy_equipment ``_equipment_shelf_search``).
            stash = policy._equipment_shelf_search
        post(policy, recorded["key"])
    return policy, rows, stash


def search(policy, stash, **override):
    """The visit's search on the stashed board and inputs (read-only: no report)."""
    _sequence, board, _signature, catalog, inputs, finale, cap_lifted = stash
    result = prepare_warrior_optimization(board, catalog, policy._monrace_knowledge,
                                          **{**inputs, **override}, finale=finale,
                                          cap_lifted=cap_lifted).result
    slots = {slot: owned.item.name for slot, owned in result.best.loadout.slots}
    return result, slots


class MainHandFlipflop224RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stderr(io.StringIO()):
            cls.policy, cls.rows, cls.stash = replay(Path(cls.scratch.name))

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_rows_before_the_swap_back_replay(self):
        for row in self.rows[:REPLAYED_ROWS]:
            recorded = row["recorded"]
            self.assertEqual((row["key"], row["reason"]), (recorded["key"], recorded["reason"]),
                             recorded["row"])

    def test_the_gate_does_not_turn_on_the_worn_spear(self):
        self.assertEqual(self.rows[0]["speed"], 126)
        self.assertEqual(self.rows[SPEAR_WORN_ROW]["speed"], 135)
        self.assertEqual({row["gate"] for row in self.rows}, {GATE})

    def test_the_two_answers_of_the_search_on_the_recorded_board(self):
        """The visit's inputs (gate 91) keep the spear; the gate the worn +25 kit read before
        the fix (None) takes the axe for its blows (band 91 refused on the half-blows rule)."""
        self.assertEqual(self.stash[0], SEARCH_DECISION)
        self.assertEqual(self.stash[4]["gate_floor"], GATE)
        result, slots = search(self.policy, self.stash)
        self.assertEqual(result.chosen_depth, GATE)
        self.assertTrue(slots["main_hand"].startswith(SPEAR))
        self.assertTrue(slots["feet"].startswith("スピードの軟革ブーツ"))
        old, old_slots = search(self.policy, self.stash, gate_floor=None)
        self.assertEqual(old.chosen_depth, 90)
        self.assertTrue(old_slots["main_hand"].startswith(AXE))
        refused = next(band for band in old.band_decisions if band.band == GATE)
        self.assertEqual(refused.refusal_reason, "melee-ratio")
        self.assertGreater(old.best.metrics.expected_dps, result.best.metrics.expected_dps)

    def test_the_visit_never_goes_back_to_the_axe(self):
        self.assertFalse(self.rows[SWAP_BACK_ROW]["reason"].startswith("equipment-transaction:"))
        for row in self.rows[SPEAR_WORN_ROW:]:
            if row["target_main"] is not None:
                self.assertTrue(row["target_main"].startswith(SPEAR), row["recorded"]["row"])
        targets = {row["target_main"] for row in self.rows[SPEAR_WORN_ROW:]} - {None}
        self.assertTrue(targets)

    def test_nothing_stops_and_the_recorded_round_trip_settles(self):
        for row in self.rows:
            self.assertIsNotNone(row["key"], row["recorded"]["row"])
            if row["reason"] != FORGIVEN:
                self.assertFalse(str(row["reason"]).startswith("town:blocked"),
                                 (row["recorded"]["row"], row["reason"]))
        self.assertEqual(self.rows[STOP_ROW]["recorded"]["reason"],
                         RECORDED_STOP)
        closure = self.policy._equipment_transaction_visit_closure
        self.assertEqual((closure["reason"], closure["slot"]), (journal.SETTLED_CLOSURE, "main_hand"))
        kinds = [row["kind"] for row in self.policy._equipment_visit_journal["rows"]]
        self.assertEqual(kinds.count(journal.FLIPFLOP_SETTLED_EVENT), 1)


class OldGateSettlesTest(unittest.TestCase):
    """The gate before the fix on the same boards: it reads None under the worn +25 kit, and the
    recorded round trip (row 90's board) settles instead of stopping."""

    def test_the_old_gate_swaps_back_and_the_guard_settles(self):
        with TemporaryDirectory() as raw, contextlib.redirect_stderr(io.StringIO()), \
                mock.patch.object(depth_gap_gear, "gate_floor", _old_gate_floor):
            policy, rows, stash = replay(Path(raw))
        self.assertIsNone(rows[SPEAR_WORN_ROW]["gate"])
        self.assertIsNone(stash[4].get("gate_floor"))
        self.assertIsNotNone(rows[STOP_ROW]["key"])
        self.assertFalse(journal.is_stop(rows[STOP_ROW]["reason"]))
        self.assertFalse(str(rows[STOP_ROW]["reason"]).startswith("town:blocked:equipment-slot-flipflop"))
        self.assertEqual(policy._equipment_transaction_visit_closure["reason"],
                         journal.SETTLED_CLOSURE)


if __name__ == "__main__":
    unittest.main()
