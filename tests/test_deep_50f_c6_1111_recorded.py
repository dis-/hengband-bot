"""PLAN-50F C6, owner 2026-11-11 「2 3 5を入れる」: the Magic-Eater's floor routine on 50F+.

PLAN-50F (C:\\hengband-backups\\pdca\\captures\\deep-dive-1110\\PLAN-50F.txt) section 4 offered
the C6 bundle; the owner took items 2 (4.3 detection cadence), 3 (4.4 lighting rooms) and
5 (4.9 speed), not 1 (the 400-decision floor budget) nor 4 (the ammunition pickups):
 - 4.3 「Re-detect after walking 25 cells from the last detection ... only on 50F+ and only with an
   absorbed power or rod」: me_powers' Detect Evil row (its preferred Rod of Detection) has the
   trigger ``deep-explore-redetect``.
 - 4.4 「me-power:dark-room:lite-area ... on 50F+: not while ESP shows strong sleepers in the
   room」: lite_room wakes the sleepers on every grid it lights (spell-kind/spells-lite.cpp:45-77),
   so the dark-room trigger waits while a sleeper the 11-07 strength judgment names is within
   ``me_powers.LITE_ROOM_REACH``.
 - 4.9 「on 50F+ also haste on arrival when absorbed Speed >= 10 charges」: the Speed row's
   trigger ``deep-arrival-unhasted`` on the floor rung, once per floor visit, under the row's
   11-04 requirements (10 charges, 80% success); no potion.

Boards (tests/fixtures/deep-50f-c6-1111.json.gz, tests/extract_deep_50f_c6_1111.py): n1-b
life-367 (Magic-Eater Lv41, 629 HP, telepathy), 2026-11-10 21:0x, from the bot's own snapshots.
 - castle: Castle 61F.  Turn 5329565 at (5,18): the recorded arrival detection
   me-power:new-floor:detect-all:powerful (UCg); turn 5329572 the board after it (recorded
   seek-loot 9); turn 5329849 at (27,10), game distance 24 (recorded seek-loot 3); turn 5329853
   at (28,11), game distance 25 (recorded seek-loot 6).  Turn 5329595: the recorded dark-room
   light with no monster shown.
 - lighting: Mountain 50F (the guardian floor).  Turn 5332441 the arrival detection; turn
   5332467 at (58,30) the recorded lite-area with 15 sleepers shown by telepathy; the next board
   (5332475) says 「白い光が辺りを覆った。」 and that four woke, and the bot took *Destruction*.
Every decision is the public ``choose_key``; every posted power goes through the production
executor port, whose board (the next recorded board with the executor's completed-operation
provenance) is the next decision's board, as in the live driver.

DECLARED CONSTRUCTED: the displayed staff and rod lists (the snapshots do not keep them; the
counts and failure rates are chosen, the powers are the life's absorbed ones: the decision log
casts 全感知, 周辺感知, トラップ感知, 光, スピード and *破壊* on these floors); the replies to the posted
keys from the game's prompts (cmd-action/cmd-racial.cpp, cmd-item/cmd-magiceat.cpp); the
walks between the recorded boards are not driven (the next board of a drive is the later
recorded board); the 49F controls rewrite the boards' floor level; the hasted speed field
(``hasted``) and the Speed rows of the requirement controls are chosen.
DECLARED RECONSTRUCTED: the absorption record is life-370's policy-state checkpoint of
2026-11-11 (the same character, later; the record only names what was bought and absorbed).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from hengbot import me_powers
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.me_device_attacks import observe_lists
from hengbot.me_staff_sequence import MeStaffSequence
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import ConservativePolicy
from hengbot.quest_strategies import load_quest_strategies
from tests.support import recorded as harness
from tests.support.recorded import FaithfulHookGame, command_screen
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests.test_me_powerful_activation import racial_screen
from tests.test_me_stage2_powers import TYPE_PROMPT

FIXTURE = Path(__file__).parent / "fixtures" / "deep-50f-c6-1111.json.gz"
STRATEGIES = Path(__file__).parents[1] / "strategy" / "quests"
# life-370's checkpoint record (policy-state.json, _me_staff_sequence.absorbed).
ABSORBED = {"staff:10": 99, "staff:12": 98, "staff:13": 99, "staff:15": 99, "staff:29": 5,
            "staff:5": 99, "staff:8": 99, "staff:9": 93}
# The displayed staff list: (letter, name, current, max, fail).
STAFF_ROWS = (("i", "光", 30, 30, 5), ("j", "周辺感知", 30, 30, 5), ("m", "トラップ感知", 30, 30, 5),
              ("n", "ドア/階段感知", 30, 30, 5), ("p", "邪悪存在感知", 30, 30, 5),
              ("w", "スピード", 30, 30, 10), ("3", "*破壊*", 5, 5, 10))
ROD_ROW = ("g", "全感知", 0, 1, 10)
POWERFUL_DETECTION = "UCg"
ORDINARY_DETECTION = "mCg"
REDETECT = "me-power:deep-explore-redetect:detect-all"
HASTE = "mAw"
ARRIVAL_HASTE = "me-power:deep-arrival-unhasted:speed"


def _races(data):
    races = {}
    for key, facts in data["monraces"].items():
        facts = copy.deepcopy(facts)
        for name in ("flags", "abilities"):
            facts[name] = frozenset(facts[name])
        facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
        facts["names"] = tuple(facts.get("names", ()))  # a list in JSON; the knowledge is hashed
        races[int(key)] = MonraceKnowledge(**facts)
    return races


def hasted(raw):
    """The speed field of a hasted +5 character (+15, yellow: print_speed)."""
    raw["player"]["speed"] = 125
    raw["player"]["speed_display"] = {"value": 15, "text": "加速(+15)", "color": "yellow",
                                      "riding": False}


def at_level(boards, level):
    """DECLARED CONSTRUCTED: the same boards on another floor level."""
    boards = copy.deepcopy(boards)
    for raw in boards:
        raw["floor"]["level"] = level
    return boards


class DeepFloorRoutineRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        cls.races = _races(cls.data)

    def boards(self, name):
        return copy.deepcopy(self.data["cases"][name])

    def recorded(self, turn):
        return next(row for row in self.data["rows"] if row["turn"] == turn)

    def show_lists(self, policy, raw):
        """The game displayed the staff and rod lists just before ``raw`` (the real observer)."""
        for kind, rows in (("staff", STAFF_ROWS), ("rod", (ROD_ROW,))):
            listed = []
            for letter, name, first, second, fail in rows:
                row = {"name": name, "fail": fail, "success": 100 - fail}
                row.update({"charging": first, "max": second} if kind == "rod"
                           else {"current": first, "max": second})
                listed.append(row)
            shown = dict(copy.deepcopy(raw), _magic_eater_power_list={"kind": kind, "rows": listed})
            shown["turn"] -= 1
            observe_lists(policy, parse_snapshot(shown, policy._monrace_knowledge))

    def policy(self, raw):
        policy = ConservativePolicy(quest_strategies=load_quest_strategies(STRATEGIES))
        policy._monrace_knowledge.update(self.races)
        policy.prime(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        policy._me_staff_sequence = MeStaffSequence(absorbed=dict(ABSORBED))
        policy._dungeon_knowledge = {
            int(key): DungeonInfo(**dict(row, flags=frozenset(row["flags"])))
            for key, row in self.data["dungeons"].items()}
        self.show_lists(policy, raw)
        return policy

    def choose(self, policy, raw):
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        return policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))

    def screens(self, raw, key):
        """The game's prompts of a posted power key."""
        rod = power_screen("rod", [ROD_ROW])
        if key == POWERFUL_DETECTION:
            return [racial_screen(raw["player"]["level"]), prompt(TYPE_PROMPT), rod]
        if key == ORDINARY_DETECTION:
            return [prompt(TYPE_PROMPT), rod]
        if key.startswith("mA"):
            return [prompt(TYPE_PROMPT), power_screen("staff", list(STAFF_ROWS))]
        return []

    def post(self, policy, raw, key, following):
        """``key`` through the production executor; the game then shows ``following``."""
        game = FaithfulHookGame()
        game.capacity = 256
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [*self.screens(raw, key), command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        policy.confirm_key_posted(key)
        return port.last_result.board

    def drive(self, boards):
        """Each board's decision; a posted power's executor board is the next board."""
        policy = self.policy(boards[0])
        decided, raw = [], boards[0]
        for following in [*boards[1:], None]:
            key = self.choose(policy, raw)
            decided.append((raw["turn"], key, policy.last_reason))
            if following is None:
                break
            raw = (self.post(policy, raw, key, following)
                   if (policy.last_reason or "").startswith(me_powers.REASON + ":") else following)
        return policy, decided

    # -- 4.3: the detection again after a 25-cell walk ---------------------------

    def castle(self, *turns, level=None):
        boards = self.boards("castle")
        if level is not None:
            boards = at_level(boards, level)
        return [raw for raw in boards if raw["turn"] in turns]

    ARRIVAL = (5329565, 5329572, 5329578, 5329586, 5329595, 5329602)

    def test_recorded_castle_rows(self):
        self.assertEqual(
            [(turn, self.recorded(turn)["r"], self.recorded(turn)["k"]) for turn in
             (*self.ARRIVAL, 5329849, 5329853)],
            [(5329565, "me-power:new-floor:detect-all:powerful", POWERFUL_DETECTION),
             (5329572, "seek-loot", "9"), (5329578, "me-power:new-floor:detect-traps", "mAm"),
             (5329586, "me-power:after-destruction:map-area", "mAj"),
             (5329595, "me-power:dark-room:lite-area", "mAi"), (5329602, "seek-loot", "9"),
             (5329849, "seek-loot", "3"), (5329853, "seek-loot", "6")])

    def test_the_arrival_drive_follows_the_recorded_casts(self):
        # The recorded seek-loot of 5329572 is the arrival haste now (4.9, below).  The later
        # boards' speed field shows no haste (the recorded life did not cast it): they stand for
        # a haste run out, and the arrival haste is once per floor visit (5329602 keeps the
        # recorded seek-loot).
        _, decided = self.drive(self.castle(*self.ARRIVAL))
        self.assertEqual([row[:2] for row in decided],
                         [(5329565, POWERFUL_DETECTION), (5329572, HASTE), (5329578, "mAm"),
                          (5329586, "mAj"), (5329595, "mAi"), (5329602, "9")])

    def test_twenty_five_cells_from_the_arrival_detection_detects_again(self):
        _, decided = self.drive(self.castle(*self.ARRIVAL, 5329853))
        self.assertEqual(decided[-1][0], 5329853)
        self.assertIn(decided[-1][1:], {(POWERFUL_DETECTION, REDETECT + ":powerful"),
                                        (ORDINARY_DETECTION, REDETECT)})

    def test_the_redetection_lands_and_the_next_walk_is_measured_from_it(self):
        policy, decided = self.drive(self.castle(*self.ARRIVAL, 5329853))
        raw = self.castle(5329853)[0]
        later = dict(copy.deepcopy(raw), turn=raw["turn"] + 10)
        board = self.post(policy, raw, decided[-1][1], later)
        self.assertNotIn(self.choose(policy, board), {POWERFUL_DETECTION, ORDINARY_DETECTION})
        use = policy._me_power_floor.uses[-1]
        self.assertEqual((use.trigger, use.position), ("deep-explore-redetect", parse_snapshot(
            copy.deepcopy(raw), policy._monrace_knowledge).player.position))

    def test_control_twenty_four_cells_keeps_the_recorded_walk(self):
        _, decided = self.drive(self.castle(*self.ARRIVAL, 5329849))
        # The recorded rung (its step differs: the walk between the boards is not driven).
        self.assertEqual((decided[-1][0], decided[-1][2]), (5329849, "seek-loot"))

    def test_control_forty_nine_floor_keeps_the_recorded_walk(self):
        _, decided = self.drive(self.castle(*self.ARRIVAL, 5329853, level=49))
        self.assertEqual((decided[-1][0], decided[-1][2]), (5329853, "seek-loot"))

    # -- 4.4: no room light while strong sleepers are in its reach -----------------

    LIGHT_TURN = 5332467
    # The sleepers the strength judgment names on the recorded board (race ids): two dragons and
    # the Dracolisk by their melee, the Nightwing (722) by its disenchanting touch.
    STRONG = {728, 722, 1066, 703}

    def lighting(self, *, level=None, keep=lambda monster: True):
        """The recorded Mountain 50F arrival to the lighting board.

        WALL (pin_vacuity): the guardian-kit town return (``_should_start_town_return``) is off.
        The harness has not the life's Home and kit knowledge, so on this guardian floor it
        returned at once (guardian-kit-insufficient); the recorded life did not (the rows of
        5332446-5332467 are explore, map-area, detect-traps, lite-area)."""
        boards = self.boards("lighting")[:5]
        if level is not None:
            boards = at_level(boards, level)
        last = boards[-1]
        last["detected_monsters"] = [m for m in last["detected_monsters"] if keep(m)]
        with patch.object(ConservativePolicy, "_should_start_town_return", return_value=False):
            return self.drive(boards)

    def test_recorded_lighting_rows(self):
        self.assertEqual(
            [(self.recorded(turn)["r"], self.recorded(turn)["k"]) for turn in
             (5332441, 5332446, 5332460, self.LIGHT_TURN, 5332475)],
            [("me-power:new-floor:detect-all:powerful", POWERFUL_DETECTION), ("explore", "7"),
             ("me-power:new-floor:detect-traps", "mAm"), ("me-power:dark-room:lite-area", "mAi"),
             ("emergency:destruction:absorbed-power", "mA3")])
        # What the light did: the next board's messages name the four it woke.
        woken = self.boards("lighting")[5]
        self.assertEqual(woken["messages"][0], "白い光が辺りを覆った。")
        self.assertEqual(len([m for m in woken["messages"] if m.endswith("が目を覚ました。")]), 4)

    def test_strong_sleepers_in_reach_keep_the_dark_room_unlit(self):
        _, decided = self.lighting()
        # The recorded explore of 5332446 is the arrival haste now (4.9, below).
        self.assertEqual([row[1] for row in decided[:4]],
                         [POWERFUL_DETECTION, HASTE, "mAj", "mAm"])
        self.assertEqual(decided[-1][0], self.LIGHT_TURN)
        self.assertNotEqual(decided[-1][1], "mAi")
        self.assertNotEqual(decided[-1][2], "me-power:dark-room:lite-area")

    def test_the_strong_sleepers_of_the_recorded_board(self):
        policy, _ = self.lighting()
        board = parse_snapshot(copy.deepcopy(self.boards("lighting")[4]), policy._monrace_knowledge)
        self.assertEqual({m.race_id for m in me_powers.strong_sleepers_in_light_reach(policy, board)},
                         self.STRONG)

    def test_control_forty_nine_floor_lights_as_recorded(self):
        _, decided = self.lighting(level=49)
        self.assertEqual(decided[-1], (self.LIGHT_TURN, "mAi", "me-power:dark-room:lite-area"))

    def test_control_only_weak_sleepers_light_as_recorded(self):
        # DECLARED CONSTRUCTED: the four strong sleepers taken off the lighting board.
        _, decided = self.lighting(keep=lambda monster: monster["race_id"] not in self.STRONG)
        self.assertEqual(decided[-1], (self.LIGHT_TURN, "mAi", "me-power:dark-room:lite-area"))

    def test_the_disenchanting_summoner_alone_keeps_the_room_unlit(self):
        # DECLARED CONSTRUCTED: the Nightwing (722) is the only sleeper.  Its touch disenchants
        # and the life has no disenchantment resistance (disenchant_avoid, owner 2026-11-05).
        _, decided = self.lighting(keep=lambda monster: monster["race_id"] == 722)
        self.assertNotEqual(decided[-1][1], "mAi")
        self.assertNotEqual(decided[-1][2], "me-power:dark-room:lite-area")

    def test_control_a_deep_room_with_no_sleeper_shown_is_lit_as_recorded(self):
        # Castle 61F turn 5329595: the board shows no monster; the recorded light stands.
        _, decided = self.drive(self.castle(*self.ARRIVAL))
        self.assertEqual(decided[4], (5329595, "mAi", "me-power:dark-room:lite-area"))


    # -- 4.9: the floor starts hasted ----------------------------------------------

    HASTE_DRIVE = (5329565, 5329572)

    def test_recorded_haste_rows(self):
        self.assertEqual([(self.recorded(turn)["r"], self.recorded(turn)["k"], self.recorded(turn)["hp"])
                          for turn in self.HASTE_DRIVE],
                         [("me-power:new-floor:detect-all:powerful", POWERFUL_DETECTION, 629),
                          ("seek-loot", "9", 610)])
        self.assertEqual([raw["player"]["speed"] for raw in self.castle(*self.HASTE_DRIVE)],
                         [115, 115])

    def test_the_arrival_detection_is_followed_by_the_absorbed_haste(self):
        _, decided = self.drive(self.castle(*self.HASTE_DRIVE))
        self.assertEqual(decided, [
            (5329565, POWERFUL_DETECTION, "me-power:new-floor:detect-all:powerful"),
            (5329572, HASTE, ARRIVAL_HASTE)])

    def test_the_landed_haste_is_not_cast_again_on_the_floor(self):
        policy, decided = self.drive(self.castle(*self.HASTE_DRIVE))
        raw = self.castle(5329572)[0]
        # The speed field of the following board shows the haste (+15).
        later = dict(copy.deepcopy(raw), turn=raw["turn"] + 10)
        hasted(later)
        board = self.post(policy, raw, decided[-1][1], later)
        self.assertNotEqual(self.choose(policy, board), HASTE)
        self.assertEqual(policy._me_power_floor.uses[-1].trigger, "deep-arrival-unhasted")

    def test_control_forty_nine_floor_keeps_the_recorded_seek_loot(self):
        _, decided = self.drive(self.castle(*self.HASTE_DRIVE, level=49))
        self.assertEqual(decided[-1], (5329572, "9", "seek-loot"))

    def test_control_the_eleven_four_requirements_hold(self):
        # DECLARED CONSTRUCTED: nine charges; then 21% failure (owner 11-04 「残10回以上」,
        # 「成功率8割以上」).
        global STAFF_ROWS
        original = STAFF_ROWS
        for row in (("w", "スピード", 9, 30, 10), ("w", "スピード", 30, 30, 21)):
            with self.subTest(row=row):
                STAFF_ROWS = tuple(row if each[0] == "w" else each for each in original)
                try:
                    _, decided = self.drive(self.castle(*self.HASTE_DRIVE))
                finally:
                    STAFF_ROWS = original
                self.assertEqual(decided[-1], (5329572, "9", "seek-loot"))

    def test_control_already_hasted_keeps_the_recorded_seek_loot(self):
        # DECLARED CONSTRUCTED: the speed field shows the haste (+15) on both boards.
        boards = self.castle(*self.HASTE_DRIVE)
        for raw in boards:
            hasted(raw)
        _, decided = self.drive(boards)
        self.assertEqual(decided[-1], (5329572, "9", "seek-loot"))

if __name__ == "__main__":
    unittest.main()
