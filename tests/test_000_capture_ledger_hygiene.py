"""Discovery-root invariant protecting repository capture ledgers."""

from __future__ import annotations

from pathlib import Path
import unittest

from tests.run_follow_hygiene import fingerprint_capture_ledgers


class CaptureLedgerFingerprintTest(unittest.TestCase):
    def test_absent_directory_has_stable_fingerprint(self):
        missing = Path(__file__).with_name("definitely-absent-capture-ledger")
        self.assertEqual((False, ()), fingerprint_capture_ledgers(missing))
