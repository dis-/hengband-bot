import tests  # noqa: F401 -- live runtime-file isolation, also for bare module runs

import unittest
from pathlib import Path

from hengbot.model import Position
from hengbot.town_maps import TownMap, parse_town_map


EDIT = Path(r"C:\hengband\lib\edit")
TOWN_FILES = (
    "01_Outpost_Full", "01_Outpost_Lite", "01_Outpost_OnlyAngband",
    "02_Telmora", "03_Morivant", "04_Angwil", "05_Zul",
    "06_Rlyeh_Obsoleted",
)


def _definitions(text):
    floors, buildings, quest_entrances, quest_buildings, rewards = set(), {}, {}, {}, set()
    for line in text.splitlines():
        if not line.startswith("F:"):
            continue
        parts = line.split(":")
        if len(parts) < 3:
            continue
        symbol, terrain = parts[1], parts[2]
        special = int(parts[9]) if len(parts) > 9 and parts[9].isdigit() else 0
        if terrain == "FLOOR":
            floors.add(symbol)
            if len(parts) > 5 and parts[5].isdigit() and int(parts[5]) > 0:
                rewards.add(symbol)
        if terrain.startswith("BUILDING_"):
            buildings[symbol] = int(terrain.removeprefix("BUILDING_"))
            if special > 0:
                quest_buildings.setdefault(symbol, set()).add(special)
        if terrain == "QUEST_ENTER" and special > 0:
            quest_entrances[symbol] = special
    return floors, buildings, quest_entrances, quest_buildings, rewards


def _legacy_map(path, rows):
    preferences = path.parent.parent / "TownPreferences.txt"
    pref_text = preferences.read_text(encoding="utf-8-sig", errors="replace")
    map_text = path.read_text(encoding="utf-8-sig", errors="replace")
    floors, buildings, quest_entrances, quest_buildings, rewards = _definitions(
        pref_text + "\n" + map_text
    )
    walkable, stores, building_positions = set(), {}, {}
    entrance = None
    quest_building_positions, quest_entrance_positions, reward_positions = {}, {}, set()
    for y, row in enumerate(rows):
        for x, symbol in enumerate(row):
            pos = Position(y, x)
            if symbol in "12345678":
                stores[int(symbol) - 1] = pos
                walkable.add(pos)
            elif symbol in buildings:
                building_positions[buildings[symbol]] = pos
                walkable.add(pos)
            elif symbol in ".,<>" or symbol in floors:
                walkable.add(pos)
            if symbol in quest_entrances:
                quest_entrance_positions.setdefault(quest_entrances[symbol], set()).add(pos)
                walkable.add(pos)
            for quest_id in quest_buildings.get(symbol, set()):
                quest_building_positions.setdefault(quest_id, set()).add(pos)
            if symbol in rewards:
                reward_positions.add(pos)
            if symbol == ">":
                entrance = pos
    return TownMap(
        name=path.stem,
        width=max(map(len, rows)),
        height=len(rows),
        walkable=frozenset(walkable),
        stores=stores,
        buildings=building_positions,
        quest_buildings={key: frozenset(value) for key, value in quest_building_positions.items()},
        quest_entrances={key: frozenset(value) for key, value in quest_entrance_positions.items()},
        reward_positions=frozenset(reward_positions),
        entrance=entrance,
    )


def _legacy_rows(path):
    return [
        line[2:] for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        if line.startswith("D:")
    ]


class RealTownJsoncParityTest(unittest.TestCase):
    def test_every_legacy_pair_matches_and_rlyeh_variants_match_each_half(self):
        if not EDIT.is_dir():
            self.skipTest("real Hengband lib/edit data is unavailable")

        for name in TOWN_FILES[:-1]:
            with self.subTest(town=name):
                legacy_path = EDIT / "towns" / f"{name}.txt"
                jsonc_path = EDIT / "towns" / f"{name}.jsonc"
                self.assertTrue(legacy_path.is_file(), f"missing {legacy_path}")
                self.assertTrue(jsonc_path.is_file(), f"missing {jsonc_path}")
                legacy = _legacy_map(legacy_path, _legacy_rows(legacy_path))
                self.assertEqual(parse_town_map(jsonc_path), legacy)

        name = TOWN_FILES[-1]
        legacy_path = EDIT / "towns" / f"{name}.txt"
        jsonc_path = EDIT / "towns" / f"{name}.jsonc"
        self.assertTrue(legacy_path.is_file(), f"missing {legacy_path}")
        self.assertTrue(jsonc_path.is_file(), f"missing {jsonc_path}")
        rows = _legacy_rows(legacy_path)
        self.assertEqual(len(rows), 132)
        self.assertEqual(parse_town_map(jsonc_path, {17: 1}), _legacy_map(legacy_path, rows[:66]))
        self.assertEqual(parse_town_map(jsonc_path, {17: 0}), _legacy_map(legacy_path, rows[66:]))
        self.assertEqual(parse_town_map(jsonc_path), parse_town_map(jsonc_path, {17: 0}))


if __name__ == "__main__":
    unittest.main()
