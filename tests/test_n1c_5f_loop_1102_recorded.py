"""n1c-5f-loop-1102: the recorded n1-c life-100 Yeek cave 5F loop (2026-11-02).

n1-c life-100 (Magic-Eater, Lv8, 133 max HP, build dc64cf14a) on イークの洞窟5階
stopped twice for ``loop-detected`` (01:59:56 and 02:00:03) between (39,16)
and (38,17).  At (38,17) the sleeping グリーン・ナーガ (race 94) at (38,25)
came into view and the material-engagement gate retreated to (39,16)
(``threat:avoid-engagement``, turn 550773), claiming (38,17) as an
engagement-avoid cell — a navigation veto for the floor visit ("A committed
explore path otherwise walks straight back here").  Out of view again, the
descent route ignored that veto and stepped straight back to (38,17)
(``approach-descent`` '9', turn 550782), 40 times.

The descent router now honours the floor's engagement-avoid cells like every
other routing BFS: no descent step enters a cell the retreat vetoed.

Fixture: tests/fixtures/n1c-5f-loop-20261102.json.gz
(tests/extract_n1c_5f_loop_1102_fixture.py).  Every decision is the public
``choose_key`` and every posted key goes through the production executor port;
the next recorded board is the executor's board after the posted key.
DECLARED RECONSTRUCTED: the staff sequence record is the capture's
``_me_staff_sequence``.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import Position
from tests import test_d57_nav_depth_1101_recorded as nav


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-5f-loop-20261102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
RETREAT_TURN, RETURN_TURN = 550773, 550782
VETOED, RETREAT_CELL = Position(38, 17), Position(39, 16)
DESCENT_REASONS = {"approach-descent", "seek-downstairs"}


def staff_screen_case():
    """The case whose absorbed record keys the staff power screen by sval.

    The capture's record keys absorbed devices as ``staff:<sval>`` (the policy
    reads it as is); the recorded drive lists the power screen rows by sval."""
    absorbed = {key.split(":")[1]: count
                for key, count in CASE["sequence"]["absorbed"].items()}
    return dict(CASE, sequence=dict(CASE["sequence"], absorbed=absorbed))


NAGA_RACE = 94


def awake_naga(raw):
    """DECLARED: a copy of ``raw`` with the green naga awake."""
    raw = json.loads(json.dumps(raw))
    for monster in (*raw["visible_monsters"], *raw.get("detected_monsters", [])):
        if monster["race_id"] == NAGA_RACE:
            monster["asleep"] = False
    return raw


def recorded():
    return {row["turn"]: (row["reason"], row["key"]) for row in CASE["decisions"]}


class FiveFloorLoopRecordedTest(nav.RecordedDrive):
    def test_recorded_rows_alternate_between_retreat_and_descent(self):
        rows = recorded()
        self.assertEqual(rows[RETREAT_TURN], ("threat:avoid-engagement", "1"))
        self.assertEqual(rows[RETURN_TURN], ("approach-descent", "9"))
        loop = [rows[raw["turn"]][0] for raw in CASE["boards"]
                if raw["turn"] >= RETREAT_TURN]
        self.assertEqual(set(loop), {"threat:avoid-engagement", "approach-descent"})
        self.assertEqual(len(loop), 39)
        stand = {raw["turn"]: Position(raw["player"]["y"], raw["player"]["x"])
                 for raw in CASE["boards"]}
        self.assertEqual(stand[RETREAT_TURN], VETOED)
        self.assertEqual(stand[RETURN_TURN], RETREAT_CELL)

    def test_descent_never_steps_back_onto_the_vetoed_cell(self):
        # DECLARED CONSTRUCTED: the naga awake.  Asleep, as recorded, it is no
        # longer retreated from (a sleeping monster does not close in; n1-c
        # life-153, tests/test_maze_seal_1106_recorded), and the retreat's veto
        # is what this test routes the descent around.
        boards = [awake_naga(raw) for raw in CASE["boards"] if raw["turn"] <= RETURN_TURN]
        policy = nav.new_policy(CASE, boards)
        rows = self.drive_boards(staff_screen_case(), boards, policy)
        by_turn = {raw["turn"]: (key, reason) for raw, key, reason in rows}
        self.assertEqual(by_turn[RETREAT_TURN][1], "threat:avoid-engagement")
        self.assertIn(VETOED, policy._engagement_avoid_cells)
        raw = boards[-1]
        key, reason = by_turn[RETURN_TURN]
        step = nav.step_of(raw, key)
        self.assertFalse(reason in DESCENT_REASONS and step == VETOED,
                         (RETURN_TURN, key, reason))
        for raw, key, reason in rows:
            if raw["turn"] > RETREAT_TURN and reason in DESCENT_REASONS:
                self.assertNotIn(nav.step_of(raw, key), policy._engagement_avoid_cells,
                                 (raw["turn"], key, reason))


if __name__ == "__main__":
    unittest.main()
