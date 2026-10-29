"""Magic-Eater power list on the spectator page (owner request 2026-10-30).

Screens are DECLARED CONSTRUCTED from cmd-magiceat.cpp's list display: the
header on row 1 ("使用回数 失率" / "  状態   失率"), then entries in two
40-cell columns, each "<label> {name:<22}    {cur:2}/{max:2} {fail:3}%" for a
staff or wand and " {name:<22} 充填:{c:2}/{n:2}{fail:3}%" (Japanese) or
" {name:<22}   ({c:2}/{n:2}) {fail:3}%" (English) for a rod.
"""
import tests  # noqa: F401 -- isolate live runtime files

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot.magic_eater_input import MagicEaterStep, _answer, observed_power_list
from hengbot.model import parse_snapshot
from hengbot.spectator import SpectatorWriter
from tests import test_spectator as replay
from tests.test_magic_eater_o3 import powers


def cells(text):
    return sum(2 if ord(ch) > 0x7f else 1 for ch in text)


def pad(name, width=22):
    return name + " " * (width - cells(name))


def device(label, name, cur, count, fail):
    return f"{label} {pad(name)}    {cur:2}/{count:2} {fail:3}%"


def rod(label, name, charging, count, fail, *, japanese=True):
    if japanese:
        return f"{label} {pad(name)} 充填:{charging:2}/{count:2}{fail:3}%"
    return f"{label} {pad(name)}   ({charging:2}/{count:2}) {fail:3}%"


def two_columns(left, right=""):
    return left + " " * (40 - cells(left)) + right if right else left


def wand_list_screen():
    screen = powers(japanese=True)
    screen["lines"][1] = ("                           使用回数 失率"
                          "                           使用回数 失率")
    # Column 1 holds the first half of the sval range; Magic Missile (sval 15)
    # is in the second column.  "a)" is an empty, still absorbed wand.
    screen["lines"][2] = two_columns(device("a)", "モンスター回復", 0, 1, 12),
                                     device("p)", "マジック・ミサイル", 9, 17, 35))
    screen["lines"][17] = ""
    return screen


def raw_board(class_id, **extra):
    raw = json.loads(replay._recorded_lines(1)[0])
    raw["player"]["class_id"] = class_id
    raw.update(extra)
    return raw


def write(writer, raw):
    writer.observe(parse_snapshot(raw, {}), "5", "pin", 1, None,
                   state_line=json.dumps(raw))
    writer.last_write = None
    return json.loads(writer.path.read_text(encoding="utf-8"))


WAND_LIST = {"kind": "wand", "rows": [
    {"name": "モンスター回復", "fail": 12, "success": 88, "current": 0, "max": 1},
    {"name": "マジック・ミサイル", "fail": 35, "success": 65, "current": 9, "max": 17},
]}


class PowerListParseTest(unittest.TestCase):
    def test_japanese_wand_list_two_columns(self):
        lines = tuple(wand_list_screen()["lines"])
        self.assertEqual(observed_power_list(lines), WAND_LIST)

    def test_rod_list_japanese_and_english(self):
        for japanese, header in ((True, "  状態   失率"), (False, "  Stat   Fail")):
            with self.subTest(japanese=japanese):
                lines = [""] * 24
                lines[1] = " " * 27 + header
                name = "罠と扉感知" if japanese else "Door/Trap Location"
                lines[2] = two_columns(rod("a)", name, 1, 2, 20, japanese=japanese),
                                       rod("b)", "Illumination" if not japanese else "光源",
                                           0, 1, 5, japanese=japanese))
                self.assertEqual(observed_power_list(lines), {"kind": "rod", "rows": [
                    {"name": name, "fail": 20, "success": 80, "charging": 1, "max": 2},
                    {"name": "Illumination" if not japanese else "光源",
                     "fail": 5, "success": 95, "charging": 0, "max": 1}]})

    def test_menu_cursor_rows(self):
        lines = [""] * 24
        lines[1] = " " * 27 + " Charges Fail"
        lines[2] = two_columns(device("  ", "Heal Monster", 1, 1, 10),
                               device("> ", "Magic Missile", 3, 17, 35))
        self.assertEqual([row["name"] for row in observed_power_list(lines)["rows"]],
                         ["Heal Monster", "Magic Missile"])

    def test_prompt_without_list_is_not_an_observation(self):
        screen = powers(japanese=True)
        screen["lines"][17] = ""
        self.assertIsNone(observed_power_list(tuple(screen["lines"])))

    def test_executor_answer_keeps_the_displayed_list(self):
        operation = SimpleNamespace(observation={})
        step = MagicEaterStep(frozenset(), "6", stage="power")
        self.assertEqual(_answer(step, wand_list_screen(), operation), ("p", "aim"))
        self.assertEqual(operation.magic_eater_wand_charges, 9)
        self.assertEqual(operation.magic_eater_power_list, WAND_LIST)


class SpectatorFrameTest(unittest.TestCase):
    def test_magic_eater_frame_unobserved_then_kept_with_turn(self):
        with TemporaryDirectory() as tmp:
            writer = SpectatorWriter(Path(tmp) / "spectate.json")
            raw = raw_board(16)
            self.assertEqual(write(writer, raw)["magic_eater_powers"],
                             {"staff": None, "wand": None, "rod": None})
            observed = dict(raw, _magic_eater_power_list=WAND_LIST)
            turn = observed["turn"]
            expected = {"staff": None, "wand": {"turn": turn, "rows": WAND_LIST["rows"]},
                        "rod": None}
            self.assertEqual(write(writer, observed)["magic_eater_powers"], expected)
            # Later boards carry no list: the last observed one stays, with its turn.
            later = dict(raw, turn=turn + 50)
            self.assertEqual(write(writer, later)["magic_eater_powers"], expected)
            # A new life (turn restarts) forgets the old list.
            reborn = dict(raw, turn=1)
            self.assertEqual(write(writer, reborn)["magic_eater_powers"]["wand"], None)

    def test_warrior_frame_unchanged(self):
        with TemporaryDirectory() as tmp:
            raw = raw_board(0)
            plain = write(SpectatorWriter(Path(tmp) / "a.json"), raw)
            listed = write(SpectatorWriter(Path(tmp) / "b.json"),
                           dict(raw, _magic_eater_power_list=WAND_LIST))
            self.assertNotIn("magic_eater_powers", plain)
            for frame in (plain, listed):
                frame.pop("time")
            self.assertEqual(plain, listed)


if __name__ == "__main__":
    unittest.main()
