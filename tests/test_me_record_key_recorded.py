"""#47 N1: a non-stage staff the staff sequence absorbed reads as absorbed.

The absorption record keyed the stage staffs by their int sval and every
other device by "kind:sval" (me_device_policy ``Device.key``), while the
readers of a staff's absorption (``me_powers.recorded_charges`` ->
``me_staff_sequence.absorbed_charges``, ``me_absorbed_substitutes.held``)
looked only at the int keys.  So a staff outside the stages that the Tower
recharged and absorbed (an ``absorb_after_charge`` row: Speed, *Destruction*,
Healing, Power, Holiness, Genocide, Mana Storm) read as not absorbed until a
staff list was displayed again, and the device policy table kept charging
its next copy first (``charge_first``: 「持ち帰ってチャージしてから取り込む」
was for a kind not yet absorbed unless the row says 「2本目以降も買う」).
Owner 2026-11-07 「2本目以降も充填して取り込み、上限を増やす」: every copy is
charged and absorbed now, so the record's count is what stops it (the cap).

Board: the recorded D24 Tower board with the stage-2 staffs of
test_me_stage2_staffs and a Staff of Genocide (``absorb_after_charge``
without ``buy_more``; the D24 Identify staff row with sval 27 and 3
charges) added, DECLARED CONSTRUCTED as test_me_device_policy's Speed case;
after the recorded flow absorbs it at the Tower (the production executor
answers every posted key), a second Genocide staff (the same row) is put in
the pack (DECLARED CONSTRUCTED).  No staff list is displayed after the
absorption, so the record is the only evidence.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import unittest

from hengbot import me_device_policy as table
from hengbot import me_staff_sequence as sequence
from hengbot.model import TVAL_STAFF, parse_snapshot
from tests import test_me_device_policy as device_policy

GENOCIDE = 27  # BaseitemDefinitions 抹殺の杖 (absorb_after_charge only)
NAME = "抹殺の杖 (3回分)"


class AbsorbedExtraStaffRecordedTest(device_policy.AfterChargeTowerTest):
    # The Speed and wand cases run there.
    test_the_staff_is_recharged_and_absorbed_after_the_stage = None
    test_absorbed_stone_to_mud_copies_are_recharged_and_absorbed = None
    test_every_stack_of_an_absorbed_kind_is_absorbed = None
    test_absorbed_teleport_other_copy_is_recharged_and_absorbed = None
    test_a_power_at_its_count_cap_takes_no_more_copies = None

    def absorbed_genocide(self):
        policy, raw, steps = self.absorb_after_stage(GENOCIDE, NAME)
        full = sequence.morivant_tower.device_definitions()[(TVAL_STAFF, GENOCIDE)][0]
        self.assertEqual(steps[-2:], ["me-staff:stage2-complete", ("absorb", TVAL_STAFF, GENOCIDE, full)])
        lists = getattr(policy, "_me_device_lists", {}) or {}
        self.assertFalse(any(row.get("name") in table.devices()[(TVAL_STAFF, GENOCIDE)].names
                             for _, rows in lists.values() for row in rows))
        return policy, raw

    def test_the_record_count_bounds_the_next_copy(self):
        """Owner 2026-11-07: the next copy is charged and absorbed too, until the
        count the record holds under "staff:27" is at the cap."""
        policy, raw = self.absorbed_genocide()
        board = parse_snapshot(copy.deepcopy(raw), self.knowledge)
        row = table.devices()[(TVAL_STAFF, GENOCIDE)]
        self.assertTrue(table.charge_first(policy, board, row))
        record = sequence.state(policy)
        record.absorbed = {**record.absorbed, f"staff:{GENOCIDE}": table.POWER_COUNT_CAP}
        # Unfixed (the record's "staff:27" not read for a staff): True.
        self.assertFalse(table.charge_first(policy, board, row))

    def test_a_second_copy_keeps_the_tower_visit(self):
        """Owner 2026-11-07 「2本目以降も充填して取り込み、上限を増やす」 (it was
        me-staff:return-outpost before)."""
        policy, raw = self.absorbed_genocide()
        second = copy.deepcopy(next(it for it in device_policy.d24.MeTowerRechargeRecordedTest.case[
            "approach"]["inventory"] if (it["tval"], it["sval"]) == (TVAL_STAFF, sequence.SV_STAFF_IDENTIFY)))
        second.update(sval=GENOCIDE, name=NAME, charges=3, pval=3)
        raw = copy.deepcopy(raw)
        raw["inventory"].append(second)
        raw["inventory"].sort(key=lambda it: (-it["tval"], it["sval"]))
        for index, item in enumerate(raw["inventory"]):
            item["slot"] = chr(ord("a") + index)
        self.decide(policy, raw)
        self.assertEqual(policy.last_reason, "me-staff:recharge-all")


if __name__ == "__main__":
    unittest.main()
