import tests  # noqa: F401 -- live runtime-file isolation, also for bare module runs

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import hengbot.wilderness_map as wilderness_map_module
from hengbot.cli import (
    _build_argument_parser,
    _initial_town_quest_statuses,
    _load_town_maps,
)
from hengbot.model import QuestState
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.town_maps import find_town_map, parse_town_map
from hengbot.wilderness_map import find_wilderness_definition, load_wilderness_map


EDIT = Path(r"C:\hengband\lib\edit")


class JsoncDataLoaderTest(unittest.TestCase):
    def test_wilderness_loader_documents_jsonc_only_input(self):
        self.assertEqual(
            wilderness_map_module.__doc__,
            "Static global-wilderness routing from Hengband's JSONC definition.",
        )
        self.assertIn("jsonc", load_wilderness_map.__doc__.casefold())

    def test_cli_documents_jsonc_paths(self):
        actions = {option: action for action in _build_argument_parser()._actions
                   for option in action.option_strings}
        self.assertIn("01_Outpost_Full.jsonc", actions["--outpost-map"].help)
        self.assertIn("JSONC", actions["--quest-definitions"].help)

    def test_startup_reads_quest_status_from_the_latest_board(self):
        snapshot = SimpleNamespace(quests={17: QuestState(id=17, status=1)})
        with (
            patch("hengbot.cli._read_last_snapshot_line", return_value=['{"board": true}']),
            patch("hengbot.cli.parse_snapshot", return_value=snapshot),
        ):
            self.assertEqual(_initial_town_quest_statuses(Path("state.jsonl"), None), {17: 1})

    def test_startup_loads_indexed_town_six_with_current_quest_status(self):
        if not EDIT.is_dir():
            self.skipTest("real Hengband lib/edit data is unavailable")
        snapshot = SimpleNamespace(quests={17: QuestState(id=17, status=1)})
        with (
            patch("hengbot.cli._read_last_snapshot_line", return_value=['{"board": true}']),
            patch("hengbot.cli.parse_snapshot", return_value=snapshot),
        ):
            _outpost, town_maps = _load_town_maps(EDIT, None, None)
        self.assertEqual(set(town_maps), {0, 1, 2, 3, 4, 5})
        town_six_path = find_town_map(6, EDIT)
        self.assertEqual(town_maps[5], parse_town_map(town_six_path, {17: 1}))
        self.assertEqual(town_maps[5].height, 66)

    def test_quest_helpers_accept_only_jsonc_sources(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "run" / "state.jsonl"
            state.parent.mkdir()
            quests = root / "quests"
            quests.mkdir()
            legacy = root / "QuestDefinitionList.txt"
            legacy.write_text("", encoding="utf-8")
            with patch("pathlib.Path.cwd", return_value=state.parent):
                self.assertIsNone(find_quest_definitions(state, legacy))
            with self.assertRaises(ValueError):
                load_quest_knowledge(legacy)
            (quests / "001_test.jsonc").write_text('{"id": 1}', encoding="utf-8")
            self.assertEqual(find_quest_definitions(state, quests), quests)

    def test_wilderness_helpers_discover_and_load_only_jsonc(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            edit = root / "lib" / "edit"
            edit.mkdir(parents=True)
            legacy = edit / "WildernessDefinition.txt"
            legacy.write_text("W:D:#", encoding="utf-8")
            with patch("pathlib.Path.cwd", return_value=root):
                self.assertIsNone(find_wilderness_definition(root))
            with self.assertRaises(ValueError):
                load_wilderness_map(legacy)
            jsonc = edit / "WildernessDefinition.jsonc"
            jsonc.write_text(
                '{"width": 3, "height": 1, "maps": '
                '{"normal": {"layout": ["#1#"]}}}',
                encoding="utf-8",
            )
            with patch("pathlib.Path.cwd", return_value=root):
                self.assertEqual(find_wilderness_definition(root), jsonc)
            self.assertEqual(load_wilderness_map(jsonc).rows, ("#1#",))


if __name__ == "__main__":
    unittest.main()
