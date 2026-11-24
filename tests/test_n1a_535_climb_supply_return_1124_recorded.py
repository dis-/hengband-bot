"""n1-a life-535: the climb gives way to the supply return (teleport-low) on a climb floor.

n1-a life-535 (Warrior Lv50, no *Destruction* means: the unsafe-recall fallback's Mountain climb,
dungeon 14, band 38-42) died on Mountain 45F at 2026-11-24 14:41:42.  It left town with 15
Scrolls of Teleportation, landed on 48F, climbed to 45F and read all 15 there in four minutes
(``flee:scroll`` / ``emergency:teleport`` against the Mountain's summoners: Gwaihir, the Greater
and Middle titans, Teresa).  With 3 left (14:41:14, turn 10679228) and then 0 (14:41:28) it went on
searching for the up stairs (``castle-climb:search-upstairs``); a Middle titan's summons and the
GREAT THING (RES_TELE, speed +20, a ROCKET of min(HP/4, 800) = 800) came on 14:41:31, the only
escape left was Word of Recall (read 14:41:32 on the 即死 board, 15-34 ticks), and it died ten
seconds later with the Recall still counting down.

The supply ledger's return (policy_town ``_should_start_town_return``: ``teleport-low`` below 4
scrolls at this depth) never started: deep_climb's rung is the objectives layer's first, above the
return's rungs, and answered every climb-floor board.  Owner 2026-10-03 (verbatim, the intent of
the returns): 「回復・テレポート・帰還が尽きる前に町へ戻る。既存の teleport-low / escape-kit-empty /
recall 不足の帰還がそれ」.

Recorded: the 14:35:47 town-arrival checkpoint of the death capture
(tests/fixtures/n1a-535-death-1124, tests/extract_n1a_535_death_1124_fixture.py), its 190 visit
rows replayed as recorded, and the capture's boards: the first 48F board the copy holds, the 45F
arrival and the 45F boards with 3 (turn 10679228) and 0 (10679445) scrolls left, the last one.

DECLARED CONSTRUCTED:

* the 45F boards between the arrival and 10679228 are not fed (each board below is decided by a
  copy of the policy after the arrival);
* on the 3- and 0-scroll boards the dungeon identify of the unidentified Lochaber axe (one action, the
  objectives rung above the return's) is answered None, so the board shows the return's own key;
* the controls: the same board with 15 scrolls (``count`` replaced) and with a depth-gap return
  (``_should_start_town_return`` answering ``resist-gap``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import deep_climb, dive_floor, return_start
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load
from town_work_corpus import replay_window

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-535-death-1124"
MOUNTAIN = 14
ARRIVAL_45 = 10673707
THREE_LEFT = 10679228  # recorded ('4', 'castle-climb:search-upstairs')
NONE_LEFT = 10679445  # recorded ('1', 'castle-climb:search-upstairs')
DEATH = 10679565  # recorded ('8', 'emergency:cornered-attack'), HP 32, the Recall counting down
SV_SCROLL_TELEPORT = 9
SV_SCROLL_WORD_OF_RECALL = 11
GREAT_THING = 1345


def _quiet(call):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return call()


def _teleports(board) -> int:
    return sum(item.count for item in board.inventory
               if item.is_scroll and item.sval == SV_SCROLL_TELEPORT)


class ClimbSupplyReturnTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, _journal, steps = _quiet(lambda: load(FIXTURE, Path(cls.scratch.name)))
        cls.town = _quiet(lambda: replay_window("n1a-535-death", cls.policy, iter(steps)))
        lines = lzma.decompress((FIXTURE / "boards.jsonl.xz").read_bytes()).decode(
            "utf-8").splitlines()
        cls.boards = {}
        for line in lines:
            raw = json.loads(line)
            cls.boards[raw["turn"]] = parse_snapshot(raw, cls.policy._monrace_knowledge)
        for turn in sorted(cls.boards):
            if turn > ARRIVAL_45:
                break
            key = _quiet(lambda: cls.policy.choose_key(cls.boards[turn]))
            if key:
                cls.policy.confirm_key_posted(key)

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def _decide(self, board, policy=None, *, identify=True):
        policy = copy.deepcopy(self.policy) if policy is None else policy
        if identify:
            key = _quiet(lambda: policy.choose_key(board))
        else:
            with mock.patch.object(type(policy), "_dungeon_equipment_identify_key",
                                   return_value=None):
                key = _quiet(lambda: policy.choose_key(board))
        return policy, key, policy.last_reason

    def test_the_recorded_boards(self):
        self.assertIsNone(self.town.first_divergence)
        self.assertEqual(self.town.matched_rows, 190)
        three, none = self.boards[THREE_LEFT], self.boards[NONE_LEFT]
        self.assertEqual(three.floor_key, (MOUNTAIN, 45, 0))
        self.assertEqual((_teleports(self.boards[ARRIVAL_45]), _teleports(three),
                          _teleports(none)), (15, 3, 0))
        self.assertFalse(three.player.recalling or none.player.recalling)
        # The climb floor of the held Mountain climb, below the band.
        self.assertEqual(dive_floor.climb_dungeon(self.policy), MOUNTAIN)
        self.assertEqual(dive_floor.band(self.policy, three), (38, 42))
        self.assertTrue(deep_climb.climb_floor(self.policy, three))
        self.assertFalse(deep_climb.on_floor(self.policy, three))
        # The death board: the Recall read at 14:41:32 still counting down, no Teleportation,
        # the GREAT THING beside (RES_TELE: no Teleport Other moves it).
        death = self.boards[DEATH]
        self.assertTrue(death.player.recalling)
        self.assertEqual(_teleports(death), 0)
        self.assertTrue(any(monster.race_id == GREAT_THING and monster.distance <= 1
                            for monster in death.visible_monsters))
        self.assertIn("RES_TELE", self.policy._monrace_knowledge[GREAT_THING].flags)

    def test_three_scrolls_left_start_the_teleport_low_return(self):
        board = self.boards[THREE_LEFT]
        policy = copy.deepcopy(self.policy)
        self.assertTrue(_quiet(lambda: policy._should_start_town_return(board)))
        self.assertEqual(policy._last_return_trigger, "teleport-low")
        self.assertTrue(deep_climb.return_due(policy, board))
        self.assertIsNone(_quiet(lambda: deep_climb.key(policy, board)))
        # The board's decision: the climb no longer answers it (recorded: castle-climb:search-
        # upstairs); the identify of the axe is the one rung above the return's.
        _policy, _key, reason = self._decide(board)
        self.assertFalse(reason.startswith("castle-climb"), reason)
        policy, key, reason = self._decide(board, identify=False)
        recall = next(item for item in board.inventory
                      if item.is_scroll and item.sval == SV_SCROLL_WORD_OF_RECALL)
        self.assertEqual(reason, "return:recall")
        self.assertEqual(key, "r" + recall.slot)
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._last_return_trigger, "teleport-low")

    def test_no_scroll_left_reads_recall(self):
        board = self.boards[NONE_LEFT]
        _policy, _key, reason = self._decide(board)
        self.assertFalse(reason.startswith(("castle-climb", "area-mapping:deep-climb")), reason)
        policy, key, reason = self._decide(board, identify=False)
        recall = next(item for item in board.inventory
                      if item.is_scroll and item.sval == SV_SCROLL_WORD_OF_RECALL)
        self.assertEqual((key, reason), ("r" + recall.slot, "return:recall"))
        self.assertTrue(policy._returning_to_town)

    def test_control_a_full_kit_climbs_on(self):
        board = self.boards[THREE_LEFT]
        full = replace(board, inventory=tuple(
            replace(item, count=15) if item.is_scroll and item.sval == SV_SCROLL_TELEPORT
            else item for item in board.inventory))
        self.assertEqual(_teleports(full), 15)
        policy = copy.deepcopy(self.policy)
        self.assertFalse(deep_climb.return_due(policy, full))
        _policy, _key, reason = self._decide(full)
        self.assertTrue(reason.startswith(("castle-climb", "area-mapping:deep-climb")), reason)

    def test_control_a_depth_gap_keeps_the_climb(self):
        """The depth gap of the floor stood on is the climb's own answer (no return there)."""
        board = self.boards[THREE_LEFT]
        policy = copy.deepcopy(self.policy)

        def gap(snapshot):
            return_start.set_trigger(policy, "resist-gap")
            return True

        with mock.patch.object(policy, "_should_start_town_return", side_effect=gap):
            self.assertFalse(deep_climb.return_due(policy, board))
            self.assertIsNotNone(_quiet(lambda: deep_climb.key(policy, board)))


if __name__ == "__main__":
    unittest.main()
