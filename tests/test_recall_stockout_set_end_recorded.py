"""Recorded prefix pin for the recall-stockout process lifetime.

2026-09-21 19:33:56-19:38:42 (one bot process, 1431 decisions).  Back in town
at 18,365 gold with recall 9/10 and no actionable supplier, the stockout run
started on a supplier page and the every-town-return gold set-end cleared it on
the next decision; stockout/shop alternated until the owner retired.

Substrate: recorded decisions through the first changed loot move (1141),
replayed through the public response path on one policy
(tests/extract_recall_stockout_set_end_fixture.py). Later stockout boards are
counterfactual after that move, so this module does not assert their policy
state. Walls, each on a collaborator that is not under test:
- policy_combat.CHOKE_ENGAGEMENT_MIN_DAMAGE_RATIO = 0.0 restores the choke
  combat code the live process ran (the floor landed after the incident);
- the recorded periodic save/dump decisions receive the CLI timer request
  that produced them;
- Home history/disposal files and the calibration file live in a temporary
  directory (the calibration file is the one the process loaded).
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import gzip
import hashlib
import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.cli import _consume_response_sequence
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.home_disposal import HomeDisposalState
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
import hengbot.policy_combat as policy_combat
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from hengbot.terrain_knowledge import load_damaging_terrain_ids
from hengbot.town_maps import find_town_map, parse_town_map
from hengbot.wilderness_map import find_wilderness_definition, load_wilderness_map


GAME_ROOT = Path("C:/hengband")
EDIT = GAME_ROOT / "lib" / "edit"
FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "recall-stockout-set-end-20260921.jsonl.gz"
CALIBRATION = FIXTURES / "recall-stockout-set-end-20260921.character-calibration.json"
FIXTURE_SHA256 = "a18d5e6cec3e9a8ff5ea8d0ba997f201cdfbe4b1493933d69be615ff36911558"
BOUNDARIES_SHA256 = "53b906d917a7d0750feeb45dc6fb96eb2b18bfe1d50aebbcec274395f8f21d26"
CALIBRATION_SHA256 = "d470a028bdf04cfe5847fa11f28c2f17eafcbe92a07b4314eaf62dadd286edf7"


def _live_like_policy(directory: Path) -> tuple[HengbotPolicy, dict]:
    monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
    town_maps = {}
    for town_index in range(1, 6):
        path = find_town_map(town_index, GAME_ROOT)
        if path is not None:
            town_maps[town_index - 1] = parse_town_map(path)
    policy = HengbotPolicy(
        town_map=town_maps.get(0),
        town_maps=town_maps,
        wilderness_map=load_wilderness_map(find_wilderness_definition(GAME_ROOT)),
        dungeon_knowledge=load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc"),
        monrace_knowledge=monrace,
        damaging_terrain_ids=load_damaging_terrain_ids(EDIT / "TerrainDefinitions.jsonc"),
        quest_knowledge=load_quest_knowledge(
            find_quest_definitions(GAME_ROOT / "bot-client" / "state.jsonl")
        ),
        quest_strategies=load_quest_strategies(
            Path(__file__).resolve().parents[1] / "strategy" / "quests"
        ),
        home_disposal_state=HomeDisposalState(
            directory / "home-withdraw-history.jsonc",
            directory / "home-disposal-decisions.jsonc",
            directory / "home-disposal-queue.json",
            directory / "events.jsonl",
        ),
        baseitem_costs=load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc"),
    )
    calibration = directory / "character-calibration.json"
    shutil.copyfile(CALIBRATION, calibration)
    policy._character_calibration_path = calibration
    return policy, monrace


class RecallStockoutSetEndRecordedTest(unittest.TestCase):
    replay = None

    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        boundaries_path = FIXTURE.with_suffix(".boundaries.json")
        assert hashlib.sha256(boundaries_path.read_bytes()).hexdigest() == (
            BOUNDARIES_SHA256
        )
        assert hashlib.sha256(CALIBRATION.read_bytes()).hexdigest() == (
            CALIBRATION_SHA256
        )
        cls.boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        assert len(cls.lines) == sum(cls.boundaries["input_rows"])

    @classmethod
    def _replay(cls):
        """Drive recorded inputs only through the first changed loot move."""
        if cls.replay is not None:
            return cls.replay
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy, monrace = _live_like_policy(directory)
            decisions = {}
            cursor = 0
            snapshot = None
            with patch.object(
                policy_combat, "CHOKE_ENGAGEMENT_MIN_DAMAGE_RATIO", 0.0
            ):
                for index in range(1141):
                    count = cls.boundaries["input_rows"][index]
                    segment = cls.lines[cursor : cursor + count]
                    cursor += count
                    _decoded, snapshots = _consume_response_sequence(
                        segment, policy, lambda _key: True, monrace,
                        knowledge_ledger_path=directory / "knowledge.jsonl",
                    )
                    snapshot = snapshots[-1]
                    recorded_reason = cls.boundaries["recorded"][index][1]
                    if recorded_reason == "periodic:game-save":
                        policy.request_game_save()
                    elif recorded_reason == "periodic:character-dump":
                        policy.request_character_dump()
                    key = policy.choose_key(snapshot)
                    decisions[index + 1] = (str(key), policy.last_reason)
                    policy.confirm_key_posted(key)
                cls.replay = (policy, decisions)
        return cls.replay

    def test_replay_matches_recorded_prefix_until_loot_route_changes(self):
        _policy, decisions, *_rest = self._replay()
        recorded = self.boundaries["recorded"]
        divergent = {
            sequence
            for sequence, decided in decisions.items()
            if list(decided) != recorded[sequence - 1]
        }
        # The fallback removal leaves a fundraising loot route selectable at
        # 1141. On frozen later boards the changed keys recur over 1141-1144,
        # 1186-1188, 1282-1284, 1288-1289 and 1308. Only the first move is
        # a trajectory pin; later boards describe the old route.
        self.assertEqual(
            {sequence for sequence in divergent if sequence < 1141},
            {501, 502, 503},
        )
        self.assertIn(1141, divergent)
        self.assertEqual(recorded[1140], ["4", "fundraise:seek-loot"])
        self.assertEqual(decisions[1141][1], "fundraise:seek-loot")

if __name__ == "__main__":
    unittest.main()
