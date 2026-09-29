import json
import unittest

import tests  # noqa: F401  (bare runs stay isolated from runtime files)
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _build_argument_parser
from hengbot.flight_recorder import append_session_marker
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.policy import HengbotPolicy


class TownClaimSwitchTest(unittest.TestCase):
    def test_opt_in_and_default(self):
        parser = _build_argument_parser()
        self.assertFalse(parser.parse_args(["--state-file", "state.jsonl"]).enforce_town_claims)
        self.assertTrue(parser.parse_args([
            "--state-file", "state.jsonl", "--enforce-town-claims",
        ]).enforce_town_claims)

    def test_session_header_echoes_both_modes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            for enabled in (False, True):
                append_session_marker(path, [], enforce_town_claims=enabled)
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["enforce_town_claims"] for row in rows], [False, True])

    def test_checkpoint_preserves_on_and_defaults_old_checkpoint_off(self):
        policy = HengbotPolicy()
        policy._town_claim_bar_enforced = True
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertTrue(restored._town_claim_bar_enforced)
        del policy._town_claim_bar_enforced
        old_restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertFalse(old_restored._town_claim_bar_enforced)


class CrossareaFundraisingSwitchTest(unittest.TestCase):
    def test_opt_in_and_default(self):
        parser = _build_argument_parser()
        self.assertFalse(parser.parse_args(
            ["--state-file", "state.jsonl"]).enforce_crossarea_fundraising)
        self.assertTrue(parser.parse_args([
            "--state-file", "state.jsonl", "--enforce-crossarea-fundraising",
        ]).enforce_crossarea_fundraising)

    def test_session_header_echoes_both_modes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            for enabled in (False, True):
                append_session_marker(
                    path, [], enforce_crossarea_fundraising=enabled)
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(
                [row["enforce_crossarea_fundraising"] for row in rows],
                [False, True])

    def test_checkpoint_preserves_on_and_defaults_old_checkpoint_off(self):
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertTrue(restored._crossarea_fundraising_enforced)
        del policy._crossarea_fundraising_enforced
        old_restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertFalse(old_restored._crossarea_fundraising_enforced)


if __name__ == "__main__":
    unittest.main()
