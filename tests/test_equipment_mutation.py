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
from hengbot.model import TVAL_CAPTURE


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

    def test_capture_with_sub_melee_uses_sub_melee_first_branch(self):
        capture = item("c", "Capture Ball", tval=TVAL_CAPTURE)
        main = item("main_hand", "Shield", tval=34)
        sub = item("sub_hand", "Sword", tval=23, melee=True)
        self.assertEqual(
            EquipmentMutationExecutor().request_wield(
                board(equipment=(main, sub), inventory=(capture,)),
                "transaction-apply", capture, "main_hand", SLOTS,
            ).key,
            "wc",
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

    def test_non_opposing_post_does_not_erase_flip_memory(self):
        ex = EquipmentMutationExecutor()
        snap = board(inventory=(item("s", "Shovel", digger=True),))
        mining = ex.request_takeoff(snap, "mining-loadout", "a")
        ex.bind_post_snapshot(snap)
        ex.confirm_posted(mining.key)
        ex.observe(board(equipment=(item("main_hand", "Shovel", digger=True),)))
        light = ex.request_takeoff(snap, "light-loadout", "g")
        ex.bind_post_snapshot(snap)
        ex.confirm_posted(light.key)
        self.assertEqual(ex.last_posted_goal, "mining-loadout")

    def test_policy_has_no_direct_wield_or_takeoff_composition(self):
        root = Path(__file__).parents[1] / "src" / "hengbot"
        for filename in ("policy.py", "cli.py", "home_errand.py"):
            tree = ast.parse((root / filename).read_text(encoding="utf-8"))
            forbidden = {"WIELD_KEY", "TAKEOFF_KEY"}
            names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
            self.assertFalse(names & forbidden, filename)

            def has_key_literal(node):
                return any(
                    isinstance(part, ast.Constant) and part.value in {"w", "t"}
                    for part in ast.walk(node)
                )

            composers = []
            for node in ast.walk(tree):
                if isinstance(node, ast.JoinedStr) and has_key_literal(node):
                    composers.append(node)
                elif isinstance(node, ast.AugAssign) and has_key_literal(node.value):
                    composers.append(node)
                elif isinstance(node, ast.BinOp) and isinstance(
                    node.op, (ast.Add, ast.Mod)
                ) and has_key_literal(node):
                    composers.append(node)
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "join"
                    and has_key_literal(node.func.value)
                ):
                    composers.append(node)
            self.assertEqual(composers, [], filename)


if __name__ == "__main__":
    unittest.main()
