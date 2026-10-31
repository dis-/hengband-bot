"""#47 owner answers 1-3 of 2026-10-31 15h (dungeon survival), on recorded boards.

Fixture: tests/fixtures/owner-a-survival-1031.json.gz
(tests/extract_owner_a_survival_fixture.py).  Every decision goes through the
public choose_key and every posted key through the production executor port.

1. 「隣に敵がいても譲る」 (n1-a life-446, 鉄獄48階): with the town return
   latched (emergency-repeat at 1712410) the immobile-summoner avoidance
   meleed the adjacent hostile at 1712931.  The return owner now takes that
   board and reads Recall.
2. 「盲目で治す薬がないときは…見えない敵を攻撃することを試みる方が生存確率は
   上がる。」 (same death): blinded beside the デス・ドレイク it fought at
   [14,81], unseen-recall walked '4' away.  Without a cure it now attacks the
   remembered cell ('+' alter, '6').
3. 「明るいマスへ歩いて帰還を読むが、そもそも光源を切らさない努力が必要」
   (n1-c life-055, 鉄獄1階, every '<' to the wilderness): (b) the burnt-out
   torch was worn while the Brass Lantern {average} and oil were carried; the
   darkness recovery now wears the lantern under the last-resort rule.  (a)
   With no light to restore, the return walks to a lit floor it saw and reads
   Recall there.

DECLARED CONSTRUCTED / RECONSTRUCTED: the captures hold no ~f reply, so the
skill knowledge is supplied before each decision (test_dungeon_1031_recorded).
Item 2 removes the carried Cure Critical Wounds from the blind board (the
recorded board had one; the owner's case has none).  Item 3 sets the return
latched as the recorded return:* reasons show and removes the frontier as
test_dungeon_1031_recorded does; 3(a) removes the lantern and the oil (else
3(b) answers first).  The board after the 3(a) step is the recorded lit-room
board of the turn before, re-stamped ten turns later.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path

from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import WAIT_KEY
from tests import test_input_executor as executor_pins
from tests.test_dungeon_1031_recorded import (
    QUAFF_PROMPT, READ_PROMPT, RecordedHarness, decide,
)
from tests.test_town_decision_speed_caches import EDIT, build_policy

FIXTURE = Path(__file__).with_name("fixtures") / "owner-a-survival-1031.json.gz"
WIELD_PROMPT = "どれを装備しますか? "
DIRECTION_PROMPT = "方向 (ESCで中断)?"
DRAKE_CELL = Position(14, 81)
LIT_ROOM_CELL = Position(19, 114)


class SurvivalHarness(RecordedHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = json.load(stream)
        cls.monraces = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def recorded(self, name):
        return {row["turn"]: row for row in self.cases[name]["decisions"] if row}

    def replay(self, names, stop_turn):
        boards = [board for name in names for board in self.boards(name)]
        policy = HengbotPolicy(monrace_knowledge=dict(self.monraces))
        policy.prime(parse_snapshot(boards[0], policy._monrace_knowledge))
        for raw in boards:
            if raw["turn"] == stop_turn:
                return policy, raw
            decide(policy, raw)
        self.fail(stop_turn)


class LatchedReturnBesideAHostileTest(SurvivalHarness):
    def test_recorded_row(self):
        row = self.recorded("adjacent")[1712931]
        self.assertEqual((row["reason"], row["key"]), ("melee", "9"))

    def test_latched_return_reads_recall_beside_the_adjacent_hostile(self):
        policy, raw = self.replay(("latch", "adjacent"), 1712931)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertTrue(policy._returning_to_town)
        self.assertFalse(board.player.recalling)
        self.assertTrue(any(m.hostile and m.distance <= 1 for m in board.visible_monsters))
        key = decide(policy, raw)
        # Unfixed: ("melee", "9") from the avoidance's adjacent-melee branch.
        self.assertEqual(policy.last_reason, "return:recall")
        recall = next(item for item in board.inventory if item.is_recall_scroll)
        self.assertEqual(key, "r" + recall.slot)
        self.assertEqual(self.post(policy, raw, key, [executor_pins.prompt_screen(READ_PROMPT)],
                                   self.later(raw)), ["r", recall.slot])


class BlindWithoutCureTest(SurvivalHarness):
    def without_cure(self, policy, raw):
        board = parse_snapshot(raw, policy._monrace_knowledge)
        cure = policy._find_status_cure_potion(board)
        self.assertIsNotNone(cure)  # the recorded board carried one
        raw = copy.deepcopy(raw)
        raw["inventory"] = [item for item in raw["inventory"] if item["slot"] != cure.slot]
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertIsNone(policy._find_status_cure_potion(board))
        return raw, board

    def test_recorded_rows(self):
        rows = self.recorded("blind")
        self.assertEqual((rows[1713405]["reason"], rows[1713405]["key"]), ("melee", "6"))
        self.assertEqual((rows[1713414]["reason"], rows[1713414]["key"]),
                         ("unseen-recall:move", "4"))

    def test_blind_without_cure_attacks_the_remembered_attacker(self):
        policy, raw = self.replay(("blind",), 1713414)
        raw, board = self.without_cure(policy, raw)
        self.assertTrue(board.player.blind)
        self.assertTrue(board.player.recalling)
        self.assertEqual(board.visible_monsters, [])
        key = decide(policy, raw)
        # Unfixed: ("unseen-recall:move", "4"), a step away from the drake.
        self.assertEqual((policy.last_reason, key), ("unseen-recall:blind-strike", "+6"))
        self.assertEqual(board.player.position.distance_to(DRAKE_CELL), 1)
        self.assertEqual(self.post(policy, raw, key, [executor_pins.prompt_screen(DIRECTION_PROMPT)],
                                   self.later(raw)), ["+", "6"])

    def test_control_nothing_remembered_stays(self):
        policy, raw = self.replay(("blind",), 1713414)
        raw, _board = self.without_cure(policy, raw)
        policy._blind_strike_memory = None  # DECLARED CONSTRUCTED: never saw it
        # The player stays; at HP 250/703 the low-HP walk gate relabels the
        # same WAIT (emergency:wait).
        self.assertEqual(decide(policy, raw), WAIT_KEY)
        self.assertIn(policy.last_reason, {"unseen-recall:blind-stay", "emergency:wait"})

    def test_control_cure_carried_is_quaffed_first(self):
        policy, raw = self.replay(("blind",), 1713414)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        key = decide(policy, raw)
        cure = policy._find_status_cure_potion(board)
        self.assertEqual((policy.last_reason, key), ("item:cure-critical", "q" + cure.slot))
        self.assertEqual(self.post(policy, raw, key, [executor_pins.prompt_screen(QUAFF_PROMPT)],
                                   self.later(raw)), ["q", cure.slot])


class DarkWildernessExitFloorTest(SurvivalHarness):
    def policy(self, raw):
        policy = build_policy()
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        policy._returning_to_town = True  # DECLARED RECONSTRUCTED
        policy._explore_step = lambda snapshot: None  # DECLARED RECONSTRUCTED
        policy._floor_key = parse_snapshot(raw, policy._monrace_knowledge).floor_key
        return policy

    @staticmethod
    def without_light(raw):
        raw = copy.deepcopy(raw)  # DECLARED CONSTRUCTED: no lantern, no oil
        raw["inventory"] = [item for item in raw["inventory"]
                            if "ランタン" not in item["name"] and "油" not in item["name"]]
        return raw

    def test_recorded_rows(self):
        # The stop board has no decision row of its own; the stop's log shows
        # return:search-upstairs 's' on the stair (LUNA-REPORT-fix-dungeon-1031).
        room = self.cases["dark-room"]["decisions"]
        self.assertEqual([(row["reason"], row["key"]) for row in room],
                         [("return:seek-secret-wall", "1"), ("dark:backtrack", "7")])

    def test_dark_stair_wears_the_carried_average_lantern(self):
        raw = self.boards("dark-stair")[0]
        policy = self.policy(raw)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertFalse(policy._can_read_scrolls(board))
        self.assertTrue(policy._up_stairs_exit_to_wilderness())
        worn = next(item for item in board.equipment if item.is_light)
        self.assertEqual((worn.is_torch, worn.fuel), (True, 0))
        lantern = next(item for item in board.inventory if item.is_lantern)
        self.assertEqual((lantern.known, lantern.pseudo_feeling), (False, "average"))
        key = decide(policy, raw)
        # Unfixed: ("return:search-upstairs", "s") in the dark for 114 boards.
        self.assertEqual((policy.last_reason, key), ("wield-light", "w" + lantern.slot))
        self.assertEqual(self.post(policy, raw, key, [executor_pins.prompt_screen(WIELD_PROMPT)],
                                   self.later(raw)), ["w", lantern.slot])
