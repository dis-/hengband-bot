"""n1-c life-140, random quest 40: 周辺感知 after a *Destruction*, and in a sealed pocket.

Owner 2026-11-05: 「*破壊*後の地形を全マス探索するのは無駄なので周辺感知があれば使って」
(area_mapping).

Recorded (tests/extract_area_mapping_1105_fixture.py; every decision through the public
choose_key): the *Destruction* use at (19,98), turn 3969877, and the flash board after it,
turn 3969879, where the live bot read ``me-power:before-rest:detect-all``.  The sealed
board: test_sealed_pocket_quest_1105_recorded's stop board.

DECLARED CONSTRUCTED: the displayed power lists (the live process had them, the capture
does not); the use's memory; a carried staff or rod in the pack; the board and the memory
after a use; the floor with no quest (the mapped area is not applied on a quest floor);
the rock around the sealed cells; the executor's prompts.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run
from recorded_junk_scope import install_past_destroyed_junk

import copy
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import area_mapping, destruction_use, mapped_area, me_powers, sealed_pocket
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.me_device_attacks import observe_lists
from hengbot.model import Position, game_distance, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy
from tests import test_input_executor as executor_pins
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_list, power_screen, row
from tests.test_sealed_pocket_quest_1105_recorded import _cell_set, _pin as _sealed_pin

FIXTURE = Path(__file__).with_name("fixtures") / "area-mapping-1105.json.xz"
USE_TURN, FLASH_TURN = 3969877, 3969879
CENTRE = Position(19, 98)
MAP_NAME = "周辺感知"
DOOR_NAME = "ドア/階段感知"
DESTRUCTION_NAME = "*破壊*"
MAP_KEY = "mAj"
AFTER = "me-power:after-destruction:map-area"
SEALED = "me-power:sealed-pocket:map-area"
STAFF_TVAL, STAFF_SVAL, ROD_TVAL, ROD_SVAL = 55, 9, 66, 5
SCROLL_TVAL, SCROLL_SVAL = 70, 25
GRANITE_TERRAIN_ID = 56
MAPPING = ("staff", me_powers.SV_STAFF_MAPPING)
FAR = Position(19, 2)  # 96 away: past the disc's 30 and the circle's 17
_undo_past_junk = None


def setUpModule():
    # Owner 2026-11-02: these boards carry junk the first safe decision destroys.
    global _undo_past_junk
    _undo_past_junk = install_past_destroyed_junk()


def tearDownModule():
    _undo_past_junk()


def _boards():
    rows = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))
    return {json.loads(line)["turn"]: json.loads(line) for line in rows}


def _device(raw, tval, sval, name, **fields):
    item = dict(copy.deepcopy(raw["inventory"][0]), slot="s", tval=tval, sval=sval, count=1, known=True,
                aware=True, fully_known=True, charging=False, charges=5, pval=5, name=name, weight=50,
                **fields)
    raw["inventory"].append(item)
    return raw


class AreaMappingRecordedTest(executor_pins.ProductionHarness):
    def setUp(self):
        self.boards = _boards()
        self.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def policy(self, raw, *rows):
        policy = _policy(self.root, self.monrace)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        policy.prime(board)
        # DECLARED: the skill list the live process had read.
        skill = next(json.loads(line) for line in _sealed_pin()["lines"] if '"skill_exp"' in line)
        policy.consume_skill_knowledge({**skill, "player": {"level": board.player.level}})
        if rows:
            listed = dict(copy.deepcopy(raw), turn=raw["turn"] - 1,
                          _magic_eater_power_list=power_list("staff", *rows))
            observe_lists(policy, parse_snapshot(listed, policy._monrace_knowledge))
        return policy

    def choose(self, policy, raw):
        board = parse_snapshot(raw, policy._monrace_knowledge)
        board = policy.with_known_skill_exp(board)
        return policy.choose_key(board), board

    def flashed(self, *rows, raw=None):
        """A policy deciding on the flash board, the use remembered from the turn before."""
        raw = copy.deepcopy(self.boards[FLASH_TURN] if raw is None else raw)
        use = copy.deepcopy(self.boards[USE_TURN])
        if raw["floor"] != self.boards[FLASH_TURN]["floor"]:
            use["floor"] = raw["floor"]
        policy = self.policy(use, *rows)
        floor = parse_snapshot(raw, policy._monrace_knowledge).floor_key
        destruction_use._memory(policy).pending = (floor, USE_TURN, CENTRE)
        # DECLARED: the floor's arrival mapping, far from the circle (the recorded rows cast
        # new-floor on this floor; the capture's boards begin later).
        memory = me_powers.FloorMemory(floor, USE_TURN)
        memory.uses.append(me_powers.Use(MAPPING, MAPPING, "new-floor", FAR, USE_TURN - 1))
        policy._me_power_floor = memory
        return policy, raw

    def full_rows(self):
        return (row(DESTRUCTION_NAME, 5, current=3, count=3), row(MAP_NAME, 5, current=3, count=3))

    def test_the_flash_board_maps_first_through_the_executor(self):
        policy, raw = self.flashed(*self.full_rows())
        key, board = self.choose(policy, raw)
        self.assertEqual((key, policy.last_reason), (MAP_KEY, AFTER))
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
                        power_screen("staff", [("j", MAP_NAME, 3, 3, 5)]),
                        executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [dict(raw, turn=raw["turn"] + 10) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                             "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(game.accepted, ["m", "A", "j"])

    def test_it_maps_once(self):
        policy, raw = self.flashed(*self.full_rows())
        self.choose(policy, raw)
        memory = policy._me_power_floor
        memory.uses.append(memory.pending)  # DECLARED: the use landed
        memory.pending = None
        later = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=[])
        self.choose(policy, later)
        self.assertNotEqual(policy.last_reason, AFTER)

    def test_no_mapping_power_keeps_the_recorded_answer(self):
        policy, raw = self.flashed(row(DESTRUCTION_NAME, 5, current=3, count=3))
        self.choose(policy, raw)
        self.assertFalse(policy.last_reason.endswith(":map-area"), policy.last_reason)
        self.assertFalse(policy.last_reason.startswith(area_mapping.REASON), policy.last_reason)

    def test_the_door_power_is_no_stand_in(self):
        # The row's fallback, Door/Stairs Detection, does not map: the owner named 周辺感知.
        policy, raw = self.flashed(row(MAP_NAME, 5, current=0, count=3), row(DOOR_NAME, 5, current=3, count=3))
        self.choose(policy, raw)
        self.assertNotIn("after-destruction", policy.last_reason)

    def test_being_hit_comes_first(self):
        for rows, carried in ((self.full_rows(), False), ((), True)):
            raw = copy.deepcopy(self.boards[FLASH_TURN])
            if carried:
                _device(raw, STAFF_TVAL, STAFF_SVAL, "周辺感知の杖 (5回分)")
            policy, raw = self.flashed(*rows, raw=raw)
            board = parse_snapshot(raw, policy._monrace_knowledge)
            destruction_use.observe(policy, board)
            me_powers.observe(policy, board)
            policy._took_damage = True
            self.assertIsNone(me_powers.power_key(policy, board, me_powers.FLOOR))
            self.assertIsNone(area_mapping.after_destruction_key(policy, board))

    def test_blind_waits(self):
        policy, raw = self.flashed(*self.full_rows())
        raw["player"]["status"]["blind"] = True
        self.choose(policy, raw)
        self.assertNotEqual(policy.last_reason, AFTER)

    def carried(self, tval, sval, name, **fields):
        raw = _device(copy.deepcopy(self.boards[FLASH_TURN]), tval, sval, name, **fields)
        raw["floor"]["quest_id"] = 0
        return self.flashed(raw=raw)

    def test_a_carried_staff_maps_and_exploration_stays_out_of_the_circle(self):
        policy, raw = self.carried(STAFF_TVAL, STAFF_SVAL, "周辺感知の杖 (5回分)")
        key, board = self.choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("us", "area-mapping:after-destruction"))
        # DECLARED: the board after the use, no failure in its messages.
        later = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=[])
        key, board = self.choose(policy, later)
        self.assertNotEqual(policy.last_reason, "area-mapping:after-destruction")
        self.assertEqual(area_mapping.carried_areas(policy, board), ((CENTRE, me_powers.DETECT_RAD),))
        area = mapped_area.current(policy)
        self.assertIsNotNone(area)
        # The recorded board's blanks in the sure radius are all explored.
        sure = {(y, x) for y, x in mapped_area.disc_cells(board, CENTRE, destruction_use.GUARANTEED_RADIUS)
                if game_distance(CENTRE, Position(y, x)) <= area.discs[0][1]
                and (y, x) not in policy._remembered_known_t}
        self.assertTrue(sure)
        self.assertLessEqual(sure, set(area.corridor))

    def test_a_failed_staff_stays_due(self):
        policy, raw = self.carried(STAFF_TVAL, STAFF_SVAL, "周辺感知の杖 (5回分)")
        self.choose(policy, raw)
        later = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=["杖をうまく使えなかった。"])
        key, board = self.choose(policy, later)
        self.assertEqual((key, policy.last_reason), ("us", "area-mapping:after-destruction"))
        self.assertEqual(area_mapping.carried_areas(policy, board), ())

    def test_a_carried_rod_zaps_unless_it_charges(self):
        policy, raw = self.carried(ROD_TVAL, ROD_SVAL, "周辺感知のロッド", charging_count=0)
        key, _ = self.choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("zs", "area-mapping:after-destruction"))
        policy, raw = self.carried(ROD_TVAL, ROD_SVAL, "周辺感知のロッド", charging_count=1)
        raw["inventory"][-1]["charging"] = True
        self.choose(policy, raw)
        self.assertFalse(policy.last_reason.startswith(area_mapping.REASON), policy.last_reason)

    def scroll(self, raw=None):
        raw = copy.deepcopy(self.boards[FLASH_TURN] if raw is None else raw)
        return _device(raw, SCROLL_TVAL, SCROLL_SVAL, "魔法の地図の巻物")

    def scroll_key(self, raw):
        return "r" + parse_snapshot(raw, self.monrace).inventory[-1].slot

    def test_a_held_scroll_is_read_and_its_map_counts(self):
        # Owner 2026-11-05 「持っていれば読む」: read before the junk rung destroys the 「捨てる」 kind.
        raw = self.scroll()
        raw["floor"]["quest_id"] = 0
        policy, raw = self.flashed(raw=raw)
        key, _ = self.choose(policy, raw)
        self.assertEqual((key, policy.last_reason), (self.scroll_key(raw), "area-mapping:after-destruction"))
        later = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=[])
        _, board = self.choose(policy, later)
        self.assertEqual(area_mapping.carried_areas(policy, board), ((CENTRE, me_powers.DETECT_RAD),))
        self.assertIsNotNone(mapped_area.current(policy))
        self.assertFalse(area_mapping._due(policy, board))

    def test_the_scroll_is_the_last_source(self):
        raw = _device(self.scroll(), ROD_TVAL, ROD_SVAL, "周辺感知のロッド", charging_count=0)
        policy, raw = self.flashed(raw=raw)
        self.assertEqual(self.choose(policy, raw)[0][0], "z")
        policy, raw = self.flashed(*self.full_rows(), raw=self.scroll())
        self.assertEqual((self.choose(policy, raw)[0], policy.last_reason), (MAP_KEY, AFTER))

    def test_the_scroll_needs_a_read_and_a_destruction(self):
        policy, raw = self.flashed(raw=self.scroll())
        raw["player"]["status"]["confused"] = True
        self.choose(policy, raw)
        self.assertFalse(policy.last_reason.startswith(area_mapping.REASON), policy.last_reason)
        # A sealed pocket with no *Destruction* on record is no reason to read it: the
        # owner's answer named the *Destruction*.
        sealed = _device(json.loads(_sealed_pin()["lines"][-1]), SCROLL_TVAL, SCROLL_SVAL, "魔法の地図の巻物")
        policy = self.policy(sealed)
        self.assertIsNone(area_mapping.sealed_key(policy, parse_snapshot(sealed, policy._monrace_knowledge)))

    def test_an_absorbed_rod_maps_where_the_staff_is_not_absorbed(self):
        policy, raw = self.flashed()
        listed = dict(copy.deepcopy(raw), turn=raw["turn"] - 1,
                      _magic_eater_power_list=power_list("rod", row(MAP_NAME, 5, charging=0, count=1)))
        observe_lists(policy, parse_snapshot(listed, policy._monrace_knowledge))
        key, _ = self.choose(policy, raw)
        self.assertEqual((key, policy.last_reason), ("mCf", AFTER))

    def test_the_destruction_forgets_a_map_it_met(self):
        raw = copy.deepcopy(self.boards[FLASH_TURN])
        raw["floor"]["quest_id"] = 0
        policy, raw = self.flashed(*self.full_rows(), raw=raw)
        board = parse_snapshot(raw, policy._monrace_knowledge)
        memory = policy._me_power_floor
        memory.uses.append(me_powers.Use(MAPPING, MAPPING, "new-floor", CENTRE, USE_TURN - 1))
        destruction_use.observe(policy, board)
        self.assertEqual(me_powers.mapped_areas(policy, board), ((FAR, me_powers.DETECT_RAD),))
        # The row still counts them as uses: 「new-floor」 does not fire for them.
        self.assertEqual(len(memory.uses), 2)

    def test_a_sealed_pocket_reads_the_map_before_it_melts(self):
        raw = json.loads(_sealed_pin()["lines"][-1])
        policy = self.policy(raw, row(MAP_NAME, 5, current=3, count=3))
        board = parse_snapshot(raw, policy._monrace_knowledge)
        me_powers.observe(policy, board)
        self.assertEqual(sealed_pocket.key(policy, board), MAP_KEY)
        self.assertEqual(policy.last_reason, SEALED)

    def test_with_the_map_read_the_blank_floor_gives_the_direction(self):
        raw = json.loads(_sealed_pin()["lines"][-1])
        granite = next(entry for entry in raw["grid_map"]["palette"] if entry[0] == GRANITE_TERRAIN_ID)
        # DECLARED: the map showed rock all around but a blank passage beyond the wall, right.
        passage = {(19, x) for x in range(100, 104)}
        rock = {(y, x) for y in range(15, 24) for x in range(93, 104)} - {(19, 97), (19, 98)} - passage
        walled = _cell_set(raw, rock, granite)
        walled["grid_map"]["runs"] = [run for run in walled["grid_map"]["runs"]
                                      if (run[0], run[1]) not in passage]
        policy = self.policy(walled)
        board = parse_snapshot(walled, policy._monrace_knowledge)
        area_mapping._memory(policy, board).discs.append((CENTRE, me_powers.DETECT_RAD))
        self.assertTrue(sealed_pocket.key(policy, board).endswith("6"), policy.last_reason)
        self.assertEqual(policy.last_reason, sealed_pocket.REASON)
