"""The decided side's memory keeps its pickle path across the threat_tiers split.

Maintainability review 2026-11-09, step 4 moved ``TierMemory`` and ``Decided`` from
``threat_tiers`` to ``threat_tier_memory``.  Policy checkpoints (town arrival, incident
captures, the recorded fixtures) hold them as ``policy._threat_tier_memory`` under
``hengbot.threat_tiers``: a checkpoint written before the split must restore after it, and one
written after it must restore on a tree from before it (the same path both ways).

The fixture is a real town-arrival checkpoint (stops-1109-town/h497, n1-a life-497) whose memory
holds a decided monster.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import lzma
import pickle
import pickletools
import unittest
from pathlib import Path

from hengbot import threat_tier_memory, threat_tiers
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).parent / "fixtures" / "stops-1109-town" / "h497" / "policy.pkl.xz"


def globals_of(payload: bytes) -> set:
    """The (module, name) pairs a pickle loads, memoised strings followed."""
    found, stack, memo, last = set(), [], {}, None
    for op, arg, _ in pickletools.genops(payload):
        if op.name in ("SHORT_BINUNICODE", "BINUNICODE", "UNICODE", "BINUNICODE8"):
            stack.append(arg)
            last = arg
        elif op.name == "MEMOIZE":
            memo[len(memo)] = last
        elif op.name in ("BINPUT", "LONG_BINPUT", "PUT"):
            memo[arg] = last
        elif op.name in ("BINGET", "LONG_BINGET", "GET"):
            last = memo.get(arg)
            stack.append(last)
        elif op.name == "STACK_GLOBAL":
            found.add((stack[-2], stack[-1]))
            last = None
        else:
            last = None
    return found


class TierMemoryPickleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = lzma.decompress(FIXTURE.read_bytes())
        cls.policy = restore_checkpoint_bytes(HengbotPolicy, cls.payload)

    def test_the_recorded_checkpoint_names_the_old_path(self):
        names = globals_of(self.payload)
        self.assertIn(("hengbot.threat_tiers", "TierMemory"), names)
        self.assertIn(("hengbot.threat_tiers", "Decided"), names)

    def test_a_checkpoint_from_before_the_split_restores_its_decided_sides(self):
        memory = getattr(self.policy, threat_tiers.TIER_MEMORY)
        self.assertIsInstance(memory, threat_tier_memory.TierMemory)
        self.assertTrue(memory.decided)
        for entry in memory.decided.values():
            self.assertIsInstance(entry, threat_tier_memory.Decided)

    def test_the_classes_keep_the_threat_tiers_path(self):
        for cls in (threat_tier_memory.TierMemory, threat_tier_memory.Decided):
            self.assertEqual(cls.__module__, "hengbot.threat_tiers")
            self.assertIs(getattr(threat_tiers, cls.__name__), cls)

    def test_a_checkpoint_after_the_split_writes_the_same_path(self):
        payload = checkpoint_bytes(self.policy)
        names = {pair for pair in globals_of(payload) if pair[1] in ("TierMemory", "Decided")}
        self.assertEqual(names, {("hengbot.threat_tiers", "TierMemory"),
                                 ("hengbot.threat_tiers", "Decided")})
        restored = restore_checkpoint_bytes(HengbotPolicy, payload)
        before = getattr(self.policy, threat_tiers.TIER_MEMORY)
        after = getattr(restored, threat_tiers.TIER_MEMORY)
        self.assertEqual(after, before)

    def test_pickle_round_trip_of_the_memory_alone(self):
        memory = getattr(self.policy, threat_tiers.TIER_MEMORY)
        self.assertEqual(pickle.loads(pickle.dumps(memory)), memory)


if __name__ == "__main__":
    unittest.main()
