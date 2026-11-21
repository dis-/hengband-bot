"""Equipment review E3: the town visit decides its loadout target once (owner Q1 and Q7, 2026-11-22).

Owner 2026-11-22, Q1 (verbatim): 「基本的にはそれで良い。99F100Fもそれでバグらず行けるか確認」 to "decide
the target loadout once at the start of each town visit and do not change it during the visit;
decide again only on named events -- buying, picking up, withdrawing from Home an item (the owned
set gained a candidate)".  Q7: 「先に外してから探索する」 (a banned piece worn while the search cannot
run comes off first; one that cannot come off is a named stop).  Q2 (E0) 「往復が起きたら停止して直す」
stays: the round-trip stop is untouched.

Recorded visits, replayed through the public ``choose_key`` (recorded keys posted):

* n1-c life-219's visit of 2026-11-22 01:34 (tests/fixtures/n1c-219-flipflop-1122), the shovel case;
* n1-c life-217's 99F/100F preparation visit of 2026-11-21 05:55 (tests/fixtures/n1c-finale-prep-1121):
  a ★-less 守りのミラー・シールド bought at row 21, the finale phase's check step at rows 37/38, a
  Gold Dragon Scale Mail withdrawn from the Home by the supplies step;
* n1-b life-411's visit of 2026-11-21 12:41 (tests/fixtures/n1b-411-robe-town-1121), the twilight
  robe worn and the character sheet refusing every calibration (the live process's state).

DECLARED CONSTRUCTED:
* n1c-219: on the board after the swap wore ノートゥング (row 13), the two writes the transaction's
  completion makes (policy ``_set_equipment_transaction_session(None)``, a forced re-search,
  policy.py's session-complete branch) -- the swap's Home deposit failed in the record, so its
  completion never ran;
* n1b-411: the robe moved from the body slot to the pack (as after its take-off), and the robe
  made cursed (``is_cursed``) for the named stop.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import equipment_target
from hengbot.equipment_optimizer import equipment_move_identity
from hengbot.equipment_rules import TR_NO_AC
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")


def _decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        return policy.choose_key(board)


def _prepare(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        return policy._prepare_equipment_optimization(policy._with_cached_skill_exp(board))


def _target(policy):
    best = getattr(equipment_target.loadout_target_result(policy), "best", None)
    loadout = getattr(best, "loadout", None)
    return None if loadout is None else tuple(
        (slot, equipment_move_identity(owned.item)) for slot, owned in loadout.slots)


def _rows(policy, kind):
    return [row for row in policy._equipment_visit_journal["rows"] if row["kind"] == kind]


def _raw(entry):
    return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()

    def tearDown(self):
        self.scratch.cleanup()

    def load(self, name, **kwargs):
        policy, journal, steps = load(FIXTURES / name, Path(self.scratch.name) / name, **kwargs)
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        return policy, journal, steps

    def replay(self, policy, steps):
        for recorded, supply in steps:
            board = supply()
            _decide(policy, board)
            if recorded["key"]:
                policy.confirm_key_posted(recorded["key"])
        return board


class VisitTargetHeldTest(_Fixture):
    """(a) The worn set changing by the swap itself decides nothing again.  (The bought
    *Destruction* staff: tests/test_equip_e3b_destruction_means_1122_recorded, owner 2026-11-22
    「決め直す」.)"""

    def test_n1c_219_the_completed_swap_keeps_the_visits_target(self):
        policy, _journal, steps = self.load("n1c-219-flipflop-1122")
        self.replay(policy, steps[:13])
        self.assertEqual(len(_rows(policy, "search")), 1)
        decided = _target(policy)
        main = dict(decided)["main_hand"]
        board = steps[13][1]()
        worn = {item.slot: item for item in board.equipment}
        self.assertIn("ノートゥング", worn["main_hand"].name)   # the swap wore the target weapon
        policy._set_equipment_transaction_session(None)       # DECLARED: the completion's writes
        equipment_target.invalidate_loadout_search(policy)
        _prepare(policy, board)
        # Before E3 the worn set's change searched again (a second ``search`` row).
        self.assertEqual(len(_rows(policy, "search")), 1)
        self.assertEqual(_target(policy), decided)
        self.assertEqual(dict(_target(policy))["main_hand"], main)
        self.assertEqual(equipment_move_identity(worn["main_hand"]), main)
        self.assertEqual([row.get("events") for row in _rows(policy, "search")], [["visit-start"]])
        self.assertEqual(_rows(policy, "held")[-1]["changed"], ["no-previous"])


class VisitTargetEventsTest(_Fixture):
    """(b) A bought piece decides once; (c) the finale's phase decides its own searches."""

    def test_n1c_finale_visit_decides_on_the_purchase_and_the_phase_only(self):
        policy, _journal, steps = self.load("n1c-finale-prep-1121")
        self.replay(policy, steps)
        searches = _rows(policy, "search")
        # Before E3: seven searches (two Home withdrawals, a forced reset after a deposit).
        self.assertEqual(len(searches), 4, [row["changed"] for row in searches])
        self.assertEqual([row.get("events") for row in searches],
                         [["visit-start"], ["candidate-gained"], ["finale-phase"],
                          ["finale-phase"]])
        # The purchase (row 21): the Mirror Shield, a piece the visit did not own.
        held = equipment_target.visit_target(policy, policy._town_visit_epoch)
        owned = {key[0] for key, carried, home in held.candidates}
        shield = next(owned_item for owned_item in policy._equipment_catalog.items
                      if "ミラー・シールド" in owned_item.item.name)
        self.assertIn(equipment_move_identity(shield.item), owned)
        # The Home withdrawals of a piece the visit already owned decided nothing (before E3
        # each searched again: owned-catalog).
        held_rows = _rows(policy, "held")
        self.assertTrue(any("owned-catalog" in row["changed"] for row in held_rows), held_rows)
        self.assertFalse(_rows(policy, "equipment-slot-flipflop:body"))


class BannedGearTest(_Fixture):
    """(d) Q7: the robe comes off before the search that cannot run; stuck -> named stop."""

    def load_robe(self):
        policy, journal, steps = self.load("n1b-411-robe-town-1121",
                                           adopt_recorded_calibration=False)
        self.assertIsNone(policy._character_calibration)
        self.assertEqual(policy._calibration_unavailable_reason, "unsupported-ac-interaction")
        return policy, journal, steps

    def test_the_robe_is_taken_off_first(self):
        policy, _journal, steps = self.load_robe()
        robe = None
        for recorded, supply in steps[:12]:
            board = supply()
            key = _decide(policy, board)
            robe = next((item for item in board.equipment if TR_NO_AC in item.known_flags), None)
            if policy.last_reason == "equipment-transaction:takeoff":
                break
            if recorded["key"]:
                policy.confirm_key_posted(recorded["key"])
        # Before E3 no take-off was composed while no calibration let the search run.
        self.assertEqual(policy.last_reason, "equipment-transaction:takeoff")
        self.assertIsNotNone(robe)
        self.assertTrue(key.startswith("t"), key)
        self.assertEqual(robe.slot, "body")
        self.assertIsNone(policy._character_calibration)
        actions = [(action.kind, action.target_slot)
                   for action in policy._equipment_transaction_session.plan.actions]
        self.assertEqual(actions, [("takeoff", "body")])

    def test_after_the_takeoff_the_search_runs_and_a_stuck_robe_stops(self):
        policy, journal, steps = self.load_robe()
        raw = _raw(journal[0])
        robe = next(item for item in raw["equipment"] if 141 in item.get("known_flags", ()))
        # DECLARED: the robe in the pack, as after its take-off.
        off = json.loads(json.dumps(raw))
        off["equipment"] = [item for item in off["equipment"]
                            if 141 not in item.get("known_flags", ())]
        letters = sorted(item["slot"] for item in off["inventory"])
        off["inventory"].append({**robe, "slot": chr(ord(letters[-1]) + 1)})
        board = parse_snapshot(off, policy._monrace_knowledge)
        _decide(policy, board)
        _prepare(policy, board)
        # No banned piece is worn: the search's own path (the calibration it waits for).
        self.assertEqual(policy._equipment_optimization_telemetry["result_source"],
                         "calibration-required-return")
        # DECLARED: the robe cursed -- it cannot come off.
        cursed = json.loads(json.dumps(raw))
        for item in cursed["equipment"]:
            if 141 in item.get("known_flags", ()):
                item["is_cursed"] = True
        board = parse_snapshot(cursed, policy._monrace_knowledge)
        key = _decide(policy, board)
        self.assertIsNone(key)
        self.assertEqual(policy.last_reason, "town:blocked:banned-gear-stuck:body")


if __name__ == "__main__":
    unittest.main()
