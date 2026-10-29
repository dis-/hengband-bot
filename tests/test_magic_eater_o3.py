"""Source-derived class-16 O3 boards through public policy and follow input."""

import tests  # noqa: F401 -- isolate live runtime files
from dataclasses import asdict, replace
from pathlib import Path
import json
import unittest

from policy_fixtures import grid, hostile, item, player
import test_policy_quest as quest_tests
import test_input_executor as input_tests
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.control_client import ControlClient
from hengbot.input_executor import OperationExecutor
from hengbot.magic_eater import ABSORB_REASON, MISSILE_REASON
from hengbot.model import (Snapshot, Position, QuestState, TVAL_LITE, TVAL_WAND,
                           SV_LITE_TORCH, parse_snapshot)


def prompt(text, kind="command_char", **details):
    screen = input_tests.prompt_screen(text)
    screen["cursor"]["visible"] = True
    screen["input_context"] = ({"kind": kind, "prompt": text, **details}
                               if kind else None)
    return screen


def powers(charges=17, *, menu=False, selected=True, japanese=False):
    text = ("('*'で一覧, ESCで中断) どの魔力を使いますか？" if japanese else
            "(*=List, ESC=exit) Use which power? ")
    screen = prompt(text, "spell")
    label = ("》" if japanese else "> ") if menu and selected else "  " if menu else "p)"
    name = "マジック・ミサイル" if japanese else "Magic Missile"
    screen["lines"][17] = f"{label} {name:<22}    {charges:2}/17  35%"
    if menu and not selected:
        screen["lines"][2] = ">  Heal Monster               1/1  10%"
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
        monster = replace(hostile(1, *target, distance=2), race_id=race)
        snap = Snapshot(
            replace(player(*stand, hp=100, max_hp=100, class_id=class_id, food_type=4),
                    race_id=25),
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

    def test_public_missile_uses_existing_stationary_combat_guard(self):
        from hengbot.cli import _cell_loop_guard_applies
        policy = self.policy()
        board = self.board()
        self.assertEqual(self.choose(policy, board), "mBp6")
        self.assertFalse(_cell_loop_guard_applies(board, policy.last_reason, board.player.position))
        self.assertTrue(_cell_loop_guard_applies(
            board, policy.last_reason, Position(board.player.position.y, board.player.position.x - 1)))

    def test_public_sword_prefers_absorbed_missile(self):
        policy = self.policy()
        board = self.board(race=107)
        policy._quest_strategy_cleared_targets[34] = {(243, 7, 15)}
        self.assertEqual(self.choose(policy, board), "mBp8")
        self.assertEqual(policy.last_reason, MISSILE_REASON)

    def test_public_zero_charges_tries_one_rest_before_torch(self):
        policy = self.policy()
        self.assertEqual(self.choose(policy, self.board(charges=0)), "R100\r")
        self.assertEqual(policy.last_reason, MISSILE_REASON)
        self.assertEqual(self.choose(policy, self.board(charges=0)), "vt6")
        self.assertEqual(policy.last_reason, "quest-strategy:throw-torch")

    def test_public_reobserves_charge_regeneration_after_throw_turn(self):
        policy = self.policy()
        board = self.board(charges=0)
        self.assertEqual(self.choose(policy, board), "R100\r")
        self.assertEqual(self.choose(policy, replace(board, magic_eater_wand_charges=None)), "vt6")
        later = replace(board, turn=board.turn + 1, magic_eater_wand_charges=None)
        self.assertEqual(self.choose(policy, later), "mBp6")

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

    def test_absorption_registers_quest_owner_and_observation_goal(self):
        from hengbot.claim_goal_typing import goal_typing
        from hengbot.claim_ladder import rung_of
        from hengbot.town_arbiter import reason_owner_family
        from hengbot.claim_register import CLAIM_OWNER_ATTRIBUTE
        from hengbot.magic_eater import absorb_key
        self.assertEqual(reason_owner_family(ABSORB_REASON), "quest-request")
        self.assertEqual(rung_of("quest-request", ABSORB_REASON).producer, "absorb_key")
        self.assertIsNotNone(goal_typing("quest-request", ABSORB_REASON))
        self.assertEqual(getattr(absorb_key, CLAIM_OWNER_ATTRIBUTE).value, "quest-request")

    def run_follow(self, key, owner, screens, *, inventory=()):
        # Every prompt variant starts with the public producer on a class-16
        # zombie board, including menu, failure and cancellation paths.
        board = self.board()
        if owner == ABSORB_REASON:
            board = replace(self.board(wand=True), visible_monsters=[])
        policy = self.policy()
        produced = self.choose(policy, board)
        self.assertEqual((produced, policy.last_reason), (key, owner))
        game = input_tests.FaithfulHookGame()
        game.state = {"turn": 1, "player": {"y": 10, "x": 20, "class_id": 16,
                                            "race_id": 25, "food_type": 4,
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
        status = send(produced, decision={"reason": owner, "sequence": 1})
        return game, send.last_result, status

    def test_follow_answers_each_nonmenu_prompt_and_tracks_screen_charges(self):
        for jp in (False, True):
            with self.subTest(japanese=jp):
                kind = "[A] 杖, [B] 魔法棒, [C] ロッド:" if jp else "[A] staff, [B] wand, [C] rod:"
                list_prompt = prompt("('*'で一覧, ESCで中断) どの魔力を使いますか？" if jp else
                                     "(*=List, ESC=exit) Use which power? ", "spell")
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

    def test_follow_power_menu_moves_then_observes_selection(self):
        game, result, status = self.run_follow("mBp6", MISSILE_REASON, [
            prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
            powers(menu=True, selected=False, japanese=True),
            powers(menu=True, selected=True, japanese=True),
            prompt("方向 ('*'でターゲット選択, ESCで中断)? ",
                   "direction", can_choose_target=True)])
        self.assertEqual(status, SendResult.SENT, result.reason)
        self.assertEqual(game.accepted, ["m", "B", "2", "\r", "6"])

    def test_follow_missile_kill_keeps_existing_level_up_owner(self):
        stat = json.loads((Path(__file__).parent / "fixtures" /
                           "screen-20260920-levelup-stat-prompt.json").read_text(encoding="utf-8"))
        game, result, status = self.run_follow("mBp6", MISSILE_REASON, [
            prompt("[A] staff, [B] wand, [C] rod:"), powers(),
            prompt("Direction?", "direction", can_choose_target=True), stat])
        self.assertEqual(status, SendResult.SENT, result.reason)
        self.assertEqual(game.accepted, ["m", "B", "p", "6", "ay"])

    def test_follow_zero_cancels_without_aim_and_public_tries_recharge(self):
        game, result, status = self.run_follow("mBp6", MISSILE_REASON, [
            prompt("[A] staff, [B] wand, [C] rod:"), powers(0)])
        self.assertEqual(status, SendResult.SENT, result.reason)
        self.assertEqual(game.accepted, ["m", "B", "\x1b"])
        observed = parse_snapshot(result.board, {}).magic_eater_wand_charges
        self.assertEqual(observed, 0)
        self.assertEqual(self.choose(self.policy(), self.board(charges=observed)), "R100\r")

    def test_follow_spell_failure_drops_direction(self):
        failure = input_tests.command_screen(2)
        failure["lines"][0] = "You failed to get the magic off!"
        game, result, status = self.run_follow("mBp6", MISSILE_REASON, [
            prompt("[A] staff, [B] wand, [C] rod:"), powers(2), failure])
        self.assertEqual(status, SendResult.SENT, result.reason)
        self.assertEqual(game.accepted, ["m", "B", "p"])

    def test_follow_failure_more_keeps_observed_charges_and_drops_aim(self):
        game, result, status = self.run_follow("mBp6", MISSILE_REASON, [
            prompt("[A] staff, [B] wand, [C] rod:"), powers(2),
            input_tests.prompt_screen("You failed to get the magic off! -more-")])
        self.assertEqual(status, SendResult.SENT, result.reason)
        self.assertEqual(game.accepted, ["m", "B", "p", " "])
        self.assertEqual(result.board["_magic_eater_wand_charges"], 2)

    def test_follow_unlearned_wand_falls_back(self):
        failure = input_tests.command_screen(2)
        failure["lines"][0] = "You don't have that type of magic!"
        game, result, status = self.run_follow("mBp6", MISSILE_REASON, [
            prompt("[A] staff, [B] wand, [C] rod:"), failure])
        self.assertEqual(status, SendResult.SENT, result.reason)
        self.assertEqual(game.accepted, ["m", "B"])
        self.assertEqual(result.board["_magic_eater_wand_charges"], -1)

    def test_follow_absorption_is_context_and_identity_bound(self):
        board = replace(self.board(wand=True), visible_monsters=[])
        policy = self.policy()
        key = self.choose(policy, board)
        game, result, status = self.run_follow(key, policy.last_reason, [
            prompt("Gain power of which item? ", "item", area="inventory",
                   areas=["inventory", "floor"], menu=False, first_label="b", last_label="b")],
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

    def test_follow_power_and_aim_reject_wrong_context(self):
        bad_power = powers()
        bad_power["input_context"]["kind"] = "item"
        bad_aim = prompt("Direction?", "direction", can_choose_target=False)
        for screens, expected in (([prompt("[A] staff, [B] wand, [C] rod:"), bad_power],
                                   ["m", "B"]),
                                  ([prompt("[A] staff, [B] wand, [C] rod:"), powers(), bad_aim],
                                   ["m", "B", "p"])):
            with self.subTest(expected=expected):
                game, result, status = self.run_follow("mBp6", MISSILE_REASON, screens)
                self.assertEqual(status, SendResult.TERMINAL)
                self.assertEqual(game.accepted, expected)

    def test_follow_absorb_floor_switch_is_observed(self):
        wand = {"slot": "b", "tval": TVAL_WAND, "sval": 15, "known": True,
                "name": "a Wand of Magic Missile (17 charges)", "charges": 17, "count": 1}
        floor = prompt("Gain power of which item? ", "item", area="floor",
                       areas=["floor", "inventory"], menu=False)
        pack = prompt("Gain power of which item? ", "item", area="inventory",
                      areas=["floor", "inventory"], menu=False, first_label="b", last_label="b")
        game, result, status = self.run_follow("Gb", ABSORB_REASON, [floor, pack], inventory=[wand])
        self.assertEqual(status, SendResult.SENT, result.reason)
        self.assertEqual(game.accepted, ["G", "/", "b"])

    def test_follow_absorb_menu_observes_named_device(self):
        wand = {"slot": "b", "tval": TVAL_WAND, "sval": 15, "known": True,
                "name": "a Wand of Magic Missile (17 charges)", "charges": 17, "count": 1}
        first = prompt("Gain power of which item? ", "item", area="inventory", menu=True)
        first["lines"][1:3] = [">  a Staff of Nothing (5 charges)", "   " + wand["name"]]
        second = {**first, "lines": list(first["lines"])}
        second["lines"][1:3] = ["   a Staff of Nothing (5 charges)", ">  " + wand["name"]]
        game, result, status = self.run_follow("Gb", ABSORB_REASON, [first, second], inventory=[wand])
        self.assertEqual(status, SendResult.SENT, result.reason)
        self.assertEqual(game.accepted, ["G", "2", "\r"])

    def test_follow_absorb_rejects_unowned_area(self):
        game, result, status = self.run_follow("Gb", ABSORB_REASON, [
            prompt("Gain power of which item? ", "item", area="equipment", menu=False)])
        self.assertEqual(status, SendResult.TERMINAL)
        self.assertEqual(game.accepted, ["G"])


if __name__ == "__main__":
    unittest.main()
