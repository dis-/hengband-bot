"""The town stops of the 2026-11-04 morning on the viewing bots, one per root.

Recorded: each capture's arrival checkpoint, calibration and visit journal
(tests/extract_town_stops_1104_fixtures.py).  The rows before the fixed decision
replay unchanged through the public chooser unless a test declares otherwise;
the fixed decision is posted through the production executor port.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from contextlib import contextmanager, redirect_stdout
import copy
from dataclasses import replace
import gzip
import io
import json
import lzma
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import time
import unittest
from unittest import mock

from hengbot.cli import (
    PostingContract,
    _ExecutorInputPort,
    _send_decision_key_with_prompt_chain,
    _send_new_decision_key,
)
from hengbot.model import Position, STORE_ALCHEMIST, parse_snapshot
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_types import StoreVisit, StoreVisitPhase
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)
from hengbot.warrior_optimization import CharacterCalibration, load_character_calibration
from replay_town_arrival import adopt_calibration, decisions, journal, restore
from tests import test_classA_observed_input as follow_harness
from tests import test_input_executor as executor_pins
from tests import test_lv7_town_stop_recorded as lv7
from town_work_corpus import replay_window


FIXTURES = Path(__file__).with_name("fixtures") / "town-stops-1104"
TRAVEL_MAGIC = "\x1b`n&."
TRAVEL_HOME = "\x1b`n(."


class TownStops1104RecordedTest(executor_pins.ProductionHarness):
    def setUp(self):
        super().setUp()
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self, stop):
        """The stop's arrival policy, its journal rows and its board suppliers."""
        visit = self.scratch / stop / "town-arrival"
        visit.mkdir(parents=True)
        fixture = FIXTURES / stop
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((fixture / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((fixture / "journal.jsonl.xz").read_bytes())))
        runtime = self.scratch / stop / "runtime"
        runtime.mkdir()
        if (fixture / "runtime").is_dir():
            shutil.copytree(fixture / "runtime", visit / SIDECAR_DIRECTORY)
            (visit / SIDECAR_MANIFEST).write_text(json.dumps({
                path.name: {"copied": True} for path in (fixture / "runtime").iterdir()}))
        policy = restore(visit, runtime)
        adopt_calibration(policy, fixture / "calibration.json", runtime)
        # The stops share the isolated runtime directory; each has its own history.
        Path(policy._home_disposal.history_path).unlink(missing_ok=True)
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def replay(self, stop, rows):
        """Replay the first ``rows`` rows unchanged; the policy and next steps."""
        policy, recorded, steps = self.load(stop)
        result = replay_window(stop, policy, iter(steps[:rows]))
        self.assertIsNone(result.first_divergence)
        self.assertEqual(result.matched_rows, rows)
        return policy, recorded, steps

    def publish_nothing(self):
        """DECLARED: the replay writes no dump file, so a dump row publishes nothing."""
        publish = mock.patch.object(HengbotPolicy, "_publish_character_dump",
                                    lambda *_args, **_kwargs: None)
        publish.start()
        self.addCleanup(publish.stop)

    @contextmanager
    def recorded_calibration(self, stop):
        """DECLARED: the sheet the visit's dump published is not in the journal, so
        the arrival's calibration stands in for it, also where the arrival's level
        is one behind; without it the optimizer answers calibration-required."""
        calibration = load_character_calibration(FIXTURES / stop / "calibration.json")

        def validated(policy, _snapshot):
            policy._calibration_unavailable_reason = None
            return calibration
        with (mock.patch.object(HengbotPolicy, "_validated_character_calibration", validated),
              mock.patch.object(CharacterCalibration, "stale_reason",
                                lambda *_args, **_kwargs: None)):
            yield

    def assert_posts(self, policy, row, board, key):
        """The production executor posts ``key`` on the recorded board."""
        raw_board = json.loads(row["line"] or row["inputs"][-1])
        game = executor_pins.FaithfulHookGame()
        game.state = raw_board
        game.screen = executor_pins.command_screen(raw_board["turn"])
        # DECLARED CONSTRUCTED: the next board after the command.
        game.screens = [executor_pins.command_screen(raw_board["turn"] + 10)]
        game.states = [dict(raw_board, turn=raw_board["turn"] + 10)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)

    def test_failed_home_take_releases_the_visit_for_the_next_store(self):
        """n1-a life-475 01:53, town:blocked:survival:identify_staff_ready.

        failed: identify_staff_ready; the Magic Shop's 12-charge staff at $808
        with 93194 gold.  The three Teleport Away wands merged into the carried
        one, the take read as failed, and the visit stayed in flight
        (operation-released-effect-not-observed): acquire_result "refused".
        """
        policy, recorded, steps = self.replay("merged-take", 15)
        self.assertEqual(recorded[15]["reason"], "town:entrance-step-off:town:end-step-off")
        board = steps[15][1]()
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), (TRAVEL_MAGIC, "shop:travel"))
        self.assert_posts(policy, recorded[15], board, key)

    def test_home_requests_of_carried_items_end_with_the_home_list(self):
        """n1-a life-476 02:51, town:blocked:survival:identify_staff_ready.

        failed: identify_staff_ready; town plan Home, Magic Shop, Weapon Smiths,
        Black Market.  The withdrawals of the diggers the last visit took stayed
        queued, and each board's Home stop was their refused terminal
        (reservation-unavailable).

        DECLARED: the arrival checkpoint holds the character dump request the
        recorded first row did not answer; the dump is off for that row.
        """
        policy, recorded, steps = self.load("stale-requests")
        with mock.patch.object(HengbotPolicy, "_periodic_character_dump_key",
                               lambda _self, _snapshot, key: key):
            result = replay_window("stale-requests", policy, iter(steps[:1]))
            self.assertIsNone(result.first_divergence)
            board = steps[1][1]()
            key = policy.choose_key(board)
        self.assertEqual(recorded[1]["reason"], "town:blocked:survival:identify_staff_ready")
        self.assertEqual((key, policy.last_reason), (TRAVEL_HOME, "shop:travel"))
        self.assert_posts(policy, recorded[1], board, key)

    def test_entry_leaves_a_blocker_the_open_mining_order_does_not_buy(self):
        """n1-a life-476 02:30, town:blocked:shop-required-operation-uncomposable.

        The tagged ring's sale lost its item to an equipment plan, and the
        preflight still required the Identify staff the open mining set's
        ordinary order does not buy (cause selection-emission-mismatch).
        """
        policy, recorded, steps = self.replay("reserved-ring", 8)
        self.assertEqual(recorded[8]["reason"], "town:blocked:shop-required-operation-uncomposable")
        key = policy.choose_key(steps[8][1]())
        self.assertEqual((key, policy.last_reason), ("\x1b", "shop:in-store-done"))
        self.assertIsNone(policy._town_blocked_reason)

    def test_no_owner_left_reaches_the_town_end_and_its_release(self):
        """n1-a life-476 04:36, departure-unsatisfiable.

        failed: home_candidate_resolved, identification_need_clear,
        departure_identification_need_clear; the fallback of _town_special_key
        stopped before the town end could release a wait this visit cannot
        finish (no candidate, no source for one).
        """
        policy, recorded, steps = self.replay("identification-wait", 19)
        self.assertEqual(recorded[19]["reason"], "town:blocked:departure-unsatisfiable")
        board = steps[19][1]()
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         ("7", "town:entrance-step-off:town:end-step-off"))
        self.assertEqual(policy._visit_departure_recorded, set())
        self.assert_posts(policy, recorded[19], board, key)

    def test_mining_kit_rebuys_the_detection_a_churn_latch_names(self):
        """n1-b life-306 00:32, owner-retired-burst (depth-gate then fundraising).

        DECLARED CONSTRUCTED: on the recorded Alchemist page the latch and the
        open mining set are written, as the visit reached them later: the sold
        Treasure Detection latched (4, 70, 26) before the mining set opened.
        The later recorded rows no longer replay since the stale Home requests
        end (test_home_requests_of_carried_items_end_with_the_home_list).
        """
        policy, _recorded, steps = self.load("kit-latch")
        board = steps[27][1]()
        policy._town_visit_ledger.purchase_churn_class_exclusions.add((STORE_ALCHEMIST, 70, 26))
        policy._town_visit_sale_signatures.add((70, 26))
        policy._fundraising_mode = "prepare"
        with policy._in_store_pure_scope():
            item = policy._next_purchase(board)
        self.assertIsNotNone(item)
        self.assertTrue(item.is_treasure_detection_scroll)

    def test_ability_gap_opens_the_no_safe_destination_set(self):
        """n1-a life-476 07:24, town:blocked:survival:depth_abilities, Lv26 retired.

        failed: depth_abilities (resist_fire, Angband 20F); gold 144025.  The
        Black Market shelved 火炎の指輪 {r火} at 30145, but no owner buys ability
        gear (owner 2026-10-03).  Owner 2026-10-19: fundraise whatever the gold.
        """
        policy, recorded, steps = self.replay("ability-gap", 11)
        self.assertEqual(recorded[11]["reason"], "town:blocked:survival:depth_abilities")
        board = steps[11][1]()
        self.assertEqual(board.player.gold, 144025)
        self.assertEqual(policy._missing_required_abilities(board, 20), frozenset({"resist_fire"}))
        with redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("5", "fundraising:no-safe-destination"))
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertTrue(policy._no_safe_destination_set)
        self.assertIsNone(policy._town_blocked_reason)
        self.assert_posts(policy, recorded[11], board, key)

    def test_opened_set_releases_a_spent_home_bound_for_its_kit(self):
        """n1-a life-476 07:23 (06:50 too), owner-retired-burst.

        procurement: Treasure Detection 0/5, on Home's shelf.  The visit's
        earlier work had spent Home's passes, so the kit claim was hidden, the
        destination gate became the blocked reason and the visit waited.
        """
        policy, recorded, steps = self.replay("home-kit-bound", 24)
        self.assertEqual(recorded[23]["reason"].split(":")[0], "fundraising")
        self.assertEqual(recorded[24]["reason"], "fundraise:fallback-exhausted-plan")
        board = steps[24][1]()
        with redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), (TRAVEL_HOME, "shop:travel"))
        self.assertEqual(policy._town_visit_ledger.blocked_stores, set())
        self.assert_posts(policy, recorded[24], board, key)

    def test_swap_only_the_reserve_refuses_departs_on_the_worn_loadout(self):
        """n1-a life-477 08:17, town:blocked:unmet:equipment_departure_ready.

        failed: equipment_departure_ready (blockers pack-space-required:1, four
        actions, free_pack_slots_ready true at 4 free).  A one-slot body swap,
        Home with room, nothing to shelve or sell.  Owner 2026-10-03: a failed
        optional change departs on the confirmed loadout.

        DECLARED: the departure dump is a prompt macro the test game does not
        answer, so the decision is pinned without posting it.
        """
        self.publish_nothing()
        with self.recorded_calibration("pack-unrelieved"):
            policy, recorded, steps = self.replay("pack-unrelieved", 26)
            self.assertEqual(recorded[26]["reason"],
                             "town:blocked:unmet:equipment_departure_ready")
            board = steps[26][1]()
            key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         ("Cf\ry\x1b\x1b", "town:character-dump"))
        self.assertIsNone(policy._town_blocked_reason)
        self.assertEqual(policy._equipment_optional_failure_pending["reason"],
                         "pack-space-unrelieved-current-loadout")

    def test_transaction_the_visit_closed_is_not_home_work_left(self):
        """n1-c life-129 13:18, town:blocked:unmet:equipment_departure_ready.

        failed: equipment_departure_ready (blockers equipment-transaction-failed,
        closure retain-reserved).  Home was left for a shop, so it was not
        "attempted", and a closed transaction read as reachable Home work while
        the route projection said no work was outstanding.

        DECLARED: the departure dump is a prompt macro the test game does not
        answer, so the decision is pinned without posting it.
        """
        self.publish_nothing()
        policy, recorded, steps = self.replay("closed-transaction", 1)
        with self.recorded_calibration("closed-transaction"):
            result = replay_window("closed-transaction", policy, iter(steps[1:20]))
            self.assertIsNone(result.first_divergence)
            self.assertEqual(recorded[20]["reason"], "town:entrance-step-off:town:end-step-off")
            board = steps[20][1]()
            key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         ("Cf\ry\x1b\x1b", "town:character-dump"))
        self.assertIsNone(policy._town_blocked_reason)

    def test_equipment_refusing_only_the_landing_opens_the_set(self):
        """n1-a life-477 09:52 (09:55 too), town:blocked:survival:depth_abilities.

        failed: equipment_departure_ready beside depth_abilities (free_action,
        20F, gold 16502); blockers pending-random-teleport-suppression.  The
        worn-loadout wait is refused only while a landing ability is missing, so
        the town end named two conditions and ac3d070e0's one-condition test
        stopped.  Owner 2026-10-19: fundraise whatever the gold.
        """
        policy, recorded, steps = self.replay("ability-suppression", 26)
        self.assertEqual(recorded[26]["reason"], "town:blocked:survival:depth_abilities")
        board = steps[26][1]()
        self.assertEqual(policy._missing_required_abilities(board, 20), frozenset({"free_action"}))
        with redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("5", "fundraising:no-safe-destination"))
        self.assertTrue(policy._no_safe_destination_set)
        self.assertIsNone(policy._town_blocked_reason)
        self.assert_posts(policy, recorded[26], board, key)

    def test_spent_entry_budget_leaves_for_the_visit_to_come_back(self):
        """n1-a life-477 08:54, town:blocked:shop-required-operation-uncomposable.

        cause entry-budget, row k, Identify staff 18 of 20: eight operations that
        all took effect (a 30000-gold book, a staff, a swap of the 1-charge staves).

        DECLARED CONSTRUCTED: the Magic Shop entry's ledger, its visit and the Home
        list's currency are written on the recorded last page; this arrival's
        optimizer does not replay the visit's Home rows.
        """
        policy, recorded, steps = self.load("entry-spent")
        self.assertEqual(recorded[65]["reason"], "town:blocked:shop-required-operation-uncomposable")
        board = steps[65][1]()
        policy._decision_sequence = 393
        policy._in_store_entry_ledger = {
            "store": board.store.store_type, "opened_sequence": 384,
            "ops": 8, "pending": None, "ended": False,
        }
        policy._store_visit = StoreVisit("town-errand", "shopping", board.store.store_type,
                                         phase=StoreVisitPhase.OPERATING, opened_sequence=384)
        policy._in_store_screen_verified = True
        policy._home_knowledge_current = True
        self.assertEqual(policy._departure_blocking_page_operation(board)["op"], "buy")
        key = policy._in_store_entry_key(board)
        self.assertEqual((key, policy.last_reason), ("\x1b", "shop:in-store-done"))
        self.assertIsNone(policy._town_blocked_reason)

    def test_empty_staff_under_an_identification_need_makes_room_for_its_buy(self):
        """n1-b life-308 13:14, town:blocked:survival:identify_staff_ready.

        failed: identify_staff_ready, home_candidate_resolved,
        identification_need_clear, departure_identification_need_clear; 0 of 20
        charges, a 20-charge Identify staff at $941 with 14742 gold, 4 free slots,
        seven stacks the pack pass may shelve.  An identification need hid the
        staff from the need list, so the pass never learned the buy waited on a slot.
        """
        self.publish_nothing()
        policy, recorded, steps = self.replay("staff-need-room", 9)
        with self.recorded_calibration("staff-need-room"):
            result = replay_window("staff-need-room", policy, iter(steps[9:20]))
            self.assertIsNone(result.first_divergence)
            self.assertEqual(recorded[20]["reason"], "town:entrance-step-off:town:end-step-off")
            board = steps[20][1]()
            key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), (TRAVEL_HOME, "shop:travel"))
        self.assertIsNotNone(policy._pack_headroom_visit)
        self.assert_posts(policy, recorded[20], board, key)

    def test_gold_pile_is_walked_and_a_refused_pile_is_no_target(self):
        """n1-c life-123 04:33, owner-retired-burst.

        seek-loot '3' and shop:approach '7' alternated beside a gold pile: the
        floor-step budget counted its one object at the pack's reserve floor.

        DECLARED: the rows up to the board are posted as this replay decides
        them (the Magic-Eater's arrival dump and destroy rows do not match the
        recorded ones); only the board's own decision is pinned.
        """
        policy, recorded, steps = self.load("gold-pile")
        with mock.patch.object(HengbotPolicy, "_periodic_character_dump_key",
                               lambda _self, _snapshot, key: key):
            for _row, supply in steps[:50]:
                key = policy.choose_key(supply())
                if key:
                    policy.confirm_key_posted(key)
                    chain = policy.peek_staged_prompt_chain()
                    if chain is not None and staged_prompt_chain_matches(chain, key):
                        policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
            board = steps[50][1]()
            cell = Position(36, 108)
            self.assertEqual(board.grid_at(cell).object_tvals, (127,))
            key = policy.choose_key(board)
        self.assertEqual(recorded[50]["reason"], "shop:approach")
        self.assertEqual((key, policy.last_reason), ("3", "seek-loot"))
        # The same board with a pack item on that cell: no step, and no target.
        grids = dict(board.grids)
        grids[cell] = replace(grids[cell], object_tvals=(23,))
        policy._deferred_loot.discard(cell)
        self.assertNotIn(cell, policy._loot_candidates(replace(board, grids=grids)))
        self.assertIn(cell, policy._deferred_loot)

    def test_pack_source_reads_the_taken_item_during_mining_preparation(self):
        """n1-a life-476 03:08, town:blocked:survival:recall_departure_ready,
        then town:blocked:overweight-retained-only.

        failed: recall_departure_ready, inventory_weight_ready.  Five weapons
        taken out for three carried *Identify* scrolls; the open mining set's
        hold on identification kept them unread until the pack and the weight
        stopped the visit.
        """
        policy, recorded, steps = self.replay("pack-identify", 44)
        self.assertEqual(recorded[44]["reason"], "shop:approach")
        key = policy.choose_key(steps[44][1]())
        self.assertEqual(policy.last_reason, "identify:full")
        self.assertTrue(key.startswith("r"), repr(key))

    def publish_recorded_dump(self, policy, edit=None, stop="worn-average"):
        """The life's last C response and dump, published on their own board.

        DECLARED CONSTRUCTED: the ring keeps no CLI sequence, so one is given,
        and the response is read as its own board (turn 1086963, before this
        visit; the final board's lantern fuel no longer matches the dump).
        """
        fixture = FIXTURES / stop
        response = json.loads(lzma.decompress((fixture / "character.json.xz").read_bytes()))
        response["sequence"] = 1
        if edit is not None:
            edit(response)
        policy._character_dump_path.write_bytes(
            lzma.decompress((fixture / "dump.txt.xz").read_bytes()))
        board = parse_snapshot(
            {name: value for name, value in {**response, "type": "player_turn"}.items()
             if name != "character"}, policy._monrace_knowledge)
        policy._publish_character_dump(
            {"started_ns": 0, "baseline": None, "sequence": None},
            response["character"], response, policy.with_known_skill_exp(board))

    def test_worn_average_item_keeps_the_calibration_and_the_weapons_are_shelved(self):
        """n1-b life-307 03:32, town:blocked:pack-full-no-room.

        Owner 2026-11-04 「修正なしとして使う」: the Q34 {average} cloak is read as
        having no modifiers.  The sheet is accepted, the optimizer plans at the
        open Home page, and the board of the stop deposits the five carried
        weapons first instead of stopping.

        DECLARED: the published dump (publish_recorded_dump) replaces the
        calibration the recorded visit never had; rows 33 and 34 follow it.
        """
        policy, recorded, steps = self.replay("worn-average", 33)
        self.assertEqual(recorded[34]["reason"], "town:blocked:pack-full-no-room")
        self.publish_recorded_dump(policy)
        self.assertIsNone(policy._calibration_unavailable_reason)
        self.assertIsNotNone(policy._character_calibration)
        key = policy.choose_key(steps[33][1]())
        self.assertEqual((key, policy.last_reason),
                         ("\x1b", "equipment-transaction:home-catalog-acquired"))
        policy.confirm_key_posted(key)
        actions = policy._equipment_transaction_session.plan.actions
        self.assertEqual([action.kind for action in actions[:5]], ["deposit"] * 5)
        board = steps[34][1]()
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("5", "equipment-transaction:atomic-deposit"))
        self.assertIsNone(policy._town_blocked_reason)
        self.assert_posts(policy, recorded[34], board, key)

    def test_control_worn_item_without_average_still_refuses_the_calibration(self):
        def unsensed(response):
            cloak = next(item for item in response["equipment"] if item.get("slot") == "outer")
            cloak.pop("pseudo_feeling")

        policy, _recorded, _steps = self.replay("worn-average", 33)
        self.publish_recorded_dump(policy, unsensed)
        self.assertIsNone(policy._character_calibration)
        self.assertEqual(policy._calibration_unavailable_reason,
                         "equipment-stat-modifiers-unknown")

    def ability_shelf(self):
        """Row 7 of the stop's visit: the Black Market page, the sheet accepted.

        DECLARED: the visit's own rows ran before b0af0c63a1 read the worn {並}
        cloak as unmodified, so they had no calibration; the visit's last C
        response and dump are published here, as the live build reads them.
        """
        policy, recorded, steps = self.replay("ability-gap", 7)
        self.assertEqual(recorded[7]["reason"], "shop:observe-and-leave")
        self.publish_recorded_dump(policy, stop="ability-gap")
        self.assertIsNotNone(policy._character_calibration)
        return policy, recorded, steps[7][1]()

    def post_purchase(self, policy, raw, following, key, ware):
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        game.screen = lv7.Lv7TownStopRecordedTest.shelf_screen(raw)
        # The recorded item prompt, the price question (store/purchase-order.cpp,
        # no quantity for a single row), the shelf again.
        game.screens = [follow_harness.recorded("live-screen-cap-05-alchemist-buy-p.json"),
                        executor_pins.prompt_screen(f"買値 ${ware['price']} で買いますか？[Y/n]"),
                        lv7.Lv7TownStopRecordedTest.shelf_screen(following)]
        game.states = [copy.deepcopy(raw)] * 2 + [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "ability-gear", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=True)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")

    def test_missing_ability_buys_the_cheapest_shelf_row_and_the_comparison_wears_it(self):
        """n1-a life-476 07:24, resist_fire for Angband 20F, 144025 gold.

        Owner 2026-11-04 「買えるなら買う」: 火炎の指輪 {r火} at 30145 is cheaper
        than 全耐性スケイル・メイル at 121388 on the same page.  Once carried the
        comparison wears it, and the dearer row is not bought for the same gap.

        DECLARED CONSTRUCTED: the board after the purchase, with enough gold
        left for the dearer row, so only the judgement refuses it; the capture
        has no later Home boards, so the transaction's own steps are not played.
        """
        policy, recorded, board = self.ability_shelf()
        self.assertEqual(policy._missing_required_abilities(board, 20), frozenset({"resist_fire"}))
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("pG\r", "shop:in-store-buy"))
        raw = json.loads(recorded[7]["inputs"][-1] if not recorded[7]["line"] else recorded[7]["line"])
        store_rows = raw["store"]["items"]
        ware = next(row for row in store_rows if row["letter"] == "G")
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["player"]["gold"] = 121388 + 1
        following["store"]["items"] = [row for row in store_rows if row["letter"] != "G"]
        following["inventory"].append({**{name: value for name, value in ware.items()
                                          if name not in {"letter", "price"}},
                                       "slot": "s"})
        self.post_purchase(policy, raw, following, key, ware)
        policy.confirm_key_posted(key)
        after = parse_snapshot(following, policy._monrace_knowledge)
        key = policy.choose_key(after)
        self.assertFalse(key.startswith("p"), (key, policy.last_reason))
        # The next comparison, once the session planned before the purchase has
        # ended at Home, reaches the 20F band with the ring.
        policy._set_equipment_transaction_session(None)
        policy._equipment_optimization_signature = None
        result = policy._prepare_equipment_optimization(policy.with_known_skill_exp(after)).result
        self.assertEqual(result.chosen_depth, 20)
        worn = result.best.loadout.item_ids
        ring = next(owned for owned in policy._equipment_catalog.items
                    if owned.item.tval == ware["tval"] and owned.item.sval == ware["sval"])
        self.assertIn(ring.id, worn)

    def test_control_too_little_gold_leaves_the_shelf(self):
        """One gold short of the ring: the recorded page's answer stands."""
        policy, recorded, board = self.ability_shelf()
        short = replace(board, player=replace(board.player, gold=30144))
        key = policy.choose_key(short)
        self.assertEqual((key, policy.last_reason), (recorded[7]["key"], recorded[7]["reason"]))


if __name__ == "__main__":
    unittest.main()
