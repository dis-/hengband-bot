"""Shared replay of the Forest 32F walk-away capture (2026-10-03).

Used by ``test_unseen_retreat_visible_attacker_recorded`` (the recorded pins)
and ``test_low_hp_no_unchecked_walk`` (constructed boards derived from the same
capture).  ``ReplayMixin`` is not a TestCase, so neither test module binds the
other's test classes; each module mixes it into its own ``_Replay`` TestCase.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge

from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "unseen-retreat-visible-20261003.jsonl.gz"
RECORDED = FIXTURES / "unseen-retreat-visible-20261003.recorded.json"
CALIBRATION = FIXTURES / "unseen-retreat-visible-20261003.character-calibration.json"
# R9: digests of the bytes with CRLF normalized to LF.
SHA256 = {
    FIXTURE: "22c63672d956347a29d704f7f37c933d4fcf3a419e1285a6b61a45f04d725d37",
    RECORDED: "3a40ca00f865bf2984e105d9cfefedacb9ce5363b72a240f774fc622d036b4ad",
    CALIBRATION: "071816f863bea7c7c6286299e32a674e016d7ea43cfdba2345277f0958712614",
}

A_WARMUP = 532
A_DIVERGENCE = 545
B_START = 588
B_DIVERGENCE = 594


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class ReplayMixin:
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream]
        cls.knowledge = json.loads(records[0]["line"])
        cls.boards = {
            record["sequence"]: record["line"]
            for record in records[1:]
        }
        rows = json.loads(RECORDED.read_text(encoding="utf-8"))["recorded"]
        cls.recorded = {row[0]: row for row in rows}
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.policy = _policy(Path(self._tmp.name), self.monrace)
        self.policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
        self.policy._crossarea_fundraising_enforced = True  # live argv
        self.policy.consume_skill_knowledge(self.knowledge)

    def _replay(self, first, last):
        rows, board = {}, None
        for sequence in range(first, last + 1):
            _decoded, snapshots = _consume_response_sequence(
                [self.boards[sequence]], self.policy, lambda _key: True,
                self.monrace,
                knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl",
            )
            board = snapshots[-1]
            key = self.policy.choose_key(board)
            rows[sequence] = (str(key), self.policy.last_reason)
            self.policy.confirm_key_posted(key)
        return rows, board

    def _live(self, sequence):
        row = self.recorded[sequence]
        return (row[2], row[3])


