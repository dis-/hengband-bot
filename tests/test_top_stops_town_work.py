"""Town work projected from October 26 incidents; no post-change live replay."""
import tests  # noqa: F401
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key, _observe_owner_retired_progress
from hengbot.model import *
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import DecisionCandidate
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.town_maps import parse_town_map
from policy_fixtures import player, item, grid
from tests.test_input_executor import ProductionHarness, FaithfulHookGame, command_screen

FIXTURE = Path(__file__).parent / "fixtures/top-stops-retirement-projection.json"
EDIT = Path("C:/hengband/lib/edit")


class TopStopsTownWorkTest(ProductionHarness):
    def send(self, board, key, reason):
        game = FaithfulHookGame()
        game.state = {"turn": board.turn, "grid_map": {"runs": []}}
        game.screen = command_screen(board.turn)
        game.screens = [command_screen(board.turn + 1)]
        game, _client, executor = self.make(game)
        executor.observe_boundary(deadline=9999999999)
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _posted = _send_new_decision_key(
            port, "top-stops-C", key, None, set(), in_store=False,
            decision={"sequence": 1, "reason": reason}, snapshot=board,
            posting_contract=PostingContract())
        self.assertTrue(sent)
        self.assertEqual(port.last_result.outcome, "completed", port.last_result.reason)
        return game

    @staticmethod
    def supplies():
        return [item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=10),
                item("b", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
                item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
                item("d", TVAL_FOOD, 35, count=10),
                item("e", TVAL_FLASK, 0, count=5, fuel=7500)]

    def test_public_claim_walk_keeps_its_quest_route_instead_of_old_supplier_goal(self):
        cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
        case = next(c for c in cases if "214708" in c["source"])
        row = next(d for d in case["decisions"] if d["reason"].startswith("town-progress-invariant:defect:"))
        pos = Position(**row["position"])
        actor = row["player"]
        town = parse_town_map(EDIT / "towns/01_Outpost_Full.jsonc")
        # DECLARED CONSTRUCTED: the capture's compressed snapshot was cut at
        # 16 MiB and has no gzip header. Use measured position/level/HP/gold,
        # the game's static town topology and a supplied quiet quest kit.
        terrain = {p: grid(p.y, p.x) for p in town.walkable}
        for quest_id, positions in town.quest_buildings.items():
            if quest_id == 14:
                for target in positions:
                    terrain[target] = replace(terrain[target], building_special=14)
        pack = self.supplies()
        pack[2] = replace(pack[2], count=7)  # a live competing supply route
        board = Snapshot(
            player(pos.y, pos.x, level=actor["level"], hp=actor["hp"], max_hp=actor["max_hp"], gold=actor["gold"]),
            terrain, [], turn=row["turn"], town_flag=True, town_id=0,
            width=town.width, height=town.height, inventory=pack,
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True),
                       item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=7500, is_equipment=True)],
            quests={q: QuestState(q, status=2 if q == 14 else 4, fixed=True, level=5) for q in (1, 34, 14)},
        )
        policy = HengbotPolicy(town_maps={0: town}, quest_knowledge=load_quest_knowledge(EDIT / "quests"))
        policy.consume_home_knowledge(())
        policy._equipment_optimization_last_depth = 19
        policy._shopping_approach_goal = Position(37, 91)  # observed Alchemist in the cycle
        policy._shopping_approach_store_type = 4
        policy._town_progress_history().append(policy._town_progress_fingerprint(board))
        key = policy.choose_key(board)
        self.assertIsInstance(key, DecisionCandidate)
        self.assertEqual(policy.last_reason, "fixedquest:claim:approach")
        self.assertEqual(str(key), "9")
        self.assertNotEqual(key.route_declaration.goal, policy._shopping_approach_goal)
        self.assertTrue(policy._town_result_makes_progress(board, key))
        game = self.send(board, key, policy.last_reason)
        self.assertEqual(game.accepted, ["9"])

    def test_public_home_junk_destroy_publishes_observed_effect_receipt(self):
        # DECLARED CONSTRUCTED: life-360's long-sword junk sweep, projected onto
        # a quiet fully supplied board after its Home withdrawal; mark this
        # control cursed so junk classification needs no missing optimizer dump.
        pos = Position(10, 10)
        junk = item("f", TVAL_SWORD, 17, name="ロング・ソード (2d5) (+3,+4)",
                    to_h=3, to_d=4, damage_dice_num=2, damage_dice_sides=5,
                    is_equipment=True, is_cursed=True)
        board = Snapshot(player(10, 10, level=26, hp=474, max_hp=474, gold=17022),
                         {pos: grid(10, 10)}, [], turn=1422807, town_flag=True, town_id=0,
                         inventory=(*self.supplies(), junk),
                         equipment=[item("main_hand", TVAL_SWORD, 17, to_h=10, to_d=10,
                                         damage_dice_num=3, damage_dice_sides=6, is_equipment=True, is_ego=True),
                                    item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=7500, is_equipment=True)])
        policy = HengbotPolicy()
        policy.prime(board)
        policy.consume_home_knowledge(())
        policy._home_full_relief = dict(deposits=(), remaining=1,
            sale=(policy._item_signature(junk), None, 0), withdrawn=True,
            town=0, sweep=True, sweep_class="cursed", mode="destroy")
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "home:junk-sweep:cursed")
        self.assertEqual(str(key), "01kf")
        self.send(board, key, policy.last_reason)
        policy.confirm_key_posted(key)
        _observe_owner_retired_progress(policy, board, key)
        policy._owner_retired_no_progress_count = 2
        # Source-derived successful destroy effect. No captured later board is
        # presented as a response to this new command.
        after = replace(board, turn=board.turn + 1, inventory=tuple(i for i in board.inventory if i.slot != "f"))
        next_key = policy.choose_key(after)
        _observe_owner_retired_progress(policy, after, next_key)
        self.assertEqual(policy._owner_retired_no_progress_count, 0)
        self.assertTrue(policy._owner_retired_progress["last_settlement"]["matched_effect_identity"])

    def test_stockout_preparation_routes_to_mining_kit_not_exhausted_staff(self):
        # DECLARED CONSTRUCTED: life-194's staff shortage and the same one-run
        # preparation as life-358, on a small complete shop corridor.
        terrain = {Position(10, x): grid(10, x) for x in range(6, 15)}
        for x, store in ((6, STORE_MAGIC), (8, STORE_ALCHEMIST), (12, STORE_HOME), (14, STORE_GENERAL)):
            terrain[Position(10, x)] = replace(terrain[Position(10, x)], store_number=store)
        board = Snapshot(player(10, 10, level=26, hp=615, max_hp=615, gold=1189, class_id=PLAYER_CLASS_WARRIOR),
            terrain, [], turn=1113527, town_flag=True, town_id=0,
            width=20, height=20,
            inventory=(*self.supplies(), item("f", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=19)),
            equipment=[item("main_hand", TVAL_SWORD, 17, to_h=10, to_d=10, is_equipment=True),
                       item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=7500, is_equipment=True)])
        policy = HengbotPolicy()
        policy.prime(board)
        policy.consume_home_knowledge(())
        policy._equipment_optimization_last_depth = 19
        # The one-run stockout initiator cleared supplier attempts, as in the
        # incidents; the missing kit is now preparation's live work.
        policy._identify_staff_mining_plan = True
        policy._fundraising_mode = "prepare"
        policy._planned_mining_runs = 1
        key = policy.choose_key(board)
        self.assertTrue(policy._identify_staff_mining_plan)
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertFalse(policy._fundraising_identify_staff_only_block(board))
        self.assertNotEqual(policy._shopping_approach_store_type, STORE_MAGIC)
        self.send(board, key, policy.last_reason)
