"""hourly-0600-1102: the n1-c life-102 Morivant return stop (2026-11-02 05:10).

n1-c life-102 (Magic-Eater, Lv14, build bot-ff4196953) recharged and absorbed
its last staffs at the Tower of Sorcery in Morivant at night, and the staff
sequence took the inn leg home (``me-staff:return-outpost``, the game's
travel command toward the inn at (43,92)).  A puppy in view stopped the
travel at (28,63) (turn 2457605); the next decision found no route to the
inn and the sequence stopped (``quest:blocked:me-staff``, failure
``return-outpost-unavailable``), three times after the restarts, and the
character was retired.

At night Morivant shows only its lit grids, and the bot fills the unlit
cells from the static town map (policy_navigation._build_grid_index).  That
map took walkable cells from the floor glyphs only, but the JSONC towns draw
grass as '-' (GRASS, TownPreferences.jsonc), and Morivant is mostly grass:
the static map left the player on an island of lit grass with no way to the
inn.  GRASS has the game's MOVE and FLOOR flags like FLOOR and DIRT
(TerrainDefinitions.jsonc); the static map now walks it.

Fixture: tests/fixtures/me-staff-grass-route-1102.json.gz
(tests/extract_me_staff_grass_route_1102_fixture.py).  Every decision is the
public ``choose_key`` and every posted key goes through the production
executor port; the next recorded board is the executor's board after it.
DECLARED RECONSTRUCTED: the staff sequence record is the capture's
``_me_staff_sequence``; the wand power list the game showed at 05:09:44 ('mBp3')
holds the Stone to Mud wand (``wand:6``), so the carried one is not absorbed;
the town maps are the game's lib/edit/towns, as production loads them.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from pathlib import Path

from hengbot import me_staff_sequence
from tests import test_d57_nav_depth_1101_recorded as nav
from tests import test_me_staff_loops_1031_recorded as loops
from tests.test_surface_map_walks import _town_maps


FIXTURE = Path(__file__).with_name("fixtures") / "me-staff-grass-route-1102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
STOP_TURN = 2457605
RETURN_REASON = "me-staff:return-outpost"
TRAVEL_PREFIX = "\x1b`n"


def recorded_case():
    """The inn-leg boards with the reconstructed staff sequence record."""
    absorbed = dict(CASE["sequence"]["absorbed"], **{"wand:6": 12})
    return dict(CASE, sequence=dict(CASE["sequence"], absorbed=absorbed))


class MorivantGrassRouteRecordedTest(nav.RecordedDrive):
    def test_recorded_rows_stop_after_the_interrupted_travel(self):
        rows = {(row["turn"], row["reason"]): row["key"] for row in CASE["decisions"]}
        self.assertTrue(rows[(2457512, RETURN_REASON)].startswith(TRAVEL_PREFIX))
        self.assertEqual(rows[(STOP_TURN, "quest:blocked:me-staff")], "")
        self.assertEqual(CASE["sequence"]["failure"],
                         "return-outpost-unavailable:me-staff:return-outpost")

    def test_the_inn_leg_continues_across_the_grass_after_the_travel_stops(self):
        case = recorded_case()
        policy = nav.new_policy(case)
        policy._town_maps = _town_maps()
        policy._town_map = policy._town_maps[0]
        staffs = {int(key.split(":")[1]): count for key, count in case["sequence"]["absorbed"].items()
                  if key.startswith("staff:")}
        rows, raw = [], case["boards"][0]
        for following in [*case["boards"][1:], None]:
            key = loops.decide(policy, raw)
            rows.append((raw["turn"], key, policy.last_reason))
            if following is None:
                break
            following = self.send(policy, raw, key, following, staffs)
            policy.confirm_key_posted(key)
            raw = following
        self.assertEqual([turn for turn, _key, _reason in rows], [2457512, STOP_TURN])
        self.assertEqual(rows[0][2], RETURN_REASON)
        turn, key, reason = rows[-1]
        self.assertEqual(reason, RETURN_REASON, (turn, key, reason))
        self.assertTrue(key.startswith(TRAVEL_PREFIX), key)
        self.assertIsNone(me_staff_sequence.state(policy).failure)


if __name__ == "__main__":
    unittest.main()
