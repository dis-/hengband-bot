"""The armour smith at the recall read (owner 2026-11-04).

Owner: 「資金が潤沢なとき、防具鍛冶を利用してACを強化できる」: 30,000 gold or more
raises the worn armour, lowest modifier first, after shopping and Home, before
departure, never a departure condition.

Recorded: n1-c life-130's Outpost visit (tests/fixtures/town-stops-1104,
``ring-departure``, row 34 is its recall read, Lv37, feet [6,-6], arms [5,+1],
armour in the pack), and the recorded Telmora board of life-422
(tests/fixtures/quest-stops-20261030.json.gz, q2) for the smith's town.

DECLARED CONSTRUCTED: the gold and modifiers changed on those boards, the board's
player placed beside the Fighters Hall, and ``SmithHookGame``, an interpreter of
market/building-enchanter.cpp under cmd-building.cpp's menu.  The prompts are the
source's; no live screen of this building was captured.  DECLARED: the spare
*Identify* of the same read is out of charges (its own test covers it), and the
Tower sequence is finished, which a fresh policy cannot know.

The whole trip (``test_whole_trip``): every key from the recorded read board to
the landing back in the Outpost is chosen by the public chooser and posted through
the production executor port.  Recorded: the Outpost read board and the Telmora
board.  CONSTRUCTED: ``TripGame``'s replies (the walks, the inn's fare and landing,
the raises), the character carried onto the Telmora board, and the line (see
``line_at``).  No live screen of the smith or of this trip exists yet.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from dataclasses import replace
import gzip
import json
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import armor_smith
from hengbot.cli import _ExecutorInputPort, _send_new_decision_key
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import _strip_jsonc
from hengbot.policy_constants import TOWN_TELEPORT_BUILDING_TYPES, TOWN_TELEPORT_COST
from hengbot.town_maps import find_town_map, parse_town_map
from tests import test_input_executor as executor_pins
from tests import test_q2_tower_recharge_recorded as q2_town
from tests import test_town_stops_1104_recorded as stops

setUpModule = stops.setUpModule
tearDownModule = stops.tearDownModule

GAME = Path("C:/hengband")
FIXTURES = Path(__file__).with_name("fixtures")
READ_ROW = 34
RECORDED_GOLD = 17700
LINE = 15900  # test_whole_trip: three raises above it after the fare
FIGHTERS_HALL = 7
PRICE = 600  # 02_Telmora.jsonc building 7, a Magic-Eater is no owner of it
CAP = 37 // 5
PACK_PAGE = "(持ち物: k-l, '/' 装備品, ESC) どのアイテムを改良しますか？"
EQUIP_PAGE = "(装備品: h-l, '/' 持ち物, ESC) どのアイテムを改良しますか？"
EQUIP_ONLY_PAGE = "(装備品: h-l, ESC) どのアイテムを改良しますか？"
SLOTS = {"h": "body", "i": "outer", "j": "head", "k": "arms", "l": "feet"}


def smith_screen(prompt=""):
    # CONSTRUCTED: building-service.cpp's menu, Telmora's Fighters Hall letters.
    lines = [""] * 24
    lines[0] = prompt
    lines[2] = " ハイアム (人間) 戦士の集会所"
    lines[19] = " w) 武器を強化する ($800)       a) 防具を強化する ($600)"
    lines[23] = " ESC) 建物を出る"
    return {"width": 80, "height": 24, "lines": lines,
            "cursor": {"visible": True, "x": 0, "y": 0}}


class SmithHookGame(executor_pins.FaithfulHookGame):
    """CONSTRUCTED: enchant_item, one key at a time, on the harness's FIFO."""

    capacity = 64

    def __init__(self, board, *, cap=CAP):
        super().__init__()
        self.state = copy.deepcopy(board)
        self.state["messages"] = []
        self.phase = "command"
        self.cap = cap
        self.raised = []
        self.posted = []
        self.pack_has_armour = any(
            it["tval"] in armor_smith.PROTECTOR_TVALS for it in self.state["inventory"])

    def _raise(self, slot):
        item = next(it for it in self.state["equipment"] if it["slot"] == slot)
        if item["to_a"] >= self.cap:
            return  # 「改良に失敗した。」: nothing charged
        item["to_a"] += 1
        item["name"] = re.sub(r"\[(\d+),[+-]\d+\]",
                              lambda m: f"[{m.group(1)},{item['to_a']:+d}]", item["name"])
        self.state["player"]["gold"] -= PRICE
        self.raised.append(slot)

    def _key(self, key):
        if self.phase == "command":
            self.phase = "building"
        elif self.phase == "building":
            if key == "a" and self.state["player"]["gold"] >= PRICE:
                self.phase = "pack" if self.pack_has_armour else "equip"
            elif key == "\x1b":
                self.phase = "command"
                self.state["turn"] += 1
        elif self.phase == "pack":
            assert key == "/", key
            self.phase = "equip"
        elif self.phase == "equip":
            self._raise(SLOTS[key])
            self.phase = "building"

    def _consume(self, *, pump_frontend=True):
        if pump_frontend:
            self.term_fifo.extend(self.frontend_fifo)
            self.frontend_fifo.clear()
        raw = "".join(self.term_fifo)
        self.term_fifo.clear()
        if not raw:
            return
        for key in raw:
            self.posted.append(key)
            self._key(key)
        if self.phase == "command":
            self.screen = executor_pins.command_screen(self.state["turn"])
            self.jsonl.append(copy.deepcopy(self.state))
        elif self.phase == "pack":
            self.screen = smith_screen(PACK_PAGE)
        elif self.phase == "equip":
            self.screen = smith_screen(EQUIP_PAGE if self.pack_has_armour else EQUIP_ONLY_PAGE)
        else:
            self.screen = smith_screen()


class TripGame(SmithHookGame):
    """CONSTRUCTED: the walks, the inn and the smith over two recorded boards."""

    capacity = 256
    MOVES = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
             "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}

    def __init__(self, boards, maps):
        super().__init__(boards[0])
        self.boards, self.maps, self.town = boards, maps, 0
        self.fares = 0
        self.cursor = None

    def _here(self):
        return self.state["player"]["y"], self.state["player"]["x"]

    def _building_at(self, y, x):
        return next((number for number, cell in self.maps[self.town].buildings.items()
                     if (cell.y, cell.x) == (y, x)), None)

    def _land(self, town):
        """cmd-building.cpp BACT_TELEPORT_TOWN: a new floor of that town; the fare paid."""
        board = copy.deepcopy(self.boards[town])
        for name in ("inventory", "equipment", "progress"):
            board[name] = self.state[name]
        board["player"] = dict(self.state["player"], y=board["player"]["y"], x=board["player"]["x"])
        board["turn"] = self.state["turn"] + 10
        board["messages"] = []
        self.state, self.town, self.phase = board, town, "command"

    def _key(self, key):
        if self.phase == "travel":
            if key == ".":
                self.state["player"].update(y=self.cursor[0], x=self.cursor[1])
                self.state["turn"] += 10
                self.phase = "command"
            elif key in self.MOVES:
                self.cursor = (self.cursor[0] + self.MOVES[key][0], self.cursor[1] + self.MOVES[key][1])
        elif self.phase == "command":
            if key == "`":
                self.cursor, self.phase = self._here(), "travel"
            elif key in self.MOVES:
                y, x = self._here()
                y, x = y + self.MOVES[key][0], x + self.MOVES[key][1]
                self.state["player"].update(y=y, x=x)
                self.state["turn"] += 10
                building = self._building_at(y, x)
                if building == TOWN_TELEPORT_BUILDING_TYPES[self.town]:
                    self.phase = "inn"
                elif building is not None:
                    self.phase = "building"
            else:
                assert key == "\x1b", repr(key)
        elif self.phase == "inn":
            assert key == "m", repr(key)
            self.state["player"]["gold"] -= TOWN_TELEPORT_COST
            self.fares += 1
            self.phase = "inn-choice"
        elif self.phase == "inn-choice":
            self._land(ord(key) - ord("a"))
        else:
            super()._key(key)


class ArmorSmithRecordedTest(executor_pins.ProductionHarness):
    load = stops.TownStops1104RecordedTest.load
    replay = stops.TownStops1104RecordedTest.replay
    publish_nothing = stops.TownStops1104RecordedTest.publish_nothing
    rings_already_repaired = stops.TownStops1104RecordedTest.rings_already_repaired
    q2_policy = q2_town.Q2TowerRechargeRecordedTest.policy

    @classmethod
    def setUpClass(cls):
        q2_town.Q2TowerRechargeRecordedTest.setUpClass.__func__(cls)

    def setUp(self):
        super().setUp()
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        self.publish_nothing()
        patcher = mock.patch("hengbot.me_capability.charges", lambda *_args: 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def read_board(self):
        """The visit replayed up to its recall read; (policy, recorded row, board)."""
        with self.rings_already_repaired():
            policy, recorded, steps = self.replay("ring-departure", READ_ROW)
        self.assertEqual(recorded[READ_ROW]["reason"], "town:recall-to-angband")
        return policy, recorded[READ_ROW], steps[READ_ROW][1]()

    @staticmethod
    def with_gold(board, gold):
        return replace(board, player=replace(board.player, gold=gold))

    @staticmethod
    def with_names(board, names):
        return replace(board, equipment=[
            replace(item, name=names[item.slot]) if item.slot in names else item
            for item in board.equipment])

    def decide(self, policy, board):
        with self.rings_already_repaired():
            return policy.choose_key(board)

    def smith_town(self, gold, *, pack_armour=True):
        """The recorded Telmora board with the Lv37 Magic-Eater beside the Hall."""
        with self.rings_already_repaired():
            _policy, recorded, _steps = self.replay("ring-departure", READ_ROW)
        character = json.loads(recorded[READ_ROW]["line"] or recorded[READ_ROW]["inputs"][-1])
        raw = copy.deepcopy(self.q2["board"])
        for name in ("inventory", "equipment", "progress"):
            raw[name] = copy.deepcopy(character[name])
        position = raw["player"]
        raw["player"] = dict(copy.deepcopy(character["player"]), y=position["y"], x=position["x"])
        raw["player"]["gold"] = gold
        if not pack_armour:
            raw["inventory"] = [it for it in raw["inventory"]
                                if it["tval"] not in armor_smith.PROTECTOR_TVALS]
        hall = self.maps[1].building_position(FIGHTERS_HALL)
        raw["player"].update(y=hall.y - 1, x=hall.x)
        policy = self.q2_policy(raw)
        armor_smith.state(policy).origin = 0
        armor_smith.state(policy).travelled = True
        return policy, raw, parse_snapshot(copy.deepcopy(raw), self.monraces)

    def post(self, policy, raw, key, game):
        game.screen = executor_pins.command_screen(raw["turn"])
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason})
        self.assertTrue(sent, port.last_result)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.phase, "command")
        policy.confirm_key_posted(key)
        return parse_snapshot(copy.deepcopy(game.state), self.monraces)

    # -- facts ---------------------------------------------------------------

    def test_table_is_the_town_files(self):
        """Every smith of SMITHS as lib/edit/towns writes it; none in the played Outpost."""
        rows = {}
        for town in range(5):
            path = find_town_map(town + 1, GAME)
            text = _strip_jsonc(path.read_text(encoding="utf-8"))
            for index, fields in re.findall(
                    r'"index":\s*(\d+),\s*"locale":\s*"en",\s*"command":\s*"A",\s*'
                    r'"fields":\s*\[([^\]]*)\]', text):
                values = re.findall(r'"([^"]*)"', fields)
                if values[1] == "Enchant armor":
                    self.assertEqual((values[4], values[5], values[6]), ("a", "24", "0"))
                    rows.setdefault(town, []).append(
                        (int(index), int(values[2]), int(values[3])))
                    self.assertIsNotNone(parse_town_map(path).building_position(int(index)))
        self.assertEqual(rows, {
            town: [(smith.building, smith.member_price, smith.other_price) for smith in smiths]
            for town, smiths in armor_smith.SMITHS.items()})
        self.assertNotIn(0, armor_smith.SMITHS)

    def test_shown_modifier_only_from_a_known_name(self):
        _policy, _row, board = self.read_board()
        feet = next(item for item in board.equipment if item.slot == "feet")
        self.assertEqual(armor_smith.shown_modifier(feet), -6)
        # flavor-describer.cpp describe_ac: an unknown protector shows [ac] only.
        unknown = replace(feet, known=False, name=re.sub(r"\[6,-6\]", "[6]", feet.name))
        self.assertEqual(unknown.to_a, -6)
        self.assertIsNone(armor_smith.shown_modifier(unknown))

    # -- the recall read -----------------------------------------------------

    @staticmethod
    def line_at(gold):
        """DECLARED: the line moved, not the recorded 17,700 gold: more gold on this
        board reopens the visit's shopping, which is the purchase-first order."""
        return mock.patch.object(armor_smith, "GOLD_LINE", gold)

    def test_above_the_line_goes_to_the_smith(self):
        """The played Outpost has no smith: the inn's teleport, then the read."""
        policy, _row, board = self.read_board()
        self.assertEqual(board.player.gold, RECORDED_GOLD)
        self.assertIn(1, board.visited_town_ids)
        with self.line_at(RECORDED_GOLD - TOWN_TELEPORT_COST):
            self.decide(policy, board)
        self.assertTrue(policy.last_reason.startswith(armor_smith.TRAVEL_REASON), policy.last_reason)
        self.assertEqual(armor_smith.state(policy).origin, 0)

    def test_below_the_line_reads_the_recall(self):
        policy, row, board = self.read_board()
        with self.line_at(RECORDED_GOLD + 1):
            key = self.decide(policy, board)
        self.assertEqual((key, policy.last_reason), (row["key"], row["reason"]))

    def test_the_fare_counts_against_the_line(self):
        policy, row, board = self.read_board()
        with self.line_at(RECORDED_GOLD - TOWN_TELEPORT_COST + 1):
            key = self.decide(policy, board)
        self.assertEqual((key, policy.last_reason), (row["key"], row["reason"]))

    def test_a_reserve_above_the_line_is_respected(self):
        policy, row, board = self.read_board()
        with (self.line_at(1), mock.patch.object(
                type(policy), "_full_departure_resupply_reserve",
                lambda *_a: RECORDED_GOLD)):
            key = self.decide(policy, board)
        self.assertEqual((key, policy.last_reason), (row["key"], row["reason"]))

    def test_at_cap_reads_the_recall(self):
        policy, row, board = self.read_board()
        board = self.with_names(board, {
            "arms": next(it.name for it in board.equipment if it.slot == "arms").replace("[5,+1]", "[5,+7]"),
            "feet": next(it.name for it in board.equipment if it.slot == "feet").replace("[6,-6]", "[6,+7]"),
        })
        with self.line_at(1):
            key = self.decide(policy, board)
        self.assertEqual((key, policy.last_reason), (row["key"], row["reason"]))

    def test_no_route_reads_the_recall(self):
        """Not a departure condition: a refused leg ends the errand."""
        policy, row, board = self.read_board()
        with (self.line_at(1),
              mock.patch.object(type(policy), "_town_teleport_key", lambda *_a, **_k: None)):
            key = self.decide(policy, board)
        self.assertEqual((key, policy.last_reason), (row["key"], row["reason"]))
        self.assertTrue(armor_smith.state(policy).closed)

    def test_home_comes_first(self):
        """A rich visit's Home row keeps the board: the smith waits for the read."""
        with self.rings_already_repaired():
            _policy, recorded, _steps = self.load("ring-departure")
        index = next(i for i, row in enumerate(recorded) if str(row["reason"]).startswith("home"))
        shutil.rmtree(self.scratch / "ring-departure")
        with self.rings_already_repaired(), self.line_at(1):
            policy, recorded, steps = self.replay("ring-departure", index)
            key = policy.choose_key(steps[index][1]())
        self.assertEqual((key, policy.last_reason), (recorded[index]["key"], recorded[index]["reason"]))
        self.assertIsNone(armor_smith.state(policy).origin)

    # -- the whole trip ------------------------------------------------------

    def test_whole_trip(self):
        """Read board, walk to the inn, teleport, walk to the smith, raises, back, read.

        Live n1-b life-310, n1-c life-140: one travel key, then the read.  The walk
        to the inn is still in the town the trip started from.
        """
        with self.rings_already_repaired():
            policy, recorded, steps = self.replay("ring-departure", READ_ROW)
        outpost = json.loads(recorded[READ_ROW]["line"] or recorded[READ_ROW]["inputs"][-1])
        # DECLARED: Telmora is the listed town the board's character goes to.
        outpost["progress"]["visited_town_ids"] = [0, 1]
        game = TripGame({0: outpost, 1: copy.deepcopy(self.q2["board"])}, self.maps)
        game.screen = executor_pins.command_screen(outpost["turn"])
        reasons = []
        with self.rings_already_repaired(), self.line_at(LINE):
            for _decision in range(60):
                _game, _client, executor = self.make(game)
                self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
                port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
                board = parse_snapshot(copy.deepcopy(game.state), policy._monrace_knowledge)
                key = policy.choose_key(board)
                self.assertIsNotNone(key)
                reason = policy.last_reason
                if not reasons or reasons[-1] != reason:
                    reasons.append(reason)
                sent, _line = _send_new_decision_key(
                    port, "trip-board", key, None, set(), in_store=False,
                    decision={"sequence": policy._decision_sequence, "reason": reason})
                self.assertTrue(sent, (reason, key, port.last_result))
                self.assertEqual(port.last_result.outcome, "completed", (reason, key))
                policy.confirm_key_posted(key)
                if game.fares == 2:
                    break
        names = [name.removesuffix("-step-off") for name in reasons]
        names = [name for index, name in enumerate(names) if index == 0 or names[index - 1] != name]
        self.assertEqual(names, [armor_smith.TRAVEL_REASON, armor_smith.APPROACH_REASON,
                                 armor_smith.RAISE_REASON, armor_smith.RETURN_REASON])
        self.assertEqual(game.town, 0)
        # 17,700 - 500 = 17,200, then 16,600 and 16,000 still pay; 15,400 stops.
        self.assertEqual(game.raised, ["feet"] * 3)
        self.assertEqual(game.state["player"]["gold"], 15400 - TOWN_TELEPORT_COST)
        feet = next(it for it in game.state["equipment"] if it["slot"] == "feet")
        self.assertIn("[6,-3]", feet["name"])
        stay = armor_smith.state(policy)
        self.assertTrue(stay.travelled)

        # Back on the Outpost: the errand ends and is not started again.
        landed = parse_snapshot(copy.deepcopy(game.state), policy._monrace_knowledge)
        with self.line_at(1):
            self.assertIsNone(armor_smith.trip_key(policy, landed))
            self.assertIsNone(armor_smith.town_key(policy, landed))
        self.assertIsNone(stay.origin)

        # The read: the recorded board with this stay.  DECLARED: the return's fresh
        # visit (its shops and Home have no reply in TripGame) is replaced by the
        # recorded visit's rows.
        shutil.rmtree(self.scratch / "ring-departure")
        policy, row, read = self.read_board()
        policy._armor_smith_stay = stay
        with self.line_at(1):
            key = self.decide(policy, read)
        self.assertEqual((key, policy.last_reason), (row["key"], row["reason"]))

    # -- the smith's town ----------------------------------------------------

    def test_30600_raises_the_lowest_through_the_executor(self):
        policy, raw, board = self.smith_town(30600)
        with mock.patch("hengbot.me_staff_sequence.town_key", lambda *_a: None):
            key = policy.choose_key(board)
            self.assertEqual(policy.last_reason, armor_smith.RAISE_REASON)
            self.assertEqual(key[1:], "a/la/l\x1b")  # 30,600 and 30,000 pay; 29,400 stops
            game = SmithHookGame(raw)
            after = self.post(policy, raw, key, game)
            self.assertEqual(game.posted, [key[0], "a", "/", "l", "a", "/", "l", "\x1b"])
            self.assertEqual(game.raised, ["feet", "feet"])
            self.assertEqual(after.player.gold, 29400)
            self.assertEqual(armor_smith.shown_modifier(
                next(it for it in after.equipment if it.slot == "feet")), -4)
            policy.choose_key(after)
            self.assertTrue(policy.last_reason.startswith(armor_smith.RETURN_REASON), policy.last_reason)

    def test_29999_leaves_the_smith(self):
        policy, _raw, board = self.smith_town(29999)
        with mock.patch("hengbot.me_staff_sequence.town_key", lambda *_a: None):
            policy.choose_key(board)
        self.assertTrue(policy.last_reason.startswith(armor_smith.RETURN_REASON), policy.last_reason)

    def test_chooser_opening_on_the_equipment(self):
        policy, raw, board = self.smith_town(30600, pack_armour=False)
        with mock.patch("hengbot.me_staff_sequence.town_key", lambda *_a: None):
            key = policy.choose_key(board)
            game = SmithHookGame(raw)
            self.post(policy, raw, key, game)
        self.assertEqual(game.posted, [key[0], "a", "l", "a", "l", "\x1b"])
        self.assertEqual(game.raised, ["feet", "feet"])

    def test_refused_attempt_does_not_loop(self):
        """The game refuses (a constructed lower cap): nothing charged, no second try."""
        policy, raw, board = self.smith_town(500000)
        with mock.patch("hengbot.me_staff_sequence.town_key", lambda *_a: None):
            key = policy.choose_key(board)
            self.assertEqual(policy.last_reason, armor_smith.RAISE_REASON)
            # feet -6 -> +7 is 13 raises, arms +1 -> +7 is 6: lowest first.
            self.assertEqual(re.findall(r"a/(.)", key).count("l"), 13)
            self.assertEqual(re.findall(r"a/(.)", key).count("k"), 6)
            game = SmithHookGame(raw, cap=-99)
            after = self.post(policy, raw, key, game)
            self.assertEqual(game.raised, [])
            self.assertEqual(after.player.gold, 500000)
            policy.choose_key(after)
            self.assertTrue(policy.last_reason.startswith(armor_smith.RETURN_REASON), policy.last_reason)


if __name__ == "__main__":
    unittest.main()
