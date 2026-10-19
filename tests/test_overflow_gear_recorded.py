"""Replay the C4-A overflow stop with a pack of spare gear (issue #87).

The fixture is state rows 59-76 of the soak capture
c4a-loops-20261016/20261019-202913-town-blocked-overflow-no-legal-disposal,
copied as-is (life-014, Level 26, town, gold 3,106): line 0 is the ~9 Home
knowledge answer (158 entries, Home not full), lines 1-17 the boards and store
pages of the last bot session, line 17 the stop board (turn 1712301, 20 pack
entries, three free slots).  Live, the Home visits were
``home:route-claim-unfulfilled``, the Alchemist and Black Market visits
``shop:observe-and-leave``, and decision 12 ``town:blocked:overflow-no-legal-
disposal``.

The character has a mutation (the recorded character row: ``mutations``
[12]), so every calibration was rejected ``unsupported-mutation`` and the
optimizer was skipped (decision rows: ``calibration-required-return``).

DECLARED CONSTRUCTED: the calibration rejection reason recorded in the
decision rows (``equipment_optimization.calibration.unavailable_reason``),
which the replay cannot derive because the character dump file is not part
of the capture; the posted ~9 request answered by line 0; the ~f skill-exp
cache.  In the controls, the trimmed pack and the valid-calibration state.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "overflow-gear-20261019.jsonl.gz"
SHA256 = "0d32bfa64ee684aa25e71bc4e9880b64e7f610b9b5495784115309d6f53e2522"
HOME_PAGE = 4  # line of the first Home store page of the session
STOP = "town:blocked:overflow-no-legal-disposal"
GEAR_SLOTS = tuple("jklmnopqr")


class OverflowGearRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = gzip.decompress(FIXTURE.read_bytes())
        assert hashlib.sha256(data).hexdigest() == SHA256
        cls.lines = data.decode("utf-8").splitlines()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def _policy(self, *, calibration_rejected=True):
        policy = _policy(self.directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        if calibration_rejected:
            # DECLARED CONSTRUCTED: the recorded rejection reason.
            policy._calibration_unavailable_reason = "unsupported-mutation"
        policy._home_knowledge_scan_inflight = True
        policy._home_knowledge_scan_epoch = None
        self._consume(policy, self.lines[0])
        return policy

    def _consume(self, policy, line):
        _decoded, snapshots = _consume_response_sequence(
            [line], policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl",
        )
        return snapshots

    def _drive(self, policy, last):
        decisions = []
        for line in self.lines[1:last + 1]:
            board = self._consume(policy, line)[-1]
            policy._skill_exp_cache = (
                0, 0, board.player.level, policy._town_visit_epoch
            )
            decisions.append((policy.choose_key(board), policy.last_reason))
        return decisions, board

    def test_recorded_home_visit_deposits_spare_rings(self):
        policy = self._policy()
        decisions, home = self._drive(policy, HOME_PAGE)
        self.assertIsNotNone(home.store)
        self.assertEqual(len(home.inventory), 20)
        self.assertTrue(policy._town_pack_space_shortage(home))
        self.assertEqual(
            decisions[-1], ("dkdj\x1b", "home:atomic-deposit")
        )
        deposited = {item.slot: item.name for item in home.inventory
                     if item.slot in ("j", "k")}
        self.assertEqual(deposited, {"j": "耐火の指輪", "k": "耐冷の指輪"})

    def test_recorded_session_no_longer_ends_in_the_stop(self):
        policy = self._policy()
        decisions, board = self._drive(policy, len(self.lines) - 1)
        self.assertEqual((board.turn, len(board.inventory)), (1712301, 20))
        self.assertNotIn(STOP, [reason for _key, reason in decisions])

    def test_control_reserved_and_kept_items_are_never_deposited(self):
        policy = self._policy()
        _decisions, home = self._drive(policy, HOME_PAGE)
        candidates = {item.slot for item in home.inventory
                      if policy._home_deposit_candidate(item, home)}
        # Plain spare gear only; the shovel is the only digging tool and
        # stays out of _find_home_deposit.
        self.assertEqual(candidates, set(GEAR_SLOTS) | {"s"})
        for item in home.inventory:
            if item.slot not in candidates:
                self.assertTrue(
                    policy._retention_reservation(home, item) > 0
                    or not item.is_equipment, item.name)
        self.assertFalse(policy._is_surplus_digging_tool(
            home, next(item for item in home.inventory if item.slot == "s")))

    def test_control_valid_calibration_keeps_the_target_gate(self):
        # Constructed: no calibration rejection, so a target loadout is still
        # expected and spare gear waits for it.
        policy = self._policy(calibration_rejected=False)
        _decisions, home = self._drive(policy, HOME_PAGE)
        self.assertFalse(policy._target_loadout_known())
        for slot in GEAR_SLOTS:
            item = next(item for item in home.inventory if item.slot == slot)
            self.assertFalse(policy._home_deposit_candidate(item, home))

    def test_control_no_shortage_keeps_the_target_gate(self):
        policy = self._policy()
        _decisions, home = self._drive(policy, HOME_PAGE)
        # Constructed: the pack without the two Identify staff stacks and the
        # Stinking Cloud wands has the free-slot minimum.
        trimmed = replace(home, inventory=[
            item for item in home.inventory if item.slot not in ("g", "h", "i")
        ])
        self.assertFalse(policy._town_pack_space_shortage(trimmed))
        for slot in GEAR_SLOTS:
            item = next(item for item in trimmed.inventory if item.slot == slot)
            self.assertFalse(policy._home_deposit_candidate(item, trimmed))


if __name__ == "__main__":
    unittest.main()
