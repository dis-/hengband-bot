"""The 99F/100F preparation phase's check step ends on the decision its search runs (finale_prep
``check_done``), so that decision no longer holds the swap with no town work left.

Recorded: n1-c life-222 (Zombie Magic-Eater Lv50), the town arrival of 2026-11-26 07:46:26 of the
process the deploy restarted while the phase stood at its recall step (the phase lives in the
process: the restarted one entered it again from ``home``).  Row 17 read the Home (``~9``); on
row 18 (07:46:59) the phase entered ``check``, the departure's equipment verdict ran the worn
loadout's search (a 26-action swap from the worn finale set to the ordinary target) and the check
step's own search in the finale's rank in the same decision, but the step ended only on the next
board's ``observe``: the swap stayed held (``holds_swap``), ``equipment_departure_ready`` was the
only unmet departure value and the town stopped with ``town:blocked:unmet:equipment_departure_ready``
(owner-halted).  Replayed with the fix, the same decision ends the check step and composes the
swap's first key.

DECLARED CONSTRUCTED:
* the periodic character dump of row 5 is not taken (``_periodic_dump_requested`` cleared before
  every row): the replay cannot answer it with the game's new dump file, and its recorded
  response at row 6 would leave the calibration rejected; the calibration recorded at the arrival
  (the same process's constants) is adopted again where the replay rejected it;
* the searches' time caps (warrior_optimization ``CLOSURE_TIME_CAP_SECONDS``,
  ``FINALE_SEARCH_SECONDS``) are lowered so the test runs in seconds; the verdict does not depend
  on them: the test asserts the scenario's premise (a swap planned from the worn set) on the
  decision itself;
* the Scrolls of Recharging (angband_finale ``RECHARGING_CARRY``, owner 2026-11-26) carried as
  none: the recorded visit predates that carry, whose Alchemist errand would change the recorded
  route before the check step (row 14).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import angband_finale, equipment_target, finale_prep, warrior_optimization
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import SIDECAR_DIRECTORY
from replay_town_arrival import adopt_calibration
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-222-finale-check-1126"
DUMP_ROW = 5     # the recorded periodic character dump (DECLARED: not taken)
SCAN_ROW = 17    # the recorded Home read (~9)
STOP_ROW = 18    # the recorded town:blocked:unmet:equipment_departure_ready


class FinaleCheckStepRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        for name, seconds in (("CLOSURE_TIME_CAP_SECONDS", 6.0), ("FINALE_SEARCH_SECONDS", 2.0)):
            patcher = mock.patch.object(warrior_optimization, name, seconds)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(angband_finale, "RECHARGING_CARRY", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def deliver(policy, key):
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def replay_to_stop(self):
        """The visit decided through row 17 (the recorded keys delivered), then row 18's board."""
        scratch = Path(self.scratch.name)
        policy, _journal, steps = load(FIXTURE, scratch)
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        calibration = scratch / "town-arrival" / SIDECAR_DIRECTORY / "_character_calibration_path"
        for recorded, supply in steps[:STOP_ROW]:
            board = supply()
            policy._periodic_dump_requested = False
            if policy._character_calibration is None:
                adopt_calibration(policy, calibration, scratch / "runtime")
                policy._calibration_rejection = None
                policy._calibration_unavailable_reason = None
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            if recorded["row"] != DUMP_ROW:
                self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                                 recorded["row"])
            self.deliver(policy, recorded["key"])
        self.assertEqual(steps[STOP_ROW][0]["reason"], "town:blocked:unmet:equipment_departure_ready")
        policy._periodic_dump_requested = False
        return policy, steps[STOP_ROW][1]()

    def test_check_step_ends_on_its_search_and_the_swap_starts(self):
        policy, board = self.replay_to_stop()
        self.assertEqual(finale_prep.phase(policy).step, finale_prep.IDLE)
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        reason = policy.last_reason
        held = finale_prep.phase(policy)
        # The restarted process entered the phase again on this board: home (current), check.
        steps = [step for _sequence, step, _note in held.log]
        self.assertEqual(steps[:2], [finale_prep.HOME, finale_prep.CHECK])
        # The premise: the worn loadout's target is not the worn set (the swap the check held).
        target = equipment_target.loadout_target(policy)
        self.assertIsNotNone(target.result.best)
        self.assertNotEqual(target.result.best.loadout.item_ids, target.current.item_ids)
        # The check step ended in this decision: no swap is held and the town is not stopped.
        self.assertNotEqual(held.step, finale_prep.CHECK)
        self.assertFalse(finale_prep.holds_swap(policy))
        self.assertFalse(reason.startswith("town:blocked"), (key, reason))
        self.assertIsNotNone(policy._equipment_transaction_session)
        self.assertTrue(reason.startswith("equipment-transaction:"), (key, reason))


if __name__ == "__main__":
    unittest.main()
