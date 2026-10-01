"""Production input-port pins for Class A, using verbatim recorded screens.

Command waits and modified player/stock boards are declared constructed
protocol controls. They do not claim action-consistent post-divergence effects.
All successful modal screen shapes come from existing live-screen captures.
"""

import tests  # noqa: F401
import copy
import json
import time
from pathlib import Path

from hengbot.cli import _ExecutorInputPort, _send_new_decision_key
from hengbot.input_executor import Continuation, ScreenKind, classify_screen
from hengbot.model import InventoryItem, TVAL_RING, STORE_ALCHEMIST, parse_snapshot
from hengbot.policy import ConservativePolicy
from hengbot.policy_constants import EQUIPMENT_SLOT_KEY, REST_MACRO, CHARACTER_DUMP_MACRO, ENTER_DUNGEON_MACRO
from tests.test_input_executor import ProductionHarness, FaithfulHookGame, command_screen, prompt_screen
from tests.test_live30_identify_normal import derived_chooser


FIXTURES = Path(__file__).parent / "fixtures"


def recorded(name):
    value = json.loads((FIXTURES / "live-screens" / name).read_text(encoding="utf-8"))
    if "lines" in value:
        return value
    return value.get("screen", value)["result"]


def board():
    return json.loads((FIXTURES / "live30-identify-normal" /
                       "before-identify.json").read_text(encoding="utf-8"))


class ClassAObservedInputPins(ProductionHarness):
    def drive(self, key, owner, screens, *, initial=None, raw=None, steps=None, states=None):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw or board())
        game.screen = initial or command_screen(game.state["turn"])
        # Constructed coherent store record, explicitly a protocol control.
        if initial is not None:
            game.jsonl = [copy.deepcopy(game.state)]
        game.screens = copy.deepcopy(screens)
        game.states = copy.deepcopy(states) if states is not None else [
            copy.deepcopy(game.state) for _screen in screens]
        _, client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 1).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=0.2)
        if steps is not None:
            port.submit_operation(key, decision={"sequence": 1, "reason": owner},
                                  continuations=steps)
        else:
            _send_new_decision_key(port, "classA-protocol-control", key, None, set(),
                in_store=initial is not None,
                decision={"sequence": 1, "reason": owner},
                snapshot=parse_snapshot(game.state, {}), posting_contract=None)
        return game, port.last_result

    def home(self):
        raw = board()
        raw["store"] = {"store_type": 7, "items": [], "stock_num": 0,
                        "page_top": 0, "page_size": 52}
        return raw, recorded("live-screen-cap-17-home-wield-ring-hand-e.json")

    def test_quaff_producer_never_answers_a_recorded_read_chooser(self):
        raw = board()
        # Constructed status change; unmodified captured pack provides cure.
        raw["player"].setdefault("status", {})["cut"] = True
        policy = ConservativePolicy()
        key = policy._emergency_item(parse_snapshot(raw, {}), [])
        self.assertEqual((key, policy.last_reason), ("qc", "item:cure-critical"))
        game, result = self.drive(key, policy.last_reason,
            [recorded("live15-read-scroll-prompt.json")], raw=raw)
        self.assertEqual(game.accepted, ["q"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_recorded_quaff_accepts_its_item_only_after_observation(self):
        game, result = self.drive("qc", "item:cure-critical", [
            recorded("live30-quaff-prompt.json"), command_screen(2)])
        self.assertEqual(game.accepted, ["q", "c"])
        self.assertEqual(result.outcome, "completed")

    def test_read_composer_drops_source_on_recorded_quaff(self):
        raw = board()
        snapshot = parse_snapshot(raw, {})
        scroll = next(item for item in snapshot.inventory if item.slot == "j")
        key = ConservativePolicy()._read_key(snapshot, scroll)
        self.assertEqual(key, "rj")
        game, result = self.drive(key, "light:scroll", [recorded("live30-quaff-prompt.json")])
        self.assertEqual(game.accepted, ["r"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_device_source_prefix_is_gated_even_with_existing_target_chain(self):
        for key in ("um", "zi", "rf"):
            with self.subTest(key=key):
                game, result = self.drive(key, "identify:device", [recorded("live30-quaff-prompt.json")],
                    steps=[Continuation(frozenset({ScreenKind.ITEM_TARGET}), "q",
                                        "どのアイテムを鑑定しますか?")])
                self.assertEqual(game.accepted, [key[0]])
                self.assertEqual(result.outcome, "stuck-prompt")

    def test_town_device_producer_cannot_answer_a_quaff_chooser(self):
        raw = board()
        # Constructed device knowledge variant; no pipeline result is injected.
        for item in raw["inventory"]:
            if item["slot"] == "m":
                item["known"] = False
        policy = ConservativePolicy()
        key = policy._town_device_processing_key(parse_snapshot(raw, {}))
        self.assertEqual((key, policy.last_reason), ("rhm", "identify:device"))
        game, result = self.drive(key, policy.last_reason,
                                   [recorded("live30-quaff-prompt.json")], raw=raw)
        self.assertEqual(game.accepted, ["r"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_recorded_failure_message_withholds_target_after_staff_selection(self):
        before = board()
        failed = json.loads((FIXTURES / "live30-identify-normal" /
                             "staff-failed.json").read_text(encoding="utf-8"))
        # Reuse the authorized live30 constructed chooser/command-wait control.
        # The posted prefix is u,o; q is the first withheld/divergent key. No
        # later board is treated as the effect of that unposted target answer.
        game, result = self.drive("uoq", "identify:device",
            [derived_chooser(before), command_screen(failed["turn"])], states=[before, failed])
        self.assertEqual(game.accepted, ["u", "o"])
        self.assertEqual(result.outcome, "completed")
        self.assertEqual(result.operation.dropped_continuations, ["q"])

    def test_constructed_more_consumes_only_space_before_wrong_chooser(self):
        # Constructed MORE control, declared here; successful item UI is never invented.
        game, result = self.drive("rj", "light:scroll", [
            prompt_screen("-more-"), recorded("live30-quaff-prompt.json")])
        self.assertEqual(game.accepted, ["r", " "])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_floor_identify_target_waits_for_its_own_chooser(self):
        raw = board()
        snapshot = parse_snapshot(raw, {})
        scroll = next(item for item in snapshot.inventory if item.slot == "h")
        key = ConservativePolicy()._read_key(snapshot, scroll, "-")
        game, result = self.drive(key, "loot:identify-floor-item", [
            recorded("live-screen-cap-27-dungeon-read-r.json"),
            recorded("live30-quaff-prompt.json")])
        self.assertEqual(game.accepted, ["r", "h"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_normal_equipped_producer_requires_an_advertised_equipment_page(self):
        raw = board()
        # Constructed pack restriction/knowledge change, explicitly not a replay.
        raw["inventory"] = [item for item in raw["inventory"] if item["slot"] == "h"]
        for item in raw["equipment"]:
            item["known"] = False
        policy = ConservativePolicy()
        key = policy._town_equipped_identification_key(parse_snapshot(raw, {}), macro=True)
        self.assertEqual((key, policy.last_reason), ("rh/a", "identify:normal-equipped"))
        game, result = self.drive(key, policy.last_reason, [
            recorded("live-screen-cap-27-dungeon-read-r.json"),
            recorded("20-sweep-identify-item-target.json")], raw=raw)
        self.assertEqual(game.accepted, ["r", "h"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_page_switch_and_item_are_separately_observed(self):
        raw, idle = self.home()
        game, result = self.drive("d", "home:deposit-equipment", [
            recorded("live-screen-cap-31-home-deposit-d.json"),
            recorded("live30-quaff-prompt.json")], initial=idle, raw=raw,
            steps=[Continuation(frozenset({ScreenKind.ITEM_SOURCE}), "/j",
                                "どのアイテムを置きますか?")])
        self.assertEqual(game.accepted, ["d", "/"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_store_price_confirmation_never_answers_quest_entry(self):
        raw, idle = self.home()
        raw["store"]["store_type"] = STORE_ALCHEMIST
        idle = recorded("live-screen-cap-08-alchemist-buy-confirm.json")
        game, result = self.drive("pq", "shop:one-shot-buy", [
            recorded("live-screen-cap-05-alchemist-buy-p.json"),
            recorded("19-quest-entry-confirm-yn.json")], initial=idle, raw=raw,
            steps=[Continuation(frozenset({ScreenKind.CONFIRM}), "\r")])
        self.assertEqual(game.accepted, ["p", "q"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_equipment_takeoff_composer_never_answers_quaff(self):
        snapshot = parse_snapshot(board(), {})
        policy = ConservativePolicy()
        key = policy._equipment_takeoff(snapshot, "classA-takeoff", "e")
        self.assertEqual(key, "te")
        game, result = self.drive(key, "equipment-transaction:takeoff",
                                   [recorded("live30-quaff-prompt.json")])
        self.assertEqual(game.accepted, ["t"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_wield_hand_answer_waits_for_observed_hand_chooser(self):
        # Constructed ring, using the name and address shown by recorded cap-15.
        ring = InventoryItem("l", "恐れ知らずの指輪", 1, TVAL_RING, 2, True, True)
        policy = ConservativePolicy()
        key = policy._equipment_mutation.request_wield(
            parse_snapshot(board(), {}), "classA-ring", ring, "sub_ring",
            EQUIPMENT_SLOT_KEY).key
        self.assertEqual(key, "wl)")
        game, result = self.drive(key, "equipment-transaction:equip", [
            recorded("live-screen-cap-15-home-wield-w.json"),
            recorded("live30-quaff-prompt.json")])
        self.assertEqual(game.accepted, ["w", "l"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_recorded_hand_prompt_releases_ring_answer(self):
        game, result = self.drive("wl)", "equipment-transaction:equip", [
            recorded("live-screen-cap-15-home-wield-w.json"),
            recorded("live-screen-cap-16-home-wield-ring-l.json"), command_screen(2)])
        self.assertEqual(game.accepted, ["w", "l", ")"])
        self.assertEqual(result.outcome, "completed")

    def test_home_deposit_composer_never_answers_a_take_chooser(self):
        raw, idle = self.home()
        snapshot = parse_snapshot(raw, {})
        item = next(item for item in snapshot.inventory if item.slot == "c")
        key = ConservativePolicy()._home_deposit_key(snapshot, item, forced_count=1)
        self.assertEqual(key, "dc1\r")
        game, result = self.drive(key, "home:deposit",
            [recorded("live-screen-cap-11-home-withdraw-g.json")], initial=idle, raw=raw)
        self.assertEqual(game.accepted, ["d"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_home_withdraw_quantity_never_answers_rest_prompt(self):
        raw, idle = self.home()
        game, result = self.drive("px1\r\x1b", "home:atomic-withdraw", [
            recorded("live-screen-cap-11-home-withdraw-g.json"),
            recorded("10-rest-prompt.json")], initial=idle, raw=raw)
        self.assertEqual(game.accepted, ["p", "x"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_home_batch_next_command_requires_return_to_store(self):
        raw, idle = self.home()
        snapshot = parse_snapshot(raw, {})
        policy = ConservativePolicy()
        staff = next(item for item in snapshot.inventory if item.slot == "o")
        cure = next(item for item in snapshot.inventory if item.slot == "c")
        first = policy._home_deposit_key(snapshot, staff, forced_count=1)
        second = policy._home_deposit_key(snapshot, cure, forced_count=1)
        self.assertEqual((first, second), ("do", "dc1\r"))
        game, result = self.drive(first + second + "\x1b", "home:atomic-deposit", [
            recorded("live-screen-cap-31-home-deposit-d.json"),
            recorded("live30-quaff-prompt.json")], initial=idle, raw=raw)
        self.assertEqual(game.accepted, ["d", "o"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_store_entry_does_not_post_purchase_on_a_prompt(self):
        game, result = self.drive("5px1\r\x1b", "home:atomic-withdraw",
            [recorded("live15-read-scroll-prompt.json")])
        self.assertEqual(game.accepted, ["5"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_store_buy_prefix_and_price_are_separately_observed(self):
        raw, idle = self.home()
        raw["store"]["store_type"] = STORE_ALCHEMIST
        idle = recorded("live-screen-cap-08-alchemist-buy-confirm.json")
        game, result = self.drive("pq", "shop:one-shot-buy", [
            recorded("live-screen-cap-05-alchemist-buy-p.json"),
            recorded("10-rest-prompt.json")], initial=idle, raw=raw,
            steps=[Continuation(frozenset({ScreenKind.QUANTITY}), "1\r"),
                   Continuation(frozenset({ScreenKind.CONFIRM}), "\r")])
        self.assertEqual(game.accepted, ["p", "q"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_default_quantity_enter_and_price_enter_use_different_prompts(self):
        raw, idle = self.home()
        raw["store"]["store_type"] = STORE_ALCHEMIST
        idle = recorded("live-screen-cap-08-alchemist-buy-confirm.json")
        game, result = self.drive("pq\r\r", "shop:one-shot-buy", [
            recorded("live-screen-cap-05-alchemist-buy-p.json"),
            recorded("live-screen-cap-06-alchemist-buy-select-detection.json"),
            recorded("19-quest-entry-confirm-yn.json")], initial=idle, raw=raw)
        self.assertEqual(game.accepted, ["p", "q", "\r"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_knowledge_menu_selection_does_not_land_on_quaff(self):
        game, result = self.drive("~9", "home:scan", [recorded("live30-quaff-prompt.json")],
            steps=[Continuation(frozenset({ScreenKind.FILE_VIEWER}), "\x1b", "home-inventory")])
        self.assertEqual(game.accepted, ["~"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_knowledge_viewer_exit_does_not_land_on_quaff(self):
        game, result = self.drive("~9", "home:scan", [
            recorded("02-knowledge-menu.json"), recorded("live30-quaff-prompt.json")],
            steps=[Continuation(frozenset({ScreenKind.FILE_VIEWER}), "\x1b", "home-inventory")])
        self.assertEqual(game.accepted, ["~", "9"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_once_mode_reuses_existing_plans_at_the_common_port(self):
        for key, owner, prefix in (
                (CHARACTER_DUMP_MACRO, "character:periodic", "C"),
                ("gaaa", "loot:pickup", "g"),
                (ENTER_DUNGEON_MACRO, "descend", ">")):
            with self.subTest(key=key):
                game, result = self.drive(key, owner, [recorded("live30-quaff-prompt.json")], steps=[])
                self.assertEqual(game.accepted, [prefix])
                self.assertEqual(result.outcome, "stuck-prompt")

    def test_rest_argument_does_not_answer_store_quantity(self):
        game, result = self.drive(REST_MACRO, "rest",
            [recorded("live-screen-cap-06-alchemist-buy-select-detection.json")])
        self.assertEqual(game.accepted, ["R"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_look_exit_is_withheld_on_other_modal(self):
        key = ConservativePolicy()._look_probe_key(parse_snapshot(board(), {}))
        self.assertEqual(key, "l\x1b")
        game, result = self.drive(key, "observe:look", [recorded("live30-quaff-prompt.json")])
        self.assertEqual(game.accepted, ["l"])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_map_commands_are_rejected_before_any_post_on_store(self):
        raw, idle = self.home()
        for key in ("Eg", "qc", "rh", "uo", "am6", "zk", "R&\r", "fs6", "va6", "kq",
                    "s", "wq", "te", "dq", "ga", "T6", "o6", "D6", "\\Fa", "6", "0", "5",
                    "{q.\r", "}q", "<", ">", "+6y"):
            with self.subTest(key=key):
                game, result = self.drive(key, "survival:map-command", [], initial=idle, raw=raw)
                self.assertEqual(game.accepted, [])
                self.assertEqual(result.outcome, "stuck-prompt")
                self.assertEqual(result.reason.split("reason=")[-1], "map command on store screen")

    def test_recorded_mana_producer_is_refused_by_the_common_store_admission(self):
        raw = json.loads((FIXTURES / "live35-store-page.json").read_text(encoding="utf-8"))["boards"][1]
        snapshot = parse_snapshot(raw, {})
        policy = ConservativePolicy()
        policy.prime(snapshot)
        key = policy._mana_food_survival_override_key(snapshot)
        self.assertEqual((key, policy.last_reason), ("Eg", "survival:mana-absorb"))
        # Constructed coherent current-store record for the protocol admission;
        # the producer input above is the unchanged captured live35 board.
        raw = copy.deepcopy(raw)
        raw["store"] = self.home()[0]["store"]
        game, result = self.drive(key, policy.last_reason, [],
                                   initial=self.home()[1], raw=raw)
        self.assertEqual(game.accepted, [])
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_recorded_home_chooser_cannot_be_admitted_as_store_boundary(self):
        screen = recorded("live-screen-cap-11-home-withdraw-g.json")
        self.assertEqual(classify_screen(screen).kind, ScreenKind.ITEM_SOURCE)
        game = FaithfulHookGame()
        game.screen = screen
        _, _, executor = self.make(game)
        result = executor.observe_boundary(deadline=time.monotonic() + 1)
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertEqual(game.accepted, [])

    def test_constructed_unknown_store_input_is_not_a_command_page(self):
        # Constructed negative variant of recorded cap-11. Keep its observed
        # active row-zero cursor and complete Home footer; replace only the
        # recognized question to model a UI form whose recording is missing.
        screen = recorded("live-screen-cap-11-home-withdraw-g.json")
        screen["lines"][0] = "An unrecorded item question?"
        self.assertEqual(classify_screen(screen).kind, ScreenKind.UNKNOWN)
        game = FaithfulHookGame()
        game.state = self.home()[0]
        game.jsonl = [copy.deepcopy(game.state)]
        game.screen = screen
        _, _, executor = self.make(game)
        result = executor.observe_boundary(deadline=time.monotonic() + 1)
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertEqual(game.accepted, [])
