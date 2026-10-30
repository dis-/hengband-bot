"""D32 / USER DECISION 2026-10-31 「勝てない時は攻撃しない」: town friendlies.

The town hunt attacked friendly uniques the character could not defeat and
then chased them (tests/fixtures/friendly-unbeatable-20261030.json.gz, see
tests/extract_friendly_unbeatable.py):

* n1-b life 268 (warrior Lv7, 85 HP) approached Farmer Maggot (35d10
  FORCE_MAXHP, HIT 1d5) and attacked him ('+2y'); he followed at the same
  speed and the flee steps alternated with ``town:kill-mob-approach`` until
  death.
* n1-c life 34 (Magic-Eater Lv8, 114 HP) did the same ('+3y'); once he was
  angered the hunt re-approached him between flee steps until death.
* n1-c life 10 (Magic-Eater Lv8, 129 HP) attacked the pigeon Poppo ('+4y')
  and was beaten to HP 14 (the D22 stop).

Owner: survival first; a friendly the character cannot defeat (uniques
included) is never attacked by choice, and the character keeps to its errand
when it comes close.  A friendly it can defeat is still hunted.

Each board is decided through the public chooser and the key is posted
through the production executor.  DECLARED RECONSTRUCTED: the policy is the
lv7 harness policy given the recorded board, the recorded skill/home
knowledge rows and the checkpoint's supplier shelves; life 34's fundraising
mode and staff-stockout target come from its checkpoint (as in
tests/test_me_town_stops_recorded.py).  Life 10 ran a build without the
Magic-Eater staff sequence; its fundraising run is given an explicit target
so that sequence yields as the recorded build had none.  The beatable
friendly is CONSTRUCTED from life 268's board (Maggot's race replaced by
race 1320).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path

from hengbot import me_staff_sequence
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.model import Position, parse_snapshot
from tests import test_input_executor as harness
from tests import test_lv7_town_stop_recorded as lv7
from tests.test_input_executor import FaithfulHookGame, command_screen

FIXTURE = Path(__file__).parent / "fixtures" / "friendly-unbeatable-20261030.json.gz"
MAGGOT, POPPO, BEATABLE = 8, 1083, 1320
# Life 10's explicit run target (DECLARED RECONSTRUCTED, module docstring).
LIFE010_RUN_TARGET = 5000
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


class FriendlyUnbeatableRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        lv7.Lv7TownStopRecordedTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)

    def policy(self, life, turn, raw=None):
        case = self.data["cases"][life]
        raw = copy.deepcopy(raw or case["boards"][str(turn)])
        policy, raw = lv7.Lv7TownStopRecordedTest().boundary(dict(
            monraces=self.data["monraces"], snapshot=raw, knowledge=case["knowledge"],
            state={"modes_and_latches": case["modes"]}))
        modes = case["modes"]
        target = (modes["_supply_stockout_gold_target"] if life == "n1-c/life-034"
                  else LIFE010_RUN_TARGET if life == "n1-c/life-010" else None)
        if target is not None:
            policy._fundraising_mode = modes["_fundraising_mode"]
            policy._supply_stockout_gold_target = target
            me_staff_sequence.state(policy).fundraise_target = target
        return policy, raw

    def decide(self, life, turn, raw=None):
        policy, raw = self.policy(life, turn, raw)
        key = policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))
        return policy, raw, key

    def post(self, policy, raw, key):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10)
        game.states = [following]
        game.screens = [command_screen(raw["turn"] + 10)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertIs(port(key, decision={"reason": policy.last_reason,
                                          "sequence": policy._decision_sequence}),
                      SendResult.SENT, port.last_result.reason)
        return game

    @staticmethod
    def monster(raw, race_id):
        return next(row for row in raw["visible_monsters"] if row["race_id"] == race_id)

    def test_recorded_rows_attacked_the_friendly_and_reapproached_it_angered(self):
        rows = {life: case["decisions"] for life, case in self.data["cases"].items()}
        self.assertEqual(rows["n1-b/life-268"]["75256"]["key"], "+2y")
        self.assertEqual(rows["n1-c/life-034"]["151886"]["key"], "+3y")
        self.assertEqual(rows["n1-c/life-010"]["478794"]["key"], "+4y")
        for life, turn in (("n1-b/life-268", 75224), ("n1-c/life-034", 151878),
                           ("n1-c/life-034", 152427), ("n1-c/life-034", 152545)):
            self.assertEqual(rows[life][str(turn)]["reason"], "town:kill-mob-approach")
        board = self.data["cases"]["n1-c/life-034"]["boards"]
        for turn in ("151886", "152427"):
            maggot = self.monster(board[turn], MAGGOT)
            self.assertEqual(maggot["friendly"], turn == "151886")
        self.assertEqual(self.data["monraces"][str(MAGGOT)]["average_hp"], 350)

    def test_unbeatable_friendly_is_neither_attacked_nor_approached(self):
        for life, turn, race in (("n1-b/life-268", 75224, MAGGOT),
                                 ("n1-b/life-268", 75256, MAGGOT),
                                 ("n1-c/life-034", 151878, MAGGOT),
                                 ("n1-c/life-034", 151886, MAGGOT),
                                 ("n1-c/life-010", 478794, POPPO)):
            with self.subTest(life=life, turn=turn):
                policy, raw, key = self.decide(life, turn)
                friendly = self.monster(raw, race)
                self.assertTrue(friendly["friendly"])
                self.assertTrue(policy._town_friendly_unbeatable(
                    parse_snapshot(raw, policy._monrace_knowledge),
                    next(m for m in parse_snapshot(raw, policy._monrace_knowledge)
                         .visible_monsters if m.race_id == race)))
                self.assertIsInstance(key, str)
                self.assertFalse(key.startswith("+"), key)
                self.assertNotEqual(policy.last_reason, "town:kill-mob-friendly")
                self.assertNotEqual(policy._town_hunt_target,
                                    Position(friendly["y"], friendly["x"]))
                game = self.post(policy, raw, key)
                self.assertNotIn("y", "".join(game.accepted)[-1:])

    def test_angered_unbeatable_friendly_is_not_reapproached(self):
        for turn in (152427, 152545):
            with self.subTest(turn=turn):
                policy, raw, key = self.decide("n1-c/life-034", turn)
                maggot = self.monster(raw, MAGGOT)
                self.assertFalse(maggot["friendly"])
                self.assertNotEqual(policy.last_reason, "town:kill-mob-approach")
                here = Position(raw["player"]["y"], raw["player"]["x"])
                there = Position(maggot["y"], maggot["x"])
                self.assertIn(key, DIRECTIONS)
                dy, dx = DIRECTIONS[key]
                after = Position(here.y + dy, here.x + dx)
                self.assertGreater(after.distance_to(there), 1)
                self.post(policy, raw, key)

    def test_beatable_friendly_is_still_hunted(self):
        # CONSTRUCTED (module docstring): the same board with a friendly the
        # warrior can defeat in Maggot's place.
        raw = copy.deepcopy(self.data["cases"]["n1-b/life-268"]["boards"]["75256"])
        row = self.monster(raw, MAGGOT)
        row["race_id"] = BEATABLE
        policy, raw, key = self.decide("n1-b/life-268", 75256, raw)
        self.assertEqual(policy.last_reason, "town:kill-mob-friendly")
        self.assertEqual(key, "+2y")
        game = self.post(policy, raw, key)
        self.assertEqual(game.accepted[0], "+2y")
