"""Source-derived class-16 O3 boards through public policy and follow input."""

import tests  # noqa: F401 -- isolate live runtime files
from dataclasses import asdict, replace
from pathlib import Path
import unittest

from policy_fixtures import grid, hostile, item, player
import test_policy_quest as quest_tests
import test_input_executor as input_tests
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.control_client import ControlClient
from hengbot.input_executor import OperationExecutor
from hengbot.magic_eater import ABSORB_REASON, MISSILE_REASON
from hengbot.model import (Snapshot, Position, QuestState, TVAL_LITE, TVAL_WAND,
                           TVAL_STAFF, SV_LITE_TORCH, parse_snapshot)


def prompt(text, kind="command_char", **details):
    screen = input_tests.prompt_screen(text)
    screen["cursor"]["visible"] = True
    screen["input_context"] = ({"kind": kind, "prompt": text, **details}
                               if kind else None)
    return screen


def powers(charges=17, *, menu=False, selected=True, japanese=False):
    text = ("('*'で一覧, ESCで中断) どの魔力を使いますか？" if japanese else
            "(*=List, ESC=exit) Use which power? ")
    screen = prompt(text)
    label = ("》" if japanese else "> ") if menu and selected else "  " if menu else "p)"
    name = "マジック・ミサイル" if japanese else "Magic Missile"
    screen["lines"][3] = f"{label} {name:<22}    {charges:2}/17  35%"
    return screen


class MagicEaterO3Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        quest_tests.ApprovedQuestStrategyExecutionTest.setUpClass()

    def policy(self):
        policy = quest_tests.ApprovedQuestStrategyExecutionTest()._policy()
        policy._fixed_quest_speed_attempted = True
        return policy

    def board(self, *, class_id=16, race=243, charges=None, wand=False):
        # DECLARED CONSTRUCTED: real Q34 approved stands, class-16 zombie,
        # completed light/hold phase, observed stationary target and torches.
        stand, target = ((7, 13), (7, 15)) if race == 243 else ((11, 11), (9, 11))
        torch = item("t", TVAL_LITE, SV_LITE_TORCH, count=20, fuel=5000)
        inventory = [torch]
        if wand:
            inventory.append(item("b", TVAL_WAND, 15, charges=17))
        monster = replace(hostile(1, *target, distance=3), race_id=race)
        snap = Snapshot(
            replace(player(*stand, hp=100, max_hp=100, class_id=class_id),
                    race_id=30),
            {Position(y, x): grid(y, x, monster=(y, x) == target, in_view=True)
             for y in range(3, 14) for x in range(1, 17)},
            [monster], inventory=inventory, equipment=[replace(torch, slot="light", count=1)],
            floor_key=(0, 5, 34),
            quests={34: QuestState(34, status=1, fixed=True)},
            magic_eater_wand_charges=charges)
        return snap

    def choose(self, policy, board):
        return policy.choose_key(board)

    def test_public_cloaker_prefers_absorbed_missile(self):
        policy = self.policy()
        self.assertEqual(self.choose(policy, self.board()), "mBp6")
        self.assertEqual(policy.last_reason, MISSILE_REASON)

    def test_public_sword_prefers_absorbed_missile(self):
        policy = self.policy()
        board = self.board(race=107)
        policy._quest_strategy_cleared_targets[34] = {(243, 7, 15)}
        self.assertEqual(self.choose(policy, board), "mBp8")
        self.assertEqual(policy.last_reason, MISSILE_REASON)

    def test_public_zero_charges_falls_back_to_torch(self):
        policy = self.policy()
        self.assertEqual(self.choose(policy, self.board(charges=0)), "vt6")
        self.assertEqual(policy.last_reason, "quest-strategy:throw-torch")

    def test_public_warrior_preserves_torch(self):
        policy = self.policy()
        self.assertEqual(self.choose(policy, self.board(class_id=0)), "vt6")
        self.assertEqual(policy.last_reason, "quest-strategy:throw-torch")

    def test_public_safe_quest_absorbs_identified_birth_wand(self):
        policy = self.policy()
        board = replace(self.board(wand=True), visible_monsters=[])
        self.assertEqual(self.choose(policy, board), "Gb")
        self.assertEqual(policy.last_reason, ABSORB_REASON)

    def test_absorption_waits_for_safety_and_identification(self):
        for unsafe in ("hostile", "unidentified", "charging", "injured", "confused"):
            with self.subTest(unsafe=unsafe):
                board = replace(self.board(wand=True), visible_monsters=[])
                if unsafe == "hostile":
                    board = self.board(wand=True)
                elif unsafe in {"unidentified", "charging"}:
                    wand = replace(board.inventory[-1], **(
                        {"known": False} if unsafe == "unidentified" else {"charging": True}))
                    board = replace(board, inventory=[board.inventory[0], wand])
                else:
                    board = replace(board, player=replace(board.player, **(
                        {"hp": 99} if unsafe == "injured" else {"confused": True})))
                self.assertNotEqual(self.choose(self.policy(), board), "Gb")

    def test_public_town_absorbs_before_q34_preparation(self):
        board = replace(self.board(wand=True), visible_monsters=[],
                        floor_key=(0, 0, 0), town_id=0, town_flag=True)
        policy = self.policy()
        self.assertEqual(self.choose(policy, board), "Gb")
        self.assertEqual(policy.last_reason, ABSORB_REASON)

    def test_missile_is_reserved_from_zombie_food_and_counts(self):
        policy = self.policy()
        board = replace(self.board(wand=True), player=replace(self.board().player, food_type=4))
        self.assertIsNone(policy._find_edible(board))
        self.assertEqual(policy._count_mana_food_uses(board), 0)
        self.assertEqual(policy._count_mana_food_devices(board), 0)
        unknown = replace(board.inventory[-1], known=False)
        self.assertIsNone(policy._find_edible(replace(board, inventory=[unknown])))
        food = item("c", TVAL_STAFF, 32, charges=5)
        self.assertEqual(policy._find_edible(replace(board, inventory=[unknown, food])), food)

    def run_follow(self, key, owner, screens, *, inventory=()):
        game = input_tests.FaithfulHookGame()
        game.state = {"turn": 1, "player": {"y": 10, "x": 20, "class_id": 16,
                                            "hp": 100, "max_hp": 100},
                      "inventory": list(inventory), "equipment": [], "grid_map": {"runs": []}}
        client = ControlClient(1, request_budget=2, retries=1, backoff=0,
                               socket_factory=game.socket_factory)
        self.addCleanup(client.close)
        executor = OperationExecutor(client, drain=lambda: list(game.jsonl))
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        game.screens = [*screens, input_tests.command_screen(2)]
        game.states = [dict(game.state) for _ in game.screens]
        send = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        status = send(key, decision={"reason": owner, "sequence": 1})
        return game, send.last_result, status

    def test_follow_answers_each_nonmenu_prompt_and_tracks_screen_charges(self):
        for jp in (False, True):
            with self.subTest(japanese=jp):
                kind = "[A] 杖, [B] 魔法棒, [C] ロッド:" if jp else "[A] staff, [B] wand, [C] rod:"
                list_prompt = prompt("('*'で一覧, ESCで中断) どの魔力を使いますか？" if jp else
                                     "(*=List, ESC=exit) Use which power? ")
                key = self.choose(self.policy(), self.board())
                game, result, status = self.run_follow(key, MISSILE_REASON, [
                    prompt(kind), list_prompt, powers(7, japanese=jp),
                    prompt("Direction ('*' to choose a target, Escape to cancel)? ",
                           "direction", can_choose_target=True, has_target=False, at_feet=False)])
                self.assertEqual(status, SendResult.SENT, result.reason)
                self.assertEqual(game.accepted, ["m", "B", "*", "p", "6"])
                self.assertEqual(parse_snapshot(result.board, {}).magic_eater_wand_charges, 7)

    def test_follow_menu_observes_cursor_before_selecting(self):
        kind = prompt("Which type of magic do you use?", kind=None)
        kind["lines"][2:5] = ["               >  staff", "                  wand", "                  rod"]
        wand = {**kind, "lines": list(kind["lines"])}
        wand["lines"][2:5] = ["                  staff", "               >  wand", "                  rod"]
        game, result, status = self.run_follow("mBp6", MISSILE_REASON, [
            kind, wand, powers(menu=True), prompt("Direction?", "direction", can_choose_target=True)])
        self.assertEqual(status, SendResult.SENT, result.reason)
        self.assertEqual(game.accepted, ["m", "2", "\r", "\r", "6"])

    def test_follow_zero_cancels_without_aim_and_public_falls_back(self):
        game, result, status = self.run_follow("mBp6", MISSILE_REASON, [
            prompt("[A] staff, [B] wand, [C] rod:"), powers(0)])
        self.assertEqual(status, SendResult.SENT, result.reason)
        self.assertEqual(game.accepted, ["m", "B", "\x1b"])
        observed = parse_snapshot(result.board, {}).magic_eater_wand_charges
        self.assertEqual(observed, 0)
        self.assertEqual(self.choose(self.policy(), self.board(charges=observed)), "vt6")

    def test_follow_spell_failure_drops_direction(self):
        failure = input_tests.command_screen(2)
        failure["lines"][0] = "You failed to get the magic off!"
        game, result, status = self.run_follow("mBp6", MISSILE_REASON, [
            prompt("[A] staff, [B] wand, [C] rod:"), powers(2), failure])
        self.assertEqual(status, SendResult.SENT, result.reason)
        self.assertEqual(game.accepted, ["m", "B", "p"])

    def test_follow_absorption_is_context_and_identity_bound(self):
        board = replace(self.board(wand=True), visible_monsters=[])
        policy = self.policy()
        key = self.choose(policy, board)
        game, result, status = self.run_follow(key, policy.last_reason, [
            prompt("Gain power of which item? ", "item")],
            inventory=[{key: value for key, value in asdict(board.inventory[-1]).items()
                        if key != "known_flags"}])
        self.assertEqual(status, SendResult.SENT, result.reason)
        self.assertEqual(game.accepted, ["G", "b"])

    def test_follow_missing_or_wrong_context_posts_no_answer(self):
        for screen in (prompt("[A] staff, [B] wand, [C] rod:", "item"),
                       input_tests.prompt_screen("[A] staff, [B] wand, [C] rod:"),
                       prompt("Unrelated prompt")):
            with self.subTest(screen=screen):
                game, result, status = self.run_follow("mBp6", MISSILE_REASON, [screen])
                self.assertEqual(status, SendResult.TERMINAL)
                self.assertEqual(game.accepted, ["m"])


if __name__ == "__main__":
    unittest.main()
