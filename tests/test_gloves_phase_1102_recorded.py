"""2026-11-02 n1-a life-464: Dragon Gloves {r呪} are not plain-gear junk.

Owner 2026-11-02: 「ドラゴングローブは破壊対象になるべきではない」.  {r呪} is
the game's auto-inscription of TR_RES_CURSE (flavor/flag-inscriptions-table.cpp,
the resistance group); Dragon Gloves always roll one high resistance
(apply-magic-gloves.cpp dragon_resist, object-boost.cpp high_resistances).
The Warrior dominance set (warrior_loadout_search.BENEFICIAL_GEAR_FLAGS) held
every high resistance but 148, so the spare [4,+8] {r呪} pair looked dominated
by the worn [4,+11] {r時} pair and the full-Home relief took and destroyed it
(decisions 2292-2294).

Recorded boards: tests/fixtures/gloves-phase-1102.json.gz (state rows 63-79
of the 07:12 capture, see tests/extract_gloves_phase_1102_fixture.py).  The
fresh policy replays them through the public choose_key; before the fix it
repeats the recorded 2292 ('\x1b' home:junk-sweep-withdraw) and 2293
('5  pq\x1b' home-errand:atomic-withdraw:full-home-discard) keys.

DECLARED CONSTRUCTED: the character calibration (the capture has none; it is
seeded from the board with the stat tops as the displayed stats, as in
test_junk_plain_gear_recorded), the ~f skill-exp cache and the awaited ~9.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from policy_fixtures import seed_character_calibration
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "gloves-phase-1102.json.gz"
SHA256 = "0d7737f7e57d875908ee1fcff1d4d1a6d06b116f63b4f3c5d1b14dbd323d2584"
HOME_PAGE_ROW = 15  # state row 78, decision 2292
OUTSIDE_ROW = 16  # state row 79, decision 2293
GLOVES = (31, 3, 8)  # tval, sval, to_a of the destroyed pair
STAT_ORDER = ("str", "int", "wis", "dex", "con", "chr")


class DragonGlovesNotJunkRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = FIXTURE.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == SHA256
        cls.case = json.loads(gzip.decompress(payload))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def _replay(self, last_row):
        policy = _policy(self.directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        policy._in_store_ops_enabled = True
        decided = {}
        for index, line in enumerate(self.case["rows"][:last_row + 1]):
            row = json.loads(line)
            knowledge = row["type"] == "knowledge"
            if knowledge:
                # DECLARED CONSTRUCTED: the fresh policy awaits the recorded ~9.
                policy._home_knowledge_scan_inflight = True
                policy._home_knowledge_scan_epoch = None
            _decoded, snapshots = _consume_response_sequence(
                [line], policy, lambda _key: True, self.monrace,
                knowledge_ledger_path=self.directory / "knowledge.jsonl")
            if knowledge or not snapshots:
                continue
            board = snapshots[-1]
            # DECLARED CONSTRUCTED: the ~f skill-exp cache.
            policy._skill_exp_cache = (0, 0, board.player.level,
                                       policy._town_visit_epoch)
            if policy._character_calibration is None:
                stats = row["player"]["stats"]
                tops = tuple(stats[name]["top"] for name in STAT_ORDER)
                # DECLARED CONSTRUCTED: the calibration (see the docstring).
                seed_character_calibration(policy, replace(
                    board, player=replace(board.player, stat_cur=tops,
                                          stat_use=tops)))
                policy._character_calibration = replace(
                    policy._character_calibration,
                    stat_cur=tuple(board.player.printed_stat_cur_key))
            decided[index] = (policy.choose_key(board), policy.last_reason)
        return policy, decided

    @staticmethod
    def _is_gloves(item):
        return (item.tval, item.sval, item.to_a) == GLOVES

    def test_recorded_facts(self):
        recorded = {row["decision_sequence"]: (row["key"], row["reason"])
                    for row in self.case["decisions"]}
        self.assertEqual(recorded[2292], ("\x1b", "home:junk-sweep-withdraw"))
        self.assertEqual(recorded[2293], (
            "5  pq\x1b", "home-errand:atomic-withdraw:full-home-discard"))
        self.assertEqual(recorded[2294][1], "home:junk-sweep:plain-gear")

    def test_resist_curse_gloves_are_not_withdrawn_to_destroy(self):
        policy, decided = self._replay(OUTSIDE_ROW)
        gloves = next(item for item in policy._home_knowledge_items
                      if self._is_gloves(item))
        self.assertIn(148, gloves.known_flags)  # TR_RES_CURSE
        self.assertIsNone(
            policy._junk_class(policy._decision_input_snapshot, gloves))
        relief = policy._home_full_relief
        self.assertFalse(relief and relief.get("sale")
                         and relief["sale"][0][1:] == GLOVES[:2])
        # The recorded 2292 / 2293 keys took the pair out to destroy it.
        self.assertNotEqual(decided[HOME_PAGE_ROW][1], "home:junk-sweep-withdraw")
        self.assertNotIn("full-home-discard", decided[OUTSIDE_ROW][1])
        self.assertFalse(decided[OUTSIDE_ROW][0].startswith("5"))


if __name__ == "__main__":
    unittest.main()
