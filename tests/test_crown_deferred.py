"""Issue #47: reconstructed equipment episode from the preserved dump/report.

DECLARED CONSTRUCTED: no raw state stream/checkpoint was supplied. The board
uses the existing lamp fixture's town grid/UI envelope, recorded v2 calibration,
and the dump's worn gear plus the three selected Home items. Proficiency,
weights, item subtype details absent from the dump are constructed constants;
the launcher and unrelated pack/Home stock are omitted. Item flags transcribe
the dump abbreviations, not hidden properties. Home deferral is seeded from
bot-decisions.jsonl:2097 (02:22:01); the chosen set is retained as evidence.
No selector, gate, transaction, or decision producer is mocked.
"""
import tests
import copy
from dataclasses import replace
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.equipment_optimizer import equipment_identity
from hengbot.warrior_optimization import load_character_calibration
from test_esp_threat_rest_recorded import _policy, EDIT

FIXTURE = Path(__file__).parent / "fixtures/crown-deferred-1027.json"

class CrownDeferredTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(FIXTURE.read_text(encoding="utf8"))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.board = copy.deepcopy(self.data["board"])
        self.policy = _policy(self.root, self.monrace)
        calibration = self.root / "calibration.json"
        calibration.write_text(json.dumps(self.data["calibration"]), encoding="utf8")
        self.policy._character_calibration = load_character_calibration(calibration)
        self.policy._character_calibration_loaded = True
        snapshot = parse_snapshot(self.board, self.monrace)
        self.policy.prime(snapshot)
        self.policy._equipment_catalog.refresh_carried(snapshot.inventory, snapshot.equipment)
        self.policy._equipment_catalog.complete_home_scan(snapshot.store.items)
        self.policy._home_knowledge_items = snapshot.store.items
        self.policy._home_knowledge_current = True
        self.policy._home_knowledge_valid_before = len(snapshot.store.items)
        self.plate = snapshot.store.items[-1]
        self.policy._deferred_home_items.add(self.policy._item_signature(self.plate))
        self.preparation = self.policy._prepare_equipment_optimization(snapshot)

    def test_ready_slots_are_selected_while_the_plate_waits(self):
        prep = self.preparation
        best = prep.result.best.loadout
        self.assertEqual(best.item_at("head").item.name,
                         self.data["recorded_candidate"]["head"]["name"])
        self.assertEqual(best.item_at("body").item.name, self.plate.name)
        self.assertEqual(prep.blockers, ("pending-random-teleport-suppression",))
        self.assertIsNotNone(self.policy._equipment_transaction_session)
        actions = prep.transaction.actions
        self.assertIn(("equip", "head"), [(a.kind, a.target_slot) for a in actions])
        self.assertFalse(any(a.target_slot == "body" for a in actions))
        self.assertFalse(any(a.item_identity == equipment_identity(self.plate) for a in actions))
        self.assertTrue(any(a.kind == "withdraw" for a in actions))

    def _apply(self, action):
        """Construct only the physical effect of a posted transaction command."""
        board = self.board
        def identity(raw):
            # Parse through the production model, retaining item identity rules.
            probe = copy.deepcopy(board)
            probe["inventory"] = [dict(raw, slot="a")]
            return equipment_identity(parse_snapshot(probe, self.monrace).inventory[0])
        target = action.item_identity
        if action.kind == "withdraw":
            source = board["store"]["items"]
            raw = next(i for i in source if identity(i) == target)
            source.remove(raw)
            board["inventory"].append(dict(raw, slot=chr(97+len(board["inventory"]))))
        elif action.kind == "takeoff":
            raw = next(i for i in board["equipment"] if i["slot"] == action.target_slot)
            board["equipment"].remove(raw)
            board["inventory"].append(dict(raw, slot=chr(97+len(board["inventory"]))))
        elif action.kind in {"equip", "reposition"}:
            raw = next(i for i in board["inventory"] if identity(i) == target)
            board["inventory"].remove(raw)
            board["equipment"].append(dict(raw, slot=action.target_slot))
        elif action.kind == "deposit":
            raw = next(i for i in board["inventory"] if identity(i) == target)
            board["inventory"].remove(raw)
            board["store"]["items"].append(dict(raw, letter="z", price=0))
        for index, raw in enumerate(board["inventory"]):
            raw["slot"] = chr(97+index)
        for index, raw in enumerate(board["store"]["items"]):
            raw["letter"] = chr(97+index)
        board["store"]["stock_num"] = len(board["store"]["items"])
        board["turn"] += 10
        # DECLARED CONSTRUCTED: the next board shows the equipment's stat effect.
        from hengbot.warrior_equipment_evaluator import modify_stat_value
        from hengbot.warrior_loadout_evaluator import constitution_hp_bonus
        cal = self.policy._character_calibration
        for n, stat in enumerate(("str", "int", "wis", "dex", "con", "chr")):
            value = modify_stat_value(cal.natural_stats[n], cal.intrinsic_adjustments[n]
                + sum(i["pval"] for i in board["equipment"] if n in i["known_flags"]))
            board["player"]["stats"][stat]["use"] = value
        board["player"]["max_hp"] = cal.base_hp + constitution_hp_bonus(
            board["player"]["stats"]["con"]["use"], 27)
        board["player"]["hp"] = board["player"]["max_hp"]

    def _post_through_follow_executor(self, before, key, action):
        """Use follow's sender, TCP protocol client and causal-barrier executor.

        Only the game is simulated: Term prompts followed by the constructed
        inventory/equipment delta. No executor or policy method is replaced.
        """
        from hengbot.cli import _ExecutorInputPort, _send_new_decision_key, PostingContract
        from hengbot.control_client import ControlClient
        from hengbot.input_executor import OperationExecutor
        from hengbot.observed_input import _GET, _PUT, _WIELD, _TAKEOFF, _HAND
        from test_input_executor import FaithfulHookGame, store_screen, prompt_screen
        game = FaithfulHookGame()
        def screen_for(board):
            import unicodedata
            screen = store_screen()
            screen["lines"][20] = "You may: g) Get an item. d) Drop an item."
            for index, raw in enumerate(board["store"]["items"]):
                text, width = "", 0
                for char in raw["name"]:
                    size = 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
                    if width + size > 64:
                        break
                    text += char
                    width += size
                screen["lines"][6 + index] = raw["letter"] + ") " + text
            return screen
        game.state, game.screen = before, screen_for(before)
        game.jsonl.append(copy.deepcopy(before))
        feature = {"withdraw": _GET, "deposit": _PUT,
                   "equip": _WIELD, "reposition": _WIELD,
                   "takeoff": _TAKEOFF}[action.kind][0]
        if action.kind == "withdraw":
            feature = "(\u30a2\u30a4\u30c6\u30e0:a-z, ESC\u3067\u4e2d\u65ad) " + feature
        game.screens = [prompt_screen(feature)]
        game.states = [copy.deepcopy(before)]
        if action.kind in {"equip", "reposition"} and len(key) == 3:
            game.screens.append(prompt_screen(_HAND[0]))
            game.states.append(copy.deepcopy(before))
        game.screens.append(screen_for(self.board))
        game.states.append(copy.deepcopy(self.board))
        client = ControlClient(1, request_budget=2, retries=0, backoff=0,
                               socket_factory=game.socket_factory)
        self.addCleanup(client.close)
        executor = OperationExecutor(client, drain=lambda: list(game.jsonl))
        boundary = executor.observe_boundary(deadline=9999999999)
        self.assertEqual(boundary.outcome, "ready", boundary)
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2,
                                  policy=self.policy)
        snapshot = parse_snapshot(before, self.monrace)
        sent, _ = _send_new_decision_key(
            port, json.dumps(before), key, None, set(), in_store=True,
            decision={"sequence": self.policy._decision_sequence,
                      "reason": self.policy.last_reason},
            snapshot=snapshot, posting_contract=PostingContract())
        self.assertTrue(sent, (key, port.last_result.reason))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), key)
        self.assertEqual(port.last_result.board["equipment"], self.board["equipment"])
        self.policy.reconcile_input_operation(port.last_result.operation.owner,
                                               port.last_result.operation.business_outcome)

    def test_public_choose_key_withdraws_and_wears_ready_items(self):
        posted = []
        session = self.policy._equipment_transaction_session
        self.assertIsNotNone(session)
        for _ in range(len(session.plan.actions) * 2 + 1):
            snapshot = parse_snapshot(self.board, self.monrace)
            key = self.policy.choose_key(snapshot)
            action = session.current_action
            self.assertIsNotNone(key, self.policy.last_reason)
            if session.complete:
                break
            self.assertIsNotNone(action, self.policy.last_reason)
            if key == "\x1b":
                self.policy.confirm_key_posted(key)
                self.policy.prime(replace(snapshot, store=None))
                self.board["turn"] += 10
                self.policy._store_visit = None
                self.policy.prime(parse_snapshot(self.board, self.monrace))
                continue
            self.assertTrue(self.policy.last_reason.startswith("equipment-transaction:"),
                            (key, self.policy.last_reason))
            posted.append((action.kind, action.target_slot, key))
            before = copy.deepcopy(self.board)
            self._apply(action)
            self._post_through_follow_executor(before, key, action)
            self.policy.confirm_key_posted(key)
            # Same observation ingress used by the follow driver.
            self.policy.prime(parse_snapshot(self.board, self.monrace))
        self.assertTrue(session.complete, posted)
        self.assertIn(("equip", "head"), [(k,s) for k,s,_ in posted])
        self.assertTrue(any(k == "withdraw" for k,_,_ in posted))
        worn = {i["slot"]: i["name"] for i in self.board["equipment"]}
        self.assertEqual(worn["head"], self.data["recorded_candidate"]["head"]["name"])
        self.assertIn(self.data["recorded_candidate"]["main_ring"]["name"], worn.values())
        self.assertNotEqual(worn["body"], self.plate.name)

    def test_fully_identified_plate_joins_the_same_selected_set(self):
        self.board["store"]["items"][-1]["fully_known"] = True
        self.policy._deferred_home_items.clear()
        snapshot = parse_snapshot(self.board, self.monrace)
        self.policy._set_equipment_transaction_session(None)
        self.policy._equipment_catalog.complete_home_scan(snapshot.store.items)
        prep = self.policy._prepare_equipment_optimization(snapshot)
        self.assertFalse(prep.blockers, prep.blockers)
        self.assertTrue(any(a.kind == "equip" and a.target_slot == "body"
                            for a in prep.transaction.actions))

    def test_partial_target_does_not_authorize_departure(self):
        snapshot = parse_snapshot(self.board, self.monrace)
        self.assertFalse(self.policy._equipment_departure_ready(snapshot, destination_depth=30))
