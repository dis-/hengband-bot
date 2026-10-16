import tests  # noqa: F401 -- live runtime-file isolation, also for bare module runs

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hengbot.cli import _build_argument_parser
from hengbot.model import Position
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.town_maps import parse_town_map
from hengbot.wilderness_map import find_wilderness_definition, load_wilderness_map


_LEGEND = (
    '{"legend": {'
    '"#": {"terrain": "PERMANENT"}, '
    '".": {"terrain": "FLOOR"}, '
    '">": {"terrain": "ENTRANCE", "special": 2}, '
    '"1": {"terrain": "GENERAL_STORE"}}}'
)


def _write_town(root: Path, variants: str) -> Path:
    edit = root / "lib" / "edit"
    (edit / "towns").mkdir(parents=True)
    (edit / "TownPreferences.jsonc").write_text(_LEGEND, encoding="utf-8")
    town = edit / "towns" / "99_Test.jsonc"
    town.write_text(
        '{"version": 2, "featureRules": [], "mapVariants": [' + variants + "]}",
        encoding="utf-8",
    )
    return town


class JsoncDataLoaderTest(unittest.TestCase):
    def test_cli_documents_jsonc_paths(self):
        actions = {option: action for action in _build_argument_parser()._actions
                   for option in action.option_strings}
        self.assertIn("01_Outpost_Full.jsonc", actions["--outpost-map"].help)
        self.assertIn("JSONC", actions["--quest-definitions"].help)

    def test_town_map_variant_follows_the_quest_status_condition(self):
        with TemporaryDirectory() as directory:
            town = _write_town(
                Path(directory),
                '{"when": "[EQU $QUEST17 1]", "rows": ["#1>#"]}, '
                '{"when": "[EQU $QUEST17 0 2 3 4]", "rows": ["#1.#"]}',
            )
            completed = parse_town_map(town, {17: 1})
            self.assertEqual(completed.entrance, Position(0, 2))
            self.assertIsNone(parse_town_map(town).entrance)
            self.assertIsNone(parse_town_map(town, {17: 3}).entrance)
            with self.assertRaises(ValueError):
                parse_town_map(town, {17: 5})

    def test_town_map_rejects_the_legacy_text_format(self):
        with TemporaryDirectory() as directory:
            legacy = Path(directory) / "01_Outpost_Full.txt"
            legacy.write_text("N:test\nD:#1>#\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_town_map(legacy)

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
