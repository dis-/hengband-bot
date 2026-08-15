from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from hengbot.equipment_mutation import (
    EquipmentMutationExecutor,
    EquipmentMutationState,
    progress_core,
)


def item(slot, name, *, tval=20, count=1, melee=False, digger=False):
    return SimpleNamespace(
        slot=slot, name=name, tval=tval, sval=0, count=count, charges=0,
        inscription="", known=True, fully_known=True, is_equipment=True,
        is_melee_weapon=melee, is_digging_tool=digger,
    )


def board(*, equipment=(), inventory=(), gold=0, exp=0):
    return SimpleNamespace(
        equipment=list(equipment), inventory=list(inventory),
        player=SimpleNamespace(gold=gold, exp=exp),
    )


SLOTS = {"main_hand": "a", "sub_hand": "b"}


class EquipmentMutationExecutorTest(unittest.TestCase):
    def test_observed_hand_tail_table(self):
        tool = item("s", "Shovel", digger=True)
        empty = board(inventory=(tool,))
        self.assertEqual(
            EquipmentMutationExecutor().request_wield(
                empty, "mining-loadout", tool, "main_hand", SLOTS
            ).key, "ws"
        )
        main = item("main_hand", "Sword", tval=23, melee=True)
        self.assertEqual(
            EquipmentMutationExecutor().request_wield(
                board(equipment=(main,), inventory=(tool,)),
                "mining-loadout", tool, "sub_hand", SLOTS,
            ).key, "wsy"
        )
        sub = item("sub_hand", "Sword", tval=23, melee=True)
        self.assertEqual(
            EquipmentMutationExecutor().request_wield(
                board(equipment=(sub,), inventory=(tool,)),
                "mining-loadout", tool, "main_hand", SLOTS,
            ).key, "wsy"
        )
        self.assertEqual(
            EquipmentMutationExecutor().request_wield(
                board(equipment=(main, sub), inventory=(tool,)),
                "mining-loadout", tool, "sub_hand", SLOTS,
            ).key, "wsb"
        )

    def test_posted_serialization_releases_loudly_at_eight(self):
        ex = EquipmentMutationExecutor()
        snap = board(inventory=(item("s", "Shovel", digger=True),))
        first = ex.request_takeoff(snap, "transaction-apply", "a")
        ex.bind_post_snapshot(snap)
        self.assertTrue(ex.confirm_posted(first.key))
        for _ in range(7):
            self.assertEqual(
                ex.request_takeoff(snap, "transaction-apply", "a").report,
                "posting-contract:equipment-mutation-unobserved",
            )
        released = ex.request_takeoff(snap, "transaction-apply", "a")
        self.assertEqual(
            released.report, "posting-contract:equipment-mutation-released"
        )
        self.assertEqual(ex.state, EquipmentMutationState.IDLE)

    def test_observed_confirmation_resets_cleanly(self):
        ex = EquipmentMutationExecutor()
        before = board(equipment=(item("main_hand", "Sword", tval=23),))
        result = ex.request_takeoff(before, "transaction-apply", "a")
        ex.bind_post_snapshot(before)
        ex.confirm_posted(result.key)
        after = board(inventory=(item("a", "Sword", tval=23),))
        ex.observe(after)
        self.assertEqual(ex.state, EquipmentMutationState.IDLE)
        self.assertEqual(ex.refusals, 0)

    def test_stacked_split_is_not_progress_and_gold_is(self):
        stacked = board(inventory=(item("s", "Shovel", count=2, digger=True),))
        split = board(
            equipment=(item("main_hand", "Shovel", digger=True),),
            inventory=(item("s", "Shovel", count=1, digger=True),),
        )
        self.assertEqual(progress_core(stacked), progress_core(split))
        ex = EquipmentMutationExecutor()
        result = ex.request_wield(
            stacked, "mining-loadout", stacked.inventory[0], "main_hand", SLOTS
        )
        ex.bind_post_snapshot(stacked)
        ex.confirm_posted(result.key)
        ex.observe(split)
        refused = ex.request_takeoff(split, "combat-loadout", "a")
        self.assertEqual(refused.report, "goal-already-superseded")
        progressed = board(
            equipment=split.equipment, inventory=split.inventory, gold=1
        )
        self.assertIsNotNone(
            ex.request_takeoff(progressed, "combat-loadout", "a").key
        )

    def test_restart_immunity(self):
        snap = board(equipment=(item("main_hand", "Sword", tval=23),))
        keys = [
            EquipmentMutationExecutor().request_takeoff(
                snap, "transaction-apply", "a"
            ).key
            for _ in range(2)
        ]
        self.assertEqual(keys, ["ta", "ta"])

    def test_policy_has_no_direct_wield_or_takeoff_composition(self):
        path = Path(__file__).parents[1] / "src" / "hengbot" / "policy.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        forbidden = {"WIELD_KEY", "TAKEOFF_KEY"}
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertFalse(names & forbidden)
        direct = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Add)
            and isinstance(node.left, ast.Constant)
            and node.left.value in {"w", "t"}
        ]
        self.assertEqual(direct, [])


if __name__ == "__main__":
    unittest.main()
