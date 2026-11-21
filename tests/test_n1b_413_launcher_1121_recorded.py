"""n1-b life-413: the artifact Short Bow in Home lost to an ordinary Light Crossbow.

Owner 2026-11-21 (verbatim): 「n1-b 50F以下の射撃武器選定に関して、「ライトクロスボウを優先、ただし
高級品やアーティファクトなら他種でも威力で評価」が守られていない」 and 「★森の狩人ロビンフッドの
ショート・ボウ　は短弓である。今の実装も機能していない。」

Recorded: n1-b's town visit of 2026-11-21 23:12:21 (tests/fixtures/n1b-413-launcher-1121, 13
journal rows).  The worn ライト・クロスボウ (x3) (+8,+7) shoots the pack's 鋼鉄のクロスボウの矢
(3d5) (+2,+5): (9 + 5 + 7) x 3 = 63 a shot, 1.20 turns a shot, 52.5 a player turn.  Home holds
★森の狩人ロビンフッドのショート・ボウ (x3) (1.00turn) (+15,+17) {..;倍} and no arrow: with the
Weaponsmith's plain arrows (1d4, always stocked) (2.5 + 17) x 3 = 58.5 a shot and a turn.  The
optimizer's launcher comparison read the bow 0 (no owned or seen arrow), its multiplier without the
extra might (x2) and every launcher per shot, so the crossbow stayed.  The replay matches the record
through row 9; the visit's search then targets the Short Bow.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.equipment_optimizer import ordinary_launcher_yields_to_light_crossbow
from hengbot.launcher_damage import launcher_turn_damage
from hengbot.model import SV_BOW_HEAVY_XBOW, SV_BOW_LIGHT_XBOW, SV_BOW_LONG, SV_BOW_SLING
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-launcher-1121"
MATCHED = 9
ROBIN = "★森の狩人ロビンフッドのショート・ボウ"
STEEL_BOLTS = "鋼鉄のクロスボウの矢"


class LauncherRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.decided = []
        for recorded, supply in steps[:MATCHED + 1]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            cls.decided.append((recorded, key, policy.last_reason))
            if recorded["key"]:
                policy.confirm_key_posted(recorded["key"])
        cls.policy, cls.board = policy, board
        cls.launchers = {item.item.name: item.item for item in policy._equipment_catalog.items
                         if item.item.ammo_tval is not None}

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def launcher(self, prefix):
        return next(item for name, item in self.launchers.items() if name.startswith(prefix))

    def test_the_visit_replays_through_the_home_deposits(self):
        for recorded, key, reason in self.decided:
            self.assertEqual((key, reason), (recorded["key"], recorded["reason"]), recorded["row"])

    def test_the_damage_per_player_turn_of_both_launchers(self):
        bolts = next(item for item in self.board.inventory if item.name.startswith(STEEL_BOLTS))
        self.assertEqual(launcher_turn_damage(self.launcher("ライト・クロスボウ"), bolts), 52.5)
        self.assertEqual(launcher_turn_damage(self.launcher(ROBIN)), 58.5)

    def test_the_search_targets_the_artifact_short_bow(self):
        preparation = self.policy._equipment_optimization_preparation
        bow = dict(preparation.result.best.loadout.slots)["bow"]
        self.assertTrue(bow.item.name.startswith(ROBIN), bow.item.name)
        self.assertEqual(bow.origin, "home")

    # CONSTRUCTED from the recorded Home Long Bow: the rule over every other kind.
    def test_ordinary_launchers_of_every_other_kind_yield(self):
        long_bow, crossbow = self.launcher("ロング・ボウ"), self.launcher("ライト・クロスボウ")
        for sval in (SV_BOW_SLING, SV_BOW_LONG, SV_BOW_HEAVY_XBOW):
            self.assertTrue(ordinary_launcher_yields_to_light_crossbow(
                replace(long_bow, sval=sval), crossbow), sval)
        self.assertFalse(ordinary_launcher_yields_to_light_crossbow(
            replace(long_bow, sval=SV_BOW_LIGHT_XBOW), crossbow))

    def test_high_grade_launchers_compete_by_damage(self):
        long_bow, crossbow = self.launcher("ロング・ボウ"), self.launcher("ライト・クロスボウ")
        for grade in ({"is_ego": True}, {"is_artifact": True}):
            self.assertFalse(ordinary_launcher_yields_to_light_crossbow(
                replace(long_bow, sval=SV_BOW_HEAVY_XBOW, **grade), crossbow), grade)


if __name__ == "__main__":
    unittest.main()
