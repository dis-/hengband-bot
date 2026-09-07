"""Structural guards for the behavior-preserving policy mixin split."""

import base64
import importlib
import json
import pickle
from pathlib import Path
import sys
import unittest

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.flight_recorder import jsonable
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import HengbotPolicy, ProcurementHomeGate
from hengbot.policy_calibration import CalibrationMixin
from hengbot.policy_combat import CombatMixin
from hengbot.policy_equipment import EquipmentMixin
from hengbot.policy_fundraising import FundraisingMixin
from hengbot.policy_helpers import PolicyHelpersMixin
from hengbot.policy_identification import IdentificationMixin
from hengbot.policy_navigation import NavigationMixin
from hengbot.policy_quest import QuestMixin
from hengbot.policy_supply import SupplyMixin


ROOT = Path(__file__).resolve().parents[1]
EQUIP_SWAP = ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.snapshots.jsonl"


def _member_names(owner):
    return {
        name
        for name in vars(owner)
        if not name.startswith("__")
    }


def _member_collisions(policy_type):
    owners = tuple(owner for owner in policy_type.__mro__ if owner is not object)
    members = {owner: _member_names(owner) for owner in owners}
    return [
        (left, right, members[left] & members[right])
        for index, left in enumerate(owners)
        for right in owners[index + 1:]
        if members[left] & members[right]
    ]


def _import_test_module(stem):
    qualified_name = f"tests.{stem}"
    if qualified_name in sys.modules:
        sys.modules[stem] = sys.modules[qualified_name]
    elif stem in sys.modules:
        sys.modules.setdefault(qualified_name, sys.modules[stem])
    return importlib.import_module(qualified_name)


class PolicyStructureTest(unittest.TestCase):
    def test_old_policy_module_pickle_resolves_lifted_home_gate(self):
        old_reference = b"chengbot.policy\nProcurementHomeGate\n."
        self.assertIs(pickle.loads(old_reference), ProcurementHomeGate)

    def test_test_modules_do_not_bind_foreign_test_cases(self):
        offenders = []
        scripts = str(ROOT / "scripts")
        sys.path.insert(0, scripts)
        try:
            for path in sorted((ROOT / "tests").glob("test_*.py")):
                module = _import_test_module(path.stem)
                for name, value in vars(module).items():
                    if (
                        isinstance(value, type)
                        and issubclass(value, unittest.TestCase)
                        and value.__module__ != module.__name__
                    ):
                        offenders.append(
                            f"{module.__name__}.{name} from {value.__module__}"
                        )
        finally:
            sys.path.remove(scripts)
        self.assertEqual(offenders, [])

    def test_duplicate_collection_guard_imports_one_module_object_per_stem(self):
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            qualified_name = f"tests.{path.stem}"
            imported = _import_test_module(path.stem)
            after = {
                name: module
                for name, module in sys.modules.items()
                if name in {path.stem, qualified_name}
            }
            self.assertIs(after[qualified_name], imported)
            self.assertEqual(
                len({id(module) for module in after.values()}),
                1,
            )

    def test_policy_composes_all_nine_split_mixins(self):
        self.assertTrue(
            {
                CalibrationMixin,
                CombatMixin,
                EquipmentMixin,
                FundraisingMixin,
                PolicyHelpersMixin,
                IdentificationMixin,
                NavigationMixin,
                QuestMixin,
                SupplyMixin,
            }.issubset(HengbotPolicy.__mro__)
        )

    def test_policy_mixins_have_no_method_name_collisions(self):
        self.assertEqual(_member_collisions(HengbotPolicy), [])

    def test_collision_guard_catches_descriptor_shadowing_through_full_mro(self):
        class Grandparent:
            shadowed = classmethod(lambda cls: None)

        class Parent(Grandparent):
            pass

        class Policy(Parent):
            shadowed = property(lambda self: None)

        collisions = _member_collisions(Policy)
        self.assertEqual(
            [(left.__name__, right.__name__, names) for left, right, names in collisions],
            [("Policy", "Grandparent", {"shadowed"})],
        )

    def test_equip_swap_checkpoint_round_trip_is_byte_stable(self):
        definitions = find_monrace_definitions(EQUIP_SWAP, None)
        repository_definitions = ROOT.parent / "lib" / "edit" / "MonraceDefinitions.jsonc"
        if repository_definitions.is_file():
            self.assertIsNotNone(definitions)
        if definitions is None:
            self.skipTest(
                "MonraceDefinitions.jsonc is unavailable in the detached verification checkout"
            )
        knowledge = load_monrace_knowledge(definitions)
        policy = HengbotPolicy(monrace_knowledge=knowledge)
        with EQUIP_SWAP.open(encoding="utf-8") as stream:
            for line in stream:
                policy.choose_key(parse_snapshot(json.loads(line), knowledge))

        encoded = checkpoint(policy)
        restored = restore_checkpoint(HengbotPolicy, encoded)
        before = pickle.loads(base64.b64decode(encoded))
        after = pickle.loads(base64.b64decode(checkpoint(restored)))
        self.assertEqual(after.keys(), before.keys())
        self.assertEqual(
            json.dumps(jsonable(after), sort_keys=True, separators=(",", ":")),
            json.dumps(jsonable(before), sort_keys=True, separators=(",", ":")),
        )


if __name__ == "__main__":
    unittest.main()
