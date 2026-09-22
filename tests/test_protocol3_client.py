"""Pins: the client reads bot JSON protocol 3 and still replays protocol 2.

Protocol 3 (hengband tools/bot/README.md "版3での変更") exposes exactly what a
human perceives: it removed item ``fuel`` / ``timeout``, ``player.skills`` and
``stats.<stat>.cur`` and turned ``grid_map.palette[][1]`` into the lighting
variant.  User decisions (verbatim): 「過不足無く出力する仕様」; exact ``turn``
「例外として残す（推奨）」; ``show_actual_value`` 「有効にする（推奨）」.

Substrates:
- P1: the recorded 41F capture (tests/fixtures/esp-threat-rest-20260921.jsonl.gz,
  protocol 2) and its DERIVED protocol-3 twin
  (esp-threat-rest-20260921.protocol3.jsonl.gz), produced from it by
  tests/derive_protocol3_fixture.py exactly as the changelog specifies.  A
  restarted bot decides the same recorded input row from each.
- P2/P3: the recorded decision-1 input board of the same capture, derived by
  the same script; single keys are then replaced by the protocol-3 values the
  pin names.
Walls: Home history/disposal and calibration files live in a temporary
directory (tests.test_esp_threat_rest_recorded._policy).
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from derive_protocol3_fixture import derive_item, derive_lines, derive_row
from hengbot.cli import _consume_response_sequence, _newest_snapshot_entry
from hengbot.model import TVAL_LITE, TVAL_ROD, _parse_items, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.protocol import ProtocolSchemaError
from hengbot.warrior_optimization import CharacterCalibration
from test_esp_threat_rest_recorded import (
    CALIBRATION,
    EDIT,
    FIXTURE,
    FIXTURE_SHA256,
    _policy,
)

FIXTURES = Path(__file__).parent / "fixtures"
DERIVED = FIXTURES / "esp-threat-rest-20260921.protocol3.jsonl.gz"
DERIVED_SHA256 = "32c959daa3cd7ad25a9e3165855cc2014d4aa614b9e51598fe84fccbd95953d6"

# (sequence, recorded key, recorded reason) of dungeon decisions a restarted
# bot makes from the recorded input row (41F, Angband).
DUNGEON_DECISIONS = (
    (200, "rf", "esp-threat:leave-recall"),
    (400, "5", "return:wait-recall"),
    (625, "8", "explore"),
)
# A town decision: the equipment evaluators need two_weapon / shield skill_exp,
# which the protocol-3 board does not print (only the ~f list does).
TOWN_DECISION = (500, "\x1b`n(.", "shop:travel")


def _read_lines(path: Path) -> list[str]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return list(stream)


class _Substrate:
    loaded = None

    @classmethod
    def get(cls):
        if cls.loaded is None:
            assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
            assert hashlib.sha256(DERIVED.read_bytes()).hexdigest() == DERIVED_SHA256
            v2 = _read_lines(FIXTURE)
            v3 = _read_lines(DERIVED)
            boundaries = json.loads(
                FIXTURE.with_suffix(".boundaries.json").read_text(encoding="utf-8")
            )
            starts = [0]
            for count in boundaries["input_rows"]:
                starts.append(starts[-1] + count)
            monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
            cls.loaded = (v2, v3, starts, monrace)
        return cls.loaded


def _board(lines: list[str], index: int = 0) -> dict:
    rows = [json.loads(line) for line in lines]
    return [row for row in rows if row.get("type") == "player_turn"][index]


class DerivedFixtureTest(unittest.TestCase):
    def test_derived_fixture_is_the_script_output_of_the_recorded_capture(self):
        v2, v3, _starts, _monrace = _Substrate.get()
        self.assertEqual(derive_lines(v2), v3)
        self.assertTrue(all(json.loads(line)["protocol_version"] == 3 for line in v3))
        self.assertTrue(all(json.loads(line)["protocol_version"] == 2 for line in v2))


class P1SameDecisionTest(unittest.TestCase):
    """P1: the same recorded decision under v2 and under the derived v3 row."""

    def _decide(self, lines, sequence):
        _v2, _v3, starts, monrace = _Substrate.get()
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            policy = _policy(directory, monrace)
            segment = lines[starts[sequence - 1] : starts[sequence]]
            _decoded, snapshots = _consume_response_sequence(
                segment, policy, lambda _key: True, monrace,
                knowledge_ledger_path=directory / "knowledge.jsonl",
            )
            key = policy.choose_key(snapshots[-1])
            return snapshots[-1], (str(key), policy.last_reason)

    def test_p1_dungeon_decisions_match_under_v2_and_derived_v3(self):
        v2, v3, _starts, _monrace = _Substrate.get()
        for sequence, key, reason in DUNGEON_DECISIONS:
            with self.subTest(sequence=sequence):
                board2, decided2 = self._decide(v2, sequence)
                board3, decided3 = self._decide(v3, sequence)
                self.assertEqual(board2.protocol_version, 2)
                self.assertEqual(board3.protocol_version, 3)
                self.assertEqual(decided2, (key, reason))
                self.assertEqual(decided3, (key, reason))

    def test_p1_town_decision_fails_loudly_without_skill_exp(self):
        v2, v3, _starts, _monrace = _Substrate.get()
        sequence, key, reason = TOWN_DECISION
        self.assertEqual(self._decide(v2, sequence)[1], (key, reason))
        with self.assertRaisesRegex(ProtocolSchemaError, "two_weapon_skill"):
            self._decide(v3, sequence)


class P2UnknownProtocolTest(unittest.TestCase):
    def setUp(self):
        v2, v3, _starts, self.monrace = _Substrate.get()
        self.v3_row = _board(v3)

    def test_p2_unknown_protocol_versions_fail_loudly(self):
        for version in (1, 4, 99, "3", None, True, 3.0):
            with self.subTest(version=version):
                row = dict(self.v3_row, protocol_version=version)
                with self.assertRaises(ProtocolSchemaError):
                    parse_snapshot(row, self.monrace)

    def test_p2_cli_does_not_swallow_an_unknown_protocol_as_malformed(self):
        row = dict(self.v3_row, protocol_version=4)
        line = json.dumps(row, ensure_ascii=False)
        with self.assertRaises(ProtocolSchemaError):
            _newest_snapshot_entry([line], self.monrace)

    def test_rows_without_protocol_version_parse_as_protocol_2(self):
        v2, _v3, _starts, _monrace = _Substrate.get()
        row = _board(v2)
        del row["protocol_version"]
        self.assertEqual(parse_snapshot(row, self.monrace).protocol_version, 2)


class P3RemovedKeyReplacementTest(unittest.TestCase):
    """P3: each removed key is read from its protocol-3 replacement."""

    def setUp(self):
        v2, _v3, _starts, self.monrace = _Substrate.get()
        self.v2_row = _board(v2)
        self.v3_row = derive_row(self.v2_row)

    def _parse(self, row):
        return parse_snapshot(row, self.monrace)

    def test_p3_fuel_is_read_from_light_turns(self):
        row = copy.deepcopy(self.v3_row)
        lantern = {
            "slot": "z", "name": "真鍮のランタン(1419ターンの寿命)", "count": 1,
            "tval": TVAL_LITE, "sval": 1, "aware": True, "known": True,
            "fully_known": True, "charging": False, "light_turns": 1419,
        }
        row["inventory"] = [lantern]
        item = self._parse(row).inventory[0]
        self.assertEqual((item.fuel, item.light_turns, item.timeout), (1419, 1419, None))
        # The removed key is never consulted: a stale raw value is ignored.
        row["inventory"] = [dict(lantern, fuel=0)]
        self.assertEqual(self._parse(row).inventory[0].fuel, 1419)
        # A known light that prints its life must carry light_turns.
        del lantern["light_turns"]
        row["inventory"] = [lantern]
        with self.assertRaisesRegex(ProtocolSchemaError, "light_turns"):
            self._parse(row)

    def test_p3_recorded_fuel_survives_the_round_trip(self):
        # Recorded light sources (torch 2500, lantern 4667; an older emitter
        # row, items only) and a recorded protocol-2 oil flask (7500).
        with open(FIXTURES / "descend-in-place-2026-07-18-0124-snapshots.jsonl",
                  encoding="utf-8") as stream:
            board = json.loads(stream.readline())
            lights = board["inventory"] + board["equipment"]
        with gzip.open(
            FIXTURES / "incident-20260920-1025-restore-blocked-count-identity.jsonl.gz",
            "rt", encoding="utf-8",
        ) as stream:
            flasks = json.loads(stream.readline())["inventory"]
        recorded = [
            item for item in lights + flasks
            if item.get("known") and item.get("tval") in (TVAL_LITE, 77)
        ]
        v2 = _parse_items(recorded, protocol=2)
        v3 = _parse_items([derive_item(item) for item in recorded], protocol=3)
        self.assertEqual(
            sorted({(item.tval, item.sval, item.fuel) for item in v2}),
            [(39, 0, 2500), (39, 1, 4667), (77, 0, 7500)],
        )
        self.assertEqual([item.fuel for item in v3], [item.fuel for item in v2])
        self.assertTrue(all(item.timeout is None for item in v3))

    def test_p3_timeout_is_read_from_charging(self):
        row = copy.deepcopy(self.v3_row)
        rod = {
            "slot": "z", "name": "識別のロッド(2本 充填中)", "count": 3,
            "tval": TVAL_ROD, "sval": 2, "aware": True, "known": True,
            "fully_known": True, "charging": True, "charging_count": 2,
        }
        row["inventory"] = [rod]
        item = self._parse(row).inventory[0]
        self.assertEqual((item.charging, item.charging_count, item.timeout), (True, 2, None))
        row["inventory"] = [dict(rod, charging=False, charging_count=0, timeout=50)]
        self.assertFalse(self._parse(row).inventory[0].charging)
        del rod["charging"]
        row["inventory"] = [rod]
        with self.assertRaisesRegex(ProtocolSchemaError, "charging"):
            self._parse(row)

    def test_p3_skills_are_derived_from_skill_ratings(self):
        # Independent arithmetic of calc_skill_rating_sources():
        #   dex index 24 -> ADJ_DEX_TO_H 5, str index 23 -> ADJ_STR_TO_H 3,
        #   blessed +10, ring +5  => to_h_m = to_h_b = 23;
        #   bow (+7), 3 lb, not heavy => shooting terms 23 + 7 = 30.
        row = copy.deepcopy(self.v3_row)
        player = row["player"]
        player["stats"]["dex"]["index"] = 24
        player["stats"]["str"]["index"] = 23
        player["status_bar"] = [{"id": 36, "key": "blessed", "label": "祝福"}]
        player["status"]["stun_rank_name"] = "none"
        for key, value in {
            "fighting": 200, "shooting": 150, "saving_throw": 75,
            "magic_device": 26, "stealth": 8,
        }.items():
            player["skill_ratings"][key]["value"] = value
        row["equipment"] = [
            {"slot": "main_ring", "name": "ring", "count": 1, "tval": 45, "sval": 0,
             "aware": True, "known": True, "charging": False, "to_h": 5},
            {"slot": "bow", "name": "bow", "count": 1, "tval": 19, "sval": 13,
             "aware": True, "known": True, "charging": False, "to_h": 7, "weight": 30,
             "weapon_proficiency": 0, "weapon_proficiency_rank": 0},
        ]
        state = self._parse(row).player
        self.assertEqual(state.melee_skill, 200 - 3 * 23)
        self.assertEqual(state.shooting_skill, 150 - 3 * 30)
        self.assertEqual(
            (state.saving_skill, state.device_skill, state.stealth_skill), (75, 26, 8)
        )
        self.assertEqual((state.two_weapon_skill, state.shield_skill), (None, None))
        # The removed player.skills is never consulted.
        player["skills"] = {"melee": 0, "shooting": 0, "saving": 0, "device": 0}
        self.assertEqual(self._parse(row).player.melee_skill, 131)
        del player["skill_ratings"]["fighting"]["value"]
        with self.assertRaisesRegex(ProtocolSchemaError, "show_actual_value"):
            self._parse(row)

    def test_p3_recorded_skills_survive_the_round_trip(self):
        v2 = self._parse(self.v2_row).player
        v3 = self._parse(self.v3_row).player
        for name in ("melee_skill", "shooting_skill", "saving_skill", "device_skill", "stealth_skill"):
            with self.subTest(name=name):
                self.assertEqual(getattr(v3, name), getattr(v2, name))
        self.assertEqual((v2.melee_skill, v2.shooting_skill), (194, 148))

    def test_p3_stat_cur_is_replaced_by_the_printed_stats(self):
        v2 = self._parse(self.v2_row).player
        v3 = self._parse(self.v3_row).player
        self.assertIsNone(v3.stat_cur)
        self.assertEqual(v3.stat_max, v2.stat_max)
        self.assertEqual(v3.stat_use, v2.stat_use)
        self.assertEqual(v3.stat_index, v2.stat_index)
        self.assertEqual(v3.stat_top, v2.stat_use)  # undrained: top == use
        self.assertEqual(v3.printed_stat_cur_key, v2.stat_cur)
        row = copy.deepcopy(self.v3_row)
        row["player"]["stats"]["str"]["cur"] = 3  # removed key: ignored
        self.assertEqual(self._parse(row).player.stat_max, v2.stat_max)
        del row["player"]["stats"]["str"]["top"]
        with self.assertRaisesRegex(ProtocolSchemaError, "top"):
            self._parse(row)

    def test_p3_calibration_staleness_under_the_printed_stats(self):
        calibration = json.loads(CALIBRATION.read_text(encoding="utf-8"))
        v3 = self._parse(self.v3_row).player
        recorded = CharacterCalibration(
            race_id=v3.race_id, class_id=v3.class_id,
            personality_id=v3.personality_id, level=v3.level,
            stat_cur=tuple(calibration["stat_cur"]),
            base_stats=tuple(calibration["base_stats"]), base_hp=1,
            base_ac_bonus=0, intrinsic_abilities=frozenset(),
        )
        self.assertEqual(recorded.stale_reason(v3, ()), None)
        row = copy.deepcopy(self.v3_row)
        row["player"]["stats"]["con"]["drained"] = True
        drained = self._parse(row).player
        self.assertEqual(recorded.stale_reason(drained, ()), "stat_cur")

    def test_p3_palette_slot_one_is_lighting_not_cave_bits(self):
        row = copy.deepcopy(self.v3_row)
        palette = row["grid_map"]["palette"]
        tunnel_bit = 1 << 15  # terrain_bits order: ... trap, tunnel, ...
        index = next(
            i for i, entry in enumerate(palette)
            if entry[3] and not entry[2] & tunnel_bit
            and any(r[3] == i for r in row["grid_map"]["runs"])
        )
        palette[index][1] = 1  # lit; as CAVE bits this would be ``mark``
        run = next(r for r in row["grid_map"]["runs"] if r[3] == index)
        snapshot = self._parse(row)
        grid = next(
            g for g in snapshot.grids.values()
            if (g.position.y, g.position.x) == (run[0], run[1])
        )
        self.assertEqual(grid.map_lighting, 1)
        self.assertEqual(
            (grid.marked, grid.lit, grid.in_view, grid.glow, grid.mnlt, grid.mndk),
            (False, False, False, False, False, False),
        )
        palette[index][1] = 2  # dark: never cave_known
        self.assertEqual(self._parse(row).grids[grid.position].map_lighting, 2)
        palette[index][1] = 4
        with self.assertRaisesRegex(ProtocolSchemaError, "lighting"):
            self._parse(row)

    def test_proficiency_rank_without_number_fails_loudly(self):
        row = copy.deepcopy(self.v3_row)
        weapon = next(item for item in row["equipment"] if item["slot"] == "main_hand")
        self.assertEqual(self._parse(row).equipment[0].weapon_proficiency, 6452)
        self.assertEqual(self._parse(row).equipment[0].weapon_proficiency_rank, 2)
        del weapon["weapon_proficiency"]
        with self.assertRaisesRegex(ProtocolSchemaError, "show_actual_value"):
            self._parse(row)


class SnapshotShapeTest(unittest.TestCase):
    def setUp(self):
        _v2, v3, _starts, self.monrace = _Substrate.get()
        self.v3_row = _board(v3)

    def test_new_types_are_never_boards(self):
        board = json.dumps(self.v3_row, ensure_ascii=False)
        for kind, payload in (
            ("spell_list", {"spell_list": {"realm_id": 1, "spells": []}}),
            ("power_list", {"power_list": {"kind": "racial", "page": 0, "powers": []}}),
            ("lore", {"lore": {"race_id": 1, "name": "x", "text": "y"}}),
        ):
            with self.subTest(kind=kind):
                response = dict(self.v3_row, type=kind, **payload)
                line = json.dumps(response, ensure_ascii=False)
                snapshot, chosen = _newest_snapshot_entry([board, line], self.monrace)
                self.assertEqual(chosen, board)
                with self.assertRaises(ProtocolSchemaError):
                    parse_snapshot(response, self.monrace)

    def test_more_than_32_messages_are_kept(self):
        row = dict(self.v3_row, messages=[f"m{i}" for i in range(40)])
        self.assertEqual(len(parse_snapshot(row, self.monrace).messages), 40)

    def test_new_screen_fields_are_parsed(self):
        row = copy.deepcopy(self.v3_row)
        row["player"].update(max_exp=900, exp_drained=True, max_level=33, level_drained=False)
        row["player"]["status_bar"] = [{"id": 37, "key": "heroism", "label": "H"}]
        row["player"]["status"].update(cut_rank=2, stun_rank=1)
        row["clock"] = {"day": None, "hour": 13, "minute": 5}
        row["floor"]["dungeon_name"] = "アングバンド"
        row["health_bar"] = {"known": True, "index": 7, "length": 4, "color": "red",
                             "conditions": ["fast"]}
        snapshot = parse_snapshot(row, self.monrace)
        player = snapshot.player
        self.assertEqual(
            (player.max_exp, player.exp_drained, player.max_level, player.level_drained),
            (900, True, 33, False),
        )
        self.assertEqual(player.status_bar, ("heroism",))
        self.assertEqual((player.cut_rank, player.stun_rank), (2, 1))
        self.assertEqual(player.speed_display[3], False)
        self.assertEqual(snapshot.clock, (None, 13, 5))
        self.assertEqual(snapshot.dungeon_name, "アングバンド")
        self.assertEqual(snapshot.health_bar, (True, 7, 4, "red", ("fast",)))


if __name__ == "__main__":
    unittest.main()
