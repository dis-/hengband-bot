"""2026-10-30 n1-b life-249: the guardian reposition reads only a real teleport.

Owner 2026-11-02: 「そもそもショートテレポートでは十分な距離が稼げないため
代替にならない。」  ``guardian:teleport-to-cover`` (policy_combat.py, the
summoner-open reposition beside a beatable target guardian) read
``_escape_scroll``, which falls back to Phase Door.  It now reads
``_escape_scroll(teleport_only=True)``; without a teleport the existing next
rung decides (on this board ``emergency:recall``: the floor is left).

Recorded board: tests/fixtures/guardian-phase-20261030.json.gz (see
tests/extract_guardian_phase_1102_fixture.py), イークの洞穴 13F with the
guardian 237 イークの大王『ボルドール』 in view, decision 15005 ('rh',
guardian:teleport-to-cover).  A fresh policy reproduces the recorded key
through the public choose_key.

DECLARED CONSTRUCTED: the target dungeon (2, the recorded conquest target),
and, in the second test, the 14 テレポートの巻物 (slot h) removed from the pack
so that only the ショート・テレポートの巻物 (slot g) remains.  The key is a plain
read; it is not posted through the executor.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "guardian-phase-20261030.json.gz"
SHA256 = "63f35ec215fba10466cf466f60ee45ee45a8f73f3b11681354b6ba4431418427"
TARGET_DUNGEON = 2  # イークの洞穴


class GuardianRepositionTeleportOnlyRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = FIXTURE.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == SHA256
        cls.case = json.loads(gzip.decompress(payload))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _decide(self, raw):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        policy = _policy(directory, self.monrace)
        policy._target_dungeon_id = TARGET_DUNGEON  # DECLARED CONSTRUCTED
        _decoded, boards = _consume_response_sequence(
            [json.dumps(raw, ensure_ascii=False)], policy, lambda _key: True,
            self.monrace, knowledge_ledger_path=directory / "knowledge.jsonl")
        board = boards[-1]
        policy.prime(board)
        policy.consume_skill_knowledge(
            {**self.case["skill"], "player": {"level": board.player.level}})
        board = policy.with_known_skill_exp(board)
        return policy.choose_key(board), policy.last_reason

    def test_recorded_board_reads_the_teleport(self):
        recorded = {row["decision_sequence"]: (row["key"], row["reason"])
                    for row in self.case["decisions"]}
        self.assertEqual(recorded[15005], ("rh", "guardian:teleport-to-cover"))
        scrolls = {item["slot"]: item["sval"]
                   for item in self.case["board"]["inventory"]
                   if item["tval"] == 70}
        self.assertEqual((scrolls["g"], scrolls["h"]), (8, 9))  # phase, teleport
        self.assertEqual(self._decide(self.case["board"]),
                         ("rh", "guardian:teleport-to-cover"))

    def test_phase_door_is_not_read_as_the_reposition_teleport(self):
        raw = dict(self.case["board"])
        raw["inventory"] = [item for item in raw["inventory"]
                            if item["slot"] != "h"]  # DECLARED CONSTRUCTED
        key, reason = self._decide(raw)
        self.assertNotEqual(key, "rg")
        self.assertNotEqual(reason, "guardian:teleport-to-cover")
        # The existing next rung: Word of Recall (slot i) leaves the floor.
        self.assertEqual((key, reason), ("ri", "emergency:recall"))


if __name__ == "__main__":
    unittest.main()
