"""#95 step 1b-2: the Home junk sweep's own leave reason, and its declared wall.

Recorded board: identify-staff-swap-churn-20261003 (capture 2026-10-03, before
the sweep).  Its row 3 is a Home page where the Home page owner finds no Home
work and the live process left with ``home:route-claim-unfulfilled``.  The
sweep starts there (the Home is not full) and leaves the Home to take its first
junk ware at the entrance: the leave step says ``home:junk-sweep-withdraw``,
never a Home-full reason.  Under the declared ``pre_home_junk_sweep_rule`` the
recorded row comes back, so the wall the recorded replay of that capture uses
removes the sweep start and nothing else on these rows.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
import json
import unittest
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

import test_identify_staff_swap_churn_recorded as churn
from combat_decision_walls import pre_combat_decisions_rule
from hengbot.claim_goal_typing import GOAL_TERMINAL, goal_typing
from hengbot.claim_ladder import rung_of
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.warrior_optimization import load_character_calibration
from recorded_junk_scope import pre_home_junk_sweep_rule
from test_esp_threat_rest_recorded import EDIT, _policy

HOME_PAGE_ROW = 3


class _Replay:
    """The recorded segments and rows of the capture (no TestCase binding)."""


class JunkHomeSweepWallRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in churn.SHA256.items():
            assert churn._sha(path) == digest, path
        churn._RECORDS = (load_character_calibration(churn.CALIBRATION),
                          load_character_calibration(churn.DRAINED_CALIBRATION))
        boundaries = json.loads(churn.BOUNDARIES.read_text(encoding="utf-8"))
        fields = boundaries["recorded_fields"]
        with gzip.open(churn.FIXTURE, "rt", encoding="utf-8") as stream:
            lines = stream.read().splitlines(keepends=True)
        segments, start = [], 0
        for count in boundaries["input_rows"][:HOME_PAGE_ROW + 1]:
            segments.append(lines[start:start + count])
            start += count
        cls.replay = _Replay()
        cls.replay.segments = segments
        cls.replay.recorded = [dict(zip(fields, row)) for row in boundaries["recorded"]]
        cls.replay.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _rows(self, *, sweep_wall: bool):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.replay.directory = Path(temporary.name)
        policy = _policy(self.replay.directory, self.replay.monrace)
        policy._character_calibration_path.write_bytes(churn.CALIBRATION.read_bytes())
        policy._character_dump_path = self.replay.directory / "character-dump.txt"
        rows = []
        step = churn.IdentifyStaffSwapChurnRecordedTest._step.__func__
        with ExitStack() as walls:
            walls.enter_context(churn._dump_wall())
            walls.enter_context(pre_combat_decisions_rule())
            if sweep_wall:
                walls.enter_context(pre_home_junk_sweep_rule())
            for index in range(HOME_PAGE_ROW + 1):
                key, reason, board = step(self.replay, policy, index)
                rows.append((key, reason))
        self.home_page = board
        return rows, policy

    def _recorded(self, index):
        row = self.replay.recorded[index]
        return row["key"], row["reason"]

    def test_sweep_leaves_the_home_with_its_own_reason(self):
        rows, policy = self._rows(sweep_wall=False)
        for index in range(HOME_PAGE_ROW):
            self.assertEqual(rows[index], self._recorded(index), index)
        self.assertEqual(self._recorded(HOME_PAGE_ROW),
                         ("\x1b", "home:route-claim-unfulfilled"))
        self.assertEqual(rows[HOME_PAGE_ROW], ("\x1b", "home:junk-sweep-withdraw"))
        self.assertTrue(policy._home_full_relief["sweep"])
        self.assertIsNone(getattr(policy, "_home_full_retry_deposits", None))
        self.assertEqual(rung_of("home-visit", "home:junk-sweep-withdraw").producer,
                         "_home_full_relief_key")
        self.assertEqual(goal_typing("home-visit", "home:junk-sweep-withdraw").kind,
                         GOAL_TERMINAL)

    def test_sweep_take_pending_on_the_home_page_leaves_with_its_own_reason(self):
        rows, policy = self._rows(sweep_wall=False)
        self.assertEqual(rows[HOME_PAGE_ROW], ("\x1b", "home:junk-sweep-withdraw"))
        self.assertTrue(policy._home_errand.active)
        # DECLARED CONSTRUCTED: the leave did not take effect; the same Home
        # page is decided again with the sweep's take filed.
        with churn._dump_wall(), pre_combat_decisions_rule():
            policy._decision_sequence += 1
            key = policy.choose_key(self.home_page)
        self.assertEqual((str(key), policy.last_reason), ("\x1b", "home:junk-sweep-withdraw"))
        self.assertTrue(policy._home_full_relief["sweep"])

    def test_declared_wall_restores_the_recorded_rows(self):
        rows, policy = self._rows(sweep_wall=True)
        self.assertEqual(rows, [self._recorded(index) for index in range(HOME_PAGE_ROW + 1)])
        self.assertIsNone(policy._home_full_relief)


if __name__ == "__main__":
    unittest.main()
