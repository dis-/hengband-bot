"""n1-b life-414 / n1-c life-220: town:blocked:survival:combat_weapon_ready with a mining run's
shovels in hand.

What happened (2026-11-22; the server halts Lv30+ on the first stop): a staff stock-out mining
run came back to town with diggers in the hands and the combat weapon in the pack.  The run's
return lent the hands to mining (mining_loadout.hands_lent, n1-c life-220's fix 43d5052ea): the
town re-arm and the visit's swap held.  On the last board the recall departure's question
(policy_town ``_town_special_key`` -> ``_recall_town_departure_conjuncts`` ->
``_combat_weapon_ready``) ended the lending -- after the re-arm's and the swap's rungs had
already declined the board -- and the town end read the departure minimum: its
combat_weapon_ready leaf stopped the bot.  The lending's end is the departure asking for the
weapon; the hands' owner must answer that same board.

- n1-b life-414 (08:48:28, build bot-ede1d0935, Lv31 Magic-Eater): シャベル / ドワーフのシャベル
  in the hands, (防衛者)モーニング・スター in the pack; 13 journal rows.
- n1-c life-220 (09:15:54, build e7f776dd7, Lv30 Magic-Eater): シャベル in both hands and
  ★ブロード・スピア『グングニル』 to wear again, after the Tower of Sorcery's recharge
  (me-staff:return-outpost); 83 journal rows.

Recorded: each visit's town-arrival checkpoint and its journal rows
(tests/extract_n1b_414_weapon_ready_1122_fixture.py), replayed through the public ``choose_key``.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
STOP_REASON = "town:blocked:survival:combat_weapon_ready"


class _WeaponReadyRecorded:
    FIXTURE: Path
    STOP_ROW: int
    WEAPON: str

    @classmethod
    def setUpClass(cls):
        with TemporaryDirectory() as raw:
            policy, _journal, steps = load(cls.FIXTURE, Path(raw))
            cls.rows = []
            for recorded, supply in steps:
                board = supply()
                with contextlib.redirect_stdout(io.StringIO()):
                    key = policy.choose_key(board)
                cls.rows.append((recorded, key, policy.last_reason, board,
                                 policy._equipment_transaction_session))
                if key:
                    policy.confirm_key_posted(key)
            cls.catalog = {item.id: item.item.name for item in policy._equipment_catalog.items}
            policy._home_disposal.history_path.unlink(missing_ok=True)

    def test_the_visit_replays_unchanged_up_to_the_stop(self):
        self.assertEqual(len(self.rows), self.STOP_ROW + 1)
        for recorded, key, reason, _board, _session in self.rows[:self.STOP_ROW]:
            self.assertEqual((key, reason), (recorded["key"], recorded["reason"]),
                             recorded.get("decision_sequence"))
        recorded, _key, _reason, board, _session = self.rows[self.STOP_ROW]
        self.assertEqual(recorded["reason"], STOP_REASON)
        hands = {item.slot: item.name for item in board.equipment
                 if item.slot in ("main_hand", "sub_hand")}
        self.assertTrue(hands and all("シャベル" in name for name in hands.values()), hands)

    def test_the_lendings_end_lets_the_swap_take_the_hands_on_the_same_board(self):
        """Before the fix: town:blocked:survival:combat_weapon_ready (a policy final stop)."""
        _recorded, key, reason, _board, session = self.rows[self.STOP_ROW]
        self.assertFalse(reason.startswith("town:blocked:"), reason)
        self.assertEqual((key, reason), ("tb", "equipment-transaction:takeoff"))
        self.assertIsNotNone(session)
        wielded = [self.catalog.get(action.item_id, action.item_id)
                   for action in session.plan.actions
                   if (action.kind, action.target_slot) == ("equip", "main_hand")]
        self.assertTrue(wielded and all(self.WEAPON in name for name in wielded), wielded)


class N1b414WeaponReadyRecordedTest(_WeaponReadyRecorded, unittest.TestCase):
    FIXTURE = FIXTURES / "n1b-414-weapon-ready-1122"
    STOP_ROW = 12
    WEAPON = "モーニング・スター"


class N1c220WeaponReadyRecordedTest(_WeaponReadyRecorded, unittest.TestCase):
    FIXTURE = FIXTURES / "n1c-220-weapon-ready-1122"
    STOP_ROW = 82
    WEAPON = "グングニル"


if __name__ == "__main__":
    unittest.main()
