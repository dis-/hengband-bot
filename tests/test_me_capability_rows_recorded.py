"""#47 owner answers 2026-11-01 21h on the me_capability REPLACES rows.

5 「今残っている回数で数える」: the absorbed Detect Treasure power counts toward
  the detection the departure needs by the displayed current charges (the
  record only when no list was read), like every other power.

Boards: the recorded n1-c life-021 explicit-target fundraising run at the
Alchemist (D9, tests/fixtures/me-town-stops-20261030.json.gz,
tests/extract_me_town_stops.py) with its recorded shelves.  Only the replies to
newly posted keys are constructed (tests/test_me_town_stops_recorded.py);
every decision goes through the public ``choose_key`` and the production
executor.  DECLARED CONSTRUCTED where named in each case: the staff
sequence's stage 1 absorbed (the record) and the last displayed staff power
list (``_magic_eater_power_list`` rows with the BaseitemDefinitions names).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy

from hengbot import me_capability, me_staff_sequence
from hengbot.me_device_attacks import observe_lists
from hengbot.model import (
    SV_SCROLL_DETECT_TREASURE, SV_STAFF_DETECT_GOLD, SV_STAFF_IDENTIFY, TVAL_SCROLL,
    parse_snapshot,
)
from tests import test_lv7_town_stop_recorded as lv7
from tests import test_me_town_stops_recorded as d9
import tests.test_input_executor as executor_harness


DETECTION = "財宝感知の巻物"
STAGE1 = {me_capability.record_key("staff", SV_STAFF_IDENTIFY): 21,
          me_capability.record_key("staff", SV_STAFF_DETECT_GOLD): 19}


def staff_list(identify=(21, 21), detect=(19, 19)):
    """cmd-magiceat.cpp's staff list as the executor reads it: (current, max)."""
    return {"kind": "staff", "rows": [
        {"name": name, "current": current, "max": count, "fail": 10, "success": 90}
        for name, (current, count) in (("鑑定", identify), ("財宝感知", detect))]}


class DetectTreasureCountTest(executor_harness.ProductionHarness):
    """The recorded life-021 Alchemist page of the run's kit, with no
    Treasure Detection scroll in the pack and a six-scroll departure target."""

    LIFE = "life-021"
    listed = None
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post
    reply = d9.MagicEaterTownStopsRecordedTest.reply
    drive = d9.MagicEaterTownStopsRecordedTest.drive

    @classmethod
    def setUpClass(cls):
        d9.MagicEaterTownStopsRecordedTest.setUpClass()
        cls.cases = d9.MagicEaterTownStopsRecordedTest.cases

    def boundary(self, life, *, kit_bought=False):
        policy, raw = d9.MagicEaterTownStopsRecordedTest.boundary(self, life, kit_bought=kit_bought)
        # DECLARED CONSTRUCTED: stage 1 absorbed; the run's casts left one
        # Detect Treasure charge on the last displayed list.
        me_staff_sequence.state(policy).absorbed = dict(STAGE1)
        if self.listed is not None:
            raw["_magic_eater_power_list"] = self.listed
        return policy, raw

    def first_board(self):
        policy, raw = self.boundary(self.LIFE)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        observe_lists(policy, board)  # what choose_key's observation keeps
        self.assertEqual(board.store.store_type, 4)
        self.assertFalse(any(item.is_treasure_detection_scroll for item in board.inventory))
        return policy, board

    def test_the_displayed_current_charges_count(self):
        self.listed = staff_list(detect=(1, 19))
        policy, board = self.first_board()
        self.assertEqual(policy._mining_detection_stock_target(board), 6)
        self.assertEqual(me_capability.replacing_charges(
            policy, board, (TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE)), 1)
        # Unfixed: the record's 19 counted, a full six-scroll stock.
        self.assertEqual(policy._count_treasure_detection_scrolls(board), 1)

    def test_the_record_counts_only_when_no_list_was_read(self):
        self.listed = None
        policy, board = self.first_board()
        self.assertEqual(policy._count_treasure_detection_scrolls(board), 19)

    def test_the_run_buys_the_missing_scrolls_before_it_descends(self):
        self.listed = staff_list(detect=(1, 19))
        _, _, reasons = self.drive(self.LIFE, limit=80, done=lambda policy, raw, key: (
            key.startswith(">") or any(name == DETECTION for name, _ in self.bought)))
        # Unfixed: the run bought its recall and oil and descended with one
        # charge against the six detections it needs.
        self.assertIn((DETECTION, 5), self.bought, reasons[-6:])


if __name__ == "__main__":
    import unittest
    unittest.main()
