"""The finale's loadout over every combination of the owned gear (n1-c life-221, 2026-11-24).

Owner 2026-11-24 (verbatim): 「装備が最適化されていない。もう少しなんとかならんか」「botが選んだのは
こっち。明らかに知力も耐久力も劣る」, then 「加速+25 知力18/150 耐久18/200 閃光轟音時間以外の耐性を
必須とする。それ以降は加点式。」 and the score 「ほぼ推奨案で良いが、閃光と時間の耐性は1% 轟音は5%
成功率は不足1%につき5%」 (equipment_optimizer ``finale_rank``, ``FINALE_SCORE_WEIGHTS``).

The visit switching to 99F/100F wore the set the single-slot search reached (CON 18/140, HP 915);
the owner's own set (lib/user/bot_play3.txt: HP 1153, INT 18/198, speed +28) and the
investigation's plan D (C:/hengband-backups/pdca/finale-loadout-1124, six slots changed at once,
HP 1103) were in the Home.  A Zombie resists cold, poison and nether by its race
(src/player/race-info-table.cpp), which the finale's resist count now reads.

Recorded (tests/extract_finale_gear_1124_fixture.py, ``n1c-221-finale-gear-1124``): the
town-arrival checkpoint of 07:13:32 (turn 6256121); its first row runs the visit's loadout search,
whose inputs the finale's search here reuses.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from unittest import mock

from hengbot import warrior_optimization
from hengbot.equipment_optimizer import (
    FINALE_CON_GATE, EvaluatedLoadout, Loadout, current_loadout, finale_conditions_met,
    finale_gate_failures, finale_missing, finale_rank,
)
from hengbot.speed_valuation import loadout_speed
from support.town_arrival_fixture import load

TOWN = Path(__file__).with_name("fixtures") / "n1c-221-finale-gear-1124"
TR_RES_COLD, TR_RES_POIS, TR_RES_NETHER = 51, 52, 60

# The owner's set (lib/user/bot_play3.txt, its equipment a) to l)).
OWNER_SET = (
    ("main_hand", "★サーベル『グレイスワンダー』"), ("sub_hand", "★賢者マーリンの魔法の鏡"),
    ("bow", "★管子のヘヴィ・クロスボウ"), ("main_ring", "スピードの指輪 (+8)"),
    ("sub_ring", "スピードの指輪 (+14)"), ("neck", "★ものまねの始祖ゴゴのペンダント"),
    ("light", "★飛行石"), ("body", "★騎士ローエングリンのミスリル製鎖かたびら"),
    ("outer", "★天上のクローク『天女の羽衣』"), ("head", "★鉄ヘルメット『ホルヘンネス』"),
    ("arms", "★アヴァロンの主コーウィンのガントレット"), ("feet", "★シヴァの化身の軟革ブーツ"),
)
# The investigation's plan D (enum-out-intrinsic.txt: speed +31, HP 1103).
PLAN_D = (
    ("main_hand", "★ハーゲンのスピア"), ("sub_hand", "★賢者マーリンの魔法の鏡"),
    ("bow", "★管子のヘヴィ・クロスボウ"), ("main_ring", "スピードの指輪 (+8)"),
    ("sub_ring", "スピードの指輪 (+14)"), ("neck", "★八尺勾玉"), ("light", "★飛行石"),
    ("body", "★カスパニオンの重鎖かたびら"), ("outer", "至福の地アマンのクローク"),
    ("head", "★槌手王の鋼鉄ヘルメット"), ("arms", "ドラゴン・グローブ [4,+17] {r冷毒破劣}"),
    ("feet", "★シヴァの化身の軟革ブーツ"),
)


def post(policy, key):
    from hengbot.policy import staged_prompt_chain_matches
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class FinaleGear1124RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, _journal, steps = load(TOWN, Path(cls.scratch.name))
        recorded, supply = steps[0]
        with contextlib.redirect_stdout(io.StringIO()):
            cls.key = (policy.choose_key(supply()), policy.last_reason)
        cls.recorded = (recorded["key"], recorded["reason"])
        _sequence, snapshot, _signature, catalog, inputs, _order, _lifted = (
            policy._equipment_shelf_search)
        cls.catalog = catalog
        calls = []
        real = warrior_optimization.optimize_loadout

        def spy(*args, **kwargs):  # the evaluator the search scored with
            calls.append(args[1])
            return real(*args, **kwargs)

        started = monotonic()
        with mock.patch.object(warrior_optimization, "optimize_loadout", spy):
            cls.preparation = warrior_optimization.prepare_warrior_optimization(
                snapshot, catalog, policy._monrace_knowledge, **inputs,
                finale=True, cap_lifted=True)
        cls.elapsed = monotonic() - started
        cls.evaluate = staticmethod(lambda loadout: EvaluatedLoadout(loadout, calls[-1](loadout)))

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def named(self, names):
        slots = []
        for slot, name in names:
            matches = [item for item in self.catalog if item.item.name.startswith(name)
                       or name in item.item.name]
            self.assertTrue(matches, name)
            slots.append((slot, matches[0]))
        return self.evaluate(Loadout(tuple(slots), "weapon_shield"))

    def test_the_row_as_recorded(self):
        self.assertEqual(self.key, self.recorded)

    def test_the_worn_set_fails_the_con_gate(self):
        worn = self.evaluate(current_loadout(self.catalog))
        self.assertEqual(worn.metrics.finale_reading.constitution, 158)  # 18/140
        self.assertEqual(worn.metrics.finale_reading.max_hp, 915)
        self.assertIn(FINALE_CON_GATE, finale_missing(worn))
        self.assertFalse(finale_conditions_met(worn))

    def test_the_owners_set_and_plan_d_meet_the_gates(self):
        owner = self.named(OWNER_SET)
        self.assertEqual(finale_missing(owner), ())
        self.assertEqual(owner.metrics.finale_reading.max_hp, 1153)
        self.assertEqual(loadout_speed(owner.metrics), 138)  # +28
        plan_d = self.named(PLAN_D)
        self.assertEqual(finale_missing(plan_d), ())
        self.assertEqual(plan_d.metrics.finale_reading.max_hp, 1103)

    def test_the_search_finds_a_set_at_least_as_good(self):
        preparation = self.preparation
        self.assertEqual(preparation.blockers, ())
        self.assertFalse(preparation.result.search_capped)
        best = preparation.result.best
        self.assertTrue(finale_conditions_met(best))
        self.assertGreaterEqual(finale_rank(best), finale_rank(self.named(OWNER_SET)))
        self.assertGreaterEqual(finale_rank(best), finale_rank(self.named(PLAN_D)))
        self.assertGreaterEqual(best.metrics.finale_reading.max_hp, 1153)
        # The worn set's search had stayed at HP 915 (the record).
        self.assertGreater(finale_rank(best), finale_rank(self.evaluate(current_loadout(self.catalog))))

    def test_the_racial_resistances_count(self):
        best = self.preparation.result.best
        reading = best.metrics.finale_reading
        self.assertLessEqual({TR_RES_COLD, TR_RES_POIS, TR_RES_NETHER}, reading.intrinsic_flags)
        # A set whose worn gear resists no nether: the race's own resistance meets that gate.
        slots = tuple((slot, item) for slot, item in best.loadout.slots
                      if TR_RES_NETHER not in item.flags)
        bare = self.evaluate(Loadout(slots, best.loadout.hand_mode))
        self.assertNotIn(TR_RES_NETHER, bare.loadout.flags)
        self.assertNotIn("resist_neth", finale_missing(bare))
        self.assertIn("resist_neth", finale_gate_failures(
            bare.loadout.flags, loadout_speed(bare.metrics), reading.intelligence,
            reading.constitution))


if __name__ == "__main__":
    unittest.main()
