"""Replay the life-014 town board where 闇の陣笠 stayed worn (#101, light type 6th).

USER DECISION 2026-10-23 「合計で比べる」: the optimizer compares the light
radius of the whole loadout.  Linux soak c4-a/life-014 (Level 32-36, 30F):
the worn 闇の陣笠 (ego 闇の, TR_LITE_M1 + TR_RES_DARK) turned the radius 2 of
the 不朽の眼のフェアノールのランプ into 1 on every recorded board, and the dark
30F floors were never fully explored.

Fixture tests/fixtures/light-total-20261021.jsonl.gz (rows copied as-is):

  0, 2-8: state rows 0-7 of c4-a/life-014/captures/
          20261021-045344-town-blocked-departure-unsatisfiable (town, Level 32,
          turn 3446622): board, store page, board, board, C screen, board,
          the ~9 Home list (row 7), board.  Worn 闇の陣笠 [4,+6] {r暗;闇} and the
          lamp (board light_radius 1); Home holds 鋼鉄ヘルメット [6,+5].
  1:      DECLARED CONSTRUCTED: the ~f skill list of row 1 of
          20261021-193733-town-blocked-departure-unsatisfiable (same character,
          Level 33, turn 4167280) on a copy of row 0 (the 04:53 capture holds
          no ~f row; every head candidate is evaluated with the same skills).

tests/fixtures/light-total-20261021.character-calibration.json is the
character-calibration.json of life-014 (Level 32, turn 3503519) as written.

The Home list row is adopted as the reply of ~9 (consume_home_knowledge),
then the optimizer is prepared on the last board.  The live loadout report
(life-014 jsonlog/loadout-report.jsonl, 2026-10-21T04:58:41, same catalog)
ranked the worn set first (combat margin 2.546831250168902) and the
鋼鉄ヘルメット set third (2.553026284150141): both lie in the existing 1%
margin band, where the current set won the tie.  The total radius is compared
before that tie breaker, as the #86 radius was; no weight is added.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence, _parse_items
from hengbot.equipment_optimizer import SLOT_HEAD, loadout_light_radius
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.warrior_optimization import load_character_calibration
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "light-total-20261021.jsonl.gz"
SHA256 = "a3591cf81c8c23d2d72da736cf4fc82471fb49d8312384bee4f13cf6d6d3e180"
CALIBRATION = FIXTURES / "light-total-20261021.character-calibration.json"
CALIBRATION_SHA256 = (
    "7e2f33687aea22a6a7f7e80b82cdce9975b1281dca8be3b69831d8832366f95a"
)
HOME_ROW = 7
DARK_HELM = "闇の陣笠 [4,+6] {r暗;闇}"
STEEL_HELM = "鋼鉄ヘルメット [6,+5]"
STEEL_HELM_ID = "home:65b3bfbbf227e45e:0"
TR_LITE_M1 = 124
WORN_MARGIN = 2.546831250168902
STEEL_MARGIN = 2.553026284150141


def _rows():
    data = FIXTURE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SHA256
    return [json.loads(line) for line in gzip.decompress(data).decode("utf-8").splitlines()]


def _head(row):
    return next(item for item in row["equipment"] if item["slot"] == "head")


class LightTotalRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        assert hashlib.sha256(CALIBRATION.read_bytes()).hexdigest() == (
            CALIBRATION_SHA256
        )
        cls.recorded = cls._select(_rows())

    @classmethod
    def _select(cls, rows):
        """Feed the rows, adopt the Home list, prepare the optimizer."""
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy = _policy(directory, cls.monrace)
            policy._crossarea_fundraising_enforced = True
            policy._character_calibration = load_character_calibration(CALIBRATION)
            policy._character_calibration_loaded = True
            board = None
            for row in rows:
                _decoded, snapshots = _consume_response_sequence(
                    [json.dumps(row, ensure_ascii=False)], policy,
                    lambda _key: True, cls.monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                if row.get("type") != "player_turn":
                    continue
                board = snapshots[-1]
                policy.confirm_key_posted(policy.choose_key(board))
            policy.consume_home_knowledge(tuple(
                _parse_items(rows[HOME_ROW]["knowledge"]["items"], protocol=3)
            ))
            preparation = policy._prepare_equipment_optimization(
                policy.with_known_skill_exp(board)
            )
        assert preparation is not None and not preparation.blockers
        return preparation

    def test_fixture_is_the_recorded_board_and_home_list(self):
        rows = _rows()
        self.assertEqual(
            [row["type"] for row in rows],
            ["player_turn", "knowledge", "store", "player_turn", "player_turn",
             "character", "player_turn", "knowledge", "player_turn"],
        )
        board = rows[0]
        self.assertEqual(board["turn"], 3446622)
        self.assertEqual(board["player"]["light_radius"], 1)
        self.assertEqual(_head(board)["name"], DARK_HELM)
        self.assertEqual(_head(board)["known_flags"], [55, TR_LITE_M1])
        self.assertEqual(rows[1]["knowledge"]["category"], "skill_exp")
        home = rows[HOME_ROW]["knowledge"]
        self.assertEqual(home["category"], "home")
        self.assertIn(STEEL_HELM, [item["name"] for item in home["items"]])
        # The rule gives the board's radius for the worn set.
        self.assertEqual(loadout_light_radius(self.recorded.current), 1)

    def test_the_helmet_that_lowers_the_radius_is_not_selected(self):
        best = self.recorded.result.best
        head = best.loadout.item_at(SLOT_HEAD)
        # d2304637: the worn 闇の陣笠 (the recorded choice, margin 2.5468).
        self.assertEqual((head.id, head.item.name), (STEEL_HELM_ID, STEEL_HELM))
        self.assertEqual(loadout_light_radius(best.loadout), 2)
        self.assertAlmostEqual(best.metrics.combat_margin, STEEL_MARGIN)
        # Only the head changes.
        current = dict(self.recorded.current.slots)
        self.assertEqual(
            {slot: item.id for slot, item in best.loadout.slots if slot != SLOT_HEAD},
            {slot: item.id for slot, item in current.items() if slot != SLOT_HEAD},
        )

    def test_control_without_the_darkness_flag_the_worn_helmet_is_kept(self):
        rows = _rows()
        for row in rows:
            for item in row.get("equipment") or ():
                if item["slot"] == "head":
                    # DECLARED CONSTRUCTED: the worn helmet without TR_LITE_M1.
                    item["known_flags"] = [55]
        best = self._select(rows).result.best
        head = best.loadout.item_at(SLOT_HEAD)
        # As recorded: inside the 1% band the current set wins the tie.
        self.assertEqual(head.item.name, DARK_HELM)
        self.assertEqual(loadout_light_radius(best.loadout), 2)
        self.assertAlmostEqual(best.metrics.combat_margin, WORN_MARGIN)

    def test_a_same_stat_helmet_that_keeps_the_radius_replaces_the_worn_one(self):
        rows = _rows()
        home = rows[HOME_ROW]["knowledge"]["items"]
        # DECLARED CONSTRUCTED: the Home helmets (tval 32) replaced by one
        # copy of the worn helmet without TR_LITE_M1, in the Home slot of
        # 陣笠 [4,+1].  Other helmets would tie it (金属帽子 [3,+7] models the
        # same metrics) and hide which copy the search kept.
        copy = dict(_head(rows[0]))
        copy.update(
            slot=next(item["slot"] for item in home if item["name"] == "陣笠 [4,+1]"),
            name="陣笠 [4,+6] {r暗}", known_flags=[55],
        )
        rows[HOME_ROW]["knowledge"]["items"] = [
            copy if item["name"] == "陣笠 [4,+1]" else item
            for item in home
            if item["tval"] != 32 or item["name"] == "陣笠 [4,+1]"
        ]
        best = self._select(rows).result.best
        head = best.loadout.item_at(SLOT_HEAD)
        # d2304637: the worn 闇の陣笠 (one copy of the same stats, the current).
        self.assertEqual(head.item.name, "陣笠 [4,+6] {r暗}")
        self.assertEqual(loadout_light_radius(best.loadout), 2)
        self.assertAlmostEqual(best.metrics.combat_margin, WORN_MARGIN)


if __name__ == "__main__":
    unittest.main()
