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


ROOT = Path(__file__).resolve().parents[1]
EQUIP_SWAP = ROOT / "jsonlog" / "incident-equip-swap-loop-20260826.snapshots.jsonl"


def _method_names(owner):
    return {
        name
        for name, value in vars(owner).items()
        if not name.startswith("__") and callable(value)
    }


class PolicyStructureTest(unittest.TestCase):
    def test_policy_mixins_have_no_method_name_collisions(self):
        owners = (HengbotPolicy, *HengbotPolicy.__bases__)
        methods = {owner: _method_names(owner) for owner in owners}
        for index, left in enumerate(owners):
            for right in owners[index + 1:]:
                self.assertEqual(
                    methods[left] & methods[right],
                    set(),
                    f"method collision between {left.__name__} and {right.__name__}",
                )

    def test_equip_swap_checkpoint_round_trip_is_byte_stable(self):
        definitions = find_monrace_definitions(EQUIP_SWAP, None)
        self.assertIsNotNone(definitions)
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
