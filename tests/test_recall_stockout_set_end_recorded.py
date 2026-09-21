"""Recorded pins: the D1 recall-stockout time-pass vs the D2 gold set-end.

2026-09-21 19:33:56-19:38:42 (one bot process, 1431 decisions).  Back in town
at 18,365 gold with recall 9/10 and no actionable supplier, the stockout run
started on a supplier page and the every-town-return gold set-end cleared it on
the next decision; stockout/shop alternated until the owner retired.

Substrate: every recorded decision of the process lifetime, replayed through
the public response path on one policy (tests/extract_recall_stockout_set_end_
fixture.py).  Walls, each on a collaborator that is not under test:
- policy_combat.CHOKE_ENGAGEMENT_MIN_DAMAGE_RATIO = 0.0 restores the choke
  combat code the live process ran (the floor landed after the incident);
- the recorded periodic save/dump decisions receive the CLI timer request
  that produced them;
- Home history/disposal files and the calibration file live in a temporary
  directory (the calibration file is the one the process loaded).
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import shutil
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.cli import _consume_response_sequence
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.home_disposal import HomeDisposalState
from hengbot.model import STORE_HOME
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
# Decisions whose replayed (key, reason) differ from the recorded ones before
# the stockout start: 501-503 (a mid-run equipment-transaction Home trip) and
# 1417-1421 (a travel interruption the live executor reported).  The replay
# re-converges after each and matches 1422-1425 exactly.
KNOWN_HARNESS_DIVERGENCES = {501, 502, 503, 1417, 1418, 1419, 1420, 1421}
STOCKOUT_START = 1425


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
        """Drive the recorded lifetime through decision 1425, then decide 1426.

        1425's recorded key (ESC out of the supplier page) is also the key the
        replay posts, so 1426's recorded input is the true effect of that key.
        """
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
                for index in range(STOCKOUT_START + 1):
                    count = cls.boundaries["input_rows"][index]
                    segment = cls.lines[cursor : cursor + count]
                    cursor += count
                    _decoded, snapshots = _consume_response_sequence(
                        segment, policy, lambda _key: True, monrace,
                        knowledge_ledger_path=directory / "knowledge.jsonl",
                    )
                    snapshot = snapshots[-1]
                    if index == STOCKOUT_START:
                        break
                    recorded_reason = cls.boundaries["recorded"][index][1]
                    if recorded_reason == "periodic:game-save":
                        policy.request_game_save()
                    elif recorded_reason == "periodic:character-dump":
                        policy.request_character_dump()
                    key = policy.choose_key(snapshot)
                    decisions[index + 1] = (str(key), policy.last_reason)
                    policy.confirm_key_posted(key)
                # S2 decides the same 1426 input on an identical copy of the
                # replayed policy (the S1 decision below mutates the original).
                resolved_policy = copy.deepcopy(policy)
                # Decide 1426 inside the same wall and directory.
                key = policy.choose_key(snapshot)
                result = (
                    policy, decisions, snapshot,
                    (str(key), policy.last_reason),
                    {
                        "mode": policy._fundraising_mode,
                        "planned_runs": policy._planned_mining_runs,
                        "completed_runs": policy._mining_runs_completed,
                        "visit_store": policy._shopping_approach_store_type,
                        "cross_town": policy._cross_town_shopping,
                        "recall": next(
                            row for row in policy.procurement_requirements(snapshot)
                            if row["item"] == "Word of Recall scrolls"
                        ),
                    },
                )
                # S2 board: the same recorded 1426 input with the recall
                # shortage resolved (two more scrolls carried).
                resolved = replace(snapshot, inventory=type(snapshot.inventory)(
                    replace(entry, count=entry.count + 2)
                    if entry.is_recall_scroll else entry
                    for entry in snapshot.inventory
                ))
                resolved_persists = resolved_policy._recall_stockout_persists(
                    resolved
                )
                resolved_key = resolved_policy.choose_key(resolved)
                cls.replay = result + (
                    resolved_persists,
                    (str(resolved_key), resolved_policy.last_reason),
                    resolved_policy._fundraising_mode,
                    resolved_policy._recall_stockout_mining_plan,
                )
        return cls.replay

    def test_s0_replay_matches_recorded_lifetime_through_stockout_start(self):
        _policy, decisions, *_rest = self._replay()
        recorded = self.boundaries["recorded"]
        divergent = {
            sequence
            for sequence, decided in decisions.items()
            if list(decided) != recorded[sequence - 1]
        }
        self.assertEqual(divergent, KNOWN_HARNESS_DIVERGENCES)
        self.assertEqual(
            [decisions[sequence] for sequence in range(1422, STOCKOUT_START + 1)],
            [
                ("1", "melee"),
                ("1", "seek-loot"),
                ("\x1b`n#.", "shop:travel"),
                ("\x1b", "town:recall-stockout-mining"),
            ],
        )

    def test_s1_recorded_stockout_run_survives_next_town_decision(self):
        _policy, _decisions, snapshot, decided_1426, state, *_rest = self._replay()

        self.assertEqual(snapshot.player.gold, 18365)
        # Live 1426: ('1', 'shop:approach') with fundraising.mode None.  The
        # time-pass now keeps its run and heads Home for its D3 kit.
        self.assertEqual(decided_1426, ("\x1b`n(.", "shop:travel"))
        self.assertEqual(state["mode"], "prepare")
        self.assertEqual(state["planned_runs"], 1)
        self.assertEqual(state["completed_runs"], 0)
        self.assertEqual(state["visit_store"], STORE_HOME)
        # Still a stockout: recall 9/10 (prepare-mode target), no supplier.
        recall = state["recall"]
        self.assertEqual(
            (recall["current"], recall["target"], recall["blocked_reason"]),
            (9, 10, "no-actionable-supplier"),
        )

    def test_s4_no_cross_town_shopping_is_started(self):
        _policy, _decisions, _snapshot, decided_1426, state, *_rest = self._replay()

        self.assertIsNone(state["cross_town"])
        self.assertFalse(decided_1426[1].startswith("cross-town"))

    def test_s2_resolved_recall_shortage_ends_the_set_at_gold_target(self):
        (
            _policy, _decisions, _snapshot, _decided, _state,
            resolved_persists, resolved_decision, mode, flag,
        ) = self._replay()

        self.assertFalse(resolved_persists)
        self.assertIsNone(mode, resolved_decision)
        self.assertFalse(flag)


if __name__ == "__main__":
    unittest.main()
