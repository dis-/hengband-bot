"""#47 (2026-10-31): wear an unidentified {average} light.

Owner 2026-10-31 (AskUserQuestion, verbatim): 「並なら付けて良い。」

Recorded (n1-c life-055, Magic-Eater Lv7): the Wooden Torch is out (light radius
0, light_turns 0) while the Brass Lantern {average} (known=false) the Q34 opening
picked up is carried; the optimizer had no light candidate (decision 4993) and
never wore it.  The C screen of the same character (turn 205220) lists no
mutation, so the {average} feeling is trusted under owner Q-B (2026-10-22).

Every decision goes through the public choose_key; the leave and equip keys
are posted through the production executor.  Boards changed by
a test are DECLARED CONSTRUCTED where they are changed.
"""
import tests  # noqa: F401 -- isolate runtime files

import copy
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.warrior_optimization import load_character_calibration
from tests import test_lv7_town_stop_recorded as lv7
import tests.test_input_executor as executor_harness
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "unid-light-20261031.json.gz"
SHA256 = "eaba709d262ff4478db258cb92c96eb63f7e9a521a8fd107e2d1398dc7aee3dc"
LANTERN_SLOT = "f"
GLOVES_SLOT = "g"
BAD_LUCK = 92


class UnidentifiedLightRecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post
    equip_reply = staticmethod(lv7.Lv7TownStopRecordedTest.equip_reply)

    @classmethod
    def setUpClass(cls):
        payload = FIXTURE.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == SHA256
        cls.data = json.loads(gzip.decompress(payload))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def policy(self, raw, *, mutations=()):
        directory = Path(self.enterContext(TemporaryDirectory()))
        policy = _policy(directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        recorded = copy.deepcopy(self.data["calibration"])
        if mutations:
            # DECLARED CONSTRUCTED: the calibration is taken on the same C
            # screen, so it carries the constructed mutation list as well.
            recorded["mutation_signature"] = sorted(mutations)
        calibration = directory / "recorded-calibration.json"
        calibration.write_text(json.dumps(recorded), encoding="utf-8")
        policy._character_calibration = load_character_calibration(calibration)
        self.assertIsNotNone(policy._character_calibration)
        policy._character_calibration_loaded = True
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        policy.consume_skill_knowledge(self.data["skill_exp"])
        if mutations is not None:
            character = copy.deepcopy(self.data["character"]["character"])
            if mutations:
                # DECLARED CONSTRUCTED: the recorded C screen lists no mutation.
                character["mutations"] = list(mutations)
            policy.observe_character_snapshot(character)
        policy.test_directory = directory
        return policy

    def decide(self, policy, raw):
        _decoded, snapshots = _consume_response_sequence(
            [json.dumps(raw, ensure_ascii=False)], policy, lambda _key: True,
            self.monrace, knowledge_ledger_path=policy.test_directory / "knowledge.jsonl")
        return policy.choose_key(snapshots[-1]), policy.last_reason

    def board(self, name, **changes):
        raw = copy.deepcopy(self.data["boards"][name])
        for slot, fields in changes.items():
            item = next(it for it in raw["inventory"] if it["slot"] == slot)
            for key, value in fields.items():
                if value is None:
                    item.pop(key, None)
                else:
                    item[key] = value
        return raw

    @staticmethod
    def selected(policy):
        best = policy._equipment_optimization_preparation.result.best
        return {slot: owned.item.name for slot, owned in best.loadout.slots}

    @staticmethod
    def actions(policy):
        session = policy._equipment_transaction_session
        if session is None:
            return None
        return [(action.kind, action.target_slot) for action in session.plan.actions]

    def test_fixture_pins_the_dark_torch_and_the_unworn_average_lantern(self):
        board = self.data["boards"]["in-home"]
        self.assertEqual(board["player"]["class_id"], 16)
        self.assertEqual(board["player"]["light_radius"], 0)
        torch = next(it for it in board["equipment"] if it["slot"] == "light")
        self.assertEqual((torch["sval"], torch["light_turns"]), (0, 0))
        lantern = next(it for it in board["inventory"] if it["slot"] == LANTERN_SLOT)
        self.assertEqual((lantern["tval"], lantern["sval"], lantern["known"], lantern["pseudo_feeling"]),
                         (39, 1, False, "average"))
        self.assertEqual(self.data["character"]["character"]["mutations"], [])
        decisions = self.data["decisions"]
        # The same lantern: picked up and worn by the Q34 opening, later
        # replaced by a torch; with the torch out the light had no candidate.
        self.assertEqual([(decisions[n]["reason"], decisions[n]["key"]) for n in ("58", "59", "939")],
                         [("quest-strategy:pickup-opening-lantern", "g"),
                          ("quest-strategy:equip-opening-lantern", "we"),
                          ("fundraise:wield-light", "wf")])
        self.assertEqual((decisions["4993"]["light_radius"], decisions["4993"]["light_candidates"]), (0, 0))

    def test_average_lantern_is_worn_when_the_torch_is_out(self):
        inside = self.board("in-home")
        policy = self.policy(inside)
        key, _reason = self.decide(policy, inside)
        self.assertEqual(key, "\x1b")
        # 1acb3b27c: no light candidate, no transaction (None).
        self.assertEqual(self.actions(policy), [("equip", "light")])
        self.assertEqual(self.selected(policy)["light"], "真鍮のランタン {並}")
        outside = self.data["boards"]["outside"]
        self.post(policy, inside, key, outside)
        key, reason = self.decide(policy, outside)
        self.assertEqual((key, reason), ("w" + LANTERN_SLOT, "equipment-transaction:equip"))
        worn = self.equip_reply(outside, key)
        self.post(policy, outside, key, worn)
        # The worn lantern stays: no owner takes it off or swaps the torch back.
        key, reason = self.decide(policy, worn)
        self.assertIsNone(self.actions(policy))
        self.assertFalse(str(key).startswith(("w", "t")), (key, reason))
        self.assertEqual(self.selected(policy)["light"], "真鍮のランタン {並}")

    def test_selected_average_lantern_is_not_disposable(self):
        inside = self.board("in-home")
        policy = self.policy(inside)
        self.decide(policy, inside)
        lantern = next(it for it in parse_snapshot(inside, {}).inventory if it.slot == LANTERN_SLOT)
        # 1acb3b27c: True (an {average} item is junk under pack pressure).
        self.assertFalse(policy._is_disposable_item(lantern))

    def test_control_without_a_seen_mutation_list_the_lantern_is_not_worn(self):
        inside = self.board("in-home")
        policy = self.policy(inside, mutations=None)
        self.decide(policy, inside)
        self.assertIsNone(self.actions(policy))
        self.assertNotIn("light", self.selected(policy))
        lantern = next(it for it in parse_snapshot(inside, {}).inventory if it.slot == LANTERN_SLOT)
        self.assertTrue(policy._is_disposable_item(lantern))

    def test_control_bad_luck_mutation_keeps_the_lantern_off(self):
        inside = self.board("in-home")
        policy = self.policy(inside, mutations=(BAD_LUCK,))
        self.decide(policy, inside)
        self.assertIsNone(self.actions(policy))
        self.assertNotIn("light", self.selected(policy))

    def test_control_unidentified_light_without_the_average_feeling_is_not_worn(self):
        # DECLARED CONSTRUCTED: the lantern without its pseudo-ID feeling.
        inside = self.board("in-home", **{LANTERN_SLOT: {"pseudo_feeling": None, "name": "真鍮のランタン"}})
        policy = self.policy(inside)
        self.decide(policy, inside)
        self.assertIsNone(self.actions(policy))
        self.assertNotIn("light", self.selected(policy))

    def test_control_average_non_light_is_not_worn(self):
        # DECLARED CONSTRUCTED: the carried unidentified Leather Gloves sensed
        # {average}; the arms slot is empty and must be filled when it can be.
        inside = self.board("in-home", **{GLOVES_SLOT: {"pseudo_feeling": "average",
                                                        "name": "革グローブ [1] {並}"}})
        policy = self.policy(inside)
        self.decide(policy, inside)
        self.assertNotIn("arms", self.selected(policy))
        self.assertEqual(self.selected(policy)["light"], "真鍮のランタン {並}")


if __name__ == "__main__":
    import unittest
    unittest.main()
