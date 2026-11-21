"""Quest 25 on n1-b life-413 (2026-11-22 01:47-01:48): the KILL_ALL patrol lost the quylthulg it detected, recorded.

n1-b life-413 (Magic-Eater Lv37, Zombie, build bot-28c801fdd) on Quest 25 『幽霊屋敷』, every phase of
the plan over (battle phase 11, ``q25-battle.json``), the quest still TAKEN (``progress.quests``
status 1, type 6 KILL_ALL: quest-completion-checker.cpp complete_kill_all wins it only on the death
of the last hostile).  The one hostile left was a Nexus quylthulg (480, monster index 1:
MonraceDefinitions NEVER_MOVE, INVISIBLE, EMPTY_MIND, BLINK and TELE_AWAY; no telepathy shows it,
Detect Evil neither -- it is not evil).  The tome (557) was already dead: the absorbed Rod of
Detection at turn 2581392 listed the quylthulg, the Druj and the stair mimic, no tome.

 * Turn 2585615 the patrol cast the Rod of Detection; the board of turn 2585620 listed the
   quylthulg at [5,17] and the patrol stepped toward it once (``quest-patrol:hunt`` '9').  A
   detection marks a monster for that board only, so from turn 2585625 on the patrol walked its
   round elsewhere (``quest-patrol:walk``).
 * The rod list was displayed charging at turn 2586235 and stayed the remembered one: the
   detections of turns 2587075, 2587878 and 2588757 were the Staff of Detect Evil (``mAp``), which
   never shows the quylthulg.  The fifth round ended in ``quest:blocked:quest-patrol-rounds`` at
   turn 2589517.

The fixes (kill_all_patrol): the cell a hostile was last seen or detected at is walked to
(``_remember`` / ``_hunt_remembered``), forgotten when reached empty and the detection asked
again; a rod list remembered charging from an earlier turn is browsed again (``bC``, no game time)
before the round's detection falls back to Detect Evil (``_rod_read_key``).

Recorded: tests/fixtures/n1b-413-q25-patrol-1122.json.gz
(tests/extract_n1b_413_q25_patrol_1122_fixture.py): the boards and decisions of turns
2585591-2589517 and the battle record at the stop.  A fresh policy restores the record through the
real path and decides the recorded boards in order through the public ``choose_key``.

DECLARED RECONSTRUCTED: the remembered magic-eater lists (the boards do not carry them), the rows
of test_n1c_208_q25_patrol_1115_recorded.lists; the battle record's turn set to the first replayed
board's.  DECLARED CONSTRUCTED: the patrol memory set before a decided board (a lost target beside
the player; the round's detection due) where the replay's own rounds differ from the process's.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import kill_all_patrol, me_powers_refresh, quest25_battle as battle
from hengbot.me_absorbed_substitutes import CAST_SUFFIX
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.model import parse_snapshot
from tests.support import q25_house as q25
from tests.support import recorded as harness
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests.test_me_powerful_activation import racial_screen
from tests.test_n1c_208_q25_patrol_1115_recorded import lists

with gzip.open(Path(__file__).with_name("fixtures") / "n1b-413-q25-patrol-1122.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

CAST = 2585615          # the patrol's cast of the absorbed Rod of Detection
FOUND = 2585620         # the board listing the quylthulg at [5,17]
LOST = 2585625          # the next board: nothing listed, the patrol walked elsewhere
EVIL_ONLY = 2587075     # a round's detection: the Staff of Detect Evil (the rod list stale)
STOP = 2589517
QUYL, QUYL_INDEX, QUYL_CELL = 480, 1, (5, 17)
OWNED = kill_all_patrol.DETECT_REASON + CAST_SUFFIX
POWERED = getattr(kill_all_patrol, "POWERED_DETECT_REASON", kill_all_patrol.DETECT_REASON + ":powerful")
TYPE_PROMPT = "[A] 杖, [B] 魔法棒, [C] ロッド:"


def boards():
    seen, unique = set(), []
    for raw in CASE["window"]["boards"]:
        if raw["turn"] not in seen:
            seen.add(raw["turn"])
            unique.append(raw)
    return unique


def board(turn):
    return copy.deepcopy(next(raw for raw in boards() if raw["turn"] == turn))


def recorded(turn):
    return [(row["reason"], row["key"]) for row in CASE["window"]["decisions"] if row["turn"] == turn]


def decide(policy, raw):
    return policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))


class _Replay(harness.ProductionHarness):
    def setUp(self):
        super().setUp()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def replay(self, last, device_lists=None):
        """(policy, [(turn, reason, key)]) of the recorded boards ``CAST``..``last``."""
        first = board(CAST)
        record = dict(CASE["battle_record"], turn=first["turn"])   # DECLARED (module note)
        (self.directory / "q25-battle.json").write_text(json.dumps(record), encoding="utf-8")
        policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                    quest_strategies=q25.STRATEGIES)
        policy._q25_battle_record_path = self.directory / "q25-battle.json"
        policy._warning_cell_record_path = self.directory / "warning-cells.json"
        snapshot = parse_snapshot(copy.deepcopy(first), policy._monrace_knowledge)
        policy.prime(snapshot)
        policy._skill_exp_cache = (0, 0, snapshot.player.level, policy._town_visit_epoch)
        policy._me_device_lists = device_lists if device_lists is not None else lists()
        decided = []
        for raw in boards():
            if CAST <= raw["turn"] <= last:
                key = decide(policy, raw)
                decided.append((raw["turn"], policy.last_reason, key))
        return policy, decided


class TheRecordingTest(_Replay):
    def test_the_quest_is_still_taken_and_one_quylthulg_is_left(self):
        stop = board(STOP)
        quest = next(row for row in stop["progress"]["quests"] if row["id"] == 25)
        self.assertEqual((quest["status"], quest["type"]), (1, 6))   # TAKEN, KILL_ALL
        found = board(FOUND)["detected_monsters"]
        self.assertEqual([(row["race_id"], row["index"], row["y"], row["x"]) for row in found],
                         [(QUYL, QUYL_INDEX, *QUYL_CELL)])
        self.assertEqual(board(LOST)["detected_monsters"], [])
        self.assertEqual(stop["visible_monsters"], [])
        self.assertEqual(stop["detected_monsters"], [])
        fight = CASE["battle_record"]["battle"]
        self.assertEqual(fight["phase"], len(battle.PHASES))
        self.assertIn(557, fight["gone"]["set"])

    def test_the_recorded_chain(self):
        self.assertEqual(recorded(CAST), [(OWNED, "mCg")])
        self.assertEqual(recorded(FOUND), [(kill_all_patrol.HUNT_REASON, "9")])
        self.assertEqual(recorded(LOST), [(kill_all_patrol.WALK_REASON, "6")])
        self.assertEqual(recorded(EVIL_ONLY), [(OWNED, "mAp")])
        self.assertEqual(recorded(STOP), [(kill_all_patrol.STOP_REASON, "5")])
        races = {row["race_id"] for raw in boards() if raw["turn"] > FOUND
                 for row in (*raw["visible_monsters"], *raw["detected_monsters"])}
        self.assertNotIn(QUYL, races)


class TheHuntTest(_Replay):
    def test_the_detected_quylthulg_is_walked_to_after_the_detection_board(self):
        """The board after the detection lists nothing; the patrol walks on toward [5,17]."""
        policy, decided = self.replay(2585700)
        by_turn = {turn: (reason, key) for turn, reason, key in decided}
        self.assertEqual(by_turn[FOUND], (kill_all_patrol.HUNT_REASON, "9"))
        for turn in (LOST, 2585629, 2585664, 2585700):
            self.assertEqual(by_turn[turn][0], kill_all_patrol.HUNT_REASON, turn)
        self.assertEqual(policy._kill_all_patrol.targets, {QUYL_INDEX: QUYL_CELL})

    def test_a_cell_reached_empty_is_forgotten_and_the_detection_asked_again(self):
        policy, _decided = self.replay(FOUND)
        patrol = policy._kill_all_patrol
        raw = board(LOST)
        here = (raw["player"]["y"], raw["player"]["x"])
        patrol.targets = {QUYL_INDEX: (here[0] - 1, here[1])}   # DECLARED (module note)
        patrol.detected_round = patrol.round
        key = decide(policy, raw)
        self.assertEqual(patrol.targets, {})
        self.assertEqual((policy.last_reason, key), (POWERED, "UCg"))


class TheRodReadTest(_Replay):
    @staticmethod
    def charging_lists(turn):
        """The rod list as displayed at ``turn``: 全感知 charging (the recorded 2586235 list)."""
        rods = lists(rod_charging=1)
        return {"rod": (turn, rods["rod"][1]), "staff": rods["staff"]}

    def test_a_rod_list_shown_charging_earlier_is_read_again(self):
        policy, _decided = self.replay(FOUND)
        patrol = policy._kill_all_patrol
        patrol.targets = {}
        patrol.detected_round = patrol.round - 1   # DECLARED (module note): the detection due
        policy._me_device_lists = self.charging_lists(2586235)
        key = decide(policy, board(EVIL_ONLY))
        self.assertEqual((policy.last_reason, key), (me_powers_refresh.REFRESH_REASON, "bC"))
        # The list read on this board shows the rod ready: the rod is cast, not Detect Evil.
        ready = lists()
        policy._me_device_lists = {"rod": (EVIL_ONLY, ready["rod"][1]), "staff": ready["staff"]}
        key = decide(policy, board(EVIL_ONLY))
        self.assertEqual((policy.last_reason, key), (POWERED, "UCg"))

    def test_a_rod_list_read_this_turn_charging_falls_back_to_the_staff(self):
        policy, _decided = self.replay(FOUND)
        patrol = policy._kill_all_patrol
        patrol.targets = {}
        patrol.detected_round = patrol.round - 1
        policy._me_device_lists = self.charging_lists(EVIL_ONLY)
        key = decide(policy, board(EVIL_ONLY))
        self.assertEqual((policy.last_reason, key), (OWNED, "mAp"))


class ThePoweredDetectionTest(_Replay):
    """Owner 2026-11-22 「全感知の強力発動ならクエスト全域をカバーできるはずだが」 (with 2026-11-01
    「安全なら強力発動で使う」): the round's detection is the rod through Powerful Activation, its
    radius 45 (cmd-zaprod.cpp:50) over the whole house."""

    def test_the_recorded_cast_is_powered_and_posted(self):
        policy, decided = self.replay(CAST)
        self.assertEqual(decided, [(CAST, POWERED, "UCg")])
        raw = board(CAST)
        game = harness.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = harness.command_screen(raw["turn"])
        game.screens = [racial_screen(raw["player"]["level"]), prompt(TYPE_PROMPT),
                        power_screen("rod", [("g", "全感知", 0, 1, 7)]),
                        harness.command_screen(FOUND)]
        game.states = [copy.deepcopy(board(FOUND)) for _ in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        result = port("UCg", decision={"reason": policy.last_reason,
                                       "sequence": policy._decision_sequence})
        self.assertEqual(result, SendResult.SENT, port.last_result.reason)
        self.assertEqual(game.accepted, ["U", "b", "C", "g"])

    def test_unsafe_the_plain_cast(self):
        with mock.patch("hengbot.me_powerful_activation.pays_safely", return_value=False):
            _policy, decided = self.replay(CAST)
        self.assertEqual(decided, [(CAST, OWNED, "mCg")])

    def test_a_hostile_in_view_is_shot_not_detected(self):
        """「安全なら」: no detection is chosen with a hostile known (the hunt answers first)."""
        _policy, decided = self.replay(FOUND)
        self.assertEqual(decided[-1][1], kill_all_patrol.HUNT_REASON)


if __name__ == "__main__":
    import unittest
    unittest.main()
