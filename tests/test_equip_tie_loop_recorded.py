"""D40 (2026-10-31 07:38-07:42): n1-c life-055 swapped a Short Sword and a Cutlass forever.

The recorded loop: in Home after each deposit the optimizer chose the weapon
that was NOT wielded (decisions 4993 and 5001), and the next board withdrew it
(4994 and 5002).  The two swords are not equal in the game: the 11.0 lb Cutlass
gets the two-hand to-hit bonus, so it is the better weapon (screen to-hit 35
vs 33).  The flip came from the melee evaluation cache: its key omitted the
weapon proficiency, so the Cutlass under its equipped id kept the value cached
at proficiency 3192 (to-hit 4) while the same Cutlass under its Home id was
evaluated at the current 3992 (to-hit 8).

Every decision goes through the public choose_key; the in-Home leave key is
posted through the production executor.  DECLARED RECONSTRUCTED: the capture
has no policy checkpoint, so the live process's evaluator cache is rebuilt by
running the production optimizer on the recorded board with the carried
weapons' proficiencies recorded at turn 204781 (the save of the same
character), then handing that cache to the policy that decides the recorded
board.  The ~f skill
list and the calibration are the same character's recorded ones (fixture
provenance).  The board after the leave key is the recorded next board.
"""
import tests  # noqa: F401 -- isolate runtime files

import copy
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.equipment_optimizer import Loadout, OwnedEquipment
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.warrior_optimization import load_character_calibration
from tests import test_lv7_town_stop_recorded as lv7
import tests.test_input_executor as executor_harness
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "equip-tie-loop-20261031.json.gz"
SHA256 = "354c86a4fb1b76267c168775de2038fc7fdf3a32a88a6a83ffc97b06f45fcf96"
SHORT_SWORD = "50ce9bf46f5cc7d9"
CUTLASS = "585fcf732179423a"


class EquipTieLoopRecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post

    @classmethod
    def setUpClass(cls):
        payload = FIXTURE.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == SHA256
        cls.data = json.loads(gzip.decompress(payload))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.earlier = {(item["tval"], item["sval"]): item["weapon_proficiency"]
                       for item in cls.data["earlier_weapons"]["items"]}

    def policy(self, raw):
        directory = Path(self.enterContext(TemporaryDirectory()))
        policy = _policy(directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        calibration = directory / "recorded-calibration.json"
        calibration.write_text(json.dumps(self.data["calibration"]), encoding="utf-8")
        policy._character_calibration = load_character_calibration(calibration)
        self.assertIsNotNone(policy._character_calibration)
        policy._character_calibration_loaded = True
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        policy.consume_skill_knowledge(self.data["skill_exp"])
        policy.test_directory = directory
        return policy

    def decide(self, policy, raw):
        _decoded, snapshots = _consume_response_sequence(
            [json.dumps(raw, ensure_ascii=False)], policy, lambda _key: True,
            self.monrace, knowledge_ledger_path=policy.test_directory / "knowledge.jsonl")
        return policy.choose_key(snapshots[-1]), policy.last_reason

    def with_earlier_proficiency(self, raw):
        """DECLARED RECONSTRUCTED: carried weapons at their turn-204781 proficiencies.

        Only the carried ids were cached early (loadout reports 82/87 show the
        Cutlass at to-hit 4 as pack/equipped); Home ids were first evaluated
        in the loop, at the current proficiency (to-hit 8 as home).
        """
        raw = copy.deepcopy(raw)
        for item in [*raw["equipment"], *raw["inventory"]]:
            item["weapon_proficiency"] = self.earlier.get(
                (item.get("tval"), item.get("sval")), item.get("weapon_proficiency"))
        return raw

    def policy_with_live_cache(self, raw):
        warm = self.policy(raw)
        self.decide(warm, self.with_earlier_proficiency(raw))
        policy = self.policy(raw)
        policy._warrior_evaluator_cache = warm._warrior_evaluator_cache
        return policy

    def actions(self, policy):
        session = policy._equipment_transaction_session
        if session is None:
            return None
        return [(action.kind, action.item_id.split(":")[1], action.target_slot)
                for action in session.plan.actions]

    def leave_home(self, policy, inside, outside):
        key, reason = self.decide(policy, self.data["boards"][inside])
        self.assertEqual(key, "\x1b")
        actions = self.actions(policy)
        self.post(policy, self.data["boards"][inside], key, self.data["boards"][outside])
        decision = self.decide(policy, self.data["boards"][outside])
        return actions, decision, self.actions(policy)

    def test_fixture_pins_the_recorded_loop_and_the_two_cutlass_values(self):
        decisions = self.data["decisions"]
        self.assertEqual([(row["turn"], row["key"], row["reason"]) for _, row in sorted(decisions.items())], [
            (208664, "\x1b", "home:leave-after-one-operation"),
            (208671, "5pb\x1b", "equipment-transaction:atomic-withdraw"),
            (208696, "\x1b", "home:leave-after-one-operation"),
            (208706, "5pb\x1b", "equipment-transaction:atomic-withdraw"),
        ])
        self.assertEqual(decisions["4993"]["fresh_search_transition"]["added_ids"], [f"home:{SHORT_SWORD}:0"])
        self.assertEqual(decisions["5001"]["fresh_search_transition"]["added_ids"], [f"home:{CUTLASS}:0"])
        board = self.data["boards"]["cutlass-worn-in-home"]
        worn = next(item for item in board["equipment"] if item["slot"] == "main_hand")
        self.assertEqual((worn["sval"], worn["weight"], worn["weapon_proficiency"]), (12, 110, 3992))
        self.assertEqual(self.earlier[(23, 12)], 3192)
        # The first loop report: the worn Cutlass at the stale to-hit 4.
        first = {c["main_hand"]["id"]: c["melee_hands"][0]["to_hit"]
                 for c in self.data["reports"]["87"]["candidates"] if c["sub_hand"] is None}
        self.assertEqual(first[f"equipped:{CUTLASS}:0"], 4)
        self.assertEqual(first[f"home:{SHORT_SWORD}:0"], 6)

    def test_cache_keyed_by_identity_follows_the_recorded_proficiency_gain(self):
        policy = self.policy_with_live_cache(self.data["boards"]["cutlass-worn-in-home"])
        board = parse_snapshot(self.data["boards"]["cutlass-worn-in-home"], {})
        cutlass = next(item for item in board.equipment if item.slot == "main_hand")
        owned = OwnedEquipment(f"equipped:{CUTLASS}:0", cutlass, "equipped", equipped_slot="main_hand")
        hand = policy._warrior_evaluator_cache.evaluator(
            Loadout((("main_hand", owned),), "two_handed")).melee.hands[0]
        # 4 (STR/DEX) + 4 (two-hand bonus) + trunc((3992 - 4000) / 200) = 8.
        self.assertEqual(hand.to_hit, 8)

    def test_worn_cutlass_stays_and_the_short_sword_is_not_withdrawn(self):
        policy = self.policy_with_live_cache(self.data["boards"]["cutlass-worn-in-home"])
        actions, (key, reason), after = self.leave_home(
            policy, "cutlass-worn-in-home", "cutlass-worn-outside")
        # b6d47db93: [('withdraw', SHORT_SWORD, None), ('takeoff', CUTLASS, 'main_hand'),
        # ('equip', SHORT_SWORD, 'main_hand'), ('deposit', CUTLASS, None)], kept after leaving.
        self.assertIsNone(actions)
        self.assertIsNone(after)
        self.assertFalse(reason.startswith("equipment-transaction"), (key, reason))

    def test_control_strictly_better_cutlass_is_still_equipped(self):
        policy = self.policy_with_live_cache(self.data["boards"]["short-sword-worn-in-home"])
        actions, _decision, after = self.leave_home(
            policy, "short-sword-worn-in-home", "short-sword-worn-outside")
        swap = [("withdraw", CUTLASS, None), ("takeoff", SHORT_SWORD, "main_hand"),
                ("equip", CUTLASS, "main_hand"), ("deposit", SHORT_SWORD, None)]
        self.assertEqual(actions, swap)
        # The swap stays owned after the posted leave key.  This fresh policy
        # first steps off the entrance for a shop approach, where the live
        # process re-entered Home at once ('5pb').
        self.assertEqual(after, swap)


if __name__ == "__main__":
    import unittest
    unittest.main()
