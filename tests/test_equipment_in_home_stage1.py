import json
import unittest
import copy
import gzip
import tempfile
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from hengbot.cli import _dispatch_response_lines
from hengbot.control_client import ControlClient
from hengbot.equipment_optimizer import Loadout, current_loadout
from hengbot.equipment_transaction_planner import plan_equipment_transactions
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.input_executor import Operation, OperationExecutor
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from tests.support.faithful_home import FaithfulHomeGame

ROOT = Path(__file__).resolve().parents[1]
INCIDENT = ROOT / "jsonlog" / "incident-20260914-town0-resume-2305" / "decisions.jsonl"
CAPTURE = ROOT / "jsonlog" / "live-screens" / "25-town0-home-equip-leave-loop.json"
RECORDED = ROOT / "tests" / "fixtures" / "equipment-in-home-town0-2305.jsonl.gz"
ENTER_LEAVE_RECORDED = (
    ROOT / "tests" / "fixtures" /
    "home-equip-enter-leave-loop-20260915.jsonl.gz"
)


class EquipmentInHomeArtifactFacts(unittest.TestCase):
    def test_enter_leave_loop_fixture_is_the_recorded_board_window(self):
        with gzip.open(ENTER_LEAVE_RECORDED, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        self.assertEqual(len(rows), 25)
        self.assertEqual(
            [(row["type"], row["turn"],
              None if row.get("store") is None else row["store"]["store_type"])
             for row in rows[7:12]],
            [("player_turn", 2899629, None),
             ("player_turn", 2899629, None),
             ("store", 2899629, 7),
             ("knowledge", 2899629, None),
             ("store", 2899629, 7)],
        )
        self.assertEqual(len(rows[12]["inventory"]), 20)
        self.assertEqual(len(rows[15]["inventory"]), 19)

    def test_rows_7_through_14_freeze_recorded_incident(self):
        rows = [json.loads(x) for x in INCIDENT.read_text(encoding="utf-8").splitlines()][6:14]
        self.assertEqual([r["decision_sequence"] for r in rows], list(range(6, 14)))
        self.assertEqual(sum(r["key"] == "\x1b" for r in rows), 2)
        self.assertEqual(sum(r["reason"] == "equipment-transaction:leave-home-to-equip" for r in rows), 2)
        # Three physical entries total: the initial acquisition and two
        # re-entries after the two recorded voluntary exits.
        self.assertEqual(sum(r["acquire_result"] == "granted-new" for r in rows), 3)
        self.assertEqual(sum(r["store_type"] == 7 for r in rows), 3)
        tx = rows[0]["equipment_optimization"]
        self.assertEqual(tx["transaction_next"], {"phase": "equip", "kind": "takeoff", "item_id": "equipped:0838f45775733b5d:0", "target_slot": "outer"})
        self.assertEqual(tx["transaction_target_loadout_id"], "8dfe4c9a8212d725")
        self.assertEqual(rows[0]["inventory"], {"used": 19, "free": 4})

    def test_post_stop_capture_is_explicitly_not_a_store_barrier(self):
        capture = json.loads(CAPTURE.read_text(encoding="utf-8"))
        state = capture["state"]["result"]
        self.assertNotIn("store", state)
        self.assertEqual(state["type"], "player_turn")

    def test_fake_models_prompt_consumption_reorder_refusal_and_overflow(self):
        worn = {"id": "worn", "slot": "outer"}; carried = {"id": "carry", "slot": "outer"}
        game = FaithfulHomeGame(pack=[carried], equipment={"outer": worn}, pages=[[{"id": "z"}]], pack_limit=1)
        game._consume("ti")
        self.assertNotIn("outer", game.equipment)
        self.assertEqual([x["id"] for x in game.pages[0]], ["worn", "z"])
        self.assertTrue(game.inside)
        full = FaithfulHomeGame(pack=[carried], equipment={"outer": worn}, pages=[[{"id": "z"}]], pack_limit=1, home_limit=1)
        full._consume("ti")
        self.assertFalse(full.inside)


class EquipmentInHomeBehaviorPins(unittest.TestCase):
    """Public behavior pins; every mutation is downstream of accepted bytes."""

    @staticmethod
    def _recorded_rows():
        with gzip.open(RECORDED, "rt", encoding="utf-8") as stream:
            lines = stream.readlines()
        return lines, [json.loads(line) for line in lines]

    def _recorded_game(self, *, inside=True, pack=None, equipment=None, pages=None,
                       pack_limit=23, home_limit=80):
        _lines, rows = self._recorded_rows()
        raw = copy.deepcopy(rows[8])
        raw["nearby_grids"] = [{
            "y": raw["player"]["y"], "x": raw["player"]["x"], "known": True,
            "terrain": {"passable": True}, "store_number": 7,
        }]
        return FaithfulHomeGame(
            pack=raw["inventory"] if pack is None else pack,
            equipment={item["slot"]: item for item in raw["equipment"]}
            if equipment is None else equipment,
            pages=pages or [copy.deepcopy(rows[9]["store"]["items"])],
            pack_limit=pack_limit, home_limit=home_limit,
            inside=inside, state_template=raw,
        )

    def _recorded_policy(self):
        """Replay the recorded ~9 producer/consumer, then the real planner.

        The incident decision records name the two preserved pack identities;
        applying that recorded constraint to the recorded catalogue recovers
        the exact three-action continuation and target id.
        """
        lines, rows = self._recorded_rows()
        policy = HengbotPolicy()
        outside = parse_snapshot(rows[0], {})
        policy.prime(outside)
        scan_key = policy.choose_key(outside)
        self.assertEqual((scan_key, policy.last_reason),
                         ("~9\x1b\x1b", "home:request-knowledge-scan"))
        policy.confirm_key_posted(scan_key)
        with tempfile.TemporaryDirectory() as directory:
            consumed = _dispatch_response_lines(
                [lines[1]], policy, lambda _keys: None,
                knowledge_ledger_path=Path(directory) / "knowledge.jsonl",
            )
        self.assertEqual(consumed, 1)
        self.assertEqual(policy._home_scan_item_count, 62)

        incident = parse_snapshot(rows[8], {})
        policy.prime(incident)
        catalog = policy._equipment_catalog.items
        current = current_loadout(catalog)
        target_outer = next(
            item for item in catalog if item.id == "pack:dceeaad31f2254f4:0"
        )
        target = Loadout(tuple(
            (slot, target_outer if slot == "outer" else item)
            for slot, item in current.slots
        ), current.hand_mode)
        plan = plan_equipment_transactions(
            catalog, current, target,
            current_pack_items=len(incident.inventory),
            home_scan_complete=policy._equipment_catalog.home_scan_complete,
            preserve_pack_item_ids=frozenset({
                "pack:c610faea8130c1c2:0",
                "pack:e35d3b7107774db3:0",
            }),
        )
        session = EquipmentTransactionSession(plan, physical_context="home")
        self.assertEqual(session.target_loadout_id, "8dfe4c9a8212d725")
        self.assertEqual(
            (session.current_action.kind, session.current_action.item_id,
             session.current_action.target_slot),
            ("takeoff", "equipped:0838f45775733b5d:0", "outer"),
        )
        policy._set_equipment_transaction_session(session)
        return policy

    def _drive(self, game, decisions=1, policy=None):
        client = ControlClient(1, request_budget=2, retries=1, backoff=0,
                               socket_factory=game.socket_factory)
        self.addCleanup(client.close)
        # Source emitter writes the bound STORE record before the next command
        # wait; the drain supplies that independent JSONL consumer channel.
        executor = OperationExecutor(client, drain=lambda: [game._state()])
        policy = policy or HengbotPolicy()
        transaction_target = (
            policy._equipment_transaction_session.target_loadout_id
            if policy._equipment_transaction_session is not None else None
        )
        result = executor.observe_boundary(deadline=9999999999)
        reasons = []
        for sequence in range(decisions):
            if result.outcome not in ("ready", "completed"):
                break
            snapshot = parse_snapshot(result.board, {})
            policy.prime(snapshot)
            key = policy.choose_key(snapshot)
            reasons.append(policy.last_reason)
            result = executor.submit(
                Operation(sequence, f"policy:{policy.last_reason}", key, result.board),
                deadline=9999999999,
            )
            if result.outcome == "completed":
                policy.confirm_key_posted(key)
            if (
                transaction_target is not None
                and policy._equipment_transaction_session is None
                and not game.inside
            ):
                break
        return policy, result, reasons

    @staticmethod
    def _accepted(game):
        return [entry[1] for entry in game.trace
                if isinstance(entry, tuple) and entry[0] == "accepted"]

    @staticmethod
    def _ledger(game):
        def identity(item):
            return (item.get("name"), item.get("tval"), item.get("sval"))
        return Counter(
            identity(item)
            for item in (
                list(game.pack) + list(game.equipment.values())
                + [item for page in game.pages for item in page]
            )
        )

    def _assert_completed_recorded_outer_plan(self, game, before, accepted, reasons):
        recorded_outer = before.equipment["outer"]
        recorded_identity = (recorded_outer.get("name"), recorded_outer.get("tval"),
                             recorded_outer.get("sval"))
        final_outer = game.equipment.get("outer")
        self.assertTrue(any(key.startswith("t") for key in accepted),
                        ("recorded next takeoff was not posted", accepted, reasons))
        self.assertIsNotNone(final_outer, (game.equipment, reasons))
        self.assertNotEqual(
            (final_outer.get("name"), final_outer.get("tval"), final_outer.get("sval")),
            recorded_identity, ("target outer loadout was not applied", game.equipment),
        )
        displaced = [item for item in game.pack] + [item for page in game.pages for item in page]
        self.assertIn(recorded_identity, [
            (item.get("name"), item.get("tval"), item.get("sval")) for item in displaced
        ], ("displaced outer was not stored", displaced))
        self.assertEqual(self._ledger(game), self._ledger(before), "item conservation")
        self.assertFalse(any(
            reason.startswith("town:blocked:") or "unsatisfiable" in reason
            or "stuck-prompt" in reason for reason in reasons
        ), reasons)
        self.assertEqual((game.entries, game.reentries, game.exits), (1, 0, 1))
        self.assertEqual(accepted.count("\x1b"), 1, accepted)
        self.assertEqual(accepted[-1], "\x1b", "the only Home exit must be final")

    def test_h1_incident_finishes_with_one_exit_and_zero_reentries(self):
        # Public counterfactual starts outside at the recorded town-0 position.
        # The missing STORE stock is source-derived by the fake; optimization
        # and routing are produced normally by one persistent HengbotPolicy.
        game = self._recorded_game(inside=False)
        before = copy.deepcopy(game)
        _policy, _result, reasons = self._drive(
            game, 12, policy=self._recorded_policy())
        self._assert_completed_recorded_outer_plan(
            game, before, self._accepted(game), reasons,
        )

    @unittest.expectedFailure  # Stage 4 must remove: H2 prompt-owned ring suffix.
    def test_h2_pack_letter_is_not_store_letter_and_ring_suffix_is_prompt_owned(self):
        game = self._recorded_game(pages=[[{"id": "shelf-a", "name": "shelf decoy"}]])
        _policy, _result, reasons = self._drive(game, 3)
        accepted = self._accepted(game)
        rings = tuple(sorted((slot, item["name"]) for slot, item in game.equipment.items() if "ring" in slot))
        self.assertTrue(any(key.startswith("w") and len(key) > 2 for key in accepted), (accepted, rings, reasons))

    @unittest.expectedFailure  # Stage 4 must remove: H3 full two-hand reconciliation.
    def test_h3_weapon_switch_confirms_both_hands(self):
        before = self._recorded_game().equipment
        game = self._recorded_game()
        _policy, _result, reasons = self._drive(game, 3)
        pair = tuple(game.equipment.get(slot, {}).get("name") for slot in ("main_hand", "sub_hand"))
        target = tuple(before.get(slot, {}).get("name") for slot in ("sub_hand", "main_hand"))
        self.assertEqual(pair, target, (game.trace, reasons))

    @unittest.expectedFailure  # Stage 4 must remove: H4 curse refusal outcome.
    def test_h4_curse_more_refusal_is_terminal_without_repost(self):
        game = self._recorded_game()
        before = copy.deepcopy(game.equipment)
        _policy, result, reasons = self._drive(game, 4)
        accepted = self._accepted(game)
        self.assertTrue(result.outcome == "stuck-prompt" and game.equipment == before
                        and sum(key.startswith("w") for key in accepted) == 1
                        and any("curse" in reason for reason in reasons),
                        (result.outcome, accepted, reasons))

    @unittest.expectedFailure  # Stage 2 must remove: H5 implicit shelving confirmation.
    def test_h5_takeoff_accepts_source_proven_home_overflow_destination(self):
        game = self._recorded_game(pack_limit=19)
        worn = game.equipment["outer"]
        _policy, _result, reasons = self._drive(game, 3)
        self.assertTrue(game.inside and "outer" not in game.equipment
                        and any(item["name"] == worn["name"] for page in game.pages for item in page),
                        (game.trace, reasons))

    @unittest.expectedFailure  # Stage 2 must remove: H6 full refusal/rebind result.
    def test_h6_home_full_is_no_effect_and_invalidates_stale_address(self):
        game = self._recorded_game(pages=[[{"id": "only", "name": "only slot"}]], home_limit=1)
        before = copy.deepcopy(game.pack)
        _policy, result, reasons = self._drive(game, 4)
        deposits = [value for value in self._accepted(game) if value.startswith("d")]
        self.assertTrue(game.pack == before and len(deposits) == 1 and result.outcome == "stuck-prompt",
                        (deposits, result.outcome, reasons))

    @unittest.expectedFailure  # Stage 4 must remove: H7 in-Home calibration lifecycle.
    def test_h7_calibration_strip_capture_restore_and_rearm_stays_inside(self):
        game = self._recorded_game()
        before = sorted((slot, item["name"]) for slot, item in game.equipment.items())
        _policy, _result, reasons = self._drive(game, 8)
        accepted = self._accepted(game)
        after = sorted((slot, item["name"]) for slot, item in game.equipment.items())
        self.assertTrue(any("C" in key for key in accepted) and before == after
                        and game.entries == 1 and game.exits == 0, (accepted, reasons))

    @unittest.expectedFailure  # Stage 4 must remove: H8 owned viewer settlement.
    def test_h8_owned_knowledge_viewer_settles_once_or_stops_unknown_modal(self):
        game = self._recorded_game(pages=[[], [{"id": "page-b", "name": "page b"}]])
        _policy, result, reasons = self._drive(game, 5)
        scans = [value for value in self._accepted(game) if value.startswith("~9")]
        self.assertTrue(len(scans) == 1 and (game.inside or result.outcome == "stuck-prompt"),
                        (scans, game.inside, result.outcome, reasons))

    @unittest.expectedFailure  # Stage 4 must remove: H9 operation-boundary priority.
    def test_h9_known_surplus_precedes_unknown_identification_and_ammo_topup(self):
        game = self._recorded_game(pack_limit=19)
        _policy, _result, reasons = self._drive(game, 2)
        accepted = self._accepted(game)
        self.assertTrue(accepted and accepted[0].startswith("d"), (accepted, reasons))

    def test_h10_completed_operations_continue_visit_without_attempt_reset(self):
        game = self._recorded_game(inside=False)
        before = copy.deepcopy(game)
        _policy, _result, reasons = self._drive(
            game, 8, policy=self._recorded_policy())
        accepted = self._accepted(game)
        self.assertTrue(accepted and accepted[0] == "5", (accepted, reasons))
        self._assert_completed_recorded_outer_plan(game, before, accepted, reasons)

    def test_supplementary_planner_admits_pack_space_deposit_inside_home(self):
        policy = self._recorded_policy()
        catalog = policy._equipment_catalog.items
        current = current_loadout(catalog)
        pack_ids = [item.id for item in catalog if item.origin == "pack"]
        plan = plan_equipment_transactions(
            catalog, current, current,
            current_pack_items=len(pack_ids),
            home_scan_complete=True,
            preserve_pack_item_ids=frozenset(pack_ids[1:]),
        )
        self.assertEqual(
            (plan.actions[0].phase, plan.actions[0].kind),
            ("home_prepare", "deposit"),
        )
        session = policy._equipment_transaction_session_for_preparation(
            SimpleNamespace(transaction=plan, ready=True)
        )
        self.assertIsNotNone(session)
        self.assertEqual(session.physical_context, "home")
        policy._set_equipment_transaction_session(session)
        game = self._recorded_game(inside=True)
        policy, _result, reasons = self._drive(game, 4, policy=policy)
        accepted = self._accepted(game)
        # The selected Home deposit is a singleton, so no quantity prompt
        # consumes Return (sell-order.cpp:97-103).
        self.assertEqual(accepted, ["do", "\x1b"])
        self.assertEqual(
            reasons,
            ["equipment-transaction:deposit", "home:leave-after-one-operation"],
        )
        self.assertEqual((game.entries, game.reentries, game.exits), (1, 0, 1))
        outside = parse_snapshot(game._state(), {})
        policy.prime(outside)
        next_key = policy.choose_key(outside)
        self.assertEqual((next_key, policy.last_reason), ("rhj", "identify:device"))
        self.assertFalse(any("owner-retired" in reason for reason in reasons))

    def test_behavior_pins_do_not_assert_defaulted_policy_or_visit_attributes(self):
        source = Path(__file__).read_text(encoding="utf-8")
        forbidden = "get" + "attr("
        self.assertNotIn(forbidden, source)
        # Also prove the ACK/consumption causal seam so this is not a
        # source-text-only acceptance test.  ACK queues; the screen hook acts.
        item = {"name": "record-shaped cloak", "slot": "outer"}
        game = FaithfulHomeGame(pack=[], equipment={"outer": item})
        ack = game.request({"id": 1, "op": "keys", "keys": "ti"})
        self.assertTrue(ack["ok"])
        self.assertIn("outer", game.equipment)
        game.request({"id": 2, "op": "screen"})
        self.assertNotIn("outer", game.equipment)
        self.assertEqual(game.pack, [item])
