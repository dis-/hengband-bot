"""Round-7 value pin for calibration restore identity cleanup.

Run with PYTHONPATH=src;tests.  The test drives the public choose_key path on
one policy instance: two calibration deposits are batch-restored, then a
redress obligation for two identical Home copies must remain addressable.
"""

import unittest
from dataclasses import replace

import test_policy_calibration as fixtures
from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.model import STORE_HOME, StoreState


def sword(letter, bonus, *, store=False, known_flags=frozenset()):
    common = dict(
        count=1,
        name=f"Dagger (1d4) (+{bonus},+0)",
        to_h=bonus,
        is_equipment=True,
        damage_dice_num=1,
        damage_dice_sides=4,
        known=True,
        fully_known=True,
        known_flags=known_flags,
    )
    if store:
        return fixtures.store_item(letter, 23, 4, **common)
    return fixtures.item(letter, 23, 4, **common)


class RoundSevenIdentityCleanupPin(fixtures.CharacterCalibrationPhaseTest):
    def test_batch_cleanup_then_redress_twins_compose_withdrawal(self):
        policy = self._scan_complete_policy()
        first = sword("a", 21)
        second = sword("b", 18)
        base = self._snapshot(inventory=(first, second))
        entrance = replace(base, player=replace(base.player, position=self.HOME))

        policy._calibration_phase = "deposit"
        policy.consume_home_knowledge(())
        policy._shopping_approach_store_type = STORE_HOME
        policy._shopping_approach_goal = self.HOME
        self.assertEqual(policy.choose_key(entrance), "5")
        empty_home = replace(
            entrance,
            store=StoreState(STORE_HOME, [], stock_num=0, page_size=52),
        )
        self.assertEqual(policy.choose_key(empty_home), "dbda\x1b")
        policy.choose_key(replace(entrance, inventory=[], turn=1))

        deposited = [
            sword("a", 21, store=True),
            sword("b", 18, store=True),
        ]
        policy.consume_home_knowledge(tuple(deposited))
        policy._calibration_phase = "restore-supplies"
        policy._shopping_approach_store_type = STORE_HOME
        policy._shopping_approach_goal = self.HOME
        restore_entrance = replace(entrance, inventory=[], turn=2)
        self.assertEqual(policy.choose_key(restore_entrance), "5")
        restore_page = replace(
            restore_entrance,
            turn=3,
            store=StoreState(STORE_HOME, deposited, stock_num=2, page_size=52),
        )
        self.assertEqual(policy.choose_key(restore_page), "pbpa\x1b")
        policy.consume_home_knowledge(())
        policy._calibration_blocked_this_visit = True
        restored = [sword("a", 21), sword("b", 18)]
        policy.choose_key(replace(restore_entrance, inventory=restored, turn=4))

        self.assertIsNone(policy._calibration_phase)
        self.assertEqual(policy._calibration_restore_signatures, [])
        self.assertEqual(policy._calibration_restore_move_identities, {})
        self.assertEqual(policy._home_pending_quantities, {})

        learned_flags = frozenset({"ACTIVATE"})
        redress_pack_item = sword("a", 21, known_flags=learned_flags)
        redress_item = replace(redress_pack_item, slot="a")
        owner = policy._item_signature(redress_item)
        # Model the legacy stale entry that round 6 could persist.  Its value
        # itself came from the public deposit/restore path above; redress must
        # reject it before matching the changed known fields below.
        policy._calibration_restore_move_identities[owner] = (
            equipment_move_identity(restored[0])
        )
        policy._calibration_worn_before = (
            ("main_hand", equipment_identity(redress_pack_item)),
        )
        policy._calibration_stripped_unrestored = True
        policy._calibration_blocked_this_visit = False
        twins = (
            redress_item,
            replace(redress_pack_item, slot="b"),
        )
        policy.consume_home_knowledge(twins)
        policy._calibration_phase = None
        self.assertEqual(
            equipment_identity(policy._home_knowledge_items[0]),
            equipment_identity(redress_pack_item),
        )
        self.assertTrue(policy._equipment_catalog.home_scan_complete)

        redress_entrance = replace(restore_entrance, inventory=[], turn=5)
        self.assertTrue(policy._calibration_stripped_unrestored)
        self.assertEqual(
            policy._calibration_redress_accounting(redress_entrance)[2],
            [("main_hand", equipment_identity(redress_pack_item))],
        )
        self.assertEqual(policy.choose_key(redress_entrance), "5")
        policy._calibration_redress_observe(redress_entrance)
        self.assertIn(owner, policy._calibration_restore_signatures)
        self.assertNotIn(owner, policy._calibration_restore_move_identities)
        redress_page = replace(
            redress_entrance,
            turn=6,
            store=StoreState(STORE_HOME, list(twins), stock_num=2, page_size=52),
        )
        key = policy.choose_key(redress_page)
        self.assertEqual(key, "pb\x1b", policy.last_reason)
        self.assertEqual(policy.last_reason, "home:atomic-withdraw")
        self.assertNotEqual(
            policy.last_reason, "home:atomic-withdraw-target-unobserved"
        )
        print(
            "r7-pin batch phase=None restore=[] ids={} qty={}; "
            "redress key='pb\\x1b' reason=home:atomic-withdraw"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
