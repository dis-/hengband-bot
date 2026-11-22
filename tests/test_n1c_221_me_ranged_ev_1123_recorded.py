"""n1-c life-221 (Magic-Eater Lv39), Quest 25, 2026-11-23 05:00:39-05:00:48: the 28% Rocket.

Owner 2026-11-23, verbatim: 「成功率31%のロケットを多用する選択は正しくない。期待値で攻撃手段を選ぶ指示
だったはずだが」 (2026-11-12 「射撃と取り込んだ魔法道具は常に期待値で比べて高い方（耐性・命中率・成功率
まで）」).

Recorded (tests/fixtures/n1c-221-me-ranged-ev-1123.json.gz, tests/extract_n1c_221_me_ranged_ev_1123_fixture.py):
on [13,28], beside the stairway to hell on [13,29] (race 439: 15d8 FORCE_MAXHP = 120 HP,
IM_ACID/ELEC/FIRE/POIS), the bot sent the absorbed Rocket through Powerful Activation,
``UB3@13,29``, board after board.  Drained INT (17, stat index 14) leaves the Rocket (wand level
75) at 72% fail (cmd-magiceat.cpp: 80 - 3 x (2 - 1) - 3 x (39 - 37) + 1, the personality):
mostly 「呪文をうまく唱えられなかった！」, each failure still paying the activation's 12-24 HP.  The
stairway wailed, failed its theft and blinked away on the first board after; the casts went on at
its empty grid, and the HP they paid fell under the plan's heal line (0.70: 470 of 672) five times
in ten seconds, each answered by a Healing potion, the 5 carried to none.

Why: Quest 25's own chooser (quest25_battle ``_ball_powers``) scored success x damage without
the target's hit points: the powerful Rocket 28% x 484 = 135 over the rod's powerful Cold Ball,
93% x 128 = 119.  Damage past 120 is none: 28% x 120 = 34 against 93% x 120 = 112
(me_device_attacks.use_value, the one figure every absorbed-attack chooser now compares).  And
Powerful Activation was offered while its worst cost (24 at Lv39) took HP under the quest plan's
heal line (only pays_safely's ladder line, 372, was asked; me_device_attacks.powerful_ready).

DECLARED CONSTRUCTED:

* The boards carry no power lists (the executor reads them off screen): the lists are the attack
  powers the record's keys name (wand マジック・ミサイル ``p``, アイス・ボルト ``t``, アイス・ボール
  ``x``, ロケット ``3``, ドラゴンの火炎 ``0``; rod アイス・ボルト ``x``, アイス・ボール ``1``,
  サンダー・ボール ``z``), 3 charges each; their success is the game's formula on each board
  (me_power_success: no list board is recorded).
* The Quest 25 battle record of the time was not kept (the server's was reset on leaving): the
  record is n1-b life-384's at the stairway phase (tests/fixtures/n1b-384-q25-walk-sight-1113),
  without its reached sights.
* Every board is decided on its own and the key confirmed posted, without the executor; the
  recorded boards are the player's recorded HP, not what the replayed keys would have cost.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import me_device_attacks, me_powerful_activation, quest25_battle as battle
from hengbot.model import parse_snapshot
from hengbot.quest_plan_base import HEAL_REASON
from tests.support import q25_house as q25

FIXTURES = Path(__file__).with_name("fixtures")
with gzip.open(FIXTURES / "n1c-221-me-ranged-ev-1123.json.gz", "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
with gzip.open(FIXTURES / "n1b-384-q25-walk-sight-1113.json.gz", "rt", encoding="utf-8") as _stream:
    STAIRWAY_RECORD = json.load(_stream)["battle_record"]

STAIRWAY_CELL = (13, 29)
ROCKET_KEYS = {"UB3@13,29", "mB3@13,29"}
POWERFUL_COLD_BALL, COLD_BALL = "UC1@13,29", "mC1@13,29"
HELD = {"wand": ("マジック・ミサイル", "アイス・ボルト", "アイス・ボール", "ロケット", "ドラゴンの火炎"),
        "rod": ("アイス・ボルト", "アイス・ボール", "サンダー・ボール"),
        "staff": ()}
HEAL_RATIO = 0.70          # strategy/quests/QUEST_25.jsonc consumable_plan heal_threshold_ratio
FAILED = "呪文をうまく唱えられなかった！"


def lists():
    """DECLARED CONSTRUCTED (module note): the held attack powers, 3 charges each."""
    return {kind: (0, tuple({"name": name, "max": 3, "charging": 0} if kind == "rod"
                            else {"name": name, "max": 3, "current": 3} for name in names))
            for kind, names in HELD.items()}


def power(kind, name):
    return me_device_attacks._BY_NAME[(kind, name)]


class TheRecordTest(unittest.TestCase):
    def test_the_rocket_was_cast_powerfully_and_mostly_failed(self):
        rows = CASE["decisions"]
        sent = [row for row in rows if row["reason"] == me_device_attacks.POWERFUL_REASON]
        self.assertTrue(sent)
        self.assertIn("UB3@13,29", {row["key"] for row in sent})
        failures = sum(1 for row in rows for text in row["messages"] if text.startswith(FAILED))
        rockets = sum(1 for row in rows for text in row["messages"] if text == "ロケットを発射した！")
        self.assertGreater(failures, rockets)
        heals = [row for row in rows if row["reason"] == HEAL_REASON]
        self.assertEqual(len(heals), 5)
        self.assertTrue(all(row["hp"] < HEAL_RATIO * 672 for row in heals))

    def test_the_stairway_blinked_away_after_the_first_board(self):
        first, *rest = CASE["boards"]
        self.assertEqual([(m["race_id"], m["y"], m["x"]) for m in first["visible_monsters"]],
                         [(battle.geo.STAIRWAY, *STAIRWAY_CELL)])
        self.assertTrue(all(not board["visible_monsters"] for board in rest))
        self.assertEqual((first["player"]["stats"]["int"]["use"], first["player"]["stats"]["int"]["index"]),
                         (17, 14))


class TheChoiceTest(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(TemporaryDirectory()))
        boards = CASE["boards"]
        record = copy.deepcopy(STAIRWAY_RECORD)
        record["battle"]["blind_sights"] = {"set": []}
        record["turn"] = boards[0]["turn"]
        (directory / "q25-battle.json").write_text(json.dumps(record), encoding="utf-8")
        policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                    quest_strategies=q25.STRATEGIES)
        policy._q25_battle_record_path = directory / "q25-battle.json"
        policy._warning_cell_record_path = directory / "warning-cells.json"
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), policy._monrace_knowledge))
        policy.consume_skill_knowledge(dict(CASE["skill"], turn=boards[0]["turn"]))
        self.policy = policy

    def snapshot(self, raw):
        return parse_snapshot(copy.deepcopy(raw), self.policy._monrace_knowledge)

    def decide(self):
        out = []
        for raw in CASE["boards"]:
            snapshot = self.snapshot(raw)
            self.policy._me_device_lists = lists()
            key = str(self.policy.choose_key(snapshot))
            out.append((snapshot, key, self.policy.last_reason))
            self.policy.confirm_key_posted(key)
        return out

    def test_the_rates_are_the_games(self):
        snapshot = self.snapshot(CASE["boards"][0])
        self.policy._me_device_lists = lists()
        rates = {(found.kind, found.names[0], found.powerful): round(success, 2)
                 for found, success in me_device_attacks.attack_uses(self.policy, snapshot)}
        self.assertEqual(rates[("wand", "ロケット", True)], 0.28)
        self.assertEqual(rates[("rod", "アイス・ボール", True)], 0.93)

    def test_damage_past_the_stairways_hp_is_none(self):
        # use_value: the success times the damage capped by the target's hit points.
        flags = me_device_attacks.race_id_flags(self.policy, battle.geo.STAIRWAY)
        rocket = me_device_attacks.powered(power("wand", "ロケット"))
        ball = me_device_attacks.powered(power("rod", "アイス・ボール"))
        self.assertEqual(me_device_attacks.use_value(rocket, 0.28, 39, flags), 0.28 * 484)
        self.assertEqual(me_device_attacks.use_value(ball, 0.93, 39, flags), 0.93 * 128)
        self.assertEqual(me_device_attacks.use_value(rocket, 0.28, 39, flags, 120), 0.28 * 120)
        self.assertEqual(me_device_attacks.use_value(ball, 0.93, 39, flags, 120), 0.93 * 120)

    def test_the_cold_ball_not_the_rocket(self):
        answers = self.decide()
        line = HEAL_RATIO * 672
        cost = me_powerful_activation.cost(39)
        shots = [(snapshot.player.hp, key) for snapshot, key, reason in answers
                 if reason != HEAL_REASON]
        self.assertTrue(shots)
        self.assertFalse({key for _hp, key in shots} & ROCKET_KEYS, shots)
        for hp, key in shots:
            # The powerful use only while its worst cost keeps HP at the heal line.
            expected = POWERFUL_COLD_BALL if hp - cost >= line else COLD_BALL
            self.assertEqual(key, expected, hp)
        self.assertIn(COLD_BALL, {key for _hp, key in shots})
        self.assertIn(POWERFUL_COLD_BALL, {key for _hp, key in shots})

    def test_no_powerful_use_below_the_heal_line_after_its_cost(self):
        for raw in CASE["boards"]:
            snapshot = self.snapshot(raw)
            ready = me_device_attacks.powerful_ready(self.policy, snapshot)
            line = me_device_attacks.quest_heal_line(self.policy, snapshot)
            self.assertAlmostEqual(line, HEAL_RATIO * 672)
            self.assertEqual(ready, snapshot.player.hp - me_powerful_activation.cost(39) >= line,
                             snapshot.player.hp)


class OffQuestTest(unittest.TestCase):
    def test_no_plan_no_line(self):
        policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                    quest_strategies={})
        raw = copy.deepcopy(CASE["boards"][0])
        snapshot = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertIsNone(me_device_attacks.quest_heal_line(policy, snapshot))
        self.assertEqual(me_device_attacks.powerful_ready(policy, snapshot),
                         me_powerful_activation.pays_safely(policy, snapshot))


if __name__ == "__main__":
    unittest.main()
