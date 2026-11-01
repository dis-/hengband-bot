"""#47 D62: the recorded n1-c life-098 Q2 reward (Feanorian lamp) left in Telmora.

Decision 2520 (2026-11-01 20:08, turn 1283380) reported Q2 at the Telmora
castle with ``fixedquest:claim`` ``9q<ESC>``.  market/building-quest.cpp
castle_quest set REWARDED and asked for the town to be rebuilt;
floor/wild.cpp wilderness_gen placed object 582 on the '!' cell (22,42)
([EQU $QUEST2 3], lib/edit/towns/02_Telmora.jsonc) and then set FINISHED,
so the next board shows status 4 and 「フェアノールのランプ {未鑑定}」 one
step away.  The bot never picked it up: the Magic-Eater staff sequence, the
first non-emergency town owner, walked to the inn and took it to the
Outpost (me-staff:return-outpost, ``3ma``), and the town level with the
lamp was gone.

Every decision below goes through the public chooser and is posted through
the production executor port.  The claim board, the reported board and the
knowledge rows are recorded (tests/extract_q2_reward_lamp_fixture.py); the
replies to the keys posted after the reported board are constructed (marked).
"""
import tests  # noqa: F401

import copy
import gzip
import io
import json
import time
from pathlib import Path

from hengbot import me_staff_sequence
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain, _transport_key,
)
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import Position, _parse_items, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from hengbot.town_maps import find_town_map, parse_town_map
import tests.test_input_executor as executor_harness
from tests.test_input_executor import FaithfulHookGame, command_screen

FIXTURE = Path(__file__).with_name("fixtures") / "q2-reward-lamp-20261101.json.gz"
GAME = Path("C:/hengband")
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
LAMP_CELL = (22, 42)
LAMP_NAME = "フェアノールのランプ {未鑑定}"
CLAIM_KEY = "9q\x1b"


class Q2RewardLampRecordedTest(executor_harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        cls.monrace = load_monrace_knowledge(GAME / "lib/edit/MonraceDefinitions.jsonc")
        cls.maps = {n - 1: parse_town_map(find_town_map(n, GAME)) for n in range(1, 6)}

    def policy(self):
        policy = HengbotPolicy(
            town_map=self.maps[0], town_maps=self.maps, monrace_knowledge=self.monrace,
            dungeon_knowledge=load_dungeon_knowledge(GAME / "lib/edit/DungeonDefinitions.jsonc"),
            baseitem_costs=load_baseitem_costs(GAME / "lib/edit/BaseitemDefinitions.jsonc"),
            quest_knowledge=load_quest_knowledge(find_quest_definitions(GAME / "bot-client/state.jsonl")),
            quest_strategies=load_quest_strategies(Path(__file__).resolve().parents[1] / "strategy/quests"),
        )
        policy._in_store_ops_enabled = True
        policy.prime(parse_snapshot(copy.deepcopy(self.case["claim_board"]), self.monrace))
        for row in self.case["knowledge"]:
            if row["knowledge"]["category"] == "skill_exp":
                policy.consume_skill_knowledge(row)
            else:
                policy.consume_home_knowledge(_parse_items(row["knowledge"]["items"], protocol=3))
        # DECLARED CONSTRUCTED: this process had read the game's staff power
        # list long before (me_staff_sequence.read_powers, #47).
        me_staff_sequence.state(policy).powers_read = True
        return policy

    def post(self, policy, raw, key, following):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        game.screen = command_screen(raw["turn"])
        game.screens = [command_screen(following["turn"])]
        game.states = [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "q2-reward-lamp-replay", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(raw, self.monrace),
            posting_contract=PostingContract(), in_store=False)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")
        # A native travel key is posted as its tunnel macro trigger (cli.TRAVEL_MACRO_TRIGGERS).
        self.assertEqual(game.accepted, [_transport_key(key, True)])

    def decide(self, policy, raw):
        return str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.monrace)))

    @staticmethod
    def reply(raw, key):
        """DECLARED CONSTRUCTED: the engine's reply to a posted step or pickup."""
        following = copy.deepcopy(raw)
        following["turn"] += 10
        here = (raw["player"]["y"], raw["player"]["x"])
        if key in DIRECTIONS:
            dy, dx = DIRECTIONS[key]
            following["player"]["y"], following["player"]["x"] = here[0] + dy, here[1] + dx
        elif key == "g" and here == LAMP_CELL:
            # cmd-pickup: the object leaves the cell for the first free slot
            # (base item 582: tval 39, sval 2, weight 60; not yet identified).
            grid = following["grid_map"]
            grid["cells"] = [cell for cell in grid["cells"]
                             if not (cell.get("o") and (cell["y"], cell["x"]) == LAMP_CELL)]
            for name in ("found_items", "found_item_names", "found_item_ids"):
                grid[name] = [row for row in grid[name] if tuple(row[:2]) != LAMP_CELL]
            slots = {item["slot"] for item in following["inventory"]}
            following["inventory"].append(dict(
                slot=next(c for c in "abcdefghijklmnopqrstuvw" if c not in slots),
                name=LAMP_NAME, tval=39, sval=2, count=1, weight=60, aware=True,
                known=False, fully_known=False, is_equipment=True, known_flags=[],
                inscription="", pval=0, to_h=0, to_d=0, to_a=0, ac=0,
                damage_dice=dict(num=1, sides=1), is_artifact=False, is_ego=False,
                is_cursed=False, is_broken=False, is_bounty=False, charges=0, charging=False))
        else:
            raise AssertionError(("no constructed reply", key))
        return following

    def reported(self):
        """The claim board decides the recorded claim; its reply is recorded."""
        policy = self.policy()
        key = self.decide(policy, self.case["claim_board"])
        self.assertEqual((key, policy.last_reason), (CLAIM_KEY, "fixedquest:claim"))
        reported = copy.deepcopy(self.case["reported_board"])
        self.post(policy, self.case["claim_board"], key, reported)
        return policy, reported

    def test_recorded_decisions(self):
        decisions = {row["sequence"]: row for row in self.case["decisions"]}
        self.assertEqual((decisions[2520]["reason"], decisions[2520]["key"]),
                         ("fixedquest:claim", CLAIM_KEY))
        self.assertEqual(decisions[2521]["loot"]["visible"],
                         [{"position": {"y": 22, "x": 42}, "count": 1, "unsafe": False, "distance": 1}])
        # The walk passed the lamp at distance 1 and took the inn.
        self.assertEqual(decisions[2553]["position"], {"y": 23, "x": 42})
        self.assertEqual((decisions[2566]["reason"], decisions[2566]["key"]),
                         ("me-staff:return-outpost", "3ma"))
        self.assertEqual(decisions[2567]["inventory"], {"used": 21, "free": 2})
        board = parse_snapshot(copy.deepcopy(self.case["reported_board"]), self.monrace)
        self.assertEqual(board.quests[2].status, 4)
        self.assertEqual(board.grid_at(Position(*LAMP_CELL)).object_count, 1)
        self.assertEqual(self.case["reported_board"]["grid_map"]["found_item_names"],
                         [[22, 42, LAMP_NAME]])

    def test_reward_owner_holds_the_board_after_the_report(self):
        policy, reported = self.reported()
        key = self.decide(policy, reported)
        # Recorded: town-progress-invariant:...me-staff:return-outpost.
        self.assertIn("fixedquest:reward", policy.last_reason)
        self.assertNotIn("me-staff", policy.last_reason)
        self.assertEqual(policy._fixed_quest_reward_pending, 2)
        self.post(policy, reported, key, self.reply(reported, key))

    def test_lamp_is_picked_up_before_leaving_telmora(self):
        policy, raw = self.reported()
        reasons = []
        for _ in range(6):
            key = self.decide(policy, raw)
            reasons.append((key, policy.last_reason))
            following = self.reply(raw, key)
            self.post(policy, raw, key, following)
            raw = following
            if key == "g":
                break
        # The pack keeps 2 of 23 slots free, under the 4 the town walk
        # reserves for implicit pickups; the reward cell is an explicit pickup.
        self.assertEqual(len(self.case["reported_board"]["inventory"]), 21)
        self.assertEqual(reasons[-1], ("g", "fixedquest:reward-pickup"), reasons)
        self.assertTrue(all(reason.startswith("fixedquest:reward") for _, reason in reasons), reasons)
        board = parse_snapshot(copy.deepcopy(raw), self.monrace)
        self.assertIn(LAMP_NAME, [item.name for item in board.inventory])
        # The next board belongs to the other town owners again.
        self.decide(policy, raw)
        self.assertIsNone(policy._fixed_quest_reward_pending)
        self.assertFalse(policy.last_reason.startswith("fixedquest:reward"), policy.last_reason)


if __name__ == "__main__":
    import unittest
    unittest.main()
