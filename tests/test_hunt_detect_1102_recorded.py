"""The Magic-Eater searches for the hunted random-quest target by detection
(hunt_target, me_powers "hunt-target-unseen").

Owner 2026-11-02: 「ランダムクエスト討伐対象やガーディアンを討伐するとき、対象が
邪悪なら邪悪感知を用いて探すロジックが欲しい」 and 「全感知を使うケースは対象が
邪悪であることに拘らない」.

Boards, decision rows, the absorption record and the floor's earlier power uses
are recorded (tests/fixtures/hunt-detect-1102.json.gz, see
tests/extract_hunt_detect_1102_fixture.py):
 - snitch-24f: n1-c life-103, Angband 24F, RANDOM quest 41, target
   『金のスニッチ』 (race 1329, not EVIL) never in sight; turn 2408201, decision
   12584 recorded ``explore``; the nearest earlier detect-all (powerful, 45) is
   48 away.  The floor ended in livelock:exhausted.
 - senior-12f: n1-c life-098, Angband 12F, RANDOM quest 43, target
   鬼殺隊の『先輩』 (race 1164, EVIL) out of sight; turn 1171515; the only
   earlier Detect Evil within 30 is the before-rest cast at (16,97), turn
   1135238.  The floor ended in livelock:exhausted.
All go through the public choose_key and the production executor.

DECLARED CONSTRUCTED: the absorbed Rod of Detection's list row (the displayed
rod list, ``_me_device_lists``, as test_me_detection_rod_1101_recorded); the
senior-12f floor memory without its one old use at (16,97) for the cast case;
the replies to the posted keys (cmd-action/cmd-racial.cpp,
cmd-item/cmd-magiceat.cpp) and the detected target on the following board
(spells-detection.cpp marks it for one player turn).
"""
import tests  # noqa: F401 -- isolate live runtime files

from collections import Counter
import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot import hunt_target, me_powers
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.me_staff_sequence import MeStaffSequence
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from tests.support import recorded as harness
from tests.support.recorded import FaithfulHookGame, command_screen
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests.test_me_powerful_activation import racial_screen

FIXTURE = Path(__file__).parent / "fixtures" / "hunt-detect-1102.json.gz"
TYPE_PROMPT = "[A] 杖, [B] 魔法棒, [C] ロッド:"
DETECTION = "全感知"
POWERFUL_DETECTION = "UCg"
DETECT_EVIL_KEY = "mAp"


def rod_row(charging=0):
    return {"name": DETECTION, "charging": charging, "max": 1, "fail": 20, "success": 80}


class HuntDetectRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        cls.races = {}
        for key, facts in cls.data["monraces"].items():
            facts = copy.deepcopy(facts)
            for name in ("flags", "abilities"):
                facts[name] = frozenset(facts[name])
            facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
            cls.races[int(key)] = MonraceKnowledge(**facts)

    def case(self, name):
        return self.data["cases"][name]

    def policy(self, name, *, rod=None, keep=lambda use: True):
        case = self.case(name)
        raw = copy.deepcopy(case["board"])
        policy = HengbotPolicy(monrace_knowledge=dict(self.races))
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        policy._me_staff_sequence = MeStaffSequence(absorbed=dict(case["absorbed"]))
        if rod is not None:
            policy._me_device_lists = {"rod": (raw["turn"], (rod,))}
        memory = me_powers.FloorMemory(tuple(case["floor"]), raw["turn"], failed=Counter())
        memory.uses = [
            me_powers.Use(tuple(use["served"]), tuple(use["used"]), use["trigger"],
                          Position(*use["position"]), use["turn"], use["reason"], use["key"])
            for use in case["uses"] if keep(use)]
        policy._me_power_floor = memory
        return policy, raw

    def choose(self, policy, raw):
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        return policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))

    def post(self, policy, raw, key, screens, *, following):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [*screens, command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        return game, port.last_result.board

    def following(self, raw, *, detected=()):
        board = dict(copy.deepcopy(raw), turn=raw["turn"] + 10)
        board["detected_monsters"] = list(detected)
        return board

    def snitch(self, raw, y, x):
        """The target as detect_all shows it (a detected, unseen monster)."""
        return {"index": 77, "race_id": 1329, "y": y, "x": x, "hp": 1, "max_hp": 1,
                "distance": max(abs(y - raw["player"]["y"]), abs(x - raw["player"]["x"])),
                "friendly": False, "pet": False, "speed": 130, "name": "『金のスニッチ』"}

    # -- non-evil target: detect-all whatever the target ----------------------

    def test_recorded_snitch_board(self):
        case = self.case("snitch-24f")
        row = next(row for row in case["rows"] if row["turn"] == case["board"]["turn"])
        self.assertEqual((row["decision_sequence"], row["reason"]), (12584, "explore"))
        raw = case["board"]
        self.assertEqual((raw["player"]["level"], raw["player"]["hp"], raw["floor"]["quest_id"]),
                         (30, 430, 41))
        self.assertFalse(any(monster["race_id"] == 1329 for monster in
                             raw["visible_monsters"] + raw["detected_monsters"]))
        self.assertNotIn("EVIL", self.races[1329].flags)

    def test_non_evil_target_with_detection_casts_detect_all_then_walks_to_it(self):
        policy, raw = self.policy("snitch-24f", rod=rod_row())
        key = self.choose(policy, raw)
        self.assertEqual((key, policy.last_reason),
                         (POWERFUL_DETECTION, "me-power:hunt-target-unseen:detect-all:powerful"))
        # (21,59): a cell of the recorded explore walk (turn 2408406), beyond
        # the ground this board has explored: the walk goes to the frontier.
        shown = self.snitch(raw, 21, 59)
        following = self.following(raw, detected=[shown])
        game, board = self.post(policy, raw, key, [
            racial_screen(raw["player"]["level"]), prompt(TYPE_PROMPT),
            power_screen("rod", [("g", DETECTION, 0, 1, 20)])], following=following)
        self.assertEqual(game.accepted, ["U", "b", "C", "g"])
        # The shown cell is walked to, also after the mark falls (next board).
        # West along row 16 toward its frontier (16,65), not the explore walk.
        self.assertEqual(self.choose(policy, board), "4")
        self.assertEqual(policy.last_reason, hunt_target.REASON)
        use = policy._me_power_floor.uses[-1]
        self.assertEqual((use.served, use.used, use.trigger),
                         (("rod", 6), ("rod", 6), "hunt-target-unseen"))
        self.assertEqual(policy._hunt_target_memory.position, Position(shown["y"], shown["x"]))
        later = self.following(board)
        self.assertEqual(self.choose(policy, later), "4")
        self.assertEqual(policy.last_reason, hunt_target.REASON)

    def test_non_evil_target_without_detection_is_unchanged(self):
        # The absorbed Detect Evil does not reveal the snitch: the recorded
        # explore (its step depends on the explore path, not restored here).
        policy, raw = self.policy("snitch-24f")
        self.choose(policy, raw)
        self.assertEqual(policy.last_reason, "explore")

    def test_detect_all_within_its_powerful_radius_is_not_recast(self):
        # A powerful detect-all 45 cells away keeps it; 44 away does not.
        raw = self.case("snitch-24f")["board"]
        here = Position(raw["player"]["y"], raw["player"]["x"])
        for distance, expected in ((44, "explore"), (45, "me-power:hunt-target-unseen:detect-all:powerful")):
            with self.subTest(distance=distance):
                policy, raw = self.policy("snitch-24f", rod=rod_row())
                policy._me_power_floor.uses.append(me_powers.Use(
                    ("rod", 6), ("rod", 6), "hunt-target-unseen",
                    Position(here.y, here.x + distance), raw["turn"] - 5,
                    "me-power:hunt-target-unseen:detect-all:powerful", POWERFUL_DETECTION))
                self.choose(policy, raw)
                self.assertEqual(policy.last_reason, expected)

    # -- EVIL target: Detect Evil ----------------------------------------------

    def test_recorded_senior_board_searches_again_after_the_interval(self):
        case = self.case("senior-12f")
        raw = case["board"]
        self.assertEqual((raw["player"]["level"], raw["player"]["hp"], raw["floor"]["quest_id"]),
                         (21, 223, 43))
        self.assertIn("EVIL", self.races[1164].flags)
        # As recorded: Detect Evil cast at (16,97), 12 cells away, but the
        # latest Detect Evil (turn 1164339) is 7176 game turns old: searched
        # again (hunt-redetect-1102, 「1,000ゲームターン」).
        latest = max(use["turn"] for use in case["uses"] if use["used"] == ["staff", 15])
        self.assertEqual(raw["turn"] - latest, 7176)
        policy, raw = self.policy("senior-12f")
        self.assertEqual(self.choose(policy, raw), DETECT_EVIL_KEY)
        self.assertEqual(policy.last_reason, "me-power:hunt-target-unseen:detect-evil")

    def test_evil_target_out_of_detect_evil_range_casts_detect_evil(self):
        policy, raw = self.policy("senior-12f", keep=lambda use: use["position"] != [16, 97])
        key = self.choose(policy, raw)
        self.assertEqual((key, policy.last_reason),
                         (DETECT_EVIL_KEY, "me-power:hunt-target-unseen:detect-evil"))
        game, _ = self.post(policy, raw, key, [
            prompt(TYPE_PROMPT), power_screen("staff", [("p", "邪悪存在感知", 14, 14, 5)])],
            following=self.following(raw))
        self.assertEqual(game.accepted, ["m", "A", "p"])

    def test_visible_hostile_or_just_hit_does_not_search(self):
        policy, raw = self.policy("senior-12f", keep=lambda use: use["position"] != [16, 97])
        policy._took_damage = True
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        me_powers.observe(policy, snapshot)
        hunt_target.observe(policy, snapshot)
        self.assertIsNone(me_powers.power_key(policy, snapshot, me_powers.FLOOR))


if __name__ == "__main__":
    unittest.main()
