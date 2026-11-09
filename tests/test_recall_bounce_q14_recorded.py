"""n1-b life-306: the Q14 Recall bounce (2026-11-03, build e9e2c1262).

Fixtures: tests/fixtures/recall-bounce-1104.json.gz
(tests/extract_recall_bounce_1104_fixture.py) and the same capture's arrival
checkpoint, town-stops-1103/temple-loop.

Quest 14 (Warg problem, taken, 15 of 16) lives on Yeek cave 5F; floor.quest_id
is 0 there because it has no fixed map, and _active_kill_quest_id matches it by
dungeon and level.  Below five Teleportation scrolls that floor starts the town
return (random_quest_reserve), and the shallow town departure asked for four:
72 landings with 4 scrolls, each read Recall at once (146 Recall scrolls read,
145 bought) until the shops ran out and the visit stopped on
town:blocked:unmet:home_candidate_resolved.  last_return_trigger
random-quest-teleport-reserve was live, not stale.

The town now asks for the reserve, so the round that would bounce is not read.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import STORE_ALCHEMIST, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.quest_knowledge import load_quest_knowledge
from hengbot.random_quest_reserve import RANDOM_QUEST_TELEPORT_RESERVE, RETURN_TRIGGER
from hengbot.town_arrival_checkpoint import POLICY_FILE
from replay_town_arrival import restore
from tests.support import recorded as executor_pins
from tests.test_dungeon_1031_recorded import READ_PROMPT, skill
from tests.test_town_decision_speed_caches import EDIT


FIXTURES = Path(__file__).with_name("fixtures")
TRAVEL_ALCHEMIST = "\x1b`n%."
QUEST_WARG = 14


def with_teleports(raw, count):
    """DECLARED CONSTRUCTED: the recorded board after the purchase it lacked."""
    board = copy.deepcopy(raw)
    next(item for item in board["inventory"]
         if item["tval"] == 70 and item["sval"] == 9)["count"] = count
    return board


class RecallBounceQ14RecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURES / "recall-bounce-1104.json.gz", "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)

    def policy(self):
        """The capture's arrival policy (the character's knowledge and latches)."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        visit = Path(scratch.name) / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress(
            (FIXTURES / "town-stops-1103/temple-loop/policy.pkl.xz").read_bytes()))
        runtime = Path(scratch.name) / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        Path(policy._home_disposal.history_path).unlink(missing_ok=True)
        return policy

    def floor_policy(self, raw):
        """A new process on the landing: no town latch survives into the decision."""
        policy = HengbotPolicy(
            monrace_knowledge=load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc"),
            quest_knowledge=load_quest_knowledge(EDIT / "quests"))
        policy.prime(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        # DECLARED CONSTRUCTED: the ring's ~f reply is not part of the fixture.
        skill(policy, raw)
        return policy

    def decide(self, policy, raw):
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        key = policy.choose_key(board)
        policy.confirm_key_posted(key)
        return str(key), board

    def assert_posts(self, policy, raw, board, key, prompts=()):
        """The production executor posts ``key`` on the recorded board."""
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        # DECLARED CONSTRUCTED: the next board after the command.
        game.screens = [*prompts, executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [dict(copy.deepcopy(raw), turn=raw["turn"] + 10) for _ in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)

    def test_floor_below_the_reserve_returns_on_the_landing(self):
        raw = self.case["landing"]
        recorded = self.case["landing_decision"]
        self.assertEqual((recorded["reason"], recorded["key"]), ("return:recall", "rg"))
        self.assertEqual(raw["floor"]["quest_id"], 0)
        policy = self.floor_policy(raw)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(policy._active_kill_quest_id(board), QUEST_WARG)
        self.assertEqual(policy._count_teleport_scrolls(board),
                         RANDOM_QUEST_TELEPORT_RESERVE - 1)
        key, board = self.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("rg", "return:recall"))
        self.assertEqual(policy._last_return_trigger, RETURN_TRIGGER)
        self.assert_posts(policy, raw, board, key, [executor_pins.prompt_screen(READ_PROMPT)])

    def test_town_buys_the_reserve_before_it_reads_recall(self):
        raw = self.case["town_read"]
        policy = self.policy()
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        teleport = policy._supply_ledger(board, policy._planned_depth())["teleport"]
        self.assertEqual((teleport.count, teleport.required_departure),
                         (4, RANDOM_QUEST_TELEPORT_RESERVE))
        # Recorded on this board: town:recall-to-yeek-cave, 'rgb'.
        key, board = self.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), (TRAVEL_ALCHEMIST, "shop:travel"))
        self.assert_posts(policy, raw, board, key)

        # DECLARED CONSTRUCTED: the recorded Alchemist page in front of this pack.
        page = copy.deepcopy(self.case["alchemist"]["store"])
        self.assertEqual(page["store_type"], STORE_ALCHEMIST)
        shelf = next(item for item in page["items"] if item["tval"] == 70 and item["sval"] == 9)
        at_shop = copy.deepcopy(raw)
        at_shop.update(type="store", store=page, turn=raw["turn"] + 10)
        at_shop["player"].update(y=self.case["alchemist"]["player"]["y"],
                                 x=self.case["alchemist"]["player"]["x"])
        self.decide(policy, at_shop)
        wanted = policy._shop_selector_diagnostics["wanted_purchase"]
        self.assertEqual((wanted["category"], wanted["letter"]), ("teleport", shelf["letter"]))

    def test_at_the_reserve_town_reads_and_the_landing_stays(self):
        policy = self.policy()
        town = with_teleports(self.case["town_read"], RANDOM_QUEST_TELEPORT_RESERVE)
        reasons = []
        for _ in range(3):
            key, _board = self.decide(policy, town)
            reasons.append(policy.last_reason)
            if key == "rgb":
                break
        self.assertEqual(reasons[-1], "town:recall-to-yeek-cave", reasons)

        landing = with_teleports(self.case["landing"], RANDOM_QUEST_TELEPORT_RESERVE)
        policy = self.floor_policy(landing)
        board = parse_snapshot(copy.deepcopy(landing), policy._monrace_knowledge)
        self.assertFalse(policy._should_start_town_return(board))
        self.decide(policy, landing)
        self.assertNotEqual(policy.last_reason, "return:recall")


if __name__ == "__main__":
    unittest.main()
