"""The hungry Magic-Eater's Tower trip is not held behind a Home equipment session.

n1-b life-410 (Lv50 zombie Magic-Eater, build 1f6038371) stopped on
town:blocked:stage-deadline:buy (2026-11-16 22:09:54).  Back from 54F with the staple
(謎の魔法棒, 0 charges) drained, the staff sequence took the inn to Morivant for the Tower of
Sorcery (row 1, 273,766 gold).  From the first Morivant board the optimizer's Home equipment
session (8 actions, context home, next a Home withdraw) was open, and ``me_staff_sequence
.town_key`` yields every board to such a session (#47 n1-c life-054).  HP 479/1153 rested
(town:recover, rows 2-3), the rest made the character hungry, and the mana override handed the
hunger to the Tower (``tower_feeds_staple``) - whose sequence still yielded.  The generic
survival gate then walked onto the Magic shop (row 4 survival:shop-travel), whose purchase
defers to the Home device (survival:mana-home-before-purchase): survival:shop-approach /
shop:observe-and-leave alternated 18 times until the stage deadline.

Fix (me_staff_sequence.town_key): the yield to the Home session does not hold the hunger's
Tower trip (hungry and ``tower_feeds_staple``); survival comes before the equipment work.

Recorded: the capture's town-arrival checkpoint and journal rows 0-6
(tests/extract_n1b_410_tower_hunger_1116_fixture.py), replayed through the public
``choose_key``.  DECLARED RECONSTRUCTED: the capture omits session objects; the Home session is
built from the decision row's ``transaction_next`` (a Home withdraw, context home), as in
test_me_nokey_1031_recorded, and opened after row 1 as in the live log (the row-2235 decision
shows ``transaction_actions`` 0 before it, 8 from row 2236 on).  The checkpoint's restart
rejects the dump calibration that opened the live session, so the replay builds it itself.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import me_staff_sequence
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-410-tower-hunger-1116"
MORIVANT = 2
HUNGRY_BOARD = 4  # the first hungry Morivant board (live: survival:shop-travel to the Magic shop)
# The decision rows 2236-2295's equipment_optimization.transaction_next.
NEXT_ACTION = {"phase": "home_prepare", "kind": "withdraw",
               "item_id": "home:1927f63afdb24de9:0", "target_slot": None}


def home_session() -> EquipmentTransactionSession:
    action = EquipmentTransaction(**NEXT_ACTION, item_identity="1927f63afdb24de9")
    return EquipmentTransactionSession(EquipmentTransactionPlan((action,), (), 23),
                                       physical_context="home")


class N1b410TowerHunger1116RecordedTest(unittest.TestCase):
    def replay(self, upto: int):
        """(policy, rows) after rows 0..upto-1 decided as recorded, the session open from row 2."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, self.journal, rows = load(FIXTURE, Path(scratch.name))
        self.addCleanup(lambda: policy._home_disposal.history_path.unlink(missing_ok=True))
        for index, (recorded, supply) in enumerate(rows[:upto]):
            if index == 2:
                policy._equipment_transaction_session = home_session()
            board = supply()
            key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                             recorded["row"])
            policy.confirm_key_posted(key)
        if upto == 2:
            policy._equipment_transaction_session = home_session()
        return policy, rows

    def test_capture_pins_the_journal(self):
        policy, rows = self.replay(0)
        reasons = [row[0]["reason"] for row in rows]
        self.assertEqual(reasons[:6], ["periodic:character-dump", "me-staff:travel-morivant",
                                       "town:recover", "town:recover", "survival:shop-travel",
                                       "shop:observe-and-leave"])

    def test_hungry_board_goes_to_the_tower_despite_the_home_session(self):
        policy, rows = self.replay(HUNGRY_BOARD)
        board = rows[HUNGRY_BOARD][1]()
        self.assertEqual(board.town_id, MORIVANT)
        self.assertTrue(board.player.hungry)
        self.assertEqual(me_staff_sequence.staple_food(board).charges, 0)
        session = policy._equipment_transaction_session
        self.assertFalse(session.complete)
        self.assertEqual(session.required_context, "home")
        self.assertTrue(me_staff_sequence.tower_feeds_staple(policy, board))
        key = policy.choose_key(board)
        # Live (build 1f6038371): survival:shop-travel '\x1b`n&.' to the Magic shop.
        self.assertEqual(policy.last_reason, "me-staff:approach-tower", key)
        self.assertTrue(key.startswith("\x1b`n"), key)

    def test_not_hungry_still_waits_for_the_home_session(self):
        """Rows 2-3 (HP 479, not hungry) keep the life-054 yield: the replay matched them."""
        policy, rows = self.replay(2)
        board = rows[2][1]()
        self.assertFalse(board.player.hungry)
        self.assertIsNone(me_staff_sequence.town_key(policy, board, []))

    def test_hungry_without_the_tower_fare_still_waits_for_the_home_session(self):
        """DECLARED CONSTRUCTED: gold below the recharge and the fare home."""
        policy, rows = self.replay(HUNGRY_BOARD)
        board = rows[HUNGRY_BOARD][1]()
        board = replace(board, player=replace(board.player, gold=100))
        self.assertFalse(me_staff_sequence.tower_feeds_staple(policy, board))
        self.assertIsNone(me_staff_sequence.town_key(policy, board, []))


if __name__ == "__main__":
    unittest.main()
