"""Recorded pin: inside the Sewer (Q2) the phase strategy alone owns detected gremlins.

Live stops 2026-10-02 14:15:58 and 14:16:22 (``loop-detected``; commit
275a9076, ``--enforce-crossarea-fundraising``, S3.3 switch off; quest Q2 =
KILL_ALL, leaving fails it; HP 584/584, no visible hostile).  The 14:16:07
process of the 14:16:22 stop (a restart on floor (0, 15, 2)) is frozen by
tests/extract_q2_choke_loop_fixture.py, decisions 0..22.

Two owners alternate, unbounded:

- ``quest-strategy:q2-post-blue-nether-worm`` walks up-left
  (14,63) -> (13,63) -> (12,62) -> (11,61) toward the nether-worm placement.
- At (11,61) two of fourteen telepathy-detected gremlins (race 153,
  MULTIPLY, awake, behind the wall at y 5..8) stand at distance 3
  (= SWARM_LOOKAHEAD), so ``_detected_threat_preparation_key`` sees
  converging breeders and retreats ``detected:prepare-choke`` '3','3','2' to
  the choke (14,63), where ``summoner:hold-choke`` waits '5' once.
- At (14,63) no detected gremlin is within SWARM_LOOKAHEAD: the gate releases
  (``choke-threat-dispersed``), the generic owner falls silent, and the quest
  strategy (rung navigator.decide, below the detected rung) walks back.

Fix (one rule, no threshold): on the Q2 floor, when the approved strategy's
own plan names every detected monster that would drive the retreat
(QUEST_2.jsonc ``priority_targets``; gremlin 153 is P2 of its formation),
the generic detected choke yields and the phase strategy keeps the turn.

Walls (declared): ``PRE_FIX`` patches ``_quest_plan_owns_detected`` to False
and reproduces every live (key, reason) 0..22.  With the fix, 0..1 equal the
live keys and 2 is the first changed key (R4).  Boards 3..22 are the effects
of the LIVE keys, not of the new one, so past 2 the pin asserts only which
owner decides each recorded board (never an effect).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import SWARM_LOOKAHEAD

from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "q2-choke-loop-20261002.jsonl.gz"
BOUNDARIES = FIXTURES / "q2-choke-loop-20261002.boundaries.json"
CALIBRATION = FIXTURES / "q2travel-progress-20261002.character-calibration.json"
SHA256 = {
    FIXTURE: "7dc3c5f4c4140e738f1d2cc541b9dffddc06d6716a57a05e5b328567bdcfaee5",
    BOUNDARIES: "594f5ee4f10cdbe5247dc8abf6472c4d5bb637b2a4b5add00b0eb789875cb6bc",
    CALIBRATION: "78ba2af16831a9a9211784eacedc74599c53de6a9dfffe68dbb5f7ae88af6220",
}
LAST = 22
FIRST_CHANGED = 2
GREMLIN = 153
GENERIC = ("detected:", "summoner:")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _pre_fix(_self, _snapshot, _monsters):
    return False


class Q2ChokeLoopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        boundaries = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
        fields = boundaries["recorded_fields"]
        cls.recorded = [dict(zip(fields, row)) for row in boundaries["recorded"]]
        cls.detail = boundaries["detail"]
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            lines = stream.read().splitlines(keepends=True)
        assert len(lines) == sum(boundaries["input_rows"])
        cls.segments = []
        start = 0
        for count in boundaries["input_rows"]:
            cls.segments.append(lines[start:start + count])
            start += count
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    @staticmethod
    def _post(policy, key):
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": str(key)})

    def _replay(self, *, pre_fix=False, inspect=None):
        rows = []
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            policy = _policy(directory, self.monrace)
            policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
            policy._crossarea_fundraising_enforced = True  # live argv
            for index in range(LAST + 1):
                _decoded, snapshots = _consume_response_sequence(
                    self.segments[index], policy, lambda _key: True, self.monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                board = snapshots[-1]
                if pre_fix:
                    # create=True: the pre-fix source has no such seam.
                    with patch.object(HengbotPolicy, "_quest_plan_owns_detected",
                                      _pre_fix, create=True):
                        key = policy.choose_key(board)
                else:
                    key = policy.choose_key(board)
                rows.append((str(key), policy.last_reason))
                if inspect is not None:
                    inspect(index, policy, board)
                self._post(policy, key)
        return rows

    def _live(self, index):
        row = self.recorded[index]
        return row["key"], row["reason"]

    # ------------------------------------------------------------ recorded
    def test_recorded_process_alternates_two_owners(self):
        reasons = [self._live(index)[1] for index in range(1, LAST + 1)]
        cycle = (["quest-strategy:q2-post-blue-nether-worm"]
                 + ["detected:prepare-choke"] * 3 + ["summoner:hold-choke"]
                 + ["quest-strategy:q2-post-blue-nether-worm"] * 2)
        self.assertEqual(reasons, (cycle * 4)[:LAST])
        for index in range(LAST + 1):
            detail = self.detail[str(index)]
            self.assertEqual(detail["floor"]["quest_id"], 2, index)
            self.assertEqual(detail["visible_hostiles"], 0, index)
        triggers = {tuple(pair) for index in range(LAST + 1)
                    for pair in (self.detail[str(index)]["claim"]["trigger_monsters"] or [])}
        self.assertEqual({race for _index, race in triggers}, {GREMLIN})

    def test_pre_fix_reproduces_every_live_key(self):
        seen = {}

        def inspect(index, policy, board):
            if index == FIRST_CHANGED:
                seen["near"] = sorted(
                    (monster.index, monster.race_id)
                    for monster in board.detected_monsters
                    if monster.distance <= SWARM_LOOKAHEAD
                    and not monster.asleep and monster.can_multiply)

        rows = self._replay(pre_fix=True, inspect=inspect)
        # e32d0f44 (2026-10-08, USER DECISION 2026-09-20 50-turn hold): once
        # the unseen-summoner hold starts at the choke cell it owns that cell
        # until its timer expires, so the pre-fix substrate holds one more
        # board where the recorded run handed back to the quest strategy.
        hold_owned = {6, 13, 20}
        self.assertEqual(
            [row for index, row in enumerate(rows) if index not in hold_owned],
            [self._live(index) for index in range(LAST + 1) if index not in hold_owned])
        self.assertEqual({index: rows[index] for index in hold_owned},
                         {index: ("5", "summoner:hold-choke") for index in hold_owned})
        self.assertEqual({self._live(index) for index in hold_owned},
                         {("8", "quest-strategy:q2-post-blue-nether-worm")})
        # The two converging breeders that drive the recorded retreat.
        self.assertEqual(seen["near"], [(42, GREMLIN), (48, GREMLIN)])

    # ------------------------------------------------------------ fix
    def test_quest_strategy_alone_owns_every_recorded_board(self):
        rows = self._replay()
        for index in range(FIRST_CHANGED):
            self.assertEqual(rows[index], self._live(index), index)
        # First changed decision: the phase strategy keeps the turn at the
        # cell where the generic detected choke had taken it.
        self.assertNotEqual(rows[FIRST_CHANGED], self._live(FIRST_CHANGED))
        self.assertTrue(rows[FIRST_CHANGED][1].startswith("quest-strategy:q2-"),
                        rows[FIRST_CHANGED])
        # Owner per recorded board (no effect claimed past the divergence).
        owners = [reason for _key, reason in rows[1:]]
        for index, reason in enumerate(owners, start=1):
            self.assertTrue(reason.startswith("quest-strategy:q2-"), (index, reason))
            self.assertFalse(reason.startswith(GENERIC), (index, reason))


if __name__ == "__main__":
    unittest.main()
