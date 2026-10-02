"""Recorded pins: a recall target whose landing fails the depth gate.

Board: the 2026-10-02 17:01:12 process frozen by
tests/extract_town_blackmarket_stall_fixture.py (same character, town and
gold 12522 as the 17:00:27 process one minute earlier).  Boards 0..3 replay
the live keys (pinned again below); board 4 is the first board the live
router had no owner (``town:blocked:no-actionable-claim-owner``).

Declared state at board 4 (the in-memory state of the 17:00:27 process
that the 17:01:12 restart lost; values printed from
``jsonlog/autorecover-20261002-170027-town-blocked-owner-retired``):

- ``_launcher_enchant_attempted = {to-hit, to-dam}``: that process read both
  launcher enchant scrolls this visit (``rhc`` at turns 3962372
  ``town:enchant-launcher-tohit`` and 3962413 ``town:enchant-launcher-todam``),
  so its optional ``launcher-enchant`` claim was gone and the town reached
  the departure seam (then ``probe`` / ``stuck:wander`` / ``owner-retired``).
- item 9 only: ``_alternate_dungeon = 12`` (last row ``over_extension``:
  ``target_dungeon_id 12, alternate_dungeon_id 12 (Castle)``).

The character lacks resist_conf (board abilities); Angband lands on 21 and
Castle on 22 (``dungeon_recall_depths``), both in the 21..25 band that needs
free_action, resist_conf and resist_fire.  The other entered dungeons give no
safe alternate: 3 and 7 land on 21, 14 on 25, 18 on 30; 2 is the Yeek cave and
4 the conquered forgetting maze.

ITEM 9: an unsafe alternate-dungeon target is refused by the same rule as
the unsafe Angband target (same safe-fallback search, same named stop when
none), instead of returning no key (live: probe -> stuck:wander ->
owner-retired).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import dataclasses
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import (
    DUNGEON_ANGBAND,
    DUNGEON_YEEK_CAVE,
    SV_SCROLL_ENCHANT_WEAPON_TO_DAM,
    SV_SCROLL_ENCHANT_WEAPON_TO_HIT,
)
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import FUNDRAISING_GOLD_TARGET

from test_esp_threat_rest_recorded import _policy
import test_town_blackmarket_stall_recorded as stall
from test_town_blackmarket_stall_recorded import CALIBRATION, FIRST_NO_OWNER

CASTLE = 12
RECORDED_GOLD = 12522


class NoSafeDestinationRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stall.TownBlackMarketStallRecordedTest.setUpClass.__func__(cls)

    def _decide_board_4(self, *, alternate=None, gold=None):
        """Replay 0..3 as live, declare the lost state, decide board 4."""
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            policy = _policy(directory, self.monrace)
            policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
            policy._crossarea_fundraising_enforced = True  # live argv
            for index in range(FIRST_NO_OWNER + 1):
                _decoded, snapshots = _consume_response_sequence(
                    self.segments[index], policy, lambda _key: True, self.monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                board = snapshots[-1]
                if index == FIRST_NO_OWNER:
                    policy._launcher_enchant_attempted = {
                        SV_SCROLL_ENCHANT_WEAPON_TO_HIT,
                        SV_SCROLL_ENCHANT_WEAPON_TO_DAM,
                    }
                    if alternate is not None:
                        policy._alternate_dungeon = alternate
                    if gold is not None:
                        board = dataclasses.replace(
                            board,
                            player=dataclasses.replace(board.player, gold=gold),
                        )
                    key = policy.choose_key(board)
                    return str(key), policy.last_reason, policy, board
                key = policy.choose_key(board)
                live = self.recorded[index]
                self.assertEqual((str(key), policy.last_reason),
                                 (live["key"], live["reason"]), index)
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain(
                        {"outcome": "released", "posted": str(key)})
        raise AssertionError("unreachable")

    def test_board_facts(self):
        _key, _reason, policy, board = self._decide_board_4()
        self.assertEqual(board.player.gold, RECORDED_GOLD)
        self.assertNotIn("resist_conf", board.player.abilities)
        self.assertEqual(board.dungeon_recall_depths[DUNGEON_ANGBAND], 21)
        self.assertEqual(board.dungeon_recall_depths[CASTLE], 22)
        self.assertIn(CASTLE, board.entered_dungeon_ids)
        self.assertNotEqual(DUNGEON_YEEK_CAVE, CASTLE)
        self.assertIsNone(policy._pick_alternate_dungeon(
            board, max_entry_depth=21))

    # ------------------------------------------------------------ item 9
    def test_unsafe_alternate_target_stops_like_angband_when_no_fallback(self):
        # Gold at the fundraising target: the fundraising fallback of item 4
        # does not apply, so the decided terminal is the named stop.
        key, reason, policy, _board = self._decide_board_4(
            alternate=CASTLE, gold=FUNDRAISING_GOLD_TARGET)
        self.assertEqual(policy._target_dungeon_id, CASTLE)
        self.assertEqual(
            (key, reason),
            ("1", "town:blocked:depth-gate:destination-22:missing-resist_conf"))
        angband = self._decide_board_4(gold=FUNDRAISING_GOLD_TARGET)
        self.assertEqual(
            angband[:2],
            ("1", "town:blocked:depth-gate:destination-21:missing-resist_conf"))


if __name__ == "__main__":
    unittest.main()
