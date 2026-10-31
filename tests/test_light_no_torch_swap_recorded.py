"""#47: fundraising swapped a burning Brass Lantern {average} for a torch.

Owner 2026-10-31: 「そもそもなぜ松明を装備する？直したはずだが」 and the
decision 「未鑑定でも {並} の光源は付けてよい」.  Fixture:
tests/fixtures/light-no-torch-swap-1031.json.gz
(tests/extract_light_no_torch_swap_fixture.py).

n1-c life-053 03:57:41 (鉄獄1階): the worn lantern burns (radius 2) with one
flask of oil and four torches carried.  Oil is below the departure target, so
_expedition_light_ready is false for the unidentified lantern, and the
fundraising floor wore the best known spare (a torch, 'we').  The swap now
asks the one light-quality rule (_light_to_wield), which never puts a torch
in place of a lantern; the carried spare only keeps the run going.  n1-c
life-055 decisions 939/2605 are the same swap ('wf'); that capture holds no
board of those turns, so only its decision rows are pinned.

DECLARED RECONSTRUCTED: the fundraising run's purpose record lived in the
recorded process, so the policy runs with fundraising mode 'mine' and the
cross-area purpose contract off.  DECLARED CONSTRUCTED: the posted variant
removes the flask of oil, so the refill rung does not answer first.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path

from hengbot.model import parse_snapshot
from tests.test_dungeon_1031_recorded import RecordedHarness, decide
from tests.test_town_decision_speed_caches import build_policy

FIXTURE = Path(__file__).with_name("fixtures") / "light-no-torch-swap-1031.json.gz"
BEFORE, SWAP, AFTER = 85521, 85529, 85534


class FundraisingKeepsTheLanternTest(RecordedHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = json.load(stream)

    def board(self, turn):
        return copy.deepcopy(next(b for b in self.cases["life-053"]["boards"] if b["turn"] == turn))

    def policy(self):
        policy = build_policy()
        policy.prime(parse_snapshot(self.board(BEFORE), policy._monrace_knowledge))
        policy._fundraising_mode = "mine"  # DECLARED RECONSTRUCTED
        policy._crossarea_fundraising_enforced = False  # DECLARED RECONSTRUCTED
        decide(policy, self.board(BEFORE))
        return policy

    @staticmethod
    def worn_light(board):
        return next(item for item in board.equipment if item.is_light)

    def test_recorded_rows(self):
        rows = self.cases["life-053"]["decisions"]
        self.assertEqual([(row["reason"], row["key"], row["light_radius"]) for row in rows],
                         [("ranged:throw-torch", "ve6", 2), ("fundraise:wield-light", "we", 2),
                          ("fundraise:seek-loot", "9", 1)])
        rows = self.cases["life-055"]["decisions"]
        self.assertEqual([(row["reason"], row["key"]) for row in rows],
                         [("fundraise:refill-light", "\\Fa"), ("fundraise:wield-light", "wf")] * 2)
        after = parse_snapshot(self.board(AFTER), build_policy()._monrace_knowledge)
        self.assertTrue(self.worn_light(after).is_torch)

    def test_burning_average_lantern_is_not_swapped_for_a_torch(self):
        policy = self.policy()
        raw = self.board(SWAP)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        worn = self.worn_light(board)
        self.assertEqual((worn.is_lantern, worn.known, worn.pseudo_feeling), (True, False, "average"))
        self.assertFalse(policy._expedition_light_ready(board))
        self.assertTrue(policy._fundraising_wieldable_light(board).is_torch)
        key = decide(policy, raw)
        # Unfixed: ("fundraise:wield-light", "we"), the torch in slot e.
        self.assertNotEqual(policy.last_reason, "fundraise:wield-light")
        self.assertFalse(str(key).startswith(("w", "t")), (key, policy.last_reason))

    def test_without_oil_the_run_goes_on_with_the_lantern_worn(self):
        policy = self.policy()
        raw = self.board(SWAP)
        raw["inventory"] = [item for item in raw["inventory"] if "油" not in item["name"]]
        key = decide(policy, raw)
        # Unfixed: ("fundraise:wield-light", "we").
        self.assertNotEqual(policy.last_reason, "fundraise:wield-light")
        self.assertTrue(policy.last_reason.startswith(("fundraise:", "explore", "ranged:")),
                        policy.last_reason)
        self.assertFalse(str(key).startswith(("w", "t")), (key, policy.last_reason))
        accepted = self.post(policy, raw, key, [], self.later(raw))
        self.assertEqual("".join(accepted), key)

    def test_control_spent_lantern_without_refill_takes_the_torch(self):
        # DECLARED CONSTRUCTED: the worn light is a known lantern with no fuel
        # and no oil; the same rule then wears the best spare torch.
        policy = self.policy()
        raw = self.board(SWAP)
        raw["inventory"] = [item for item in raw["inventory"] if "油" not in item["name"]]
        torch = next(item for item in raw["inventory"] if item["slot"] == "e")
        spent = dict(copy.deepcopy(torch), slot="light", count=1, sval=1, light_turns=0,
                     inscription="", name="真鍮のランタン(0ターンの寿命)")
        raw["equipment"] = [spent if item["slot"] == "light" else item for item in raw["equipment"]]
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertTrue(self.worn_light(board).known)
        key = decide(policy, raw)
        self.assertTrue(str(key).startswith("w"), (key, policy.last_reason))
