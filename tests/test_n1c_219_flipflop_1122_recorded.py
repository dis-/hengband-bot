"""n1-c life-219: the failed transaction's restoration wore the mining shovel over ★ノートゥング.

Owner 2026-11-22 「決まりは足さず、着け直しを記録。往復が起きたら停止して直す。」 and Q6 (after a
temporary swap - mining, a quest, Zul - the visit's target-loadout weapon is worn).

What happened (2026-11-22 01:34, build bot-28c801fdd, jsonlog/equipment-visit.jsonl): fund-raising
by mining, the bot wore a シャベル in both hands (policy_equipment._wield_digging_tool_key).  Back
in town the equipment transaction (target loadout a7b0bed1776816ae) took both shovels off, wore
ノートゥング and the large shield (_equipment_transaction_town_key) and went Home to deposit the
two shovels, one deposit per physical shovel.  The pack held them as one stack of two and the
first deposit stored the stack ('dk2'); the second found nothing (deposit-missing) and the session
was abandoned.  The abandonment (_abandon_blocked_equipment_transaction) restores the gear the
session took off: one (shovel, main_hand) ownership was left, so it withdrew a shovel and wore it
into main_hand over ノートゥング ('wna', _equipment_transaction_home_key): main_hand
shovel -> ノートゥング -> shovel, town:blocked:equipment-slot-flipflop:main_hand.

Recorded: the visit's town-arrival checkpoint (20261122-013425, turn 1661079) and its 31 journal
rows, replayed through the public ``choose_key``.  The boards after the abandonment (row 19) are
those of the old restoration, so past it only what the policy holds is compared.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-219-flipflop-1122"
SHOVEL = "6014bec50c328225"
ABANDON_ROW = 19
WEAR_ROW = 29


def _replay(last_row: int):
    """[(row, recorded, key, reason, owned items, restoring)] of rows 0..last_row."""
    with TemporaryDirectory() as raw:
        policy, _journal, steps = load(FIXTURE, Path(raw))
        rows = []
        for recorded, supply in steps[:last_row + 1]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            rows.append((recorded["row"], recorded, key, policy.last_reason,
                         list(policy._equipment_transaction_owned_items),
                         policy._equipment_transaction_restoring, board))
            if key:
                policy.confirm_key_posted(key)
        policy._home_disposal.history_path.unlink(missing_ok=True)
    return rows


class N1c219FlipflopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = _replay(WEAR_ROW)

    def test_the_visit_replays_unchanged_up_to_the_failed_deposit(self):
        for row, recorded, key, reason, *_ in self.rows[:ABANDON_ROW + 1]:
            self.assertEqual((key, reason), (recorded["key"], recorded["reason"]), row)
        # The second shovel deposit found the stack already stored.
        self.assertEqual(self.rows[14][2], "dk2\r")
        self.assertEqual(self.rows[ABANDON_ROW][3], "equipment-transaction:deposit-missing")
        board = self.rows[ABANDON_ROW][6]
        main = next(item for item in board.equipment if item.slot == "main_hand")
        self.assertIn("ノートゥング", main.name)

    def test_the_abandonment_restores_nothing_over_the_worn_target_weapon(self):
        """Before the fix (SHOVEL, main_hand) stayed owned, the restoration withdrew the shovel
        ('pZ1') and wore it into main_hand ('wna' at row 29)."""
        _row, _recorded, _key, _reason, owned, restoring, _board = self.rows[ABANDON_ROW]
        self.assertEqual(owned, [])
        self.assertFalse(restoring)
        for row, _recorded, key, reason, owned, restoring, _board in self.rows[ABANDON_ROW:]:
            self.assertNotIn((SHOVEL, "main_hand"), owned, row)
            self.assertFalse(restoring, row)
            self.assertNotEqual(reason, "equipment-transaction:restore-blocked-terminal", row)
            self.assertFalse(reason.startswith("town:blocked:equipment-slot-flipflop"), row)
            self.assertFalse(key is not None and key.startswith("w")
                             and reason.startswith("equipment-transaction:"), (row, key, reason))


if __name__ == "__main__":
    unittest.main()
