"""Pins: awake detection-only monsters replace the interrupted rest (esp-threat-rest).

User-confirmed specification (2026-09-21/22, 「この仕様で発注」): when the player
wants to rest, awake monsters known only by telepathy/detection are tiered by
the sum of their per-action maximum damage over CURRENT HP -- below 10% hunt
them, 10-50% keep exploring, 50% and above kill if feasible with the permitted
supplies (Speed/Healing above a reserve of two each) else leave the floor.

Live incident: Angband 41F, 2026-09-21 22:45:39-22:48:39 (one bot process,
627 decisions): with the awake ESP group present every rest lasted one turn
until the loop detector stopped the bot.

Substrates:
- E1 lifetime: every recorded decision of the process replayed through the
  public response path on one policy (tests/extract_esp_threat_rest_fixture.py).
  Decisions 1..137 reproduce the recorded (key, reason) exactly; 138 is the
  first rest with an awake detected group and therefore the first faithful
  point of divergence.
- E1/E3 restart: a fresh policy (a bot restart on the parked game) decides the
  recorded input row of decision 625 / 555.
- E2-E8 boards: the lifetime policy after decision 137 (deep copies) and the
  recorded decision-138 input with only the change named in each test
  (detected list or one recorded monster re-raced, potion counts, stair
  underfoot, Free Action source).
Walls: Home history/disposal files and the calibration file live in a
temporary directory (the calibration file is the last preserved pre-run copy;
see the fixture provenance).  No wall touches the rest/tier/exit producers.
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

from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.cli import _consume_response_sequence
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.home_disposal import HomeDisposalState
from hengbot.model import (
    SV_POTION_CURE_CRITICAL,
    SV_POTION_HEALING,
    SV_POTION_SPEED,
    MonsterState,
    Position,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import REST_MACRO, UP_STAIRS_KEY, HengbotPolicy
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from hengbot.terrain_knowledge import load_damaging_terrain_ids
from hengbot.town_maps import find_town_map, parse_town_map
from hengbot.wilderness_map import find_wilderness_definition, load_wilderness_map


GAME_ROOT = Path("C:/hengband")
EDIT = GAME_ROOT / "lib" / "edit"
FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "esp-threat-rest-20260921.jsonl.gz"
CALIBRATION = FIXTURES / "esp-threat-rest-20260921.character-calibration.json"
FIXTURE_SHA256 = "cf8a4834fb54dcd5bbfe6e7ed08a7e649a80ec93cf58aed4f839cf886389d824"
BOUNDARIES_SHA256 = "be50146713bf4af3f4aa5922183951e68f409e51933977d525029a07e42cf4fa"
CALIBRATION_SHA256 = "d470a028bdf04cfe5847fa11f28c2f17eafcbe92a07b4314eaf62dadd286edf7"
FIRST_DETECTED_REST = 138
LOOP_REST = 625
FIRST_LOOP_REST = 555

WEAK = 230  # per-action maximum 22
HOUND = 338  # エア・ハウンド: melee 34, ranged 40
MONK = 870  # 黒衣の修行僧: melee 54, ranged 132
SUMMONER = 224  # can_summon, no paralysing blow
PARALYSER = 311  # PARALYZE blow, no summons
BREEDER = 529  # MULTIPLY, per-action maximum 100
WEAK_BREEDER = 1101  # MULTIPLY, per-action maximum 24
STRONG_KILLABLE = 545  # per-action maximum 190, 130 HP, speed 110


def _policy(directory: Path, monrace) -> HengbotPolicy:
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
    return policy


class EspThreatRestTest(unittest.TestCase):
    lifetime = None
    lifetime_base = None

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
        cls.starts = [0]
        for count in cls.boundaries["input_rows"]:
            cls.starts.append(cls.starts[-1] + count)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self._directory = TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.directory = Path(self._directory.name)

    def _consume(self, policy, sequence, directory):
        segment = self.lines[self.starts[sequence - 1] : self.starts[sequence]]
        _decoded, snapshots = _consume_response_sequence(
            segment, policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=directory / "knowledge.jsonl",
        )
        return snapshots[-1]

    @classmethod
    def _lifetime(cls):
        """Replay decisions 1..137 as recorded, then decide 138."""
        if cls.lifetime is not None:
            return cls.lifetime
        helper = cls("test_e1_lifetime_replays_recorded_until_first_detected_rest")
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy = _policy(directory, cls.monrace)
            decided = {}
            for sequence in range(1, FIRST_DETECTED_REST + 1):
                snapshot = helper._consume(policy, sequence, directory)
                if sequence == FIRST_DETECTED_REST:
                    # Boards decide on copies of the policy as it stood
                    # before the recorded decision-138 input was decided.
                    cls.lifetime_base = copy.deepcopy(policy)
                key = policy.choose_key(snapshot)
                decided[sequence] = [str(key), policy.last_reason]
                if sequence < FIRST_DETECTED_REST:
                    policy.confirm_key_posted(key)
                else:
                    break
            cls.lifetime = (
                decided,
                snapshot,
                policy._esp_threat_assessment,
                policy._last_return_trigger,
            )
        return cls.lifetime

    def _fresh(self, sequence):
        """A restarted bot decides the recorded input row of ``sequence``."""
        policy = _policy(self.directory, self.monrace)
        snapshot = self._consume(policy, sequence, self.directory)
        return policy, snapshot

    def _decide(self, policy, snapshot):
        key = policy.choose_key(snapshot)
        return key, policy.last_reason, policy._esp_threat_assessment

    def _as_race(self, monster: MonsterState, race_id: int, **changes):
        knowledge = self.monrace[race_id]
        return replace(
            monster,
            race_id=race_id,
            hp=knowledge.max_hp,
            max_hp=knowledge.max_hp,
            speed=knowledge.speed,
            can_summon=knowledge.can_summon,
            level=knowledge.level,
            max_melee_damage=knowledge.max_melee_damage,
            max_ranged_damage=knowledge.max_ranged_damage,
            can_multiply=knowledge.can_multiply,
            **changes,
        )

    @staticmethod
    def _with_potions(snapshot, **counts):
        svals = {
            "healing": SV_POTION_HEALING,
            "speed": SV_POTION_SPEED,
            "cure_critical": SV_POTION_CURE_CRITICAL,
        }
        by_sval = {svals[name]: count for name, count in counts.items()}
        inventory = [
            replace(item, count=by_sval[item.sval])
            if item.is_potion and item.sval in by_sval
            else item
            for item in snapshot.inventory
        ]
        return replace(
            snapshot,
            inventory=[item for item in inventory if item.count > 0],
        )

    # ------------------------------------------------------------- E1 live
    def test_e1_lifetime_replays_recorded_until_first_detected_rest(self):
        decided, *_rest = self._lifetime()
        recorded = self.boundaries["recorded"]
        self.assertEqual(
            [
                sequence
                for sequence in range(1, FIRST_DETECTED_REST)
                if decided[sequence] != recorded[sequence - 1]
            ],
            [],
        )
        self.assertEqual(recorded[FIRST_DETECTED_REST - 1], ["R&\r", "rest"])

    def test_e1_first_live_detected_rest_leaves_the_floor_by_recall(self):
        decided, snapshot, assessment, trigger = self._lifetime()

        self.assertEqual(snapshot.dungeon_level, 41)
        self.assertEqual(snapshot.visible_monsters, [])
        self.assertLess(snapshot.player.hp / snapshot.player.max_hp, 0.90)
        # Recorded: ('R&\r', 'rest').  STRONG (1010 / 379), not killable.
        self.assertEqual(
            decided[FIRST_DETECTED_REST], ["rf", "esp-threat:leave-recall"]
        )
        self.assertEqual(
            (assessment["tier"], assessment["strength"], assessment["hp"]),
            ("strong", 1010, 379),
        )
        self.assertFalse(assessment["feasibility"]["feasible"])
        self.assertEqual(assessment["action"], "leave")
        self.assertEqual(trigger, "esp-threat")
        recall = next(
            item for item in snapshot.inventory if item.slot == "f"
        )
        self.assertTrue(recall.is_recall_scroll)

    def test_e1_loop_board_restart_leaves_by_recall(self):
        policy, snapshot = self._fresh(LOOP_REST)
        self.assertEqual(self.boundaries["recorded"][LOOP_REST - 1], ["R&\r", "rest"])

        key, reason, assessment = self._decide(policy, snapshot)

        self.assertEqual((key, reason), ("rg", "esp-threat:leave-recall"))
        # 132 (monk) + 4 x 40 (hounds) over current HP 479; the asleep unique
        # (index 83, 202) is not counted.
        self.assertEqual(
            (assessment["tier"], assessment["strength"], assessment["hp"]),
            ("strong", 292, 479),
        )
        self.assertEqual(
            sorted(race for _index, race, _damage in assessment["monsters"]),
            [HOUND, HOUND, HOUND, HOUND, MONK],
        )
        self.assertNotIn(83, [index for index, *_ in assessment["monsters"]])
        feasibility = assessment["feasibility"]
        self.assertFalse(feasibility["feasible"])
        self.assertEqual(
            (feasibility["speed_spare"], feasibility["healing_spare"]), (8, 7)
        )
        self.assertTrue(
            next(item for item in snapshot.inventory if item.slot == "g")
            .is_recall_scroll
        )

    # ------------------------------------------------------------- E3 live
    def test_e3_first_loop_rest_medium_tier_keeps_exploring(self):
        policy, snapshot = self._fresh(FIRST_LOOP_REST)
        self.assertEqual(
            self.boundaries["recorded"][FIRST_LOOP_REST - 1], ["R&\r", "rest"]
        )

        key, reason, assessment = self._decide(policy, snapshot)

        # The monk alone: 132 / 355 = 37% -> MEDIUM: no rest, exploration.
        self.assertNotEqual(key, REST_MACRO)
        self.assertEqual(reason, "explore")
        self.assertEqual(
            (assessment["tier"], assessment["strength"], assessment["hp"]),
            ("medium", 132, 355),
        )
        self.assertEqual(assessment["action"], "explore")

    # -------------------------------------------------------------- boards
    # Boards: the lifetime policy after decision 137 (full floor memory) and
    # the recorded decision-138 input, with ONLY the named changes.  The
    # anchor is recorded detected monster 44 (distance 2, reachable).
    def _board(self, race_id=None, **snapshot_changes):
        _decided, snapshot, _assessment, _trigger = self._lifetime()
        policy = copy.deepcopy(self.lifetime_base)
        anchor = next(
            monster for monster in snapshot.detected_monsters
            if monster.index == 44
        )
        if race_id is not None:
            snapshot_changes.setdefault(
                "detected_monsters", [self._as_race(anchor, race_id)]
            )
        return policy, replace(snapshot, **snapshot_changes)

    def test_e2_weak_tier_hunts_then_rests(self):
        # Board: one awake 22-damage monster (22 / 379 = 6%).
        policy, board = self._board(WEAK)

        key, reason, assessment = self._decide(policy, board)

        self.assertEqual(reason, "esp-threat:hunt-weak")
        self.assertNotEqual(key, REST_MACRO)
        self.assertEqual(assessment["tier"], "weak")
        # Board: it has been dealt with -> the ordinary rest resumes.
        policy.confirm_key_posted(key)
        _unused, cleared = self._board(detected_monsters=[])
        key, reason, assessment = self._decide(policy, cleared)
        self.assertEqual((key, reason), (REST_MACRO, "rest"))
        self.assertIsNone(assessment)

    def test_e3_medium_board_does_not_rest(self):
        # Board: one awake hound (40 / 379 = 11%).
        policy, board = self._board(HOUND)

        key, reason, assessment = self._decide(policy, board)

        self.assertNotEqual(key, REST_MACRO)
        self.assertFalse(reason.startswith("esp-threat:"))
        self.assertEqual(
            (assessment["tier"], assessment["action"]), ("medium", "explore")
        )

    def test_e4_strong_feasible_hunts(self):
        # Board: one awake 190-damage, 130-HP, speed-110 monster (190 / 379 =
        # 50.1%) with the recorded 9 Healing / 10 Speed potions.
        policy, board = self._board(STRONG_KILLABLE)

        key, reason, assessment = self._decide(policy, board)

        self.assertEqual(reason, "esp-threat:hunt-strong")
        self.assertNotEqual(key, REST_MACRO)
        self.assertEqual(assessment["tier"], "strong")
        feasibility = assessment["feasibility"]
        self.assertTrue(feasibility["feasible"])
        self.assertEqual(
            (feasibility["speed_uses"], feasibility["healing_uses"]), (0, 4)
        )

    def test_e4_strong_infeasible_takes_stairs_underfoot(self):
        # Board: the recorded group with the player's grid an in-view up
        # staircase.
        _decided, snapshot, _assessment, _trigger = self._lifetime()
        here = snapshot.grid_at(snapshot.player.position)
        grids = dict(snapshot.grids)
        grids[here.position] = replace(here, has_up_stairs=True, in_view=True)
        policy, board = self._board(grids=grids)

        key, reason, assessment = self._decide(policy, board)

        self.assertEqual(
            (key, reason), (UP_STAIRS_KEY, "esp-threat:leave-ascend")
        )
        self.assertEqual(assessment["tier"], "strong")
        self.assertFalse(assessment["feasibility"]["feasible"])

    def test_e5_reserves_are_never_counted(self):
        # Boards: the E4 fight with changed potion counts.  Cure Critical
        # Wounds (10 carried) is never counted.
        _decided, snapshot, _assessment, _trigger = self._lifetime()
        outcomes = {}
        for healing, speed in ((2, 2), (3, 3), (4, 3), (4, 2)):
            policy, board = self._board(
                STRONG_KILLABLE,
                inventory=self._with_potions(
                    snapshot, healing=healing, speed=speed
                ).inventory,
            )
            key, reason, assessment = self._decide(policy, board)
            self.assertTrue(reason.startswith("esp-threat:"), reason)
            feasibility = assessment["feasibility"]
            outcomes[(healing, speed)] = (
                feasibility["healing_spare"],
                feasibility["speed_spare"],
                feasibility["feasible"],
                reason,
            )
            self.assertEqual(
                sum(
                    item.count for item in board.inventory
                    if item.is_potion and item.sval == SV_POTION_CURE_CRITICAL
                ),
                10,
            )
            if reason == "esp-threat:leave-recall":
                self.assertTrue(
                    next(item for item in board.inventory if item.slot == key[1:])
                    .is_recall_scroll
                )
        self.assertEqual(
            outcomes,
            {
                (2, 2): (0, 0, False, "esp-threat:leave-recall"),
                (3, 3): (1, 1, False, "esp-threat:leave-recall"),
                (4, 3): (2, 1, True, "esp-threat:hunt-strong"),
                (4, 2): (2, 0, False, "esp-threat:leave-recall"),
            },
        )

    def test_e6_only_asleep_detected_keeps_the_rest(self):
        # Board: every recorded detected monster asleep.
        _decided, snapshot, _assessment, _trigger = self._lifetime()
        policy, board = self._board(
            detected_monsters=[
                replace(monster, asleep=True)
                for monster in snapshot.detected_monsters
            ]
        )

        key, reason, assessment = self._decide(policy, board)

        self.assertEqual((key, reason), (REST_MACRO, "rest"))
        self.assertIsNone(assessment)

    def test_e7_summoner_and_paralyser_keep_existing_handling(self):
        policy, board = self._board(SUMMONER)
        key, reason, assessment = self._decide(policy, board)
        self.assertEqual((key, reason), (REST_MACRO, "rest"))
        self.assertIsNone(assessment)

        # Board: no Free Action source -> the existing paralyser handling.
        _decided, snapshot, _assessment, _trigger = self._lifetime()
        sources = dict(snapshot.player.ability_sources)
        sources.pop("free_action", None)
        policy, board = self._board(
            PARALYSER,
            player=replace(snapshot.player, ability_sources=sources),
        )
        key, reason, assessment = self._decide(policy, board)
        self.assertEqual((key, reason), (REST_MACRO, "rest"))
        self.assertIsNone(assessment)

        # Board: with the recorded Free Action a paralyser is ordinary (78 /
        # 379 = 21%, MEDIUM).
        policy, board = self._board(PARALYSER)
        key, reason, assessment = self._decide(policy, board)
        self.assertNotEqual(key, REST_MACRO)
        self.assertEqual(
            (assessment["tier"], assessment["action"]), ("medium", "explore")
        )

    def test_e7_breeders_are_hunted(self):
        # Boards: the anchor re-raced AND moved to the only emitted, out-of-
        # view, walkable cell 4-8 steps away (56, 74; distance 8): within
        # three steps the existing detected-breeder choke preparation owns
        # the decision before any rest check.
        _decided, snapshot, _assessment, _trigger = self._lifetime()
        anchor = next(m for m in snapshot.detected_monsters if m.index == 44)
        far = Position(56, 74)
        self.assertEqual(far.distance_to(snapshot.player.position), 8)
        self.assertFalse(snapshot.grid_at(far).in_view)

        def breeder(race_id):
            return [self._as_race(anchor, race_id, position=far, distance=8)]

        # One awake breeder whose 100 / 379 = 26% is MEDIUM.
        policy, board = self._board(detected_monsters=breeder(BREEDER))
        key, reason, assessment = self._decide(policy, board)
        self.assertEqual(reason, "esp-threat:hunt-medium")
        self.assertNotEqual(key, REST_MACRO)
        self.assertEqual(assessment["tier"], "medium")

        # A weak breeder (24 / 379 = 6%).
        policy, board = self._board(detected_monsters=breeder(WEAK_BREEDER))
        key, reason, assessment = self._decide(policy, board)
        self.assertEqual(
            (assessment["tier"], reason), ("weak", "esp-threat:hunt-weak")
        )

    def test_e8_no_detected_monster_keeps_the_rest(self):
        # Board: no detected monsters.
        policy, board = self._board(detected_monsters=[])
        key, reason, assessment = self._decide(policy, board)
        self.assertEqual((key, reason), (REST_MACRO, "rest"))
        self.assertIsNone(assessment)


if __name__ == "__main__":
    unittest.main()
