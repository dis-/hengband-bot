"""Structural guards for the behavior-preserving policy mixin split."""

import base64
import json
import pickle
from pathlib import Path
import unittest

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.flight_recorder import jsonable
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_calibration import CalibrationMixin
from hengbot.policy_combat import CombatMixin
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


class PolicyStructureTest(unittest.TestCase):
    def test_policy_composes_all_eight_split_mixins(self):
        self.assertTrue(
            {
                CalibrationMixin,
                CombatMixin,
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
