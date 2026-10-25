"""Colour and public side panels from one recorded board.

spectator-board.json is the first unchanged UTF-8 row (turn 8823126) of
anti-melee-death-20261023.jsonl.gz. Controls below are explicitly constructed
by varying only the missing/known fields under test.
"""
import tests  # noqa: F401

import copy
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from hengbot.control_client import ControlClient
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.spectator import SpectatorWriter, spectator_details
from tests import test_input_executor as executor_pins
from tests.test_esp_threat_rest_recorded import EDIT
from tests import test_spectator as spectator_pins

FIXTURE = Path(__file__).with_name("fixtures") / "spectator-board.json"


class SpectatorDetailsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.snapshot = parse_snapshot(
            cls.state, load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc"))

    def test_recorded_board_fields_are_decoded_and_projected(self):
        state = self.state
        before = copy.deepcopy(state)
        details = spectator_details(state, self.snapshot)
        self.assertEqual(set(details), {
            "equipment", "inventory", "monsters", "melee", "abilities", "status", "speed"})
        self.assertEqual(details["equipment"], [
            {"slot": item["slot"], "name": item["name"]} for item in state["equipment"]])
        self.assertEqual(details["inventory"], [
            {"slot": item["slot"], "name": item["name"], "count": item["count"]}
            for item in state["inventory"]])
        self.assertEqual(details["monsters"], [{
            "name": "\u9996\u306a\u3057\u9b3c", "distance": 1, "hp": None,
            "asleep": False, "stunned": False, "confused": False,
            "fearful": False, "friendly": False, "pet": False,
            "speed": self.snapshot.visible_monsters[0].speed}])
        expected_melee = dict(state["player"]["melee"])
        for item in state["equipment"]:
            if item["slot"] in ("main_hand", "sub_hand"):
                dice = item["damage_dice"]
                expected_melee[item["slot"] + "_dice"] = f"{dice['num']}d{dice['sides']}"
        self.assertEqual(details["melee"], expected_melee)
        self.assertEqual(details["status"], {
            "bar": state["player"]["status_bar"], "flags": [],
            "cut": "none", "stun": "none", "speed": state["player"]["speed_display"]})
        self.assertIn("\u9996", json.dumps(details, ensure_ascii=False))
        for source, target in (("ability_sources", "sources"),
                               ("immunities", "immunities"),
                               ("vulnerabilities", "vulnerabilities")):
            self.assertEqual(details["abilities"][target], {
                name: [key for key, value in values.items() if value is True]
                for name, values in state["player"][source].items() if any(values.values())})
        self.assertEqual(state, before)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spectate.json"
            writer = SpectatorWriter(path)
            self.assertTrue(writer.observe(self.snapshot, "6", "melee", 1, None,
                                           state_line=FIXTURE.read_text(encoding="utf-8")))
            written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(written["speed"], state["player"]["speed"])
        self.assertEqual(written["depth"], 45)
        self.assertEqual(written["dungeon"], 17)
        for key, value in details.items():
            self.assertEqual(written[key], value)

    def test_missing_old_emitter_fields_are_not_invented(self):
        self.assertEqual(spectator_details({"player": {}}), {})
        # DECLARED CONSTRUCTED: old emitter exports only status booleans.
        self.assertEqual(spectator_details({"player": {"status": {"blind": False}}}),
                         {"status": {"flags": []}})
        self.assertEqual(spectator_details({"equipment": [], "inventory": [],
                                            "visible_monsters": []}),
                         {"equipment": [], "inventory": [], "monsters": []})

    def test_active_sources_flags_dice_and_nearest_first_known_hp(self):
        # DECLARED CONSTRUCTED: explicit export values test the public projection.
        state = {"player": {
            "melee": {"mutation_blows": 2},
            "status": {"blind": True, "cut_rank": 1, "cut_rank_name": "graze"},
            "status_bar": [{"text": "blind", "color": "red"}],
            "ability_sources": {"telepathy": {"equipment": True, "temporary": True},
                                "free_action": {"equipment": False}},
            "immunities": {"fire": {"temporary": True}},
            "vulnerabilities": {"cold": {"permanent": True}}},
            "equipment": [{"slot": "main_hand", "damage_dice": {"num": 2, "sides": 4}},
                          {"slot": "sub_hand"}],
            "visible_monsters": [{"name": "far", "distance": 5, "hp": 7, "max_hp": 9},
                                 {"name": "near", "distance": 1, "hp": None}]}
        result = spectator_details(state)
        self.assertEqual(result["monsters"], [
            {"name": "near", "distance": 1, "hp": None},
            {"name": "far", "distance": 5, "hp": [7, 9]}])
        self.assertEqual(result["melee"], {"mutation_blows": 2, "main_hand_dice": "2d4"})
        self.assertEqual(result["abilities"], {
            "sources": {"telepathy": ["equipment", "temporary"]},
            "immunities": {"fire": ["temporary"]},
            "vulnerabilities": {"cold": ["permanent"]}})
        self.assertEqual(result["status"], {
            "flags": ["blind"], "cut": "graze", "bar": state["player"]["status_bar"]})

    def test_colour_request_is_inside_write_throttle_and_failure_isolated(self):
        clock = spectator_pins._Clock()
        screen = {"width": 2, "height": 1, "lines": ["ab"], "attrs": ["010e"]}
        client = Mock()
        client.request.return_value = screen
        stderr = io.StringIO()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spectate.json"
            writer = SpectatorWriter(path, clock=clock, stderr=stderr)
            self.assertTrue(writer.observe(self.snapshot, "6", "one", 1, None,
                                           screen_client=client))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["screen"], screen)
            clock.now += 0.5
            self.assertFalse(writer.observe(self.snapshot, "6", "two", 2, None,
                                            screen_client=client))
            client.request.assert_called_once_with("screen", term=0, attrs=True)
            clock.now += 0.5
            self.assertTrue(writer.observe(self.snapshot, "6", "three", 3, None,
                                           screen_client=client))
            self.assertEqual(client.request.call_count, 2)
            clock.now += 1
            client.request.side_effect = RuntimeError("transport")
            self.assertFalse(writer.observe(self.snapshot, "6", "four", 4, None,
                                            screen_client=client))
            self.assertIn("transport", stderr.getvalue())

    def test_no_colour_reply_keeps_observed_screen_and_bad_row_is_swallowed(self):
        client = Mock()
        client.request.return_value = None
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spectate.json"
            writer = SpectatorWriter(path, clock=spectator_pins._Clock(), stderr=io.StringIO())
            self.assertTrue(writer.observe(self.snapshot, "6", "one", 1, {"attrs": ["01"]},
                                           screen_client=client))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["screen"],
                             {"attrs": ["01"]})
            writer = SpectatorWriter(path, stderr=io.StringIO())
            self.assertFalse(writer.observe(self.snapshot, "6", "bad", 2, None,
                                            state_line="{"))


class SpectatorColourFollowTest(executor_pins.ProductionHarness):
    _replay = spectator_pins.SpectatorFollowReplayTest._replay

    def test_no_flag_no_colour_request_and_one_request_per_due_write(self):
        original = ControlClient.request
        colour_calls = []

        def request(client, op, **fields):
            if op == "screen" and fields.get("attrs") is True:
                colour_calls.append(fields)
            return original(client, op, **fields)

        with patch.object(ControlClient, "request", request):
            with TemporaryDirectory() as directory:
                self._replay(Path(directory), spectate=False)
            self.assertEqual(colour_calls, [])
            clock = spectator_pins._Clock()
            with TemporaryDirectory() as directory:
                self._replay(Path(directory), spectate=True, clock=clock)
                written = json.loads((Path(directory) / "spectate.json").read_text(encoding="utf-8"))
            self.assertEqual(len(colour_calls), 1)
            self.assertIn("equipment", written)
            self.assertIn("status", written)
            self.assertIn("abilities", written)


if __name__ == "__main__":
    unittest.main()
