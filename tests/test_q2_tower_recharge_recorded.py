"""Q2 Stone to Mud recharge at Morivant's Tower (owner 2026-10-31).

Owner: 「Q2の岩石溶解 - 回数を数える」 and 「モリバントの塔で充填」.  n1-a life-422
(a Lv-high warrior, 2026-10-30) carried one Stone to Mud wand with one charge
for the five-wall Q2 breach corridor.  With the charge count the Q2 carry is
unmet; the wand's base pval is 12, so one recharge-all at the Tower of
Sorcery (building 8) meets it.  Recorded boards (tests/fixtures/
quest-stops-20261030.json.gz, q2 section): the Telmora board approaching the
Q2 request and the last Outpost board before the inn trip to Telmora.  Both
now take the inn teleport to Morivant (Morivant is already listed, the purse
holds the Tower's whole-pack total and both fares).

The Tower leg reuses the recorded Morivant board beside the Tower of the D24
capture (tests/fixtures/me-tower-recharge-20261030.json.gz): DECLARED
CONSTRUCTED, its pack, equipment, player and quest progress are replaced by
the life-422 Telmora board's.  Replies to posted keys are constructed from
building_recharge_all (market/building-recharger.cpp).  Every decision goes
through the public chooser and the production executor port.
"""

import tests  # noqa: F401 -- isolate runtime files

import copy
import gzip
import io
import json
from pathlib import Path
import time

from hengbot import morivant_tower, q2_tower_recharge
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import SV_WAND_STONE_TO_MUD, TVAL_WAND, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STORE_BLACK, STORE_GENERAL, TOWN_TELEPORT_COST
from hengbot.policy_types import SupplyStatus
from unittest.mock import patch
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from hengbot.town_maps import find_town_map, parse_town_map
from tests import test_input_executor as executor_pins
from tests.test_me_tower_recharge_recorded import recharge_all_screens

GAME = Path("C:/hengband")
ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).with_name("fixtures")
REASON = q2_tower_recharge.REASON


class Q2TowerRechargeRecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURES / "quest-stops-20261030.json.gz", "rt", encoding="utf-8") as stream:
            cls.q2 = json.load(stream)["q2"]
        with gzip.open(FIXTURES / "me-tower-recharge-20261030.json.gz", "rt", encoding="utf-8") as stream:
            cls.me = json.load(stream)
        cls.monraces = load_monrace_knowledge(GAME / "lib/edit/MonraceDefinitions.jsonc")
        cls.maps = {n - 1: parse_town_map(find_town_map(n, GAME)) for n in range(1, 6)}

    def policy(self, raw):
        """The production construction (cli.py main): every town map."""
        policy = HengbotPolicy(
            town_map=self.maps[0], town_maps=self.maps, monrace_knowledge=self.monraces,
            dungeon_knowledge=load_dungeon_knowledge(GAME / "lib/edit/DungeonDefinitions.jsonc"),
            baseitem_costs=load_baseitem_costs(GAME / "lib/edit/BaseitemDefinitions.jsonc"),
            quest_knowledge=load_quest_knowledge(GAME / "lib/edit/quests"),
            quest_strategies=load_quest_strategies(ROOT / "strategy/quests"))
        policy._in_store_ops_enabled = True
        policy._crossarea_fundraising_enforced = True
        board = parse_snapshot(copy.deepcopy(raw), self.monraces)
        policy.prime(board)
        # DECLARED RECONSTRUCTED: the capture keeps no Home page or skill reply.
        policy.consume_home_knowledge(())
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        return policy

    def decide(self, policy, raw):
        return str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.monraces)))

    def post(self, policy, raw, key, following, screens=()):
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [*screens, executor_pins.command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw) for _ in screens] + [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "q2-tower-recharge", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(copy.deepcopy(raw), self.monraces),
            posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertFalse(game.term_fifo)
        policy.confirm_key_posted(key)
        return game

    @staticmethod
    def wand(raw):
        return next(it for it in raw["inventory"]
                    if it["tval"] == TVAL_WAND and it["sval"] == SV_WAND_STONE_TO_MUD)

    @staticmethod
    def moved(raw, key):
        """DECLARED CONSTRUCTED: the reply to one walk step (turn only)."""
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        return following

    def tower_board(self):
        tower = copy.deepcopy(self.me["approach"])
        source = self.q2["board"]
        for name in ("inventory", "equipment", "progress"):
            tower[name] = copy.deepcopy(source[name])
        tower["player"] = dict(copy.deepcopy(source["player"]),
                               y=tower["player"]["y"], x=tower["player"]["x"])
        return tower

    def recharge_reply(self, raw):
        """DECLARED CONSTRUCTED from building_recharge_all: every staff to its
        base pval, every wand stack to number * base pval, one payment."""
        following = copy.deepcopy(self.me["recharged"])
        following["turn"] = raw["turn"] + 10
        for name in ("inventory", "equipment", "progress"):
            following[name] = copy.deepcopy(raw[name])
        following["player"] = dict(copy.deepcopy(raw["player"]),
                                   y=following["player"]["y"], x=following["player"]["x"])
        total = morivant_tower.recharge_cost(parse_snapshot(copy.deepcopy(raw), self.monraces))
        definitions = morivant_tower.device_definitions()
        for item in following["inventory"]:
            if item["tval"] not in (55, 65):
                continue
            full = definitions[(item["tval"], item["sval"])][0] * (
                item["count"] if item["tval"] == 65 else 1)
            item["name"] = item["name"].replace(f"({item['charges']}回分)", f"({full}回分)")
            item["charges"] = item["pval"] = full
        following["player"]["gold"] = raw["player"]["gold"] - total
        following["messages"] = [f"＄{total} で再充填しました。"]
        return following, total

    def test_recorded_short_wand_boards_travel_to_morivant(self):
        for name in ("board", "outpost_board"):
            with self.subTest(board=name):
                raw = self.q2[name]
                self.assertEqual(self.wand(raw)["charges"], 1)
                policy = self.policy(raw)
                board = parse_snapshot(copy.deepcopy(raw), self.monraces)
                self.assertTrue(morivant_tower.morivant_unlocked(board))
                self.assertGreaterEqual(board.player.gold, morivant_tower.expedition_cost(board, 0))
                key = self.decide(policy, raw)
                self.assertEqual(policy.last_reason.removesuffix("-step-off"),
                                 REASON + "travel-morivant")
                self.post(policy, raw, key, self.moved(raw, key))

    def test_magic_eater_keeps_its_own_owners(self):
        raw = copy.deepcopy(self.q2["board"])
        raw["player"]["class_id"] = PLAYER_CLASS_MAGIC_EATER
        policy = self.policy(raw)
        self.decide(policy, raw)
        self.assertFalse(policy.last_reason.startswith(REASON), policy.last_reason)

    def test_short_purse_outside_the_outpost_returns_for_funds(self):
        # DECLARED CONSTRUCTED: the recorded Telmora board below the
        # expedition total (whole-pack Tower price and both fares).
        raw = copy.deepcopy(self.q2["board"])
        board = parse_snapshot(copy.deepcopy(raw), self.monraces)
        raw["player"]["gold"] = morivant_tower.expedition_cost(board, 0) - 1
        policy = self.policy(raw)
        self.decide(policy, raw)
        self.assertEqual(policy.last_reason.removesuffix("-step-off"),
                         REASON + "return-for-funds")

    def test_tower_recharges_the_whole_pack_then_returns_to_the_outpost(self):
        raw = self.tower_board()
        policy = self.policy(raw)
        board = parse_snapshot(copy.deepcopy(raw), self.monraces)
        total = morivant_tower.recharge_cost(board)
        # Stone to Mud (12-1)*30, Identify staffs (21-7)*40 + (21-6)*80 + (21-4)*40.
        self.assertEqual(total, 330 + 560 + 1200 + 680)
        key = self.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("1ay\x1b", q2_tower_recharge.RECHARGE_ALL_REASON))
        following, paid = self.recharge_reply(raw)
        game = self.post(policy, raw, key, following, recharge_all_screens(paid))
        self.assertEqual(game.accepted, ["1", "a", "y", " ", "\x1b"])
        self.assertEqual(self.wand(following)["charges"], 12)
        key = self.decide(policy, following)
        self.assertEqual(policy.last_reason.removesuffix("-step-off"), REASON + "return-outpost")
        self.assertGreaterEqual(following["player"]["gold"], TOWN_TELEPORT_COST)
        self.post(policy, following, key, self.moved(following, key))

    def test_full_wand_in_the_outpost_takes_the_ordinary_q2_travel(self):
        # DECLARED CONSTRUCTED: the recorded Outpost board with the wand as
        # the Tower leaves it; the trip is over and the Q2 travel resumes.
        raw = copy.deepcopy(self.q2["outpost_board"])
        wand = self.wand(raw)
        wand["name"] = wand["name"].replace("(1回分)", "(12回分)")
        wand["charges"] = wand["pval"] = 12
        policy = self.policy(raw)
        q2_tower_recharge.state(policy).active = True
        self.decide(policy, raw)
        self.assertFalse(policy.last_reason.startswith(REASON), policy.last_reason)
        self.assertFalse(q2_tower_recharge.state(policy).active)
        self.assertTrue(policy.last_reason.startswith("fixedquest:q2-travel"), policy.last_reason)

    def test_short_wand_breach_is_not_abandoned_while_the_tower_can_fill_it(self):
        # DECLARED CONSTRUCTED: every wall_breach supplier visited without stock.
        raw = self.q2["board"]
        policy = self.policy(raw)
        board = parse_snapshot(copy.deepcopy(raw), self.monraces)
        empty = SupplyStatus("utility_tools.wall_breach", 0, 1, 1, False,
                             (STORE_BLACK, STORE_GENERAL))
        with patch.object(policy, "_quest_carry_obtainability", return_value=empty):
            policy._abandon_unobtainable_quest_carries(board, policy.approved_quest_strategy(2))
        self.assertNotIn("utility_tools.wall_breach", policy._abandoned_quest_carry_requirements)
