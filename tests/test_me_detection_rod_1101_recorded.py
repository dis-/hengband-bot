"""#47: the absorbed Rod of Detection replaces Detect Evil, through Powerful
Activation when it is safe (me_powers, me_powerful_activation).

Owner 2026-11-01: 「全感知のロッドの使い方について　邪悪感知を使うタイミングで全感知が
使用可能なら代わりに使用する。安全なら強力発動で使う。」

Boards, decision rows and the absorption record are recorded
(tests/fixtures/me-detection-rod-1101.json.gz, see
tests/extract_me_detection_rod_1101.py): n1-c life-073, level 11, HP 143,
carrying a Rod of Detection (pack letter p, not absorbed).
 - arrival-7f: Angband 7F, turn 788206, decision 15253, recorded
   me-power:new-floor:detect-evil with key mAp.
 - rest-8f: Angband 8F, turn 785562, decision 14980, recorded
   me-power:before-rest:detect-evil with key mAp (HP 122/143).
Both go through the public choose_key and the production executor.

DECLARED CONSTRUCTED: the absorbed Rod of Detection (the displayed rod list
row 全感知 with its charging count, ``_me_device_lists``); the HP of the low-HP
case and the level of the level-9 case; the rest-8f floor's earlier Detect
Evil/Detect Traps/Magic Mapping uses (seeded away from the player, as
test_me_stage2_powers' before-rest case) with the town return patched out so
the recorded board reaches the rest rung; the hostile case's visible monster
(the recorded yeek of the life-016 fixture, placed beside the player); the
replies to the posted keys from the game's prompts (cmd-action/cmd-racial.cpp,
cmd-item/cmd-magiceat.cpp).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
from dataclasses import replace
import gzip
import json
from pathlib import Path
import unittest
from unittest import mock

from hengbot import me_powerful_activation as powerful
from hengbot import me_powers
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.me_staff_sequence import MeStaffSequence
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from tests import test_input_executor as harness
from tests import test_me_mining_death_recorded as mining
from tests.test_input_executor import FaithfulHookGame, command_screen
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests.test_me_kind_menu_context import USE_MENU, kind_menu
from tests.test_me_powerful_activation import racial_screen

FIXTURE = Path(__file__).parent / "fixtures" / "me-detection-rod-1101.json.gz"
TYPE_PROMPT = "[A] 杖, [B] 魔法棒, [C] ロッド:"
DETECTION = "全感知"
DETECTION_ROD = ("rod", 6)
DETECT_EVIL = ("staff", 15)
POWERFUL_DETECTION = "UCg"
ORDINARY_DETECTION = "mCg"
FAILED = "呪文をうまく唱えられなかった！"


def rod_row(charging, count=1):
    return {"name": DETECTION, "charging": charging, "max": count, "fail": 20, "success": 80}


class DetectionRodRecordedTest(harness.ProductionHarness):
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

    def board(self, name, **player):
        raw = copy.deepcopy(self.data["boards"][name])
        raw["player"].update(player)
        return raw

    def policy(self, raw, *, rod=None, races=None):
        policy = HengbotPolicy(monrace_knowledge=dict(races or self.races))
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        # The recorded absorption record (policy-state.json of the capture).
        policy._me_staff_sequence = MeStaffSequence(absorbed=dict(self.data["absorbed"]))
        if rod is not None:
            policy._me_device_lists = {"rod": (raw["turn"], (rod,))}
        return policy

    def choose(self, policy, raw):
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        return policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))

    def post(self, policy, raw, key, screens, *, elapsed=10):
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [*screens, command_screen(raw["turn"] + elapsed)]
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + elapsed)
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        return game, port.last_result.board

    def rod_list(self, charging=0):
        return power_screen("rod", [("g", DETECTION, charging, 1, 20)])

    def zap_powerful(self, policy, raw, *, charging=0, elapsed=10, after=()):
        game, board = self.post(policy, raw, POWERFUL_DETECTION, [
            racial_screen(raw["player"]["level"]), prompt(TYPE_PROMPT),
            self.rod_list(charging), *after], elapsed=elapsed)
        return game, board

    def zap_ordinary(self, policy, raw):
        game, board = self.post(policy, raw, ORDINARY_DETECTION,
                                [prompt(TYPE_PROMPT), self.rod_list()])
        self.assertEqual(game.accepted, ["m", "C", "g"])
        return board

    def with_yeek(self, raw):
        """The board with the life-016 fixture's recorded yeek two cells east."""
        source = mining.MagicEaterMiningDeathRecordedTest
        source.setUpClass()
        yeek = copy.deepcopy(source.data["cases"]["life-016"]["boards"]["94171"]
                             ["visible_monsters"][0])
        yeek.update(y=raw["player"]["y"], x=raw["player"]["x"] + 2)
        hostile = dict(copy.deepcopy(raw), visible_monsters=[yeek])
        return hostile, {**self.races, yeek["race_id"]: source.races[yeek["race_id"]]}

    def rows(self):
        return {row["decision_sequence"]: row for row in self.data["rows"]}

    def assertDecision(self, policy, key, expected_key, reason):
        self.assertEqual((key, policy.last_reason), (expected_key, reason))

    # -- the recorded arrival ---------------------------------------------------

    def test_recorded_arrival_cast_detect_evil(self):
        rows = self.rows()
        self.assertEqual((rows[15253]["reason"], rows[15253]["key"], rows[15253]["turn"]),
                         ("me-power:new-floor:detect-evil", "mAp", 788206))
        raw = self.board("arrival-7f")
        self.assertEqual((raw["player"]["level"], raw["player"]["hp"], raw["visible_monsters"]),
                         (11, 143, []))
        # Not absorbed: today's key, unchanged.
        policy = self.policy(raw)
        self.assertDecision(policy, self.choose(policy, raw), "mAp",
                            "me-power:new-floor:detect-evil")

    def test_absorbed_charged_detection_replaces_detect_evil_powerful_when_safe(self):
        raw = self.board("arrival-7f")
        policy = self.policy(raw, rod=rod_row(0))
        key = self.choose(policy, raw)
        self.assertDecision(policy, key, POWERFUL_DETECTION,
                            "me-power:new-floor:detect-all:powerful")
        game, board = self.zap_powerful(policy, raw)
        # U, the racial row of 強力発動, the rod kind, the power letter.
        self.assertEqual(game.accepted, ["U", "b", "C", "g"])
        # The cast stands for the Detect Evil row: the next arrival power is
        # Detect Traps, not Detect Evil again.
        key = self.choose(policy, board)
        self.assertDecision(policy, key, "mAm", "me-power:new-floor:detect-traps")
        use = policy._me_power_floor.uses[-1]
        self.assertEqual((use.served, use.used), (DETECT_EVIL, DETECTION_ROD))

    def test_low_hp_or_low_level_casts_ordinary_detection(self):
        raw = self.board("arrival-7f")
        threshold = HengbotPolicy._low_hp_walk_threshold(raw["player"]["max_hp"])
        worst = powerful.cost(raw["player"]["level"])
        # HP after the worst cost exactly at the low-HP walk threshold: unsafe.
        cases = {"hp low": {"hp": int(threshold) + worst},
                 "level 9": {"level": 9, "max_level": 9}}
        for label, player in cases.items():
            with self.subTest(label):
                board = self.board("arrival-7f", **player)
                policy = self.policy(board, rod=rod_row(0))
                key = self.choose(policy, board)
                self.assertDecision(policy, key, ORDINARY_DETECTION,
                                    "me-power:new-floor:detect-all")
                self.zap_ordinary(policy, board)
        # One HP more is safe.
        board = self.board("arrival-7f", hp=int(threshold) + worst + 1)
        policy = self.policy(board, rod=rod_row(0))
        self.assertEqual(self.choose(policy, board), POWERFUL_DETECTION)

    def test_charging_or_unabsorbed_detection_leaves_detect_evil(self):
        cases = {"charging": rod_row(1), "not absorbed": None}
        for label, rod in cases.items():
            with self.subTest(label):
                raw = self.board("arrival-7f")
                policy = self.policy(raw, rod=rod)
                self.assertDecision(policy, self.choose(policy, raw), "mAp",
                                    "me-power:new-floor:detect-evil")

    def test_stale_list_rod_found_charging_is_cancelled_then_detect_evil(self):
        # The remembered list says ready; the game's list shows it charging:
        # ESC before any HP is paid (do_cmd_magic_eater returns false).
        raw = self.board("arrival-7f")
        policy = self.policy(raw, rod=rod_row(0))
        self.assertEqual(self.choose(policy, raw), POWERFUL_DETECTION)
        game, board = self.zap_powerful(policy, raw, charging=1, elapsed=0)
        self.assertEqual(game.accepted, ["U", "b", "C", "\x1b"])
        self.assertDecision(policy, self.choose(policy, board), "mAp",
                            "me-power:new-floor:detect-evil")

    def test_failed_detection_retried_five_times_then_detect_evil(self):
        # Owner 2026-10-31 「最大5回まで同じ場所で試す」.
        raw = self.board("arrival-7f")
        policy = self.policy(raw, rod=rod_row(0))
        board = raw
        for failure_number in range(1, me_powers.FAILURES_PER_PLACE + 1):
            self.assertEqual(self.choose(policy, board), POWERFUL_DETECTION, failure_number)
            failure = command_screen(board["turn"] + 10)
            failure["lines"][0] = FAILED
            _, board = self.zap_powerful(policy, board, after=[failure])
            self.assertEqual(board["_completed_operation_receipt"]["refusal"],
                             "failed:magic-eater", failure_number)
        self.assertDecision(policy, self.choose(policy, board), "mAp",
                            "me-power:new-floor:detect-evil")

    def test_visible_hostile_or_just_hit_casts_neither(self):
        raw = self.board("arrival-7f")
        hostile, races = self.with_yeek(raw)
        policy = self.policy(hostile, rod=rod_row(0), races=races)
        key = self.choose(policy, hostile)
        # Neither detection (a harmless yeek still lets the mapping row cast,
        # owner 2026-11-01 「脅威でなければ感知する」).
        self.assertNotIn(key, (POWERFUL_DETECTION, ORDINARY_DETECTION, "mAp"))
        self.assertNotIn("detect-", policy.last_reason)
        policy = self.policy(raw, rod=rod_row(0))
        policy._took_damage = True
        board = parse_snapshot(raw, policy._monrace_knowledge)
        me_powers.observe(policy, board)
        self.assertIsNone(me_powers.power_key(policy, board, me_powers.FLOOR))

    def test_use_menu_kind_menu_moves_to_the_rod_row(self):
        raw = self.board("arrival-7f")
        policy = self.policy(raw, rod=rod_row(0))
        self.assertEqual(self.choose(policy, raw), POWERFUL_DETECTION)
        game, _ = self.post(policy, raw, POWERFUL_DETECTION, [
            racial_screen(11), kind_menu(USE_MENU, 0), kind_menu(USE_MENU, 1),
            kind_menu(USE_MENU, 2), self.rod_list()])
        self.assertEqual(game.accepted, ["U", "b", "2", "2", "\r", "g"])

    def test_powerful_when_safe_also_needs_no_visible_hostile(self):
        # A powerful row cast beside harmless hostiles (one field each, as the
        # next such power would be): the harmless recorded yeek in view keeps
        # it ordinary, since 「安全なら」 is no visible hostile and no hit.
        raw, races = self.with_yeek(self.board("arrival-7f"))
        rows = tuple(replace(power, beside_harmless=True) if power.ident in (DETECT_EVIL, DETECTION_ROD)
                     else power for power in me_powers.POWERS)
        with mock.patch.object(me_powers, "POWERS", rows), \
                mock.patch.object(me_powers, "BY_KEY", {power.ident: power for power in rows}):
            policy = self.policy(raw, rod=rod_row(0), races=races)
            key = self.choose(policy, raw)
            self.assertDecision(policy, key, ORDINARY_DETECTION, "me-power:new-floor:detect-all")
            policy = self.policy(raw, rod=rod_row(0), races=races)
            policy._took_damage = True
            board = parse_snapshot(raw, policy._monrace_knowledge)
            me_powers.observe(policy, board)
            self.assertIsNone(me_powers.power_key(policy, board, me_powers.FLOOR))

    # -- the recorded rest ------------------------------------------------------

    def rest_policy(self, raw):
        policy = self.policy(raw, rod=rod_row(0))
        memory = me_powers.FloorMemory(parse_snapshot(raw, policy._monrace_knowledge).floor_key,
                                       raw["turn"])
        here = Position(raw["player"]["y"], raw["player"]["x"])
        # Detect Evil cast elsewhere on the floor; traps and the map here.
        for ident, position in ((DETECT_EVIL, Position(1, 1)), (("staff", 12), here),
                                (("staff", 9), here)):
            memory.uses.append(me_powers.Use(ident, ident, "new-floor", position,
                                             raw["turn"] - 5))
        policy._me_power_floor = memory
        for name, value in {"_returning_to_town": False, "_emergency_return_active": False,
                            "_fundraising_mode": None}.items():
            setattr(policy, name, value)
        return policy

    def test_recorded_rest_casts_detection_before_resting(self):
        rows = self.rows()
        self.assertEqual((rows[14980]["reason"], rows[14980]["key"]),
                         ("me-power:before-rest:detect-evil", "mAp"))
        with mock.patch.object(HengbotPolicy, "_should_start_town_return", return_value=False), \
                mock.patch.object(HengbotPolicy, "_return_to_town_key", return_value=None):
            # Recorded HP 122/143: 122 - cost(11) = 112 stays above the gate.
            raw = self.board("rest-8f")
            policy = self.rest_policy(raw)
            key = self.choose(policy, raw)
            self.assertDecision(policy, key, POWERFUL_DETECTION,
                                "me-power:before-rest:detect-all:powerful")
            game, _ = self.zap_powerful(policy, raw)
            self.assertEqual(game.accepted, ["U", "b", "C", "g"])
            # HP 80/143: 70 after the worst cost is under 71.5, ordinary.
            raw = self.board("rest-8f", hp=80)
            policy = self.rest_policy(raw)
            key = self.choose(policy, raw)
            self.assertDecision(policy, key, ORDINARY_DETECTION, "me-power:before-rest:detect-all")
            self.zap_ordinary(policy, raw)

    # -- the table --------------------------------------------------------------

    def test_preferred_and_powerful_rows_are_executable(self):
        for power in me_powers.POWERS:
            with self.subTest(power=power.effect):
                self.assertTrue(set(power.preferred) <= set(me_powers.BY_KEY))
                if power.powerful is not None:
                    self.assertIn(power.powerful, me_powers.POWERFUL)
                    self.assertFalse(power.aimed)
                    effect = powerful.activatable(*power.ident)
                    self.assertEqual((effect.kind, effect.sval, effect.names),
                                     (power.kind, power.sval, power.names))
        self.assertEqual(powerful.racial_key(*DETECTION_ROD), POWERFUL_DETECTION)
        self.assertIsNone(powerful.activatable("rod", 14))


if __name__ == "__main__":
    unittest.main()
