"""The town stops of the viewing bots, 2026-11-05 and 06.

Recorded: each case's arrival checkpoint, sidecars and visit journal
(tests/extract_town_stops_1105_fixtures.py).  The rows before the fixed decision
replay unchanged through the public chooser and the driver's retirement entrance;
the fixed decision is posted through the production executor port.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import tarfile
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from hengbot import cli
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot import mining_oil_sale
from hengbot.me_powers_refresh import REFRESH_REASON
from hengbot.model import TVAL_ROD, lights_nothing, parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot import town_terminal
from hengbot.town_arrival_checkpoint import SIDECAR_DIRECTORY
from replay_town_arrival import adopt_calibration, decisions, journal, restore
from tests.support import recorded as executor_pins


FIXTURES = Path(__file__).with_name("fixtures") / "town-stops-1105"
DUMP_KEY = "Cf"
BURST = "town:blocked:owner-retired-burst"


class TownStops1105RecordedTest(executor_pins.ProductionHarness):
    def setUp(self):
        super().setUp()
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self, case):
        visit = self.scratch / case / "town-arrival"
        visit.mkdir(parents=True)
        with tarfile.open(FIXTURES / f"{case}.tar.xz") as tar:
            tar.extractall(visit, filter="data")
        runtime = self.scratch / case / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        calibration = visit / SIDECAR_DIRECTORY / "_character_calibration_path"
        if calibration.is_file():
            adopt_calibration(policy, calibration, runtime)
        self.visit = visit
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def decide(self, policy, supply):
        """As the driver: the chooser, then the retirement entrance."""
        board = supply()
        before = copy.copy(policy._store_visit)
        chosen = policy.choose_key(board)
        reason = policy.last_reason
        key = policy.validate_read_key(board, chosen)
        args = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
        return board, chosen, reason, cli._handle_owner_retirement(args, board, key, policy, before)

    def post(self, policy, key):
        if key.startswith(DUMP_KEY) and policy._character_dump_path is not None:
            # DECLARED CONSTRUCTED: the game writes the sheet; the arrival's sheet
            # stands for it.
            dump = Path(policy._character_dump_path)
            recorded = self.visit / SIDECAR_DIRECTORY / "_character_dump_path"
            dump.write_bytes(recorded.read_bytes() if recorded.is_file() else b"")
            os.utime(dump, ns=(time.time_ns(), time.time_ns()))
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def replay_to(self, policy, recorded, steps, row):
        """Replay the rows before ``row`` unchanged; decide ``row``."""
        for index in range(row):
            _, chosen, reason, key = self.decide(policy, steps[index][1])
            self.assertEqual((chosen, reason), (recorded[index]["key"], recorded[index]["reason"]),
                             f"row {index}")
            self.assertNotEqual(policy.last_reason, BURST, f"row {index}")
            self.post(policy, key)
        return self.decide(policy, steps[row][1])

    def assert_posts(self, policy, row, board, key):
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

    def test_a_relief_walk_after_the_browse_refresh_reaches_the_game(self):
        """n1-b life-319 01:22: resumed in town, the third browse board's Home relief
        walked to the Black Market unnamed.  The walk kept the browse label, the
        executor took it for a browse and stopped: three stops in 20 seconds."""
        policy, recorded, steps = self.load("periodic-walk")
        self.assertEqual((recorded[6]["key"], recorded[6]["reason"]), ("6", REFRESH_REASON))
        board, chosen, reason, key = self.replay_to(policy, recorded, steps, 6)
        # The last kind's browse is free to take the filler walk now.
        self.assertEqual((chosen, reason), ("bC", REFRESH_REASON))
        self.post(policy, key)

        # DECLARED CONSTRUCTED: the browse takes no game time, so the board comes back.
        again = lambda: board
        with mock.patch.object(policy, "_home_relief_names_approach", return_value=False):
            _board, chosen, reason, _key = self.decide(policy, again)
        # The walk does not inherit the bookkeeping label.  Since zero-light-1106
        # the worn ★火消しライター lights nothing (model.lights_nothing), so the walk
        # is the equipment transaction's, fetching a light from Home, under its own
        # name (before: an unnamed relief walk, then shop:approach).
        self.assertTrue(lights_nothing(next(item for item in board.equipment if item.is_light)))
        self.assertEqual((chosen, reason), ("6", "equipment-transaction:approach-home"))
        _board, chosen, reason, key = self.decide(policy, again)
        self.assertEqual((chosen, reason), ("6", "equipment-transaction:approach-home"))
        self.assert_posts(policy, recorded[6], board, key)

        # Whatever the label says, the executor posts a key the refresh did not compose.
        policy.last_reason = REFRESH_REASON
        self.assert_posts(policy, recorded[6], board, key)

    def test_a_plain_walk_earns_its_distance_credit(self):
        """n1-b life-314 13:43: town:rumor walked 11 steps to the inn.
        me_powers.fight_key, the pass-through of every decision, took the work record,
        so no walk or effect earned credit: the burst at the third retirement."""
        policy, recorded, steps = self.load("rumor-walk")
        board, _, _, key = self.replay_to(policy, recorded, steps, 11)
        self.assertEqual((key, policy.last_reason), ("1", "town:rumor"))
        self.assertLess(policy._owner_retired_no_progress_count, 3)
        self.assert_posts(policy, recorded[11], board, key)

    def test_a_relief_of_another_town_waits_for_the_trip(self):
        """n1-c life-145 23:18: relief of the Outpost, recharge at Morivant's tower;
        town:blocked:home-full-town-changed x9, then the burst."""
        policy, recorded, steps = self.load("town-changed")
        self.assertEqual(recorded[6]["reason"], "town:blocked:home-full-town-changed")
        board, _, _, key = self.replay_to(policy, recorded, steps, 6)
        self.assertEqual((key, policy.last_reason), ("9", "me-staff:return-outpost"))
        self.assert_posts(policy, recorded[6], board, key)

    def test_a_home_walk_keeps_its_way_past_the_plan(self):
        """n1-b life-317 23:19 (Lv34, retired): the relief's walk to Home and the
        plan's Alchemist alternate at (34,90) and (33,91): transfer [4, 7].

        Since zero-light-1106 (model.lights_nothing) the ★火消しライター in the
        pack is a light that lights nothing, so row 13's Home deposit shelves it
        ('ds') before the halberd the recorded build deposited ('dt').  Every
        later recorded board still holds the lighter, so the walk of row 71 is no
        longer reachable on these boards: the alternation itself lost this pin."""
        policy, recorded, steps = self.load("own-home-route")
        self.assertEqual(recorded[13]["key"], "dt")
        _, chosen, reason, _ = self.replay_to(policy, recorded, steps, 13)
        self.assertEqual((chosen, reason), ("ds", "equipment-transaction:deposit"))
        lighter = next(item for item in steps[13][1]().inventory if item.slot == "s")
        self.assertTrue(lights_nothing(lighter))

    def test_the_identify_swap_takes_the_whole_emptiest_stack(self):
        """n1-a life-487 19:14: 7, 6 and 2x3 charges, 4x18 at 816 gold on the shelf,
        726,000 gold and the pack at its budget: the swap released nothing and the
        visit stopped at survival:identify_staff_ready with 19 of 20."""
        policy, recorded, steps = self.load("staff-swap")
        board, _, _, key = self.replay_to(policy, recorded, steps, 15)
        self.assertEqual((key, policy.last_reason), ("d02\ry", "shop:in-store-sell"))
        self.assertFalse(policy._identify_staff_acquisition_worthwhile(board, 3))
        self.assertTrue(policy._identify_staff_acquisition_worthwhile(board, 18))
        self.post(policy, key)
        # DECLARED CONSTRUCTED: the shop's answers to the sales that follow.
        raw = json.loads(recorded[15]["line"] or recorded[15]["inputs"][-1])
        raw["inventory"] = [item for item in raw["inventory"]
                            if not (item["tval"] == 55 and item["sval"] == 5 and item["charges"] == 3)]
        raw["player"]["gold"] += 100
        for _ in range(4):
            raw = copy.deepcopy(raw)
            raw["turn"] += 1
            for index, item in enumerate(raw["inventory"]):
                item["slot"] = chr(ord("a") + index)
            board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            policy.observe_store_screen(True)
            key = policy.choose_key(board)
            if key.startswith("p"):
                break
            policy.confirm_key_posted(key)
            inscribed = re.match(r"\{([a-z])@(\d)\r", key)
            if inscribed:
                for item in raw["inventory"]:
                    if item["slot"] == inscribed.group(1):
                        item["inscription"] = "@" + inscribed.group(2)
                        item["name"] += " {@" + inscribed.group(2) + "}"
            sold = re.match(r"d(\d)y", key)
            if sold:
                raw["inventory"] = [item for item in raw["inventory"]
                                    if "@" + sold.group(1) not in item["name"]]
                raw["player"]["gold"] += 100
        self.assertEqual(policy.last_reason, "shop:in-store-buy")
        shelf = raw["store"]["items"]
        offset = ord(key[1]) - ord("a")
        bought = next((item for item in shelf if item.get("slot") == key[1]), shelf[offset])
        self.assertEqual((bought["tval"], bought["sval"], bought["charges"]), (55, 5, 18))

    def test_a_refused_deposit_leaves_the_filed_take_its_way_home(self):
        """n1-a life-487 19:30: the deposit a full Home refused closed Home on the pass
        the take was filed for; town:blocked:unmet:home_candidate_resolved."""
        policy, recorded, steps = self.load("filed-take")
        self.assertEqual(recorded[57]["reason"], "town:blocked:unmet:home_candidate_resolved")
        # Row 55 is the Black Market page, recorded observe-and-leave.  It shelves a
        # Staff of *Destruction* (3 charges, 53,714 gold; 734,508 carried), which
        # the owner's later rule buys (2026-11-07 「*破壊*の杖の優先度を上げる」
        # 「何本でも買う」, BM-DESTRUCTION-1107).
        recorded_page = steps[55][1]()
        staff = next(ware for ware in recorded_page.store.items
                     if policy._is_destruction_staff(ware))
        self.assertEqual((staff.letter, staff.price), ("K", 53714))
        # DECLARED WALL: the record predates that rule; the pin is the filed take,
        # so the replay's Black Market pages show the shelf without the staff and
        # the recorded leave stands.  The staff's purchase on this page is pinned
        # in test_the_recorded_black_market_page_buys_its_destruction_staff.
        steps = [(step[0], self.without_destruction_staff(policy, step[1]))
                 for step in steps]
        board, _, _, key = self.replay_to(policy, recorded, steps, 57)
        self.assertEqual((key, policy.last_reason), ("\x1b`n(.", "shop:travel"))
        self.assert_posts(policy, recorded[57], board, key)

    @staticmethod
    def without_destruction_staff(policy, supply):
        def board():
            snapshot = supply()
            store = snapshot.store
            if store is None or not any(policy._is_destruction_staff(ware) for ware in store.items):
                return snapshot
            return replace(snapshot, store=replace(store, items=[
                ware for ware in store.items if not policy._is_destruction_staff(ware)]))
        return board

    def test_the_recorded_black_market_page_buys_its_destruction_staff(self):
        """n1-a life-487 19:30, row 55: the Black Market shelved a Staff of
        *Destruction* the record left (it predates the rule).  Owner 2026-11-07
        「*破壊*の杖の優先度を上げる」「何本でも買う」: it is the first optional pick."""
        policy, recorded, steps = self.load("filed-take")
        self.assertEqual((recorded[55]["key"], recorded[55]["reason"]),
                         ("\x1b", "shop:observe-and-leave"))
        _, chosen, reason, _ = self.replay_to(policy, recorded, steps, 55)
        self.assertEqual((chosen, reason), ("pK\r", "shop:in-store-buy"))
        """n1-a life-487 13:39: one melee from the entrance on the way to a mining run,
        the hold kept the departure out of its own route:
        town:blocked:survival:cure_critical_ready."""
        policy, recorded, steps = self.load("entrance-walk")
        self.assertEqual(recorded[61]["reason"], "town:blocked:survival:cure_critical_ready")
        board, _, _, key = self.replay_to(policy, recorded, steps, 61)
        self.assertEqual((key, policy.last_reason), ("9", "seek-downstairs"))
        self.assert_posts(policy, recorded[61], board, key)

    def test_the_quest_return_leaves_the_expedition_at_morivant(self):
        """n1-a life-486 11:41: travel-2 and fixedquest:prepare-return alternate, 500
        gold a leg, 5,061 gold to 61.

        Row 10 changed with LAUNCHER-SALE-1106 (item_fate.ranked_gear_saleable): the
        Amulet of Resist Lightning ranks in the top 10, so no Magic shop sale is
        planned for it any more and the pack reserve's Home deposit (town_pack_headroom)
        comes before the launcher's enchant read.  The deposit leaves the Scroll of
        Enchant Weapon To-Dam the read consumes (town_terminal.launcher_enchant_scroll)
        and shelves the Rod of Door/Stair Location; the scroll stays for the read.
        The record's build read it at row 10.  From row 11 the boards are the
        record's, not this build's; the bot's own keys are posted on them, and the
        expedition still starts at row 53."""
        policy, recorded, steps = self.load("expedition")
        self.assertEqual(recorded[55]["reason"], "fixedquest:prepare-return")
        self.assertEqual(recorded[10]["reason"], "town:enchant-launcher-todam")
        board, chosen, reason, key = self.replay_to(policy, recorded, steps, 10)
        self.assertEqual((chosen, reason), ("5", "home:atomic-deposit"))
        batch = policy._home_atomic_deposit_pending[0]
        # (tval, sval): the Rod of Door/Stair Location, not the enchant scroll.
        self.assertEqual([entry[0][1:] for entry in batch], [(TVAL_ROD, 1)])
        self.assertIsNotNone(town_terminal.enchant_launcher_intended_terminal(policy, board))
        self.assertIsNone(policy._morivant_full_identify)
        self.post(policy, key)
        for index in range(11, 55):
            _, chosen, reason, key = self.decide(policy, steps[index][1])
            self.assertNotEqual(policy.last_reason, BURST, f"row {index}")
            if index >= 53:
                self.assertEqual((chosen, reason), (recorded[index]["key"], recorded[index]["reason"]))
            self.post(policy, key)
        board, _, _, key = self.decide(policy, steps[55][1])
        self.assertFalse(policy.last_reason.startswith("fixedquest:"))
        self.assertIsNotNone(policy._morivant_full_identify)
        self.assert_posts(policy, recorded[55], board, key)

    def test_a_short_oil_stack_keeps_the_identify_scroll_off_the_mining_shopping(self):
        """Owner 2026-11-06: 採掘の買い物で油を鑑定の巻物より先に買います.
        n1-b life-315 13:49: 79 gold, Identify at 78.  It held all five flasks, so
        the purchase stands; one flask short, the Alchemist's page leaves it."""
        policy, recorded, steps = self.load("mining-identify")
        for index in range(44):
            _, chosen, reason, key = self.decide(policy, steps[index][1])
            self.assertEqual((chosen, reason), (recorded[index]["key"], recorded[index]["reason"]))
            self.post(policy, key)
        # DECLARED CONSTRUCTED: four flasks instead of the five recorded.
        short = copy.deepcopy(json.loads(recorded[44]["line"] or recorded[44]["inputs"][-1]))
        self.assertEqual(short["inventory"][0]["tval"], 77)
        short["inventory"][0]["count"] = 4
        twin = copy.deepcopy(policy)
        _, chosen, reason, _ = self.on_page(twin, short)
        self.assertFalse(chosen.startswith("p"), (chosen, reason))

        _, chosen, reason, _ = self.decide(policy, steps[44][1])
        self.assertEqual((chosen, reason), (recorded[44]["key"], "shop:in-store-buy"))

    @staticmethod
    def mining_oil_board(recorded, row, *, gold=None, scrolls=None):
        """The recorded board, with the sale's effect on the purse and the stack."""
        raw = copy.deepcopy(json.loads(recorded[row]["line"] or recorded[row]["inputs"][-1]))
        if gold is not None:
            raw["player"]["gold"] = gold
        if scrolls is not None:
            stack = next(item for item in raw["inventory"]
                         if item["tval"] == 70 and item["sval"] == 26)
            stack["count"] = scrolls
        return raw

    def replay_to_the_alchemist(self):
        """n1-b life-315 13:50, the arrival with 1 gold, 7 scrolls, no oil and a dead
        lantern.  The recorded boards play in order to the Alchemist's page; rows 4-7,
        36, 37 and 49 now choose otherwise than the recorded build (a worn digger's
        restore), which the boards after them do not depend on."""
        policy, recorded, steps = self.load("mining-oil-sale")
        for index in range(90):
            self.post(policy, self.decide(policy, steps[index][1])[3])
        return policy, recorded, steps

    def on_page(self, policy, raw):
        policy.observe_store_screen(True)
        return self.decide(policy, lambda: parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))

    @staticmethod
    def tag_for_sale(page):
        # DECLARED CONSTRUCTED: the game's answer to the inscription.
        stack = page["inventory"][0]
        stack["inscription"] = "@0"
        stack["name"] += " {@0}"
        return stack

    def test_one_treasure_detection_scroll_buys_the_oil(self):
        """Owner 2026-11-06: 財宝感知の巻物を1本売って油を買います.
        n1-b life-315 13:50: oil at 5 gold, 1 gold, 7 scrolls: town:wait-restock:
        general:oil-light, then town:blocked:survival:recall_departure_ready."""
        policy, recorded, _ = self.replay_to_the_alchemist()
        self.assertEqual(recorded[90]["reason"], "shop:observe-and-leave")
        page = self.mining_oil_board(recorded, 90)
        _, chosen, reason, key = self.on_page(policy, page)
        self.assertEqual((chosen, reason), ("{a@0\r", "shop:in-store-inscribe"))
        self.post(policy, key)
        stack = self.tag_for_sale(page)
        _, chosen, reason, key = self.on_page(policy, page)
        self.assertEqual((chosen, reason), ("d01\ry", "shop:in-store-sell"))
        self.post(policy, key)
        # DECLARED CONSTRUCTED: the sale; 7 gold is what the Magic shop of n1-b
        # life-314 paid per scroll (売値 $35 for five).
        stack["count"] = 6
        page["player"]["gold"] = 8
        _, chosen, reason, key = self.on_page(policy, page)
        self.assertEqual((chosen, reason), ("\x1b", "shop:in-store-done"))
        self.post(policy, key)

        # DECLARED CONSTRUCTED: the recorded street with the sale's effect.
        street = self.mining_oil_board(recorded, 91, gold=8, scrolls=6)
        board = parse_snapshot(copy.deepcopy(street), policy._monrace_knowledge)
        _, chosen, reason, key = self.decide(policy, lambda: board)
        self.assertEqual((chosen, reason), ("\x1b`n!.", "shop:travel"))
        self.assert_posts(policy, dict(recorded[91], line=json.dumps(street)), board, key)
        self.post(policy, key)

        # DECLARED CONSTRUCTED: the General Store's recorded shelf with 8 gold.
        shelf = self.mining_oil_board(recorded, 62, gold=8, scrolls=6)
        oil = next(item for item in shelf["store"]["items"] if item["tval"] == 77)
        self.assertEqual(oil["price"], 5)
        _, chosen, reason, _ = self.on_page(policy, shelf)
        self.assertEqual((chosen, reason), (f"p{oil['letter']}1\r\r", "shop:in-store-buy"))

    def test_the_oil_sale_takes_one_scroll_of_a_stack_below_the_carry_target(self):
        """Three scrolls under the kit's carry target of six: one goes, two stay."""
        policy, recorded, _ = self.replay_to_the_alchemist()
        # DECLARED CONSTRUCTED: three scrolls since the General Store's page opened the sale.
        policy._mining_oil_sale["scrolls"] = 3
        page = self.mining_oil_board(recorded, 90, scrolls=3)
        _, chosen, _, key = self.on_page(policy, page)
        self.assertEqual(chosen, "{a@0\r")
        self.post(policy, key)
        self.tag_for_sale(page)
        _, chosen, _, _ = self.on_page(policy, page)
        self.assertEqual(chosen, "d01\ry")

    def test_the_oil_sale_is_one_scroll_even_when_it_buys_nothing(self):
        """Proceeds short of the oil: no second scroll; the visit goes on without it."""
        policy, recorded, _ = self.replay_to_the_alchemist()
        page = self.mining_oil_board(recorded, 90)
        self.post(policy, self.on_page(policy, page)[3])
        stack = self.tag_for_sale(page)
        self.post(policy, self.on_page(policy, page)[3])
        # DECLARED CONSTRUCTED: a sale of 2 gold leaves 3; oil is 5.
        stack["count"] = 6
        page["player"]["gold"] = 3
        _, chosen, reason, key = self.on_page(policy, page)
        self.assertEqual((chosen, reason), ("\x1b", "shop:in-store-done"))
        self.post(policy, key)
        self.assertIsNone(mining_oil_sale.scroll_to_sell(
            policy, parse_snapshot(page, policy._monrace_knowledge)))

    def test_the_oil_sale_is_only_for_a_lantern_short_of_oil_and_money(self):
        policy, recorded, _ = self.replay_to_the_alchemist()
        recorded_page = self.mining_oil_board(recorded, 90)

        def scroll(change):
            page = copy.deepcopy(recorded_page)
            change(page)
            return mining_oil_sale.scroll_to_sell(
                policy, parse_snapshot(page, policy._monrace_knowledge))

        def lantern(page):
            return next(item for item in page["inventory"] if item["tval"] == 39)

        def torch_only(page):
            page["inventory"] = [item for item in page["inventory"] if item["tval"] != 39]

        def flask(page):
            page["inventory"].append(dict(page["inventory"][0], tval=77, sval=0, name="油つぼ", slot="e"))

        self.assertIsNotNone(scroll(lambda page: None))
        # The town plan files the Alchemist for the sale, and the registry knows it.
        board = parse_snapshot(copy.deepcopy(recorded_page), policy._monrace_knowledge)
        self.assertIsNotNone(policy._candidate_need(board, "mining-oil-sale", "normal", 0))
        self.assertIn("mining-oil-sale", [spec.category for spec in policy._town_need_registry()])
        # The purse buys the oil at 5 gold.
        self.assertIsNone(scroll(lambda page: page["player"].update(gold=5)))
        # The set's one remaining run keeps the last scroll.
        self.assertIsNone(scroll(lambda page: page["inventory"][0].update(count=1)))
        # A torch takes no oil (src/cmd-item/cmd-refill.cpp).
        self.assertIsNone(scroll(torch_only))
        # A lantern with fuel left has no need yet.
        self.assertIsNone(scroll(lambda page: lantern(page).update(light_turns=100)))
        # An unidentified lantern shows no fuel.
        self.assertIsNone(scroll(lambda page: lantern(page).update(known=False)))
        self.assertIsNone(scroll(flask))

        def dark_light(page):
            page["inventory"].append(dict(lantern(page), name="★火消しライター", sval=4, slot="e",
                                          known_flags=[8, 84, 85, 86, 87, 88, 116, 124, 146]))
        # A dark light held (model.lights_nothing) neither needs oil nor lights the way.
        self.assertIsNotNone(scroll(dark_light))

    def test_a_burnt_out_torch_gives_way_to_the_q34_lantern_in_town(self):
        """Owner 2026-11-06 「町でも付けてよい」 (the 10-31 rule for Q34 gear):
        n1-c life-141 05:45, its torch at 0 turns beside the unidentified Q34
        lantern {並, Q34}, waited town:wait-restock:general:oil-light and stopped at
        town:blocked:survival:recall_departure_ready."""
        policy, recorded, steps = self.load("q34-lantern-town")
        self.assertEqual(recorded[17]["reason"], "town:wait-restock:general:oil-light")
        raw = json.loads(recorded[17]["line"] or recorded[17]["inputs"][-1])
        twin = copy.deepcopy(policy)
        board, chosen, reason, _ = self.replay_to(policy, recorded, steps, 17)
        lantern = next(item for item in board.inventory if item.is_lantern)
        self.assertEqual((lantern.slot, lantern.known, lantern.inscription), ("c", False, "Q34"))
        # The wield answers the game's prompt, which the constructed command screen
        # of the executor harness does not show: the pin stops at the chooser.
        self.assertEqual((chosen, reason), ("wc", "wield-light"))

        # DECLARED CONSTRUCTED on the same board: an unidentified lantern from
        # elsewhere, listed first, is not worn in town; a torch still burning keeps.
        for index in range(17):
            self.post(twin, self.decide(twin, steps[index][1])[3])
        other = copy.deepcopy(raw)
        stray = dict(next(item for item in other["inventory"] if item["tval"] == 39),
                     name="真鍮のランタン {並}", inscription="")
        other["inventory"].insert(0, stray)
        for index, item in enumerate(other["inventory"]):
            item["slot"] = chr(ord("a") + index)
        view = parse_snapshot(other, twin._monrace_knowledge)
        self.assertEqual(twin._find_light(view).slot, "d")
        burning = copy.deepcopy(raw)
        next(item for item in burning["equipment"] if item["slot"] == "light")["light_turns"] = 19
        self.assertIsNone(twin._town_q34_lantern(parse_snapshot(burning, twin._monrace_knowledge)))

    @staticmethod
    def lantern_worn(raw, light_radius, *, oil=0, inscription="Q34"):
        """DECLARED CONSTRUCTED: the game's board after the wield of row 17.

        The lantern takes the light slot and the torch goes to the pack;
        ``light_radius`` is the player's light (torch.cpp update_lite_radius: an
        empty lantern adds none), the only fuel fact the unidentified lantern shows.
        """
        board = copy.deepcopy(raw)
        lantern = next(item for item in board["inventory"] if item["tval"] == 39)
        board["inventory"].remove(lantern)
        if inscription != "Q34":
            lantern.update(name="真鍮のランタン {並}", inscription=inscription)
        light = next(index for index, item in enumerate(board["equipment"]) if item["slot"] == "light")
        torch = board["equipment"][light]
        board["equipment"][light] = dict(lantern, slot="light")
        board["inventory"].append(torch)
        if oil:
            scroll = board["inventory"][0]
            board["inventory"].insert(0, dict(scroll, tval=77, sval=0, name="油つぼ", count=oil))
        for index, item in enumerate(board["inventory"]):
            item["slot"] = chr(ord("a") + index)
        board["player"]["light_radius"] = light_radius
        board["turn"] += 10
        return board

    def test_the_q34_lantern_departs_on_its_fuel_and_takes_the_oil_sale(self):
        """Owner 2026-11-06 「燃料があれば出発してよい」: 「ランタンに燃料が残っていれば、
        油が5本に届かなくても出発します。財宝感知の巻物を売って油を足す決まりも、この
        ランタンに使います。」  n1-c life-141 05:45: 1 gold, no oil, three Treasure
        Detection scrolls, the Q34 lantern worn at row 17 (unidentified: no fuel figure;
        the player's light radius shows whether it burns)."""
        policy, recorded, steps = self.load("q34-lantern-town")
        for index in range(17):
            self.post(policy, self.decide(policy, steps[index][1])[3])
        _, chosen, reason, key = self.decide(policy, steps[17][1])
        self.assertEqual((chosen, reason), ("wc", "wield-light"))
        self.post(policy, key)
        raw = json.loads(recorded[17]["line"] or recorded[17]["inputs"][-1])
        view = lambda board: parse_snapshot(copy.deepcopy(board), policy._monrace_knowledge)

        # Lit: the departure passes on 0 of 5 flasks and the oil sale stays off.
        lit = self.lantern_worn(raw, 2)
        self.assertTrue(policy._fundraising_light_ready(view(lit)))
        self.assertIsNone(mining_oil_sale.scroll_to_sell(policy, view(lit)))
        # Another unidentified lantern keeps the five flasks.
        self.assertFalse(policy._fundraising_light_ready(view(self.lantern_worn(raw, 2, inscription=""))))
        twin = copy.deepcopy(policy)
        reasons = []
        for _ in range(2):
            _, chosen, reason, key = self.decide(twin, lambda: view(lit))
            reasons.append(reason)
            self.post(twin, key)
            # DECLARED CONSTRUCTED: the rest of the restock wait passes.
            lit["turn"] += 5000
        # The wait the visit held at row 17 runs out, then the mining run leaves.
        self.assertEqual(reasons, ["town:wait-restock:general", "town:travel-entrance"])

        # Out: the oil sale takes one scroll, and the oil it buys goes in at once.
        out = view(self.lantern_worn(raw, 0))
        self.assertFalse(policy._fundraising_light_ready(out))
        self.assertTrue(mining_oil_sale.scroll_to_sell(policy, out).is_treasure_detection_scroll)
        _, _, reason, _ = self.decide(copy.deepcopy(policy), lambda: view(self.lantern_worn(raw, 0, oil=1)))
        self.assertEqual(reason, "refill-light")


if __name__ == "__main__":
    unittest.main()
