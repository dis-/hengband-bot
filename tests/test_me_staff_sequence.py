"""The class-16 staff sequence after Q1 (owner 2026-10-30), step by step.

「魔道具術師でQ1クリア後の最初の採掘の目標を明示する。・資金を貯めて鑑定の杖と
財宝感知の杖を1本ずつ買う」「その後、噂でモリバントへの移動を解禁、鑑定と財宝感知を
チャージマックスにして取り込む」「2本目は買わない。以降、鑑定と財宝感知は取り込みで賄う」

Every boundary is decided by the public ``choose_key``; each posted key is
sent through the production executor (``_ExecutorInputPort`` over
``OperationExecutor``).  DECLARED CONSTRUCTED: the boards are synthetic
class-16 zombie (food type 4) boards on protocol 3 with Q34 finished and Q1
rewarded; the Magic-shop rows and prices (530 / 260), the staffs' charges,
the town ids, the inn/shop cells, the Morivant Tower cell (building 8 of
lib/edit/towns/03_Morivant.jsonc) and every prompt screen are constructed.
The game's reply to a posted key (moved player, bought row, recharged or
absorbed staff, unlocked town) is likewise constructed from the key.
"""

import tests  # noqa: F401 -- isolate live runtime files
from dataclasses import asdict, replace
import io
import time
import unittest

from policy_fixtures import grid, item, player, store_item
import test_policy_quest as quest_tests
import test_input_executor as input_tests
from test_magic_eater_o3 import prompt
from test_me_tower_recharge_recorded import recharge_all_screens
from hengbot.cli import (
    PostingContract, SendResult, _ExecutorInputPort, _send_decision_key_with_prompt_chain,
)
from hengbot.control_client import ControlClient
from hengbot.input_executor import OperationExecutor
from hengbot import me_staff_sequence as sequence
from hengbot.magic_eater import ABSORB_REASON
from hengbot.model import (
    Position, QuestState, Snapshot, StoreState, STORE_MAGIC, SV_STAFF_IDENTIFY,
    TVAL_RING, TVAL_STAFF, parse_snapshot,
)
from hengbot.policy_constants import WAIT_KEY


DETECT = sequence.SV_STAFF_DETECT_GOLD
IDENTIFY_PRICE, DETECT_PRICE = 530, 260
SHOP = Position(10, 14)
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def staff(slot, sval, charges):
    name = ("鑑定の杖" if sval == SV_STAFF_IDENTIFY else "財宝感知の杖") + f" ({charges}回分)"
    return replace(item(slot, TVAL_STAFF, sval, charges=charges, pval=charges, name=name),
                   known=True)


def magic_page():
    return [
        store_item("a", TVAL_STAFF, SV_STAFF_IDENTIFY, price=IDENTIFY_PRICE,
                   name="鑑定の杖 (8回分)", charges=8, pval=8),
        store_item("b", TVAL_STAFF, DETECT, price=DETECT_PRICE,
                   name="財宝感知の杖 (7回分)", charges=7, pval=7),
        # A second Identify staff: 「2本目は買わない」.
        store_item("c", TVAL_STAFF, SV_STAFF_IDENTIFY, price=IDENTIFY_PRICE + 40,
                   name="鑑定の杖 (9回分)", charges=9, pval=9),
    ]


def power_list(sval, current, maximum, *, japanese=True):
    screen = prompt("('*'で一覧, ESCで中断) どの魔力を使いますか？" if japanese else
                    "(*=List, ESC=exit) Use which power? ", "spell")
    name = sequence.POWER_NAMES[sval][0 if japanese else 1]
    letter = sequence.POWER_LETTER[sval]
    screen["lines"][1] = "                           使用回数 失率"
    screen["lines"][2 + sval] = f"{letter}) {name:<22}    {current:2}/{maximum:2}  12%"
    return screen


class MeStaffSequenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        quest_tests.ApprovedQuestStrategyExecutionTest.setUpClass()

    def policy(self):
        policy = quest_tests.ApprovedQuestStrategyExecutionTest()._policy()
        policy._fixed_quest_speed_attempted = True
        return policy

    def board(self, *, gold=300, inventory=(), store=None, town=0, visited=(0,),
              position=(10, 10), building=None, turn=1000):
        grids = {Position(y, x): grid(y, x) for y in range(5, 16) for x in range(5, 16)}
        grids[SHOP] = replace(grids[SHOP], store_number=STORE_MAGIC)
        if building is not None:
            grids[Position(10, 12)] = replace(grids[Position(10, 12)], building_type=building)
        return Snapshot(
            replace(player(*position, hp=100, max_hp=100, level=8, class_id=16,
                           food_type=4, gold=gold), race_id=25),
            grids, [], inventory=list(inventory), floor_key=(0, 0, 0),
            town_id=town, town_flag=True, turn=turn, store=store,
            visited_town_ids=tuple(visited), protocol_version=3,
            quests={34: QuestState(34, status=4, fixed=True),
                    1: QuestState(1, status=3, fixed=True)})

    def primed(self, board, *, shelf=True, absorbed=None):
        policy = self.policy()
        policy.prime(board)
        if shelf:
            # DECLARED CONSTRUCTED: the Magic shop page observed before Q1's
            # reward in this town (the supplier-stock memory of a store visit).
            policy._town_supplier_stock[STORE_MAGIC] = StoreState(STORE_MAGIC, magic_page())
            policy._town_supplier_stock_observations[STORE_MAGIC] = (0, board.turn - 100)
        if absorbed is not None:
            policy._me_staff_sequence = sequence.MeStaffSequence(absorbed=dict(absorbed))
        if board.player.class_id == 16:
            # DECLARED CONSTRUCTED: this process already read the game's
            # staff power list (me_staff_sequence.read_powers, #47).
            sequence.state(policy).powers_read = True
        return policy

    # -- production executor ---------------------------------------------
    @staticmethod
    def shelf(page):
        """The open store page as state and screen (lv7 shelf_screen rows)."""
        rows = [{key: value for key, value in asdict(row).items()
                 if key not in {"known_flags", "exported_fields"}} for row in page.items]
        screen = input_tests.store_screen()
        for index, row in enumerate(page.items):
            screen["lines"][6 + index] = f"{row.letter}) {row.name}"
        return {"store_type": page.store_type, "items": rows, "stock_num": page.stock_num,
                "page_top": page.page_top, "page_size": page.page_size}, screen

    def send(self, key, owner, screens=(), *, inventory=(), store=None, policy=None, board=None):
        game = input_tests.FaithfulHookGame()
        # main-gcu.cpp term_init(..., 256): the smallest frontend key queue.
        game.capacity = 256
        game.state = {"turn": 1, "player": {"y": 10, "x": 10, "class_id": 16,
                                            "race_id": 25, "food_type": 4,
                                            "hp": 100, "max_hp": 100},
                      "inventory": [self.raw_item(it) for it in inventory],
                      "equipment": [], "floor": {"dungeon_id": 0, "level": 0},
                      "grid_map": {"runs": []}}
        if store is not None:
            game.state["store"], shelf = self.shelf(store)
            if key.startswith("p"):
                # lv7 harness: the composed buy answers its price question,
                # returns to the page, then leaves (count 1: no quantity).
                ware = next(row for row in store.items if row.letter == key[1])
                screens = [input_tests.prompt_screen(f"Do you buy for ${ware.price}? [Y/n]"),
                           shelf, *screens]
        if store is not None:
            # The game writes the store record when it draws the page.
            game.jsonl = [dict(game.state)]
            game.screen = shelf
        client = ControlClient(1, request_budget=2, retries=1, backoff=0,
                               socket_factory=game.socket_factory)
        self.addCleanup(client.close)
        executor = OperationExecutor(client, drain=lambda: list(game.jsonl))
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        game.screens = [*screens, input_tests.command_screen(2)]
        game.states = [dict(game.state) for _ in game.screens]
        if store is not None:
            # These in-store keys end outside the shop (ESC / composed buy).
            game.states[-1] = {k: v for k, v in game.state.items() if k != "store"}
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        if policy is None:
            status = port(key, decision={"reason": owner, "sequence": 1})
            self.assertEqual(status, SendResult.SENT, port.last_result.reason)
            return game, port.last_result
        # The driver's own send path (lv7 harness), which splits store buys.
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "me-staff-sequence", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": owner},
            snapshot=board, posting_contract=PostingContract(), in_store=store is not None)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertFalse(game.term_fifo)
        policy.confirm_key_posted(key)
        return game, port.last_result

    @staticmethod
    def raw_item(board_item):
        return {key: value for key, value in asdict(board_item).items() if key != "known_flags"}

    def decide(self, policy, board, *screens, inventory=()):
        key = str(policy.choose_key(board))
        self.assertNotEqual(key, "", getattr(policy, "_me_staff_sequence", None))
        game, _ = self.send(key, policy.last_reason, screens, inventory=inventory,
                            store=board.store, policy=policy, board=board)
        return key, game

    # -- (a) ---------------------------------------------------------------
    def test_a_after_q1_short_gold_mines_for_the_explicit_staff_target(self):
        board = self.board(gold=300)
        policy = self.primed(board)
        key, _ = self.decide(policy, board)
        target = IDENTIFY_PRICE + DETECT_PRICE
        self.assertEqual((key, policy.last_reason), (WAIT_KEY, f"me-staff:fundraise:staffs:{target}"))
        self.assertEqual(policy._supply_stockout_gold_target, target)
        self.assertEqual((policy._fundraising_mode, policy._planned_mining_runs), ("prepare", 1))
        self.assertEqual(policy._fundraising_gold_target(), target)
        # The next town board belongs to the existing fundraising owners.
        policy.choose_key(replace(board, turn=board.turn + 10))
        self.assertFalse(policy.last_reason.startswith("me-staff:"), policy.last_reason)

    def test_a_unobserved_shelf_is_visited_before_any_target(self):
        board = self.board(gold=300)
        policy = self.primed(board, shelf=False)
        self.decide(policy, board)
        self.assertEqual(policy.last_reason, "shop:approach")
        self.assertIsNone(policy._supply_stockout_gold_target)

    def test_a_warrior_after_q1_is_not_owned(self):
        board = replace(self.board(gold=300), player=replace(self.board().player, class_id=0))
        policy = self.primed(board)
        policy.choose_key(board)
        self.assertFalse(policy.last_reason.startswith("me-staff:"), policy.last_reason)
        self.assertIsNone(getattr(policy, "_me_staff_sequence", None))

    # -- (b) ---------------------------------------------------------------
    def drive_purchases(self):
        board = self.board(gold=1000, position=(10, 13))
        policy = self.primed(board)
        rows = magic_page()
        bought = []
        for _ in range(16):
            page = StoreState(STORE_MAGIC, list(rows), stock_num=len(rows), page_top=0, page_size=12)
            key = str(policy.choose_key(board))
            reason = policy.last_reason
            self.send(key, reason, store=board.store, policy=policy, board=board)
            if len(bought) == 2:
                return policy, board, bought, key, reason
            turn = board.turn + 10
            if board.store is None and key[-1:] in DIRECTIONS:
                dy, dx = DIRECTIONS[key[-1]]
                position = Position(board.player.position.y + dy, board.player.position.x + dx)
                board = replace(board, player=replace(board.player, position=position), turn=turn,
                                store=page if position == SHOP else None)
            elif board.store is None and key == WAIT_KEY and board.player.position == SHOP:
                board = replace(board, turn=turn, store=page)
            elif board.store is not None and key.startswith("p"):
                ware = next(row for row in rows if row.letter == key[1])
                self.assertEqual(int(key[2:].strip("\r\x1b") or 1), 1, key)
                rows.remove(ware)
                bought.append(ware)
                board = replace(board, turn=turn, store=None,
                                inventory=[*board.inventory, staff("abc"[len(board.inventory)],
                                                                   ware.sval, ware.charges)],
                                player=replace(board.player, gold=board.player.gold - ware.price))
            elif board.store is not None and key == "\x1b":
                board = replace(board, turn=turn, store=None)
            else:
                return policy, board, bought, key, reason
        self.fail("purchases did not settle")

    def test_b_enough_gold_buys_exactly_one_of_each_staff(self):
        policy, board, bought, key, reason = self.drive_purchases()
        self.assertEqual([(row.sval, row.letter) for row in bought],
                         [(SV_STAFF_IDENTIFY, "a"), (DETECT, "b")])
        self.assertEqual(board.player.gold, 1000 - IDENTIFY_PRICE - DETECT_PRICE)
        # The 2nd Identify staff stays on the shelf; the sequence moves on and
        # its next shortfall (rumors, fares, recharge) is again explicit.
        recharge = (21 - 8) * 40 + (19 - 7) * 20
        self.assertEqual(reason, "town:entrance-step-off:me-staff:fundraise:"
                         f"rumor-travel-recharge:{1000 + recharge + 300 + 400}")
        page = StoreState(STORE_MAGIC, [magic_page()[2]], stock_num=1, page_top=0, page_size=12)
        self.assertIsNone(policy._next_purchase(replace(board, store=page, player=replace(
            board.player, position=SHOP, gold=5000))))

    # -- (c) ---------------------------------------------------------------
    def test_c_both_staffs_read_rumors_until_morivant_is_listed(self):
        staffs = [staff("a", SV_STAFF_IDENTIFY, 8), staff("b", DETECT, 7)]
        board = self.board(gold=3000, inventory=staffs, building=0)
        policy = self.primed(board)
        key, _ = self.decide(policy, board)
        self.assertEqual((key, policy.last_reason), ("9", "town:rumor"))
        self.assertEqual(policy._town_travel_rumor_pending, 2)
        board = replace(board, player=replace(board.player, position=Position(10, 11)), turn=1010)
        key, game = self.decide(policy, board)
        self.assertEqual(policy.last_reason, "town:rumor-batch")
        self.assertEqual(key, "6" + "u\r" * 40 + "\x1b")
        self.assertEqual(policy._me_staff_sequence.rumor_batches, 1)
        # The exported progress lists Morivant: the inn teleport is next.
        board = replace(board, visited_town_ids=(0, 2), turn=1100,
                        player=replace(board.player, position=Position(10, 10), gold=2600))
        key, _ = self.decide(policy, board)
        self.assertEqual(policy.last_reason, "me-staff:travel-morivant")
        self.assertIsNone(policy._town_travel_rumor_pending)

    def test_c_rumors_that_never_unlock_end_in_a_named_stop(self):
        staffs = [staff("a", SV_STAFF_IDENTIFY, 8), staff("b", DETECT, 7)]
        board = self.board(gold=3000, inventory=staffs, building=0)
        policy = self.primed(board)
        policy._me_staff_sequence = sequence.MeStaffSequence(
            rumor_batches=sequence.RUMOR_BATCH_LIMIT, powers_read=True)
        self.assertEqual(str(policy.choose_key(board)), "")
        self.assertEqual(policy.last_reason, "quest:blocked:me-staff")
        self.assertEqual(policy._me_staff_sequence.failure, "morivant-rumor-exhausted")

    # -- (d) / (e) ---------------------------------------------------------
    def test_d_e_morivant_recharges_both_staffs_to_max_in_one_visit_then_absorbs_both(self):
        staffs = [staff("a", SV_STAFF_IDENTIFY, 8), staff("b", DETECT, 7)]
        board = self.board(gold=2000, inventory=staffs, town=2, visited=(0, 2),
                           position=(10, 11), building=sequence.TOWER_OF_SORCERY)
        policy = self.primed(board, shelf=False)
        self.assertEqual(sequence.max_charges(SV_STAFF_IDENTIFY), 21)
        self.assertEqual(sequence.max_charges(DETECT), 19)
        # The Tower's 'a' recharges the whole pack; the executor answers 'y'
        # at the observed question and ESC leaves the building.
        total = 13 * 40 + 12 * 20
        self.assertEqual(sequence.recharge_cost(board), total)
        key, game = self.decide(policy, board, *recharge_all_screens(total), inventory=staffs)
        self.assertEqual((key, policy.last_reason), ("6ay" + chr(27), "me-staff:recharge-all"))
        self.assertEqual(game.accepted, ["6", "a", "y", " ", chr(27)])
        full = [staff("a", SV_STAFF_IDENTIFY, 21), staff("b", DETECT, 19)]
        board = replace(board, turn=1200, inventory=full,
                        player=replace(board.player, gold=2000 - 13 * 40 - 12 * 20))
        # (e) both at max: absorb each through the observed absorption prompt.
        absorb_prompt = prompt("どのアイテムの魔力を取り込みますか? ", "item", area="inventory",
                               areas=["inventory", "floor"], menu=False,
                               first_label="a", last_label="b")
        key, game = self.decide(policy, board, absorb_prompt, inventory=full)
        self.assertEqual((key, policy.last_reason), ("Ga", ABSORB_REASON))
        self.assertEqual(game.accepted, ["G", "a"])
        board = replace(board, turn=1300, inventory=[replace(full[1], slot="a")])
        key, game = self.decide(policy, board, absorb_prompt, inventory=board.inventory)
        self.assertEqual((key, policy.last_reason), ("Ga", ABSORB_REASON))
        # Both absorbed: the inn (Morivant building 4) teleport back home.
        board = replace(board, turn=1400, inventory=[], grids={
            **board.grids,
            Position(10, 12): replace(board.grids[Position(10, 12)], building_type=4)})
        key, _ = self.decide(policy, board)
        self.assertEqual(policy._me_staff_sequence.absorbed, {SV_STAFF_IDENTIFY: 21, DETECT: 19})
        # Owner 2026-10-31: stage 1 is complete (decided once) and stage 2's
        # staffs are bought at the Outpost next.
        self.assertEqual((key, policy.last_reason), (WAIT_KEY, "me-staff:stage1-complete"))
        board = replace(board, turn=1500)
        key, _ = self.decide(policy, board)
        self.assertEqual(policy.last_reason, "me-staff:return-to-shop")

    def test_d_short_recharge_gold_returns_to_the_outpost_with_the_fare(self):
        staffs = [staff("a", SV_STAFF_IDENTIFY, 8), staff("b", DETECT, 7)]
        board = self.board(gold=900, inventory=staffs, town=2, visited=(0, 2),
                           position=(10, 11), building=4)
        policy = self.primed(board, shelf=False)
        self.decide(policy, board)
        self.assertEqual(policy.last_reason, "me-staff:return-for-funds")

    # -- (f) ---------------------------------------------------------------
    def test_f_absorbed_never_buys_them_again(self):
        absorbed = {SV_STAFF_IDENTIFY: 21, DETECT: 19}
        page = StoreState(STORE_MAGIC, magic_page(), stock_num=3, page_top=0, page_size=12)
        board = self.board(gold=5000, store=page, position=(10, 14))
        policy = self.primed(board, absorbed=absorbed)
        self.assertIsNone(policy._next_purchase(board))
        key, _ = self.decide(policy, board)
        self.assertEqual((key, policy.last_reason), ("\x1b", "shop:observe-and-leave"))
        # The identify-staff readiness and the detection stock are served.
        self.assertTrue(policy._identify_staff_ready(board))
        self.assertEqual(policy._count_treasure_detection_scrolls(board), 19)

    def test_f_identify_need_uses_the_absorbed_power(self):
        ring = item("a", TVAL_RING, 1, aware=False, known=False, name="大理石の指輪",
                    is_equipment=True)
        board = replace(self.board(gold=500, inventory=[ring]), floor_key=(1, 1, 0),
                        town_id=-1, town_flag=False, turn=5000)
        policy = self.primed(board, shelf=False, absorbed={SV_STAFF_IDENTIFY: 21, DETECT: 19})
        identify = prompt("どのアイテムを鑑定しますか? ", "item", area="inventory",
                          areas=["inventory"], menu=False, first_label="a", last_label="a")
        key, game = self.decide(
            policy, board,
            prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
            prompt("('*'で一覧, ESCで中断) どの魔力を使いますか？", "spell"),
            power_list(SV_STAFF_IDENTIFY, 21, 21), identify, inventory=[ring])
        self.assertEqual((key, policy.last_reason), ("mAfa", "identify:dungeon-equipment"))
        self.assertEqual(game.accepted, ["m", "A", "*", "f", "a"])
        # Without the absorbed power the same board has no identify source.
        policy = self.primed(board, shelf=False)
        policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "identify:dungeon-equipment")

    def test_f_empty_power_is_observed_and_not_reused_on_that_board(self):
        board = replace(self.board(gold=500), floor_key=(1, 1, 0), town_id=-1,
                        town_flag=False, turn=5000)
        policy = self.primed(board, shelf=False, absorbed={SV_STAFF_IDENTIFY: 21, DETECT: 19})
        game, result = self.send(sequence.DETECT_POWER_KEY, sequence.DETECT_REASON, [
            prompt("[A] staff, [B] wand, [C] rod:"),
            prompt("(*=List, ESC=exit) Use which power? ", "spell"),
            power_list(DETECT, 0, 19, japanese=False)])
        self.assertEqual(game.accepted, ["m", "A", "*", "\x1b"])
        listed = parse_snapshot(result.board, {}).magic_eater_power_list
        self.assertEqual(listed["kind"], "staff")
        empty = replace(board, magic_eater_power_list=listed)
        self.assertIsNone(sequence.power_key(policy, empty, DETECT))
        self.assertEqual(sequence.power_key(policy, replace(board, turn=5100), DETECT),
                         sequence.DETECT_POWER_KEY)


if __name__ == "__main__":
    unittest.main()
