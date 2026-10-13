"""An in-flight Home census only consumes its own producer's decisions."""
import tests  # noqa: F401

import copy
from dataclasses import replace
import gzip
import json
import unittest

from hengbot.model import (
    parse_snapshot, TVAL_SCROLL, SV_SCROLL_ENCHANT_WEAPON_TO_HIT, STORE_HOME,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO
from hengbot.claim_ladder import rung_named, TOWN_RANK
from policy_fixtures import (
    item, seed_character_calibration, seed_confirmed_loadout,
    set_completed_equipment_optimization,
)
from tests.test_home_withdraw_moved_address import board, wares, LATER, BESIDE
import tests.test_policy_equipment as equipment_fixture
from tests.test_quest_travel_progress import QuestTravelFixtureMixin
from tests.test_quest_enter_approach_progress import INCIDENT, TURNS
import tests.test_reward_approach_progress as reward_fixture
from tests.test_travel_interrupted_store_await import EMPTY_KEY_INCIDENT, TRAVEL


class HomeScanOwnerPriorityTest(QuestTravelFixtureMixin, unittest.TestCase):
    def assert_unspent_scan(self, policy, epoch):
        self.assertTrue(policy._home_knowledge_scan_inflight)
        self.assertEqual(policy._home_knowledge_scan_epoch, epoch)
        self.assertEqual(policy._home_knowledge_scan_wait_decisions, 0)

    def test_launcher_enchant_runs_while_scan_is_inflight(self):
        captured = equipment_fixture.LauncherEnchantTest._captured_procurement_snapshot()
        launcher = next(it for it in captured.equipment if it.is_launcher)
        hit = item("a", TVAL_SCROLL, SV_SCROLL_ENCHANT_WEAPON_TO_HIT,
                   name="Enchant Weapon To-Hit")
        first = replace(captured, inventory=[hit], equipment=[launcher])
        policy = HengbotPolicy()
        seed_character_calibration(policy, first)
        set_completed_equipment_optimization(policy)
        seed_confirmed_loadout(policy, first)
        key = policy.choose_key(first)
        self.assertEqual(key, "~9\x1b\x1b")
        policy.confirm_key_posted(key)
        epoch = policy._home_knowledge_scan_epoch
        key = policy.choose_key(first)
        self.assertEqual((str(key), policy.last_reason),
                         ("rac", "town:enchant-launcher-tohit"))
        self.assert_unspent_scan(policy, epoch)

    def test_quest_inn_travel_runs_while_scan_is_inflight(self):
        policy = self._policy()
        with INCIDENT.open(encoding="utf-8") as stream:
            progress = next(raw["progress"] for raw in map(json.loads, stream)
                            if raw.get("type") == "player_turn" and raw.get("turn") == TURNS[0])
        # The entrance fixture supplies the taken-q22 progress value; the
        # stage-1 fixture supplies the independent town/inn travel boards.
        records = self._records()
        first_raw = copy.deepcopy(records[0][1])
        first_raw["progress"] = copy.deepcopy(progress)
        first = parse_snapshot(first_raw, self.monrace)
        policy.prime(first)
        policy.confirm_key_posted(policy.choose_key(first))
        seen_inflight_route = False
        for _number, raw, _line in records[2:8]:
            current = copy.deepcopy(raw)
            current["progress"] = copy.deepcopy(progress)
            key = policy.choose_key(parse_snapshot(current, self.monrace))
            if policy._home_knowledge_scan_inflight:
                self.assertEqual(policy.last_reason, "fixedquest:q22-travel")
                self.assertTrue(str(key))
                self.assertNotEqual(key, HOME_KNOWLEDGE_MACRO)
                self.assert_unspent_scan(policy, policy._home_knowledge_scan_epoch)
                seen_inflight_route = True
            policy.confirm_key_posted(key)
        self.assertTrue(seen_inflight_route)

    def test_reward_route_and_pickup_run_while_scan_is_inflight(self):
        policy = self._policy()
        boards = reward_fixture.RewardApproachProgressPins._boards(self)
        policy.confirm_key_posted(policy.choose_key(parse_snapshot(boards[0], self.monrace)))
        epoch = policy._home_knowledge_scan_epoch
        current = copy.deepcopy(boards[1])
        for offset in range(30):
            key = policy.choose_key(parse_snapshot(current, self.monrace))
            self.assert_unspent_scan(policy, epoch)
            self.assertNotEqual(key, HOME_KNOWLEDGE_MACRO)
            policy.confirm_key_posted(key)
            if policy.last_reason == "fixedquest:reward-pickup":
                self.assertEqual(str(key), "g")
                break
            self.assertEqual(policy.last_reason, "fixedquest:reward-approach")
            current = reward_fixture.RewardApproachProgressPins._advance(
                current, key, current["turn"] + 10)
        else:
            self.fail("reward pickup was not reached")

    def test_pending_store_travel_runs_while_scan_is_inflight(self):
        with gzip.open(EMPTY_KEY_INCIDENT, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        policy = HengbotPolicy(monrace_knowledge=self.monrace)
        policy.prime(parse_snapshot(rows[0], self.monrace))
        key = policy.choose_key(parse_snapshot(rows[0], self.monrace))
        self.assertEqual(key, "~9\x1b\x1b")
        policy.confirm_key_posted(key)
        epoch = policy._home_knowledge_scan_epoch
        key = policy.choose_key(parse_snapshot(rows[1], self.monrace))
        self.assertEqual((str(key), policy.last_reason), (TRAVEL, "shop:travel"))
        self.assert_unspent_scan(policy, epoch)

    def test_only_home_work_awaits_without_movement_or_repost(self):
        policy = HengbotPolicy()
        policy._fundraising_mode = "prepare"
        policy.prime(board(turn=100, at=BESIDE))
        policy._shopping_approach_store_type = STORE_HOME
        policy._home_pending_item = policy._item_signature(wares()[LATER])
        key = policy.choose_key(board(turn=101))
        self.assertEqual(key, HOME_KNOWLEDGE_MACRO)
        policy.confirm_key_posted(key)
        epoch = policy._home_knowledge_scan_epoch
        for count in range(1, 4):
            key = policy.choose_key(board(turn=101 + count))
            self.assertEqual((str(key), policy.last_reason),
                             ("", "home:scan-await-observation"))
            self.assertEqual(policy._home_knowledge_scan_wait_decisions, count)
            self.assertEqual(policy._home_knowledge_scan_epoch, epoch)
            self.assertTrue(policy._home_knowledge_scan_inflight)
            self.assertFalse(policy.confirm_key_posted(key))

    def test_home_sequence_holder_answers_at_its_router_rung(self):
        rung = rung_named("_home_full_knowledge_key")
        self.assertIsNotNone(rung)
        self.assertEqual((rung.family, rung.rank), ("home-scan", TOWN_RANK))
        policy = HengbotPolicy()
        policy._crossarea_fundraising_enforced = True
        policy._fundraising_mode = "prepare"
        policy.prime(board(turn=100, at=BESIDE))
        policy._shopping_approach_store_type = STORE_HOME
        policy._home_pending_batch = [policy._item_signature(wares()[LATER])]
        key = policy.choose_key(board(turn=101))
        self.assertEqual(key, HOME_KNOWLEDGE_MACRO)
        policy.confirm_key_posted(key)
        self.assertTrue(policy._home_sequence_has_holder())
        epoch = policy._home_knowledge_scan_epoch
        for count in (1, 2):
            key = policy.choose_key(board(turn=101 + count))
            self.assertEqual((str(key), policy.last_reason),
                             ("", "home:scan-await-observation"))
            self.assertEqual(policy._claim_register.current.owner.value, "home-scan")
            self.assertEqual(policy._home_knowledge_scan_wait_decisions, count)
            self.assertEqual(policy._home_knowledge_scan_epoch, epoch)
