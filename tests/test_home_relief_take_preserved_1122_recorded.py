"""The full-Home relief's taken ware is not deposited again by the equipment transaction.

n1-a life-532 (Lv20 warrior, a new character) stopped 2026-11-22 14:09:48 as
town:blocked:stage-deadline:equipment.  The Home junk sweep took the plain ローブ [2,+5] out of
the full Home to destroy it (``home-errand:atomic-withdraw:full-home-discard``, row 15).  On the
board after the take the equipment optimizer saw a pack piece outside the visit's target and
planned its deposit (owner 2026-11-04 「使わない装備を持ったまま出発しない・自宅に仕舞う」); the live
session owned the robe, so the relief's destroy found it reserved and skipped it
(``home:full-skip:identified-item-protected``, row 16), and the transaction put it back on the
shelf (``equipment-transaction:deposit``).  The relief took it out again: nine trips until the
stage deadline.  The broadsword the sweep destroyed just before (rows 12-13) escaped only
because the transaction preserved it as an inferior weapon.

Owner 2026-11-13 (pingpong root fix): a round trip is fixed by registering the owner in the
mechanism.  The relief's ware is registered in the transaction's pack preservation
(policy_home ``_home_full_relief_holds_carried``, read by policy_equipment
``_prepare_equipment_optimization`` beside the identification flow and the inferior weapon), so
the sweep destroys the robe and the visit goes on.

Recorded: n1-a life-532's town-arrival checkpoint (tests/fixtures/n1a-532-robe-round-trip-1122,
rows 0-19), decided through the public ``choose_key`` with the recorded keys posted; rows 0-15
match the record, row 16 is the fix.

DECLARED CONSTRUCTED:

* the character calibration adopted after row 1: the dump file the live bot read at row 1 (the
  character had just reached Lv20, STR 18/47) is not in the checkpoint, so the same character's
  Lv20 calibration the restarted bot recorded at 14:17 is used, with the worn cursed 鎖かたびら in
  its pinned set as on these boards (fixture ``character-calibration-lv20.json``);
* the boards of rows 17-19 without the robe, as after its destroy (their responses are the
  recorded ones: the Home census of row 18 is the Home without the robe).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import equipment_target
from hengbot.policy import staged_prompt_chain_matches
from replay_town_arrival import adopt_calibration
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-532-robe-round-trip-1122"
ROBE = "ローブ [2,+5]"
TAKE_ROW = 15
SKIP_ROW = 16


def _post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def _decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        return policy.choose_key(board)


def _robes(board):
    return [item for item in board.inventory if item.name.startswith(ROBE)]


def _without_robe(board):
    return replace(board, inventory=tuple(item for item in board.inventory
                                          if not item.name.startswith(ROBE)))


class HomeReliefTakePreservedRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        scratch = Path(cls.scratch.name)
        with contextlib.redirect_stdout(io.StringIO()):
            policy, cls.journal, steps = load(FIXTURE, scratch)
        cls.replayed = []
        for recorded, supply in steps[:SKIP_ROW]:
            board = supply()
            if recorded["row"] == 1:
                # DECLARED CONSTRUCTED (module docstring): the Lv20 calibration of row 1's dump.
                adopt_calibration(policy, FIXTURE / "character-calibration-lv20.json", scratch)
                policy._calibration_rejection = None
                policy._calibration_unavailable_reason = None
                equipment_target.invalidate_loadout_search(policy)
            key = _decide(policy, board)
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            _post(policy, recorded["key"])
        cls.policy, cls.steps = policy, steps
        cls.board = steps[SKIP_ROW][1]()
        [cls.robe] = _robes(cls.board)
        cls.held_before = policy._home_full_relief_holds_carried(cls.board, cls.robe)
        cls.others_held = [item.name for item in cls.board.inventory
                           if item is not cls.robe
                           and policy._home_full_relief_holds_carried(cls.board, item)]
        cls.key = _decide(policy, cls.board)
        cls.reason = policy.last_reason
        cls.telemetry = dict(policy._equipment_optimization_telemetry)
        cls.session_after_take = policy._equipment_transaction_session
        _post(policy, cls.key)

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_rows_before_the_skip_replay_as_recorded(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        self.assertEqual(self.journal[TAKE_ROW]["key"], "5pj\x1b")
        self.assertEqual(self.journal[TAKE_ROW]["reason"],
                         "home-errand:atomic-withdraw:full-home-discard")
        # The record: the relief skipped its own take, then the transaction shelved it again.
        self.assertEqual((self.journal[SKIP_ROW]["key"], self.journal[SKIP_ROW]["reason"]),
                         ("9", "town:entrance-step-off:home:full-skip:identified-item-protected"))
        self.assertEqual(self.journal[18]["reason"], "equipment-transaction:approach-home")
        self.assertEqual(self.journal[19]["reason"], "equipment-transaction:deposit")

    def test_the_relief_holds_only_its_taken_robe(self):
        self.assertEqual((self.robe.slot, self.robe.count), ("m", 1))
        self.assertTrue(self.held_before)
        self.assertEqual(self.others_held, [])

    def test_the_sweep_destroys_the_robe_and_no_deposit_is_planned(self):
        # Before: ('9', 'town:entrance-step-off:home:full-skip:identified-item-protected'),
        # the transaction's session owning the robe for its deposit.
        self.assertEqual((self.key, self.reason), ("01km", "home:junk-sweep:plain-gear"))
        self.assertIsNone(self.session_after_take)
        [preserved] = self.telemetry["preserve_pack_items"]["items"]
        self.assertEqual((preserved["name"], preserved["reasons"]),
                         (ROBE, ["home-full-relief-take"]))

    def test_after_the_destroy_the_visit_goes_on_without_a_deposit_trip(self):
        policy = self.policy
        decided = []
        for recorded, supply in self.steps[SKIP_ROW + 1:]:
            # DECLARED CONSTRUCTED (module docstring): the boards without the destroyed robe.
            board = _without_robe(supply())
            key = _decide(policy, board)
            decided.append((recorded["row"], key, policy.last_reason,
                            policy._equipment_transaction_session))
            _post(policy, key)
        for row, key, reason, session in decided:
            self.assertIsNone(session, row)
            self.assertFalse(reason.startswith("equipment-transaction"), (row, reason))
            self.assertNotIn("full-home-discard", reason, row)
        # Row 19 is the Home page after the destroy: the census is read again, nothing is put back.
        self.assertEqual(decided[-1][:3], (19, "~9\x1b", "home:request-knowledge-scan"))


if __name__ == "__main__":
    unittest.main()
