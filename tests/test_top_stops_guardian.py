"""#47 D: incident-projected guardian refusal, public policy and follow IO.

All constructed prerequisites are documented beside the projection fixture.
No replay of the truncated snapshots or successful live fix is claimed.
"""
import tests  # noqa: F401
import json
from dataclasses import replace
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot import guardian_rumor
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import (Snapshot, Position, QuestState, PLAYER_CLASS_WARRIOR, TVAL_SCROLL,
    SV_SCROLL_WORD_OF_RECALL, SV_SCROLL_TELEPORT, TVAL_POTION,
    SV_POTION_CURE_CRITICAL, TVAL_FOOD, TVAL_FLASK, TVAL_SWORD, TVAL_LITE,
    SV_LITE_LANTERN, TVAL_STAFF, SV_STAFF_IDENTIFY)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import (EMPTY_DIVE_LIMIT, QUEST_STATUS_FINISHED, RUMOR_COST,
    RUMOR_GOLD_RESERVE, WAIT_KEY, required_depth_gates)
from policy_fixtures import player, grid, item, set_completed_equipment_optimization
import tests.support.recorded as executor_harness
from tests.support.recorded import FaithfulHookGame, command_screen

FIXTURE = Path(__file__).parent / "fixtures/top-stops-guardian-projection.json"
EDIT = Path("C:/hengband/lib/edit")
# DECLARED CONSTRUCTED: the projected life-363 board with quest rows and Q2 not
# among them, the state in which 11-05 shuts Angband (random_quest_hold).
BEFORE_Q2 = {34: QuestState(34, status=QUEST_STATUS_FINISHED)}
AFTER_Q2 = {**BEFORE_Q2, 2: QuestState(2, status=QUEST_STATUS_FINISHED)}


class TopStopsGuardianTest(executor_harness.ProductionHarness):
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
                for turn in range(3):
                    key = policy.choose_key(board)
                    self.assertEqual(policy.last_reason, "town:blocked:guardian-bounce-no-alternate")
                    self.assertIsNone(policy._alternate_dungeon)
                    self.assertFalse(policy._rumor_unlock_pending)
                    self.assertEqual(str(key), WAIT_KEY)
                    game = self.send(board, key, policy.last_reason)
                    # Apply the WAIT effect confirmed by follow: time advances,
                    # the position stays put, and the named stop stays latched.
                    board = replace(board, turn=game.state["turn"])

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

    def test_public_angband_takes_priority_over_entered_alternative(self):
        # CHANGED 2026-11-07 by owner decision 「鉄獄の帰還の階が条件を満たすなら
        # 鉄獄へ行き、だめな時だけほかのダンジョンから選ぶ。」 (was: the entered
        # Orc cave kept priority over Angband, owner 2026-10-27).  Angband's
        # rumor-opened landing (its entry floor 1) passes, so the valve takes it.
        policy, board = self.scene()
        board = replace(board, entered_dungeon_ids=(2, 3), dungeon_recall_depths={2: 13, 3: 10})
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:unsafe-recall-fallback")
        self.assertEqual(policy._target_dungeon_id, 1)
        self.assertTrue(policy._rumor_unlock_pending)
        self.send(board, key, policy.last_reason)

    def test_public_entered_alternative_when_angband_is_shut(self):
        # The old choice stays when Angband does not pass: here it is shut
        # before Q2 (random_quest_hold, DECLARED CONSTRUCTED quest rows).
        policy, board = self.scene()
        board = replace(board, entered_dungeon_ids=(2, 3), dungeon_recall_depths={2: 13, 3: 10},
                        quests=BEFORE_Q2)
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:unsafe-recall-fallback")
        self.assertEqual(policy._target_dungeon_id, 3)
        self.assertFalse(policy._rumor_unlock_pending)
        self.send(board, key, policy.last_reason)

    def test_public_angband_guardian_or_no_melee_landing_stays_stopped(self):
        # The landing (1) is the guardian floor when it is the last floor (owner 2026-11-11
        # C2: the floor above the guardian floor is explored, not refused).
        for change in (dict(max_depth=1, guardian_id=237), dict(flags=frozenset({"NO_MELEE"}))):
            with self.subTest(change=change):
                policy, board = self.scene()
                # DECLARED CONSTRUCTED: isolate each landing veto using the
                # normal static-facts input; no guardian verdict is mocked.
                policy._dungeon_knowledge[1] = replace(policy._dungeon_knowledge[1], **change)
                key = policy.choose_key(board)
                self.assertEqual(policy.last_reason, "town:blocked:guardian-bounce-no-alternate")
                self.assertIsNone(policy._alternate_dungeon)
                self.send(board, key, policy.last_reason)

    def test_public_forced_departure_other_alternative_keeps_its_recall(self):
        policy, board = self.scene()
        # DECLARED CONSTRUCTED: Angband shut before Q2, so the guardian valve's
        # choice is the entered Orc cave (owner 2026-11-07 asks Angband first).
        board = replace(board, entered_dungeon_ids=(2, 3), dungeon_recall_depths={2: 13, 3: 10},
                        quests=BEFORE_Q2)
        policy._town_blocked_reason = "repetition"
        # DECLARED CONSTRUCTED: an older quest rumor request is still pending;
        # it must not make a different guardian alternate release departure.
        policy._rumor_unlock_pending = True
        key = policy.choose_key(board)
        self.assertEqual(policy._target_dungeon_id, 3)
        self.assertEqual(policy.last_reason, "town:repetition-depart:recall")
        self.send(board, key, policy.last_reason, recall=True)

    def bounced_before_q2(self):
        """Owner 2026-11-05 「噂で別のダンジョンを開く」: the board, armed by its first key."""
        policy, board = self.scene()
        board = replace(board, quests=BEFORE_Q2)
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:unsafe-recall-fallback")
        self.assertIsNone(policy._alternate_dungeon)
        self.assertEqual(policy._target_dungeon_id, 2)
        self.assertTrue(guardian_rumor.pending(policy))
        self.send(board, key, policy.last_reason)
        return policy, replace(board, turn=board.turn + 1)

    @staticmethod
    def opened(board, *rows):
        """Source-derived: a rumor sets max_level to min_depth, listed in id order."""
        depths = {**board.dungeon_recall_depths, **dict(rows)}
        return replace(board, turn=board.turn + 1, entered_dungeon_ids=tuple(sorted(depths)),
            dungeon_recall_depths=depths, angband_recall_unlocked=1 in depths)

    @staticmethod
    def moved(board, dx, **player):
        here = board.player.position
        return replace(board, turn=board.turn + 1, player=replace(board.player,
            position=Position(here.y, here.x + dx), **player))

    def test_before_q2_bounce_reads_rumors_until_a_dungeon_opens_then_recalls_there(self):
        policy, board = self.bounced_before_q2()
        key = policy.choose_key(board)
        self.assertEqual((str(key), policy.last_reason), ("6", "town:rumor"))
        self.send(board, key, policy.last_reason)
        board = self.moved(board, 1)
        key = policy.choose_key(board)
        self.assertEqual((str(key), policy.last_reason), ("6" + "u\r" * 40 + "\x1b", "town:rumor-batch"))
        self.send(board, key, policy.last_reason, rumor=True)
        # The batch opened nothing the pick takes: the character stands on the
        # inn, and two more batches run although only its gold has changed.
        for batch in range(2):
            board = self.moved(board, 1, gold=board.player.gold - RUMOR_COST * 40)
            key = policy.choose_key(board)
            self.assertEqual((str(key), policy.last_reason), ("4", "town:entrance-step-off:town:rumor"))
            self.send(board, key, policy.last_reason)
            board = self.moved(board, -1)
            key = policy.choose_key(board)
            self.assertEqual(policy.last_reason, "town:rumor-batch", batch)
            self.send(board, key, policy.last_reason, rumor=True)
        self.assertEqual(policy._target_dungeon_id, 2)
        board = self.opened(board, (3, 10))
        key = policy.choose_key(board)
        self.assertFalse(guardian_rumor.pending(policy))
        self.assertEqual(policy._alternate_dungeon, 3)
        self.assertEqual(policy._target_dungeon_reason, guardian_rumor.TARGET_REASON)
        self.assertEqual((str(key), policy.last_reason), ("rab", "town:recall-to-alt-dungeon"))
        self.send(board, key, policy.last_reason, recall=True)

    def test_before_q2_angband_forest_or_chameleon_opening_keeps_reading(self):
        for dungeon, depth in ((1, 1), (7, 15), (18, 30)):
            with self.subTest(dungeon=dungeon):
                policy, board = self.bounced_before_q2()
                board = self.opened(self.moved(board, 1), (dungeon, depth))
                key = policy.choose_key(board)
                self.assertTrue(guardian_rumor.pending(policy))
                self.assertIsNone(policy._alternate_dungeon)
                self.assertEqual(policy._target_dungeon_id, 2)
                self.assertEqual(policy.last_reason, "town:rumor-batch")
                self.send(board, key, policy.last_reason, rumor=True)

    def test_before_q2_without_funds_the_set_opens_once_and_stops_nowhere(self):
        policy, board = self.bounced_before_q2()
        board = self.moved(board, 1, gold=RUMOR_GOLD_RESERVE + RUMOR_COST - 1)
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:rumor-needs-funds")
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.send(board, key, policy.last_reason)
        # The funds wait does not reopen the shops that could not sell the kit.
        policy._town_store_attempted[6] = board.turn
        board = replace(board, turn=board.turn + 1)
        policy.choose_key(board)
        self.assertIn(6, policy._town_store_attempted)
        # DECLARED CONSTRUCTED: the shops of the kit's plan were visited and could
        # not sell it.  The cycle break settles the set instead of the funds wait.
        board = replace(board, turn=board.turn + 1)
        policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:rumor-needs-funds")
        for store in policy._town_errand_plan.stops:
            policy._town_store_attempted[store] = board.turn
        policy._retire_town_errand_plan_for_rebuild()
        board = replace(board, turn=board.turn + 1)
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "fundraise:fallback-exhausted-plan")
        self.assertEqual(str(key), WAIT_KEY)
        self.assertTrue(guardian_rumor.pending(policy))
        self.send(board, key, policy.last_reason)

    def test_before_q2_the_gold_a_set_earned_is_read_at_once(self):
        policy, board = self.bounced_before_q2()
        policy._fundraising_mode = "prepare"
        board = self.moved(board, 1, gold=RUMOR_GOLD_RESERVE + RUMOR_COST * 2)
        key = policy.choose_key(board)
        self.assertEqual((str(key), policy.last_reason), ("6" + "u\r" * 2 + "\x1b", "town:rumor-batch"))

    def test_before_q2_supplies_do_not_hold_the_reads(self):
        policy, board = self.bounced_before_q2()
        policy._town_departure_ready = lambda _snapshot: False
        key = policy.choose_key(board)
        self.assertEqual((str(key), policy.last_reason), ("6", "town:rumor"))

    def test_before_q2_forced_departure_is_released_for_the_reads(self):
        policy, board = self.scene()
        board = replace(board, quests=BEFORE_Q2)
        policy._town_blocked_reason = "repetition"
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:unsafe-recall-fallback")
        self.assertIsNone(policy._town_blocked_reason)
        self.send(board, key, policy.last_reason)
        key = policy.choose_key(replace(board, turn=board.turn + 1))
        self.assertEqual(policy.last_reason, "town:rumor")

    def test_before_q2_observation_valve_arms_the_reads_instead_of_the_stop(self):
        policy, board = self.scene()
        policy._target_empty_dives = EMPTY_DIVE_LIMIT
        policy._guardian_bounce_dives = EMPTY_DIVE_LIMIT
        key = policy.choose_key(replace(board, quests=BEFORE_Q2))
        self.assertTrue(guardian_rumor.pending(policy))
        self.assertIsNone(policy._town_blocked_reason)
        self.assertEqual(policy.last_reason, "town:rumor")
        self.assertEqual(str(key), "6")

    def test_before_q2_no_dungeon_left_to_open_stays_the_visible_stop(self):
        # DECLARED CONSTRUCTED: every other dungeon a rumor can open is refused by
        # the static facts, so no read can help.
        policy, board = self.scene()
        for did in (3, 4, 12, 14):
            policy._dungeon_knowledge[did] = replace(
                policy._dungeon_knowledge[did], flags=frozenset({"NO_MELEE"}))
        board = replace(board, quests=BEFORE_Q2)
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:blocked:guardian-bounce-no-alternate")
        self.assertFalse(guardian_rumor.pending(policy))
        self.assertEqual(str(key), WAIT_KEY)
        self.send(board, key, policy.last_reason)

    def test_before_q2_rumors_cannot_open_a_dungeon_entered_deeper_than_30(self):
        # DECLARED CONSTRUCTED: with every ability a deeper dungeon's landing would
        # be taken, but the inn's rumor never reads a dungeon entered below 30F.
        policy, board = self.scene()
        for did in (3, 4, 12, 14):
            policy._dungeon_knowledge[did] = replace(
                policy._dungeon_knowledge[did], flags=frozenset({"NO_MELEE"}))
        board = replace(board, quests=BEFORE_Q2, player=replace(board.player, abilities=frozenset(
            required_depth_gates(49))))
        policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:blocked:guardian-bounce-no-alternate")

    def test_before_q2_a_landing_the_kit_may_not_arrive_on_is_not_worth_reading_for(self):
        # DECLARED CONSTRUCTED: left are the Castle (20F) and the Mountain (25F),
        # and the character has none of the abilities their landings require.
        policy, board = self.scene()
        for did in (3, 4):
            policy._dungeon_knowledge[did] = replace(
                policy._dungeon_knowledge[did], flags=frozenset({"NO_MELEE"}))
        board = replace(board, quests=BEFORE_Q2,
            player=replace(board.player, abilities=frozenset()))
        policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:blocked:guardian-bounce-no-alternate")

    def test_before_q2_the_reads_are_only_settled_in_town(self):
        # DECLARED CONSTRUCTED: the mining set's floor, on a kit that reads passable.
        policy, board = self.bounced_before_q2()
        policy._guardian_fight_viable = lambda _snapshot, _info: True
        policy.choose_key(replace(board, town_flag=False, floor_key=(2, 1, 0)))
        self.assertTrue(guardian_rumor.pending(policy))

    def test_before_q2_reads_end_in_the_stop_when_nothing_is_left_to_open(self):
        policy, board = self.bounced_before_q2()
        for did in (3, 4, 12, 14):
            policy._dungeon_knowledge[did] = replace(
                policy._dungeon_knowledge[did], flags=frozenset({"NO_MELEE"}))
        policy.choose_key(board)
        self.assertFalse(guardian_rumor.pending(policy))
        self.assertEqual(policy.last_reason, "town:blocked:guardian-bounce-no-alternate")

    def test_before_q2_no_way_to_the_inn_is_the_visible_stop(self):
        # DECLARED CONSTRUCTED: no route from the goal search.
        policy, board = self.bounced_before_q2()
        policy._nearest_goal_step = lambda _snapshot, _predicate: None
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:blocked:guardian-bounce-no-alternate")
        self.assertFalse(guardian_rumor.pending(policy))
        self.send(board, key, policy.last_reason)

    def test_q2_resolved_ends_the_reads_for_angband(self):
        policy, board = self.bounced_before_q2()
        policy.choose_key(replace(board, quests=AFTER_Q2))
        self.assertFalse(guardian_rumor.pending(policy))
        self.assertEqual(policy._alternate_dungeon, 1)
        self.assertTrue(policy._rumor_unlock_pending)

    def test_a_passable_guardian_ends_the_reads(self):
        policy, board = self.bounced_before_q2()
        policy._guardian_fight_viable = lambda _snapshot, _info: True
        policy.choose_key(board)
        self.assertFalse(guardian_rumor.pending(policy))
        self.assertEqual(policy._target_dungeon_id, 2)
