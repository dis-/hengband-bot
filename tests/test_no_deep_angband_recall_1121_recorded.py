"""No recall toward Angband at a recall depth of 96F or deeper outside the expedition (n1-b).

Owner 2026-11-21 (verbatim, LOCKED) 「帰還の深さが96F以上なら遠征以外で鉄獄へ帰還しない」 (it replaces
「今のまま（99Fに着いたら登って95Fへ）」): n1-b life-411 died on Angband 100F at 17:16 after an ordinary
departure (no preparation phase) read Word of Recall toward Angband with its recall depth at 100.

The board: n1-b's town board of 2026-11-21 15:31:51 (tests/fixtures/n1b-hunger-100f-1121, journal
row 0), recall depth 95 there, the departure's destination Angband.

DECLARED CONSTRUCTED: Angband's saved recall depth set to 100 (as at 17:15) and 96; for the
expedition case, the preparation phase's lifted mark.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_cap, finale_prep
from hengbot.model import DUNGEON_ANGBAND
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-hunger-100f-1121"
DEATH_VISIT = Path(__file__).with_name("fixtures") / "n1b-411-deep-angband-recall-1121"
RECALL_ROW = 25  # recorded: town:recall-to-angband ('rda'), Angband's recall depth 100


class DeathVisitRecordedTest(unittest.TestCase):
    """n1-b's town visit of 2026-11-21 17:15:50 (tests/fixtures/n1b-411-deep-angband-recall-1121,
    the first 26 journal rows of capture n1b-411-20261121-death-100f): an ordinary departure
    (no preparation phase) read Word of Recall toward Angband at row 25 with the recall depth at
    100; the character died on 100F at 17:16.  Replayed row by row through the journal."""

    def setUp(self):
        self.scratch = TemporaryDirectory()

    def tearDown(self):
        self.scratch.cleanup()

    def test_the_departure_takes_no_dungeon_and_stops_for_the_owner(self):
        policy, _journal, steps = load(DEATH_VISIT, Path(self.scratch.name) / "fixture")
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        policy._me_power_resume_reads = True  # the live CLI's
        decided = {}
        for recorded, supply in steps[:RECALL_ROW + 1]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            decided[recorded["row"]] = (key, policy.last_reason)
            posted = recorded["key"]
            if posted:
                policy.confirm_key_posted(posted)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, posted):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": posted})
        self.assertEqual(board.dungeon_recall_depths[DUNGEON_ANGBAND], 100)
        self.assertFalse(finale_prep.lifted(policy))
        reasons = [reason for _key, reason in decided.values()]
        self.assertNotIn("town:recall-to-angband", reasons)
        # Owner 2026-11-19 「鉄獄50F以降は浅い階層へのフォールバックをやめる」 with the 96F+ refusal
        # (finale_hold, 2026-11-23): no other dungeon either; the finale's preparation lacks the
        # *Healing* only the dungeon and the Black Market give, so the visit stops for the owner.
        self.assertFalse(any(reason.startswith("town:recall-to-") for reason in reasons))
        self.assertNotIn("town:unsafe-recall-fallback", reasons)
        self.assertIn("town:blocked:finale-not-in-town:star_healing", reasons)
        self.assertEqual(policy._target_dungeon_id, DUNGEON_ANGBAND)


class NoDeepAngbandRecallRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, steps = load(FIXTURE, Path(self.scratch.name) / "fixture")
        self.addCleanup(self.policy._home_disposal.history_path.unlink, missing_ok=True)
        self.board = steps[0][1]()
        self.assertEqual(self.policy._town_recall_destination(self.board), ("angband", DUNGEON_ANGBAND))

    def tearDown(self):
        self.scratch.cleanup()

    def at_depth(self, depth):
        depths = {**self.board.dungeon_recall_depths, DUNGEON_ANGBAND: depth}  # DECLARED
        return replace(self.board, dungeon_recall_depths=depths)

    def test_a_deep_recall_depth_is_no_angband_destination(self):
        for depth in (100, 96):
            board = self.at_depth(depth)
            destination, _dungeon = self.policy._town_recall_destination(board)
            self.assertNotEqual(destination, "angband", depth)
            self.assertFalse(self.policy._recall_destination_safe(board, DUNGEON_ANGBAND))
        self.assertTrue(angband_cap.deep_recall_refused(self.at_depth(96), DUNGEON_ANGBAND, self.policy))
        self.assertFalse(angband_cap.deep_recall_refused(self.at_depth(95), DUNGEON_ANGBAND, self.policy))

    def test_the_expedition_still_recalls_deep(self):
        finale_prep.phase(self.policy).lifted = True  # DECLARED: the preparation's recall step
        board = self.at_depth(100)
        self.assertFalse(angband_cap.deep_recall_refused(board, DUNGEON_ANGBAND, self.policy))


if __name__ == "__main__":
    unittest.main()
