"""The loop-detected stops of the 2026-11-04 morning (build 2d4b7645d / b044fd30f).

Every board is decided through the public choose_key on the recorded boards;
a key is posted through the production executor.  Nothing but the marked seeds
is constructed.  Fixtures: tests/extract_loops_1104_fixtures.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path

from hengbot import retreat_enclosure
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position, parse_snapshot
from hengbot.policy_state import normalize_policy_state
from tests import test_input_executor as executor_pins
from tests import test_dungeon_stops_1103_recorded as _test_dungeon_stops_1103_recorded


FIXTURES = Path(__file__).with_name("fixtures") / "loops-1104"
EMPTY_AIR = "何もない空中を攻撃した。"


def fixture(name: str) -> dict:
    return json.loads(lzma.decompress((FIXTURES / name).read_bytes()))


class ItemCommandBoards(_test_dungeon_stops_1103_recorded.RecordedBoards):
    def post_item_command(self, policy, raw: dict, key: str, prompt: str) -> None:
        """Post ``key`` (command, item letter) through the production executor."""
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.prompt_screen(prompt),
                        executor_pins.command_screen(raw["turn"] + 1)]
        game.states = [copy.deepcopy(raw), copy.deepcopy(raw)]
        game.states[-1]["turn"] = raw["turn"] + 1
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge),
            posting_contract=PostingContract(),
        )
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(game.accepted, [key[0], key[1:]])


class BlindStrikeAtAnEmptyCell(ItemCommandBoards):
    """n1-b life-307, 2026-11-04 02:14, Yeek cave 13F (D13).

    Bitten blind by a ヴラスタ, it fought through at the cell north of it, the
    cell of the last sighted board.  That monster died; 「何もない空中を攻撃
    した。」 came back on most of the 40 strikes while unseen attackers took HP
    355 -> 231, and the loop guard stopped the bot.
    """

    def test_empty_air_retires_the_remembered_cell(self):
        case = fixture("blind-air.json.xz")
        policy = self.fresh_policy(case["boards"][0])
        for raw in case["boards"]:
            key = self.decide(policy, raw)
            air = any(EMPTY_AIR in message for message in raw["messages"])
            if raw["turn"] < self.FIRST_AIR_TURN:
                continue
            if raw["turn"] == self.FIRST_AIR_TURN:
                # Nothing remembered and no blow on this board: the cure.
                self.assertTrue(air)
                self.assertEqual((key, policy.last_reason), ("qb", "item:cure-critical"))
                self.post_item_command(policy, raw, key, "どの薬を飲みますか? ")
            elif raw["turn"] == self.AIR_AND_BLOW_TURN:
                # Another attacker's punch: the ヴラスタ's bite that re-blinded
                # the player ended at turn 376137, so the latch has let go.
                self.assertTrue(air)
                self.assertEqual((key, policy.last_reason), ("qb", "item:cure-critical"))
                return
        self.fail("the recorded boards ended early")

    def test_without_a_cure_the_blow_strikes_a_free_neighbour(self):
        # DECLARED CONSTRUCTED: the Cure Critical Wounds taken out after the first
        # cure.  The random free neighbour of owner 2026-10-03, not the retired cell.
        case = fixture("blind-air.json.xz")
        policy = self.fresh_policy(case["boards"][0])
        for raw in case["boards"]:
            if raw["turn"] > 376129:
                raw["inventory"] = [item for item in raw["inventory"]
                                    if item["name"] != "致命傷の治癒の薬"]
            key = self.decide(policy, raw)
            if raw["turn"] == self.AIR_AND_BLOW_TURN:
                self.assertEqual((key, policy.last_reason), ("+1", "unseen:strike-return"))
                return
        self.fail("the recorded boards ended early")

    FIRST_AIR_TURN = 376184
    AIR_AND_BLOW_TURN = 376286


class RetreatVetoesEncloseTheMazePlayer(ItemCommandBoards):
    """n1-a life-476 02:51 (Labyrinth 15F, D15), n1-b life-307 03:18 (18F, D18).

    The floor's retreat vetoes (threat:avoid-engagement, summoner:retreat) held
    every way out of a corridor pocket after the threats had died, and it waited
    with '5' at one cell until the loop guard stopped the bot.  Owner 2026-11-04:
    「一旦テレポートで離脱を試みる。同じフロアで二度同じ形で動けなくなったら帰還。」
    Owner 2026-11-06: 「閉じ込められた時はどちらも、掘る（岩石溶解を含む）・罠の解除・弱い敵を倒す
    を先に試し、駄目ならテレポート、巻物が規定数以下なら帰還。判定を1つにまとめる。」: the ladder of
    retreat_enclosure from its openers (dig, disarm, weak enemy, then Teleportation or Recall at or
    below the reserve, TELEPORT_RETURN_THRESHOLD 3 off a quest floor), with no leading
    Teleportation.  Both boards carry two shovels and a Stone to Mud wand: the dig comes first.
    """

    def without_diggers(self, raw: dict, teleportation: int) -> dict:
        """DECLARED: no shovel and no Stone to Mud, ``teleportation`` scrolls."""
        raw = copy.deepcopy(raw)
        raw["inventory"] = [item for item in raw["inventory"]
                            if item["tval"] != 20 and "岩石溶解" not in item["name"]]
        next(item for item in raw["inventory"] if "テレポートの巻物" in item["name"])["count"] = teleportation
        return raw

    def enclosed(self, case: dict):
        policy = self.fresh_policy(case["boards"][0], case["terrain"])
        # SEEDS: the stop's floor-long vetoes and written-off frontiers.
        policy._claim_engagement_avoid_cells(Position(*cell) for cell in case["avoid"])
        policy._probed_frontiers.update(Position(*cell) for cell in case["probed"])
        # The removed breakout wander (0d46d60d2) never had this step either:
        # the least-visited neighbour refuses the same vetoes.
        snapshot = parse_snapshot(copy.deepcopy(case["boards"][-1]), policy._monrace_knowledge)
        self.assertIsNone(policy._least_visited_neighbor(snapshot))
        return policy

    def enclosed_board(self, name: str, change=None):
        """The stop's board (``change`` applied) decided on the enclosed policy."""
        case = fixture(name)
        policy = self.enclosed(case)
        board = case["boards"][-2]
        if change is not None:
            board = change(board)
        vetoes = set(policy._engagement_owned_avoid_cells)
        key = self.decide(policy, board)
        self.assertTrue(vetoes <= policy._engagement_owned_avoid_cells)  # every veto is kept
        return policy, board, key

    def test_d15(self):
        policy, _board, _key = self.enclosed_board("enclosed-d15.json.xz")
        self.assertEqual(policy.last_reason, retreat_enclosure.DIG_WIELD_REASON)

    def test_d18(self):
        policy, _board, _key = self.enclosed_board("enclosed-d18.json.xz")
        self.assertEqual(policy.last_reason, retreat_enclosure.DIG_WIELD_REASON)

    def test_with_nothing_to_dig_teleportation_is_read_each_time(self):
        policy, board, key = self.enclosed_board(
            "enclosed-d15.json.xz", lambda raw: self.without_diggers(raw, 4))
        self.assertEqual((key[0], policy.last_reason), ("r", retreat_enclosure.TELEPORT_REASON))
        self.post_item_command(policy, board, key, "どの巻物を読みますか? ")
        # The same game turn decided again is the same read (the executor refused it).
        self.assertEqual(self.decide(policy, board), key)
        # A restart keeps the floor's read; enclosed again, Teleportation over the reserve.
        normalize_policy_state(policy, restart=True)
        self.assertIsNotNone(policy._enclosure_teleport_read)
        again = self.without_diggers(fixture("enclosed-d15.json.xz")["boards"][-1], 4)
        self.assertEqual((self.decide(policy, again)[0], policy.last_reason),
                         ("r", retreat_enclosure.TELEPORT_REASON))

    def test_at_the_reserve_recall_is_read(self):
        """At 15F the ordinary supply return (it returns below 4 scrolls) reads the
        Recall above the idle fallback; the ladder's own Recall at the reserve is the
        same _leave_key the walled-off pin reads on the quest floor."""
        policy, board, key = self.enclosed_board(
            "enclosed-d15.json.xz", lambda raw: self.without_diggers(raw, 3))
        self.assertEqual((key[0], policy.last_reason), ("r", "return:recall"))
        self.post_item_command(policy, board, key, "どの巻物を読みますか? ")

    def test_unanswered_hostile_in_view_still_takes_the_enclosure_ladder(self):
        """No rung answered this board (recorded: 'wait', melee on the next board),
        so the enclosure owns it: a hostile in view does not hold the ladder back."""
        case = fixture("enclosed-d18.json.xz")
        raw = case["hostile_in_view"]
        self.assertTrue(raw["visible_monsters"])
        policy = self.enclosed(case)
        self.decide(policy, raw)
        self.assertEqual(policy.last_reason, retreat_enclosure.DIG_REASON)  # the openers first

    def test_no_teleportation_reads_recall(self):
        case = fixture("enclosed-d15.json.xz")
        policy = self.enclosed(case)
        raw = copy.deepcopy(case["boards"][-1])
        kept = [item for item in raw["inventory"] if "テレポートの巻物" not in item["name"]]
        self.assertLess(len(kept), len(raw["inventory"]))
        raw["inventory"] = kept
        # Without Teleportation the ordinary return reads the Recall first.
        key = self.decide(policy, raw)
        self.assertEqual((key[0], policy.last_reason), ("r", "return:recall"))


if __name__ == "__main__":
    unittest.main()
