"""D55 (#47): the recorded n1-c life-077 town death (2026-11-01 03:25).

The Lv8 zombie Magic-Eater (127 max HP, build 577cd246b) had read its last
Teleportation scroll on a 見習戦士 (race 43, three SLASH blows) and carried
no healing potion, so the emergency ladder took the town last stand
(``town_last_stand``, owner 2026-10-31 「…諦めて戦闘を試みる」).  The stand
meleed (``emergency:cornered-attack`` '2') six times at main-hand to-hit -63,
every blow but one missing, HP 56 -> 0, while the Magic-Eater carried its
absorbed Magic Missile and sixteen spare lit torches.  The owner rule of the
same day 「近接以外の攻撃手段も街で使う」 puts the ranged order
(``me_ranged_first``) ahead of melee in town fights; the stand skipped it.

Fixture: tests/fixtures/death-n1c-077-1101.json.gz
(tests/extract_deaths_1101_fixtures.py, case n1c-077).  Every decision is the
public ``choose_key``; posted keys go through the production executor port
(test_town_combat_survival_recorded.MissilePostedKey).
DECLARED CONSTRUCTED: the new process has read the staff power list
(test_me_staff_loops_1031_recorded.new_policy); the no-missile case carries
the executor's ``_magic_eater_wand_charges`` -1 annotation (a wand power
list without Magic Missile), and the melee case also drops the torches.
The missile case drops the torches too: beside the 見習戦士 a thrown lit torch
(about 22 expected) out-scores the 2d6 missile (7), so with both carried the
stand throws the torch (owner 2026-11-01 「見込みの大きい方を使う」,
test_d57_me_combat_1101_recorded).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.magic_eater import MISSILE_REASON
from hengbot.me_ranged_first import TORCH_REASON
from tests import test_me_staff_loops_1031_recorded as loops
from tests.test_town_combat_survival_recorded import MissilePostedKey


FIXTURE = Path(__file__).with_name("fixtures") / "death-n1c-077-1101.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
STAND = "emergency:cornered-attack"
NOVICE_WARRIOR = 43


def boards(*, missile=True, torches=True):
    rows = copy.deepcopy(CASE["boards"])
    for raw in rows:
        if not missile:
            raw["_magic_eater_wand_charges"] = -1
        if not torches:
            raw["inventory"] = [item for item in raw["inventory"]
                                if (item.get("tval"), item.get("sval")) != (39, 0)]
    return rows


class TownLastStandRangedRecordedTest(MissilePostedKey):
    def stand(self, **variant):
        """The answers on the six recorded stand boards (after the first)."""
        policy = loops.new_policy(CASE, CASE["skill"], record=CASE["sequence"],
                                  monraces=CASE["monraces"])
        rows = loops.MeStaffLoopsRecordedTest.drive(self, policy, boards(**variant))
        return rows[1:]

    def test_recorded_rows_are_the_melee_stand(self):
        recorded = {row["turn"]: row for row in CASE["decisions"]
                    if row["reason"] == STAND}
        self.assertEqual(sorted(recorded), [raw["turn"] for raw in CASE["boards"][1:]])
        self.assertEqual({row["key"] for row in recorded.values()}, {"2"})
        self.assertEqual([row["player"]["hp"] for row in recorded.values()],
                         [56, 43, 43, 29, 13, 0])
        first = CASE["boards"][1]
        self.assertEqual({m["race_id"] for m in first["visible_monsters"]}, {NOVICE_WARRIOR})
        self.assertEqual(first["player"]["melee"]["main_hand_to_h"], -63)
        carried = {(item.get("tval"), item.get("sval")) for item in first["inventory"]}
        self.assertNotIn((70, 9), carried)  # no Teleportation scroll left
        self.assertNotIn(75, {tval for tval, _sval in carried})  # no potion
        self.assertEqual(sum(item["count"] for item in first["inventory"]
                             if (item.get("tval"), item.get("sval")) == (39, 0)), 16)

    def test_stand_fires_the_absorbed_magic_missile(self):
        rows = self.stand(torches=False)
        self.assertEqual([(key, reason) for _raw, key, reason in rows],
                         [("mBp2", MISSILE_REASON)] * 6)

    def test_without_the_missile_the_stand_throws_a_spare_torch(self):
        rows = self.stand(missile=False)
        self.assertEqual({reason for _raw, _key, reason in rows}, {TORCH_REASON})

    def test_with_no_ranged_answer_the_stand_still_melees(self):
        rows = self.stand(missile=False, torches=False)
        self.assertEqual({(key, reason) for _raw, key, reason in rows}, {("2", STAND)})


if __name__ == "__main__":
    unittest.main()
