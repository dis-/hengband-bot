from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
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
    @staticmethod
    def _direct_key_composers(tree):
        """Catch the explicit string forms covered by the ownership ratchet.

        This intentionally covers literals, f-strings, +/%, join, += after a
        literal string seed (including transitive ``+=``), and str.format.
        Dynamically encoding ``w``/``t`` (for
        example chr(119)) is outside this syntax ratchet.
        """
        def exact_key(node):
            return isinstance(node, ast.Constant) and node.value in {"w", "t"}

        def percent_key(node):
            return (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value[:2] in {"w%", "t%"}
            )

        seeded = {
            target.id
            for assignment in ast.walk(tree)
            if isinstance(assignment, (ast.Assign, ast.AnnAssign))
            for target in (
                assignment.targets if isinstance(assignment, ast.Assign)
                else (assignment.target,)
            )
            if isinstance(target, ast.Name)
            and isinstance(assignment.value, ast.Constant)
            and isinstance(assignment.value.value, str)
        }
        composers = []
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr) and any(
                exact_key(part) for part in ast.walk(node)
            ):
                composers.append(node)
            elif (
                isinstance(node, ast.AugAssign)
                and isinstance(node.op, ast.Add)
                and isinstance(node.target, ast.Name)
                and node.target.id in seeded
            ):
                composers.append(node)
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) and any(
                exact_key(part) for part in ast.walk(node)
            ):
                composers.append(node)
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and percent_key(
                node.left
            ):
                composers.append(node)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "join" and any(
                    exact_key(part) for arg in node.args for part in ast.walk(arg)
                ):
                    composers.append(node)
                elif (
                    node.func.attr == "format"
                    and isinstance(node.func.value, ast.Constant)
                    and isinstance(node.func.value.value, str)
                    and any(exact_key(part) for arg in node.args for part in ast.walk(arg))
                ):
                    composers.append(node)
        return composers

    def test_observed_hand_tail_table(self):
        tool = item("s", "Shovel", digger=True)
        empty = board(inventory=(tool,))
        self.assertEqual(
            EquipmentMutationExecutor().request_wield(
                empty, "mining-loadout", tool, "main_hand", SLOTS
            ).key, "ws"
        )
        impossible = EquipmentMutationExecutor().request_wield(
            empty, "calibration-redress", tool, "sub_hand", SLOTS
        )
        self.assertIsNone(impossible.key)
        self.assertEqual(impossible.report, "sub-hand-requires-main-hand")
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

    def test_cosmetic_worn_changes_do_not_complete_a_posted_wield(self):
        # Recorded 2026-09-10 destroy-superior-digger boards 2105-2109: a
        # combat re-wield was posted while only the worn lantern's fuel figure
        # changed.  Neither that nor an inscription/learned-flag suffix is
        # the wield's effect.
        shovel = item("main_hand", "Shovel (1d2)", tval=20, digger=True)
        lantern = item("light", "Brass Lantern (5146 turns of light)", tval=39)
        sword = item("n", "Sword", tval=23, melee=True)
        before = board(equipment=(shovel, lantern), inventory=(sword,))
        ex = EquipmentMutationExecutor()
        posted = ex.request_wield(before, "combat-loadout", sword, "main_hand", SLOTS)
        ex.bind_post_snapshot(before)
        self.assertTrue(ex.confirm_posted(posted.key))
        cosmetic = [
            board(
                equipment=(
                    shovel,
                    SimpleNamespace(
                        **{**vars(lantern), "name": "Brass Lantern (5145 turns of light)"}
                    ),
                ),
                inventory=(sword,),
            ),
            board(
                equipment=(
                    SimpleNamespace(
                        **{**vars(shovel), "name": "Shovel (1d2) {@w1}",
                           "inscription": "@w1", "fully_known": False}
                    ),
                    lantern,
                ),
                inventory=(sword,),
            ),
        ]
        for snap in cosmetic:
            ex.observe(snap)
            self.assertEqual(ex.state, EquipmentMutationState.POSTED)
        worn = board(
            equipment=(item("main_hand", "Sword", tval=23, melee=True), lantern),
            inventory=(item("n", "Shovel (1d2)", tval=20, digger=True),),
        )
        ex.observe(worn)
        self.assertEqual(ex.state, EquipmentMutationState.IDLE)

    def test_ring_swap_completes_on_the_requested_slot(self):
        # Recorded 2026-09-26 departure-unsatisfiable-weight 59-61: 'te' took
        # the sub_ring off, 'wm)' wore the other ring there.
        def ring(slot, name, sval):
            return SimpleNamespace(**{**vars(item(slot, name, tval=45)), "sval": sval})

        dex = ring("sub_ring", "Ring of Dexterity (+2)", 43)
        ice = ring("m", "Ring of Ice [+12]", 19)
        ex = EquipmentMutationExecutor()
        on = board(equipment=(dex,), inventory=(ice,))
        takeoff = ex.request_takeoff(on, "transaction-apply", "e")
        ex.bind_post_snapshot(on)
        ex.confirm_posted(takeoff.key)
        ex.observe(on)
        self.assertEqual(ex.state, EquipmentMutationState.POSTED)
        off = board(inventory=(ice, ring("n", "Ring of Dexterity (+2)", 43)))
        ex.observe(off)
        self.assertEqual(ex.state, EquipmentMutationState.IDLE)
        wield = ex.request_wield(
            off, "transaction-apply", ice, "sub_ring",
            {"main_ring": "d", "sub_ring": "e"},
        )
        self.assertEqual(wield.key, "wm)")
        ex.bind_post_snapshot(off)
        ex.confirm_posted(wield.key)
        ex.observe(off)
        self.assertEqual(ex.state, EquipmentMutationState.POSTED)
        worn = board(
            equipment=(ring("sub_ring", "Ring of Ice [+12] {.}", 19),),
            inventory=(ring("n", "Ring of Dexterity (+2)", 43),),
        )
        ex.observe(worn)
        self.assertEqual(ex.state, EquipmentMutationState.IDLE)

    def test_disenchanting_the_slot_occupant_does_not_complete_a_wield(self):
        # gpt-6-sol r3 P1: the requested sword is still in the pack while the
        # weapon already in the target slot loses its bonuses.
        def weapon(slot, name, sval, to_h, to_d):
            return SimpleNamespace(
                **{**vars(item(slot, name, tval=23, melee=True)),
                   "sval": sval, "to_h": to_h, "to_d": to_d, "weight": 150}
            )

        dagger = weapon("main_hand", "Dagger (1d4) (+5,+5)", 4, 5, 5)
        sword = weapon("n", "Long Sword (2d5) (+3,+3)", 17, 3, 3)
        ex = EquipmentMutationExecutor()
        before = board(equipment=(dagger,), inventory=(sword,))
        posted = ex.request_wield(before, "combat-loadout", sword, "main_hand", SLOTS)
        ex.bind_post_snapshot(before)
        self.assertTrue(ex.confirm_posted(posted.key))
        disenchanted = board(
            equipment=(weapon("main_hand", "Dagger (1d4) (+3,+4)", 4, 3, 4),),
            inventory=(sword,),
        )
        ex.observe(disenchanted)
        self.assertEqual(ex.state, EquipmentMutationState.POSTED)
        wielded = board(
            equipment=(SimpleNamespace(**{**vars(sword), "slot": "main_hand"}),),
            inventory=(SimpleNamespace(**{**vars(dagger), "slot": "n"}),),
        )
        ex.observe(wielded)
        self.assertEqual(ex.state, EquipmentMutationState.IDLE)

    @staticmethod
    def _gear(slot, name, tval, sval, **fields):
        return SimpleNamespace(**{
            **vars(item(slot, name, tval=tval)),
            "sval": sval, "weight": fields.pop("weight", 50), "aware": True,
            "is_ego": False, "is_artifact": False, "to_h": 0, "to_d": 0,
            "to_a": 0, "ac": 0, "pval": 0, "damage_dice_num": 0,
            "damage_dice_sides": 0, "fuel": 0, **fields,
        })

    def _post_wield(self, before, requested, slot):
        ex = EquipmentMutationExecutor()
        from hengbot.policy_constants import EQUIPMENT_SLOT_KEY

        posted = ex.request_wield(
            before, "light-loadout", requested, slot, EQUIPMENT_SLOT_KEY
        )
        ex.bind_post_snapshot(before)
        self.assertTrue(ex.confirm_posted(posted.key))
        return ex

    def test_same_kind_swaps_complete(self):
        # Opus r4 P1: a wield replacing an item of the same kind.
        gear = self._gear
        low = gear("light", "Brass Lantern (120 turns)", 39, 2, fuel=120)
        full = gear("f", "Brass Lantern (7500 turns)", 39, 2, fuel=7500)
        unknown = gear("f", "Brass Lantern", 39, 2, known=False)
        dagger = gear("main_hand", "Dagger (1d4) (+1,+1)", 23, 4,
                      to_h=1, to_d=1, damage_dice_num=1, damage_dice_sides=4)
        better = gear("g", "Dagger (1d4) (+9,+9)", 23, 4,
                      to_h=9, to_d=9, damage_dice_num=1, damage_dice_sides=4)
        cases = (
            ("known lantern", low, full, "light",
             SimpleNamespace(**{**vars(full), "slot": "light", "fuel": 7499})),
            ("unknown lantern", low, unknown, "light",
             SimpleNamespace(**{**vars(unknown), "slot": "light",
                                "known": True, "fuel": 3000})),
            ("dagger", dagger, better, "main_hand",
             SimpleNamespace(**{**vars(better), "slot": "main_hand"})),
        )
        for name, worn, requested, slot, after in cases:
            with self.subTest(name):
                ex = self._post_wield(
                    board(equipment=(worn,), inventory=(requested,)),
                    requested, slot,
                )
                back = SimpleNamespace(**{**vars(worn), "slot": requested.slot})
                ex.observe(board(equipment=(after,), inventory=(back,)))
                self.assertEqual(ex.state, EquipmentMutationState.IDLE)

    def test_fuel_tick_of_the_same_lantern_does_not_complete_a_swap(self):
        gear = self._gear
        low = gear("light", "Brass Lantern (120 turns)", 39, 2, fuel=120)
        full = gear("f", "Brass Lantern (7500 turns)", 39, 2, fuel=7500)
        ex = self._post_wield(board(equipment=(low,), inventory=(full,)), full, "light")
        ticked = SimpleNamespace(
            **{**vars(low), "name": "Brass Lantern (119 turns)", "fuel": 119}
        )
        ex.observe(board(equipment=(ticked,), inventory=(full,)), count_fruitless=True)
        self.assertEqual(ex.state, EquipmentMutationState.POSTED)

    def test_full_pack_takeoff_releases_within_the_limit(self):
        # Opus r4 P2: the taken-off item was dropped (full pack), so the
        # takeoff's effect never shows; nothing requests another mutation.
        from hengbot.policy_constants import EQUIPMENT_MUTATION_RELEASE_LIMIT

        shovel = self._gear("sub_hand", "Shovel", 20, 1, weight=60)
        ex = EquipmentMutationExecutor()
        on = board(equipment=(shovel,))
        posted = ex.request_takeoff(on, "combat-loadout", "b")
        ex.bind_post_snapshot(on)
        ex.confirm_posted(posted.key)
        dropped = board()
        reports = [
            ex.observe(dropped, count_fruitless=True)
            for _ in range(EQUIPMENT_MUTATION_RELEASE_LIMIT)
        ]
        self.assertEqual(ex.state, EquipmentMutationState.IDLE)
        self.assertEqual(
            reports,
            [None] * (EQUIPMENT_MUTATION_RELEASE_LIMIT - 1)
            + ["posting-contract:equipment-mutation-released"],
        )

    def test_a_request_on_a_counted_board_does_not_count_it_twice(self):
        shovel = self._gear("sub_hand", "Shovel", 20, 1, weight=60)
        ex = EquipmentMutationExecutor()
        on = board(equipment=(shovel,))
        ex.confirm_posted(ex.request_takeoff(on, "combat-loadout", "b").key)
        ex.observe(on, count_fruitless=True)
        for _request in range(2):
            refused = ex.request_takeoff(on, "combat-loadout", "b")
            self.assertEqual(
                refused.report, "posting-contract:equipment-mutation-unobserved"
            )
        self.assertEqual(ex.refusals, 1)

    def test_restored_old_expectation_ignores_a_fuel_tick(self):
        # gpt-6-sol r3 P2: a checkpoint restored from before the requested-
        # item rule carries the whole worn signature (names included).
        from hengbot.equipment_mutation import equipment_signature

        shovel = item("main_hand", "Shovel (1d2)", tval=20, digger=True)
        lantern = item("light", "Brass Lantern (5146 turns of light)", tval=39)
        sword = item("n", "Sword", tval=23, melee=True)
        before = board(equipment=(shovel, lantern), inventory=(sword,))
        ex = EquipmentMutationExecutor(
            state=EquipmentMutationState.POSTED,
            goal="combat-loadout",
            expected_signature=equipment_signature(before),
        )
        ticked = board(
            equipment=(
                shovel,
                SimpleNamespace(
                    **{**vars(lantern), "name": "Brass Lantern (5145 turns of light)"}
                ),
            ),
            inventory=(sword,),
        )
        ex.observe(ticked)
        self.assertEqual(ex.state, EquipmentMutationState.POSTED)
        worn = board(
            equipment=(item("main_hand", "Sword", tval=23, melee=True), lantern),
            inventory=(item("n", "Shovel (1d2)", tval=20, digger=True),),
        )
        ex.observe(worn)
        self.assertEqual(ex.state, EquipmentMutationState.IDLE)

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
        for path in sorted(root.glob("*.py")):
            if path.name == "equipment_mutation.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            forbidden = {"WIELD_KEY", "TAKEOFF_KEY"}
            names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
            self.assertFalse(names & forbidden, path.name)

            self.assertEqual(self._direct_key_composers(tree), [], path.name)

    def test_composition_ratchet_catches_named_round_three_forms(self):
        forms = (
            'def f(slot): return "".join(("w", slot))',
            'def f(slot):\n key = "w"\n key += slot\n return key',
            'def f(slot): return "w%s" % slot',
            'def f(slot): return "{}{}".format("w", slot)',
            'def f(slot):\n key = ""\n key += "w"\n key += slot\n return key',
        )
        for source in forms:
            with self.subTest(source=source):
                self.assertTrue(self._direct_key_composers(ast.parse(source)))


if __name__ == "__main__":
    unittest.main()
