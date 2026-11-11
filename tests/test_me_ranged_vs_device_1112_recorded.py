"""n1-b (Magic-Eater) life-370 2026-11-12: the launcher shot past stronger absorbed powers.

Owner 2026-11-12: 「射撃と取り込んだ魔法道具は常に威力比較して期待値の高い方を使用する。
敵の耐性、射撃の命中率、魔法の成功率まで考慮すること。」

Recorded: tests/fixtures/n1b-370-ranged-1112.json.xz (tests/extract_n1b_370_ranged_1112_fixture.py),
Castle 64F, the Lv45 Magic-Eater with a 高速度のロング・ボウ (x3) (+10,+19) and arrows
(1d4) (+0,+0) (74/shot 74/turn); its absorbed lists (the spectator frames' last displayed
rows) held rod bolts and balls and wand bolts, balls, Disintegrate and the dragon breaths,
all at 96% or 88% success.  The ordinary ranged rung (policy_combat ``_ranged_attack_key``)
knew the launcher only, so every distant hostile was shot with arrows:

- decision 34173 (turn 8960759): ``fl4`` at a ニーベルング (race 111, 32 hp) 10 grids west on
  the row.  The arrow hits it about 91% of the time (shooting 225 less the distance, against
  AC 12); the absorbed サンダー・ボルト rod (14d8) kills it at 96%.
- decision 34326 (turn 8961440): ``fl8`` at a 二周目の小さな泡 (race 1155, 400 hp) four
  grids north.  74 a turn at ~80% against the absorbed 分解 (Disintegrate, 245 at 88%).

Every decision is the public ``choose_key`` of a fresh policy shown the frame's lists first
(``observe_lists``, as the executor's menu reading would).

DECLARED RECONSTRUCTION / RESTORED (pin_vacuity): the capture holds no ~f reply, so the skill
knowledge is supplied before the decision (tests/support/recorded ``skill``); the absorbed
lists are the spectator frame's (the live policy held them; the boards carry no menu).
DECLARED CONSTRUCTED (each named at its test): the counter-pins' displayed success of 20% and
the Magic-Missile-only wand list (also for the fixed-order chooser); the adjacent pin's ニーベルング moved beside the player and
the player afraid (fear refuses melee only, attack_expectation.melee_refused).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path

from hengbot import attack_expectation, me_device_attacks, me_ranged_first
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.me_device_attacks import DEVICE_REASON, observe_lists
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests.support.recorded import EDIT, skill

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-370-ranged-1112.json.xz"
NIBELUNG, BUBBLE = 111, 1155
ARROWS = "l"   # 矢 (1d4) (+0,+0) (74/shot 74/turn), the first arrow stack (the rung's ammo)


class RangedVersusDeviceRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")

    def case(self, sequence):
        return copy.deepcopy(self.payload["cases"][str(sequence)])

    def decide(self, case, *, rows=None, change=None):
        """(key, reason, policy, snapshot): a fresh policy shown ``case``'s lists first."""
        raw = case["board"]
        if change is not None:
            change(raw)
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(raw), self.races))
        for kind, entry in sorted(case["lists"].items(), key=lambda item: item[1]["turn"]):
            shown_rows = entry["rows"] if rows is None else rows(kind, entry["rows"])
            shown = dict(copy.deepcopy(raw), turn=entry["turn"],
                         _magic_eater_power_list={"kind": kind, "rows": shown_rows})
            observe_lists(policy, parse_snapshot(shown, self.races))
        skill(policy, raw)
        snapshot = parse_snapshot(copy.deepcopy(raw), self.races)
        key = policy.choose_key(snapshot)
        return str(key), policy.last_reason, policy, snapshot

    @staticmethod
    def monster(snapshot, race, position=None):
        return next(monster for monster in snapshot.visible_monsters if monster.race_id == race
                    and (position is None or monster.position == position))

    def test_the_recorded_shots(self):
        self.assertEqual(self.case(34173)["decision"], {
            "turn": 8960759, "reason": "ranged:fire", "key": "fl4"})
        self.assertEqual(self.case(34326)["decision"], {
            "turn": 8961440, "reason": "ranged:fire", "key": "fl8"})

    def test_the_rod_bolt_beats_the_arrow_at_the_nibelung(self):
        key, reason, policy, snapshot = self.decide(self.case(34173))
        # The サンダー・ボルト rod (sval 21, letter v) along the row west.
        self.assertEqual((key, reason), ("mCv4", DEVICE_REASON))
        target = self.monster(snapshot, NIBELUNG, snapshot.player.position.__class__(37, 68))
        ammo = next(item for item in snapshot.inventory if item.slot == ARROWS)
        launcher = attack_expectation.launcher_shot(policy, snapshot, target, ammo)
        device = me_device_attacks.attack_choice(policy, snapshot, target, "4")
        self.assertEqual(device[1].names[1], "Lightning Bolts")
        self.assertAlmostEqual(device[0], 0.96 * 32)
        # Shooting 225 (the sheet's value), the arrow's +0 and the bow's proficiency 4000 (no
        # term), less the distance 10, against AC 12: 5% + 90% x (215 - 12 * 3 // 4) / 215.
        self.assertEqual(self.races[NIBELUNG].armor_class, 12)
        self.assertAlmostEqual(launcher, (0.05 + 0.9 * (215 - 9) / 215) * 32)
        self.assertLess(launcher, device[0])

    def test_the_absorbed_disintegrate_beats_the_arrow_at_the_bubble(self):
        key, reason, policy, snapshot = self.decide(self.case(34326))
        self.assertEqual((key, reason), ("mBz8", DEVICE_REASON))
        target = self.monster(snapshot, BUBBLE, snapshot.player.position.__class__(5, 116))
        ammo = next(item for item in snapshot.inventory if item.slot == ARROWS)
        launcher = attack_expectation.launcher_shot(policy, snapshot, target, ammo)
        device = me_device_attacks.attack_choice(policy, snapshot, target, "8")
        self.assertEqual(device[1].names[1], "Disintegrate")
        self.assertGreater(device[0], 3 * launcher)

    def test_counter_a_low_displayed_success_keeps_the_arrow(self):
        # DECLARED CONSTRUCTED: every absorbed power shown at 20% success.
        def low(kind, rows):
            return [dict(row, success=20, fail=80) for row in rows]
        key, reason, _, _ = self.decide(self.case(34173), rows=low)
        self.assertEqual((key, reason), ("fl4", "ranged:fire"))

    def test_counter_magic_missile_alone_keeps_the_arrow(self):
        # DECLARED CONSTRUCTED: the wand list holds Magic Missile alone, the rods recharge.
        def missile_only(kind, rows):
            if kind == "wand":
                return [row for row in rows if row["name"] == "マジック・ミサイル"]
            if kind == "rod":
                return [dict(row, charging=row["max"]) for row in rows]
            return rows
        key, reason, policy, snapshot = self.decide(self.case(34173), rows=missile_only)
        self.assertEqual((key, reason), ("fl4", "ranged:fire"))
        # (2 + 45 / 10)d6 at 96% (21 x 0.96) is below the arrow's 29.
        target = self.monster(snapshot, NIBELUNG, snapshot.player.position.__class__(37, 68))
        ammo = next(item for item in snapshot.inventory if item.slot == ARROWS)
        self.assertLess(me_device_attacks.seen_missile_score(policy, snapshot, target, "4"),
                        attack_expectation.launcher_shot(policy, snapshot, target, ammo))

    def test_the_fixed_order_answer_gives_way_to_a_stronger_launcher(self):
        # The distant chooser of the quest plans, the summon response and the blind strike
        # (me_ranged_first.attack_key): its fixed order used the strongest absorbed power, here
        # the 力 staff (``mAz``, 65% x 32 hp, below the arrow's 29).
        # DECLARED CONSTRUCTED: the wand list holds Magic Missile alone, the rods recharge.
        def missile_only(kind, rows):
            if kind == "wand":
                return [row for row in rows if row["name"] == "マジック・ミサイル"]
            if kind == "rod":
                return [dict(row, charging=row["max"]) for row in rows]
            return rows
        _, _, policy, snapshot = self.decide(self.case(34173), rows=missile_only)
        target = self.monster(snapshot, NIBELUNG, snapshot.player.position.__class__(37, 68))
        self.assertEqual(me_ranged_first.attack_key(policy, snapshot, target), "fl4")
        self.assertEqual(policy.last_reason, "ranged:fire")
        # A stronger answer keeps the fixed order (the rod bolt, as the rung above).
        _, _, policy, snapshot = self.decide(self.case(34173))
        target = self.monster(snapshot, NIBELUNG, snapshot.player.position.__class__(37, 68))
        self.assertEqual(me_ranged_first.attack_key(policy, snapshot, target), "mCv4")

    def test_adjacent_while_afraid_the_launcher_is_weighed(self):
        # DECLARED CONSTRUCTED: the ニーベルング of [37,68] stands beside the player at [37,77]
        # and the player is afraid; every absorbed power at 20% success.
        def beside(raw):
            raw["player"]["status"]["afraid"] = True
            raw["visible_monsters"] = [monster for monster in raw["visible_monsters"]
                                       if (monster["y"], monster["x"]) == (37, 68)]
            raw["visible_monsters"][0].update(y=37, x=77)

        def low(kind, rows):
            return [dict(row, success=20, fail=80) for row in rows]
        case = self.case(34173)
        raw = case["board"]
        beside(raw)
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(raw), self.races))
        for kind, entry in case["lists"].items():
            shown = dict(copy.deepcopy(raw), turn=entry["turn"],
                         _magic_eater_power_list={"kind": kind, "rows": low(kind, entry["rows"])})
            observe_lists(policy, parse_snapshot(shown, self.races))
        snapshot = parse_snapshot(copy.deepcopy(raw), self.races)
        target = snapshot.visible_monsters[0]
        self.assertTrue(attack_expectation.melee_answers_none_of(policy, snapshot, [target]))
        # The combat rungs' melee-refused order (me_ranged_first.melee_refused_key): the arrow
        # (about 0.92 x 32) over the 20% rod bolt (0.2 x 32).
        self.assertEqual(me_ranged_first.melee_refused_key(policy, snapshot, [target]), "fl4")
        self.assertEqual(policy.last_reason, "ranged:fire")
        # The launcher is weighed beside the target only while melee answers nothing.
        raw["player"]["status"]["afraid"] = False
        calm = parse_snapshot(copy.deepcopy(raw), self.races)
        self.assertNotIn("fl4", [send() for _, send in me_ranged_first._adjacent_options(
            policy, calm, calm.visible_monsters[0], "4")])


if __name__ == "__main__":
    unittest.main()
