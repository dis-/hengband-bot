"""#47 D: incident-projected guardian refusal, public policy and follow IO.

All constructed prerequisites are documented beside the projection fixture.
No replay of the truncated snapshots or successful live fix is claimed.
"""
import tests  # noqa: F401
import json
from dataclasses import replace
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import (Snapshot, Position, PLAYER_CLASS_WARRIOR, TVAL_SCROLL,
    SV_SCROLL_WORD_OF_RECALL, SV_SCROLL_TELEPORT, TVAL_POTION,
    SV_POTION_CURE_CRITICAL, TVAL_FOOD, TVAL_FLASK, TVAL_SWORD, TVAL_LITE,
    SV_LITE_LANTERN, TVAL_STAFF, SV_STAFF_IDENTIFY)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import EMPTY_DIVE_LIMIT, RUMOR_COST, RUMOR_GOLD_RESERVE
from policy_fixtures import player, grid, item, set_completed_equipment_optimization
from tests.test_input_executor import ProductionHarness, FaithfulHookGame, command_screen, prompt_screen

FIXTURE = Path(__file__).parent / "fixtures/top-stops-guardian-projection.json"
EDIT = Path("C:/hengband/lib/edit")


class TopStopsGuardianTest(ProductionHarness):
    def scene(self, case=None, *, unlocked=False, landing=1):
        row = (case or json.loads(FIXTURE.read_text(encoding="utf-8"))[0])["decision"]
        actor = row["player"]
        pos = Position(**row["position"])
        # DECLARED CONSTRUCTED: quiet town, inn two steps east, fully supplied
        # worn loadout after town errands, Yeek is the only entered dungeon.
        terrain = {Position(pos.y, x): grid(pos.y, x, building_type=0 if x == pos.x + 2 else -1)
                   for x in range(pos.x, pos.x + 3)}
        board = Snapshot(player(pos.y, pos.x, level=actor["level"], hp=actor["hp"],
            max_hp=actor["max_hp"], gold=actor["gold"], class_id=PLAYER_CLASS_WARRIOR,
            abilities=frozenset(row["depth_safety"]["has"])), terrain, [],
            turn=row["turn"], town_flag=True, town_id=0, recall_dungeon_id=2,
            recall_depth=13, entered_dungeon_ids=(1, 2) if unlocked else (2,),
            dungeon_recall_depths={1: landing, 2: 13} if unlocked or landing != 1 else {2: 13},
            angband_recall_unlocked=unlocked,
            inventory=[item("a", TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, count=10),
                       item("b", TVAL_SCROLL, SV_SCROLL_TELEPORT, count=15),
                       item("c", TVAL_POTION, SV_POTION_CURE_CRITICAL, count=10),
                       item("d", TVAL_FOOD, 35, count=10),
                       item("e", TVAL_FLASK, 0, count=5),
                       item("f", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=20)],
            equipment=[item("main_hand", TVAL_SWORD, 1, is_equipment=True),
                       item("light", TVAL_LITE, SV_LITE_LANTERN, fuel=7500, is_equipment=True)])
        policy = HengbotPolicy(dungeon_knowledge=load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc"))
        policy.prime(board)
        policy.consume_home_knowledge(())
        policy.consume_skill_knowledge({"player": {"level": actor["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]}})
        set_completed_equipment_optimization(policy)
        policy._equipment_optimization_last_depth = 19
        policy._char_dump_done_this_visit = True
        policy._town_store_attempted[6] = board.turn
        policy._target_dungeon_id = 2
        return policy, board

    def send(self, board, key, reason, *, recall=False, rumor=False):
        # DECLARED CONSTRUCTED: source-contract responses, not live captures.
        game = FaithfulHookGame()
        raw = {"turn": board.turn, "grid_map": {"runs": []}}
        game.state = raw
        game.screen = command_screen(board.turn)
        # These existing town macros enter their queued item/building answers
        # atomically. Simulate the next command boundary after consuming them.
        game.capacity = 1024
        game.screens = [command_screen(board.turn + 1)]
        game, _client, executor = self.make(game)
        executor.observe_boundary(deadline=9999999999)
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _posted = _send_new_decision_key(port, "top-stops-D", key, None, set(),
            in_store=False, decision={"sequence": 1, "reason": reason}, snapshot=board,
            posting_contract=PostingContract())
        self.assertTrue(sent)
        self.assertEqual(port.last_result.outcome, "completed", port.last_result.reason)
        self.assertEqual("".join(game.accepted), str(key))
        return game

    def test_public_guardian_refusal_selects_angband_then_rumor_then_recall(self):
        for case in json.loads(FIXTURE.read_text(encoding="utf-8")):
            with self.subTest(source=case["source"]):
                policy, board = self.scene(case)
                self.assertEqual(case["decision"]["reason"], "town:blocked:guardian-bounce-no-alternate")
                self.assertTrue(policy._guardian_floor_blocked(board, 2, 13))
                key = policy.choose_key(board)
                self.assertEqual(policy.last_reason, "town:unsafe-recall-fallback")
                self.assertEqual(policy._alternate_dungeon, 1)
                self.assertTrue(policy._rumor_unlock_pending)
                self.send(board, key, policy.last_reason)
                board = replace(board, turn=board.turn + 1)
                key = policy.choose_key(board)
                self.assertEqual((str(key), policy.last_reason), ("6", "town:rumor"))
                self.assertEqual(policy._target_dungeon_id, 1)
                self.send(board, key, policy.last_reason)
                board = replace(board, turn=board.turn + 1,
                    player=replace(board.player, position=Position(board.player.position.y, board.player.position.x + 1)))
                key = policy.choose_key(board)
                self.assertEqual(policy.last_reason, "town:rumor-batch")
                self.assertEqual(str(key), "6" + "u\r" * 40 + "\x1b")
                self.send(board, key, policy.last_reason, rumor=True)
                # Source-derived unlock: set_max_level(Angband.min_depth) adds
                # Angband to collect_entered_dungeon_ids in dungeon-id order.
                board = replace(board, turn=board.turn + 1, angband_recall_unlocked=True,
                    entered_dungeon_ids=(1, 2), dungeon_recall_depths={1: 1, 2: 13})
                key = policy.choose_key(board)
                self.assertFalse(policy._rumor_unlock_pending)
                self.assertEqual((str(key), policy.last_reason), ("raa", "town:recall-to-angband"))
                self.send(board, key, policy.last_reason, recall=True)

    def test_public_observation_valve_keeps_unentered_angband_target(self):
        policy, board = self.scene()
        # DECLARED CONSTRUCTED: just before the observation valve evaluates
        # the recorded guardian-only streak; no preselected alternate.
        policy._target_empty_dives = EMPTY_DIVE_LIMIT
        policy._guardian_bounce_dives = EMPTY_DIVE_LIMIT
        policy._last_return_trigger = "guardian-kit-insufficient"
        key = policy.choose_key(board)
        self.assertEqual(policy._alternate_dungeon, 1)
        self.assertEqual(policy._target_dungeon_id, 1)
        self.assertEqual(policy.last_reason, "town:rumor")
        self.send(board, key, policy.last_reason)

    def test_public_unlocked_refusal_selects_angband_and_recalls(self):
        policy, board = self.scene(unlocked=True)
        # A pursued alternate survives ordinary Angband selection.
        policy._alternate_dungeon = 2
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:unsafe-recall-fallback")
        self.assertEqual(policy._target_dungeon_id, 1)
        self.assertFalse(policy._rumor_unlock_pending)
        self.send(board, key, policy.last_reason)
        key = policy.choose_key(replace(board, turn=board.turn + 1))
        self.assertEqual(policy.last_reason, "town:recall-to-angband")
        self.send(board, key, policy.last_reason, recall=True)

    def test_public_unsafe_angband_stops_without_rumor_or_repeated_switch(self):
        for landing in (21, 81, 100):
            with self.subTest(landing=landing):
                policy, board = self.scene(landing=landing)
                # TEST_FAKERY_LINT_ALLOW: frozen-drive-state: a named terminal emits only WAIT; advance time without movement to prove the stop remains latched
                for turn in range(3):
                    key = policy.choose_key(replace(board, turn=board.turn + turn))
                    self.assertEqual(policy.last_reason, "town:blocked:guardian-bounce-no-alternate")
                    self.assertIsNone(policy._alternate_dungeon)
                    self.assertFalse(policy._rumor_unlock_pending)
                    self.send(board, key, policy.last_reason)

    def test_public_rumor_funds_use_existing_reserve(self):
        policy, board = self.scene()
        policy.choose_key(board)
        board = replace(board, turn=board.turn + 1,
            player=replace(board.player, gold=RUMOR_GOLD_RESERVE + RUMOR_COST - 1))
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:rumor-needs-funds")
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.send(board, key, policy.last_reason)

    def test_public_forced_departure_releases_block_for_locked_angband_rumor(self):
        policy, board = self.scene()
        policy._town_blocked_reason = "repetition"
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:unsafe-recall-fallback")
        self.assertIsNone(policy._town_blocked_reason)
        self.assertEqual(policy._target_dungeon_id, 1)
        self.send(board, key, policy.last_reason)
        key = policy.choose_key(replace(board, turn=board.turn + 1))
        self.assertEqual(policy.last_reason, "town:rumor")
        self.send(board, key, policy.last_reason)

    def test_public_entered_alternative_keeps_priority_over_angband(self):
        policy, board = self.scene()
        board = replace(board, entered_dungeon_ids=(2, 3), dungeon_recall_depths={2: 13, 3: 10})
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:unsafe-recall-fallback")
        self.assertEqual(policy._target_dungeon_id, 3)
        self.assertFalse(policy._rumor_unlock_pending)
        self.send(board, key, policy.last_reason)

    def test_public_angband_guardian_or_no_melee_landing_stays_stopped(self):
        for change in (dict(max_depth=2, guardian_id=237), dict(flags=frozenset({"NO_MELEE"}))):
            with self.subTest(change=change):
                policy, board = self.scene()
                # DECLARED CONSTRUCTED: isolate each landing veto using the
                # normal static-facts input; no guardian verdict is mocked.
                policy._dungeon_knowledge[1] = replace(policy._dungeon_knowledge[1], **change)
                key = policy.choose_key(board)
                self.assertEqual(policy.last_reason, "town:blocked:guardian-bounce-no-alternate")
                self.assertIsNone(policy._alternate_dungeon)
                self.send(board, key, policy.last_reason)
