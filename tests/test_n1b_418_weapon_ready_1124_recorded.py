"""n1-b life-418: town:blocked:survival:combat_weapon_ready after the Tower of Sorcery trip.

What happened (2026-11-24 22:06:08, build bot-b6ea13b5d, Lv17 Zombie Magic-Eater): a fundraising
mining run came back to the outpost with シャベル in both hands and ウォー・ハンマー in the pack;
the visit's equipment transaction (deposit, take the shovels off, wield the hammer) waited on the
run's lending of the hands.  The visit went to Morivant's Tower of Sorcery twice (me-staff,
quest-request); each trip came back by the inn teleport leg ('1ma', me-staff:return-outpost),
whose claim is a cell Reach of the Morivant building (43,92) with the declared effect ``town:0``.
Every town is floor (0, 0, 0), so on the outpost's board that Reach was never reached and the
leg's claim stayed the town's holder: on the first landing (row 64) the held decision's WAIT
was rewritten to an entrance step-off; on the second (row 148) the departure's question ended
the lending, the equipment transaction's walk to Home yielded to ``town-hold:quest-request`` and
the town end stopped on the combat_weapon_ready leaf -- necessary work that was possible.

The leg's declared effect is its completion (town_hold ``teleport_leg_landed``): the landing
closes the claim and the owners answer.

Recorded: the capture's town-arrival checkpoint (tests/extract_n1b_418_weapon_ready_1124_fixture.py,
149 journal rows, the stop is the last), decided through the public ``choose_key`` with the
recorded keys posted.

DECLARED CONSTRUCTED: the character calibration re-adopted after row 2.  The periodic dump of
row 1 is answered from the dump file the live bot wrote then, which the checkpoint does not
hold (its sidecar is the earlier dump, read as stale-dump-file); the checkpoint's own Lv17
calibration of the same character is adopted in its place, as the live board had one.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import equipment_target
from replay_town_arrival import adopt_calibration
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-418-weapon-ready-1124"
STOP_REASON = "town:blocked:survival:combat_weapon_ready"
FIRST_LANDING, SECOND_LANDING = 64, 148
CHANGED_ROWS = {FIRST_LANDING, FIRST_LANDING + 1, SECOND_LANDING}


class N1b418WeaponReadyRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with TemporaryDirectory() as raw:
            scratch = Path(raw)
            with contextlib.redirect_stdout(io.StringIO()):
                policy, _journal, steps = load(FIXTURE, scratch)
            calibration = scratch / "calibration.json"
            shutil.copy(scratch / "town-arrival" / "sidecars" / "_character_calibration_path",
                        calibration)
            cls.rows = []
            for recorded, supply in steps:
                board = supply()
                if recorded["row"] == 2:
                    # DECLARED CONSTRUCTED (module docstring): the checkpoint's calibration.
                    adopt_calibration(policy, calibration, scratch)
                    policy._calibration_rejection = None
                    policy._calibration_unavailable_reason = None
                    equipment_target.invalidate_loadout_search(policy)
                with contextlib.redirect_stdout(io.StringIO()):
                    key = policy.choose_key(board)
                cls.rows.append((recorded, key, policy.last_reason, board,
                                 policy._equipment_transaction_session))
                if recorded["key"]:
                    policy.confirm_key_posted(recorded["key"])
            cls.catalog = {item.id: item.item.name for item in policy._equipment_catalog.items}
            policy._home_disposal.history_path.unlink(missing_ok=True)

    def test_the_visit_replays_unchanged_but_the_two_landings(self):
        self.assertEqual(len(self.rows), SECOND_LANDING + 1)
        for recorded, key, reason, *_rest in self.rows:
            if recorded["row"] in CHANGED_ROWS:
                continue
            self.assertEqual((key, reason), (recorded["key"], recorded["reason"]),
                             recorded["row"])
        recorded, _key, _reason, board, *_rest = self.rows[SECOND_LANDING]
        self.assertEqual(recorded["reason"], STOP_REASON)
        hands = {item.slot: item.name for item in board.equipment
                 if item.slot in ("main_hand", "sub_hand")}
        self.assertTrue(hands and all("シャベル" in name for name in hands.values()), hands)
        self.assertTrue(any("ウォー・ハンマー" in item.name for item in board.inventory))
        for row in (FIRST_LANDING, SECOND_LANDING):
            # Each landing follows the inn teleport leg back from Morivant to the outpost.
            leg, landing = self.rows[row - 1], self.rows[row]
            self.assertEqual((leg[0]["key"], leg[0]["reason"]), ("1ma", "me-staff:return-outpost"))
            self.assertEqual((leg[3].town_id, landing[3].town_id), (2, 0))

    def test_the_first_landing_resumes_the_plan_instead_of_a_held_step_off(self):
        """Before the fix: town:entrance-step-off:policy:none-wait (the hold's WAIT rewritten)."""
        _recorded, key, reason, *_rest = self.rows[FIRST_LANDING]
        self.assertEqual((key, reason), ("\x1b`n(.", "shop:travel"))

    def test_the_second_landing_walks_home_to_wield_the_hammer(self):
        """Before the fix: town:blocked:survival:combat_weapon_ready (a policy final stop)."""
        _recorded, key, reason, _board, session = self.rows[SECOND_LANDING]
        self.assertFalse(reason.startswith("town:blocked:"), reason)
        self.assertEqual((key, reason), ("\x1b`n(.", "equipment-transaction:travel-home"))
        self.assertIsNotNone(session)
        wielded = [self.catalog.get(action.item_id, action.item_id)
                   for action in session.plan.actions
                   if (action.kind, action.target_slot) == ("equip", "main_hand")]
        self.assertTrue(wielded and all("ウォー・ハンマー" in name for name in wielded), wielded)


if __name__ == "__main__":
    unittest.main()
