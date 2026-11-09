"""『斬鉄剣』 refuses every blow at a visible female (cmd-attack.cpp:194-199).

Recorded n1-b life-310, 2026-11-04 18:07, Orc cave 23F, turn 8431422, HP 73 of 931:
key ``2``, reason ``melee``, at the female 火の神『祝融』, 「拙者、おなごは斬れぬ！」; 1,399
such rows from 17:44.  The fixture is that board, copied from the live state.jsonl
(it rotates, so no extractor can read it again).  The skill-exp cache, the stunned and
the out-of-ammunition boards are DECLARED CONSTRUCTED from it.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hengbot import threat_tiers

from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "zantetsu-female-1104.json.gz"
AMMUNITION_TVALS = (16, 17, 18, 19)


# Threat tiers step 6 (DECLARED CONSTRUCTED): at HP 73 beside six hostiles the board is T1 and is
# left (ZantetsuTiers below); the 11-04 landmine rule is pinned with the tiers not acting.
@patch.object(threat_tiers, "acts_here", new=lambda *args, **kwargs: False)
class ZantetsuFemale(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.raw = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def decide(self, raw):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        policy.prime(parse_snapshot(copy.deepcopy(raw), self.monrace))
        policy._skill_exp_cache = (0, 0, raw["player"]["level"], None)
        key = policy.choose_key(
            policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace)))
        return key, policy.last_reason

    def test_a_refused_blow_is_answered_by_the_crossbow(self):
        self.assertEqual(self.decide(self.raw), ("fg2", "ranged:fire"))

    def test_without_ammunition_the_player_leaves(self):
        raw = copy.deepcopy(self.raw)
        raw["inventory"] = [item for item in raw["inventory"] if item["tval"] not in AMMUNITION_TVALS]
        self.assertEqual(self.decide(raw), ("rb", "threat:scroll"))

    def test_a_stunned_player_still_strikes(self):
        raw = copy.deepcopy(self.raw)
        raw["player"]["status"].update(stunned=True, stun_rank=1)
        self.assertEqual(self.decide(raw), ("2", "melee"))


class ZantetsuTiers(unittest.TestCase):
    """With the tiers acting (step 6, answer 6): the recorded board is T1, read Teleportation."""

    setUp = ZantetsuFemale.__dict__.get("setUp", lambda self: None)
    decide = ZantetsuFemale.__dict__["decide"]

    @classmethod
    def setUpClass(cls):
        setup = ZantetsuFemale.__dict__.get("setUpClass")
        if setup is not None:
            setup.__func__(cls)

    def test_the_t1_board_is_left(self):
        self.assertEqual(self.decide(self.raw), ("rb", "flee:scroll"))


if __name__ == "__main__":
    unittest.main()
