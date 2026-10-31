"""#47 (2026-10-31): wear an unidentified {average} light and the Q34 items.

Owner 2026-10-31 (AskUserQuestion, verbatim): 「並なら付けて良い。加えてQ34習得品も
付けて良い。」 and 「Q34で拾った品を覚える必要があるなら銘を刻むこと」.

Recorded (n1-c life-055, Magic-Eater Lv7): the Wooden Torch is out (light radius
0, light_turns 0) while the Brass Lantern {average} (known=false) the Q34 opening
picked up is carried; the optimizer had no light candidate (decision 4993) and
never wore it.  The C screen of the same character (turn 205220) lists no
mutation, so the {average} feeling is trusted under owner Q-B (2026-10-22).

Every decision goes through the public choose_key; the leave, equip and
inscription keys are posted through the production executor.  Boards changed by
a test are DECLARED CONSTRUCTED where they are changed.
"""
import tests  # noqa: F401 -- isolate runtime files

import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time

from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _consume_response_sequence,
    _send_decision_key_with_prompt_chain,
)
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.warrior_optimization import load_character_calibration
from tests import test_lv7_town_stop_recorded as lv7
import tests.test_input_executor as executor_harness
from tests.test_input_executor import FaithfulHookGame, command_screen, prompt_screen
from tests.test_q34_collect_recorded import captured, make_policy
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "unid-light-20261031.json.gz"
SHA256 = "eaba709d262ff4478db258cb92c96eb63f7e9a521a8fd107e2d1398dc7aee3dc"
Q34_OPENING = Path(__file__).with_name("fixtures") / "q34-opening-oil-20261016.jsonl.gz"
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

    def test_q34_inscribed_items_are_worn_unidentified(self):
        # DECLARED CONSTRUCTED: the lantern without a feeling and the gloves,
        # both carrying the bot's in-game Q34 inscription.
        inside = self.board("in-home", **{
            LANTERN_SLOT: {"pseudo_feeling": None, "name": "真鍮のランタン {Q34}", "inscription": "Q34"},
            GLOVES_SLOT: {"name": "革グローブ [1] {Q34}", "inscription": "Q34"},
        })
        policy = self.policy(inside, mutations=None)
        self.decide(policy, inside)
        selected = self.selected(policy)
        self.assertEqual((selected["light"], selected["arms"]),
                         ("真鍮のランタン {Q34}", "革グローブ [1] {Q34}"))
        self.assertEqual(sorted(self.actions(policy)), [("equip", "arms"), ("equip", "light")])

    def test_control_q34_item_sensed_cursed_is_not_worn(self):
        # DECLARED CONSTRUCTED: a Q34-inscribed lantern sensed {cursed}.
        inside = self.board("in-home", **{
            LANTERN_SLOT: {"pseudo_feeling": "cursed", "name": "真鍮のランタン {呪われている, Q34}",
                           "inscription": "Q34"},
        })
        policy = self.policy(inside)
        self.decide(policy, inside)
        self.assertNotIn("light", self.selected(policy))


class Q34PickupInscriptionRecordedTest(executor_harness.ProductionHarness):
    """The recorded Q34 opening boards of 2026-10-16 (oil, lantern, carried lantern)."""

    @classmethod
    def setUpClass(cls):
        cls.rows = {}
        with gzip.open(Q34_OPENING, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                cls.rows[row["turn"]] = row
        cls.facts = captured()

    def decide(self, policy, raw):
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        return policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)), policy.last_reason

    def post(self, policy, raw, key, screens, following):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        game.screen = command_screen(raw["turn"])
        game.screens = [*screens, command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw) for _ in screens] + [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "q34-inscribe", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(raw, policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertFalse(game.term_fifo)
        policy.confirm_key_posted(key)
        return game.accepted

    def test_lantern_picked_up_on_q34_is_inscribed_then_worn(self):
        policy = make_policy(self.facts)
        policy.prime(parse_snapshot(self.rows[75392], policy._monrace_knowledge))
        self.assertEqual(self.decide(policy, self.rows[75392]), ("g", "quest-strategy:pickup-opening-oil"))
        self.assertEqual(self.decide(policy, self.rows[75402]), ("g", "quest-strategy:pickup-opening-lantern"))
        carried = self.rows[75413]
        lantern = next(it for it in carried["inventory"] if it["tval"] == 39 and not it["known"])
        self.assertEqual((lantern["slot"], lantern["inscription"]), ("d", ""))
        key, reason = self.decide(policy, carried)
        # 1acb3b27c: ('wd', 'quest-strategy:equip-opening-lantern').
        self.assertEqual((key, reason), ("{dQ34\r", "quest-strategy:q34-inscribe-pickup"))
        # DECLARED CONSTRUCTED: the game's reply to the inscription (the same
        # board with the inscription on the lantern).
        tagged = copy.deepcopy(carried)
        tagged_lantern = next(it for it in tagged["inventory"] if it["slot"] == "d")
        tagged_lantern["inscription"] = "Q34"
        tagged_lantern["name"] = "真鍮のランタン {未鑑定, Q34}"
        accepted = self.post(policy, carried, key, [
            prompt_screen("どのアイテムに銘を刻みますか? "),
            prompt_screen("銘: "),
        ], tagged)
        self.assertEqual("".join(accepted), key)
        self.assertEqual(self.decide(policy, tagged), ("wd", "quest-strategy:equip-opening-lantern"))

    def test_control_unidentified_item_carried_into_q34_is_not_inscribed(self):
        # DECLARED CONSTRUCTED: the lantern is already carried at the first
        # decision on the floor, so it was not picked up there.
        policy = make_policy(self.facts)
        carried = self.rows[75413]
        policy.prime(parse_snapshot(carried, policy._monrace_knowledge))
        key, reason = self.decide(policy, carried)
        self.assertNotEqual(reason, "quest-strategy:q34-inscribe-pickup")
        self.assertEqual((key, reason), ("wd", "quest-strategy:equip-opening-lantern"))


if __name__ == "__main__":
    import unittest
    unittest.main()
