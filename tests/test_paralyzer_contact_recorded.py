"""D55 (#47): the recorded n1-a life-450 death (2026-10-31 14:47, Labyrinth 16F).

The Lv24 warrior had no Free Action and was waiting on Word of Recall with
12 Teleportation scrolls.  On the last board an アイス・コボルド (race 1112)
stood beside it and a ランゴスタ (race 1252, speed +10, STING/CRUSH
PARALYZE) two cells away.  Both paralyzer rungs read adjacency only, so the
bot meleed the kobold ('6', ``melee``); the locust, two actions per player
action, closed and stung, and the player died paralyzed at HP 213/419
(playrecord 「16階で麻痺状態でランゴスタに殺された」).

Fixture: tests/fixtures/death-n1a-450-1101.json.gz
(tests/extract_deaths_1101_fixtures.py, case n1a-450).  Each decision is the
public ``choose_key``; the posted key goes through the production executor
port, with the capture's last ~f skill reply before each decision.
DECLARED CONSTRUCTED: executor replies
are the same board ten game turns later; the guard cases change only the
locust's speed or take the escape scrolls out of the pack, as each states.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import dataclasses
import gzip
import json
from pathlib import Path
import unittest

from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests.support import recorded as executor_pins
from tests.test_town_decision_speed_caches import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "death-n1a-450-1101.json.gz"
READ_PROMPT = "どの巻物を読みますか? "
WAIT_TURN, DEATH_TURN = 1268495, 1268509
KOBOLD, LANGOSTA = 1112, 1252
SV_TELEPORT = 9


class ParalyzerContactRecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        cls.monraces = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def raw(self, turn, *, scrolls=True, depth=None):
        raw = copy.deepcopy(next(b for b in self.case["boards"] if b["turn"] == turn))
        if depth is not None:
            # DECLARED CONSTRUCTED: the floor's depth (the guard below the shallow rule).
            raw["floor"]["level"] = depth
        if not scrolls:
            raw["inventory"] = [item for item in raw["inventory"]
                                if item.get("tval") != 70]
        return raw

    def decide(self, *, locust_speed=None, scrolls=True, depth=None):
        """Prime on the recorded recall wait, then decide the death board."""
        knowledge = dict(self.monraces)
        if locust_speed is not None:
            knowledge[LANGOSTA] = dataclasses.replace(knowledge[LANGOSTA], speed=locust_speed)
        policy = HengbotPolicy(monrace_knowledge=knowledge)
        policy.prime(parse_snapshot(self.raw(WAIT_TURN, scrolls=scrolls, depth=depth),
                                    knowledge))
        keys = []
        for turn in (WAIT_TURN, DEATH_TURN):
            raw = self.raw(turn, scrolls=scrolls, depth=depth)
            skill = self.case["skill"]
            policy.consume_skill_knowledge(dict(
                copy.deepcopy(skill), turn=raw["turn"],
                player=dict(skill["player"], level=raw["player"]["level"])))
            keys.append(policy.choose_key(parse_snapshot(raw, knowledge)))
            if turn == WAIT_TURN:
                policy.confirm_key_posted(keys[-1])
        return policy, keys

    def post(self, policy, raw, key, prompt):
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=[])
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.prompt_screen(prompt),
                        executor_pins.command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        return game.accepted

    def test_recorded_rows(self):
        rows = {row["turn"]: row for row in self.case["decisions"]}
        self.assertEqual((rows[WAIT_TURN]["key"], rows[WAIT_TURN]["reason"]),
                         ("5", "return:wait-recall"))
        self.assertEqual((rows[DEATH_TURN]["key"], rows[DEATH_TURN]["reason"]), ("6", "melee"))
        board = parse_snapshot(self.raw(DEATH_TURN), self.monraces)
        self.assertTrue(board.player.recalling)
        self.assertNotIn("free_action", board.player.abilities)
        distance = {m.race_id: m.distance for m in board.visible_monsters}
        self.assertEqual(distance, {KOBOLD: 1, LANGOSTA: 2})
        locust = next(m for m in board.visible_monsters if m.race_id == LANGOSTA)
        self.assertEqual((locust.speed, board.player.speed), (120, 110))
        self.assertEqual(sum(item.count for item in board.inventory
                             if (item.tval, item.sval) == (70, SV_TELEPORT)), 12)

    def test_fast_paralyzer_two_cells_away_reads_teleport_through_the_executor(self):
        policy, keys = self.decide()
        self.assertEqual(keys[0], "5")
        raw = self.raw(DEATH_TURN)
        slot = next(item["slot"] for item in raw["inventory"]
                    if (item.get("tval"), item.get("sval")) == (70, SV_TELEPORT))
        self.assertEqual((keys[1], policy.last_reason), ("r" + slot, "status-threat:scroll"))
        self.assertEqual(self.post(policy, raw, keys[1], READ_PROMPT), ["r", slot])

    def test_without_an_escape_scroll_the_fast_paralyzer_is_not_ignored(self):
        policy, keys = self.decide(scrolls=False)
        self.assertNotEqual(policy.last_reason, "melee", keys)
        self.assertTrue(policy.last_reason.startswith(("status-threat:", "threat:paralyzer")),
                        (keys, policy.last_reason))

    def test_equal_speed_paralyzer_two_cells_away_lets_the_fight_finish(self):
        # One action per player action: it can only step beside us, so the
        # adjacent kobold fight continues ("finish the fight already in contact").
        # DECLARED CONSTRUCTED: at the Free Action depth (20F), where the shallow
        # rule of 2026-11-09 does not apply.
        policy, keys = self.decide(locust_speed=110, depth=20)
        self.assertEqual((keys[1], policy.last_reason), ("6", "melee"))

    def test_on_the_recorded_16f_the_equal_speed_paralyzer_is_left_at_sight(self):
        # Owner 2026-11-09 (n1-a life-501) 「浅い階層で見かけたら逃げる」: above 20F the
        # locust in view is left by a Teleportation scroll though it is not in contact.
        policy, keys = self.decide(locust_speed=110)
        raw = self.raw(DEATH_TURN)
        slot = next(item["slot"] for item in raw["inventory"]
                    if (item.get("tval"), item.get("sval")) == (70, SV_TELEPORT))
        self.assertEqual((keys[1], policy.last_reason), ("r" + slot, "shallow-paralyzer:scroll"))


if __name__ == "__main__":
    unittest.main()
