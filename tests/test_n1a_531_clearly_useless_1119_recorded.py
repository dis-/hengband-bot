"""Owner 2026-11-19 「不要物の判定をもう少し頑張って。」 on n1-a life-531's Home (zombie warrior).

The owner pasted n1-a's Home and named four kinds of stock to sell rather than hoard:

1. 「高位魔法書→自宅に溜め込まずに売る」: third and fourth realm books of no realm the character
   sheet shows (``unused-book``);
2. 「使わない魔法道具は売る」: the Rod of Sleep Monster, the bolt rods, the Staffs of Starlight,
   Detect Objects, Detect Invisible and Cure Light Wounds -- device kinds no rule of the bot uses
   (item_fate ``DEVICE_USES``; ``unused-device``);
3. 「ゾンビなら絶対装備しないので売って良い」: the rings of Resist Poison (four, and one of Heroism)
   and of Resist Nether (three), whose every ability the zombie holds permanently
   (``innate-covered``);
4. 「耐性のアミュレットの下位互換」: the amulets of Resist Acid, of Resist Lightning (twelve) and
   of Resist Fire and Lightning, which the kept Amulet of Resistance outdoes (``dominated``).

All four are classes of item_fate.clearly_useless, judged for Home shelf stock whether or not the
Home is full: the Home junk sweep (item_fate.sweep_ware) and the full-Home relief take them first.

Recorded: n1-a life-531's town-arrival checkpoint of 2026-11-19 03:27:20 (turn 4127811,
tests/extract_n1a_531_overweight_1119_fixture.py): the Home's 240 stacks, the worn and carried
gear and the character's ability sources, as the arrival policy restored them.

DECLARED CONSTRUCTED: for the sweep, the arrival board's pack without its heavy loot and with
17 of 23 slots (the recorded pack is full and over the weight limit, so no sweep could begin).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import item_fate
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-531-overweight-1119"

EXPECTED = {
    # 1. realm books (the warrior's character sheet shows no realm)
    "Lv3 呪術の魔法書[怨恨呪縛]": "unused-book",
    "Lv3 歌集[リヴェンデルの竪琴]": "unused-book",
    "Lv3 生命の魔法書[一角獣の書]": "unused-book",
    # 2. devices no rule uses: the owner's examples ...
    "スリープ・モンスターのロッド": "unused-device",
    "アシッド・ボルトのロッド": "unused-device",
    "サンダー・ボルトのロッド": "unused-device",
    "ファイア・ボルトのロッド": "unused-device",
    "アイス・ボルトのロッド": "unused-device",
    "スターライトの杖 (10回分)": "unused-device",
    "アイテム感知の杖 (10回分) {@0}": "unused-device",
    "透明物体感知の杖 (14回分)": "unused-device",
    "軽傷の治癒の杖 (8回分)": "unused-device",
    # ... and the other kinds no rule zaps or aims
    "トラップ感知のロッド": "unused-device",
    "イルミネーションのロッド": "unused-device",
    "岩石溶解のロッド": "unused-device",
    "アシッド・ボルトの魔法棒 (14回分)": "unused-device",
    "アシッド・ボールの魔法棒 (7回分)": "unused-device",
    # 3. abilities the zombie warrior holds permanently (poison, nether, hold life, fear)
    "耐毒の指輪": "innate-covered",
    "勇気の耐毒の指輪 {r毒}": "innate-covered",
    "耐地獄の指輪": "innate-covered",
    # 4. outdone by kept pieces of their kind: the owner's amulets ...
    "耐酸のアミュレット": "dominated",
    "耐電のアミュレット": "dominated",
    "耐火の耐電のアミュレット {r電火}": "dominated",
    # ... the worn Amulet of the Magi [+5] (+5) outdoes the shelf's lesser two
    "探索のアミュレット (+3)": "dominated",
    "賢者のアミュレット [+5] (+3探索)": "dominated",
    # ... the Amulet of Anti-Magic and See Invisible outdoes the plain ones
    "反魔法のアミュレット": "dominated",
    # ... the two worn rings of Damage (+10), (+12) outdo the shelf's lesser ones
    "ダメージの指輪 (+9)": "dominated",
    "ダメージの指輪 (+6)": "dominated",
    # 5. 「アーティファクトであっても明確な下位互換は売る」: the dominance of every slot, each
    # piece outdone on every axis by a kept piece of its slot kind ...
    "ブラックドラゴン・スケイルメイル (-2) [40,+15]": "dominated",    # the [40,+17] one
    "全耐性のスプリント・メイル (-2) [19,+15] {r酸電火冷沌}": "dominated",  # ★ロヒアリム
    "エルフの金属製ラメラー・アーマー (-3) [23,+4] (+1隠密) {+隠r酸電火冷暗}": "dominated",
    "忍びの毛皮のクローク [3,+5] (+2隠密) {+隠}": "dominated",      # エルフのクローク (+3)
    "反射の革製スモール・シールド [3,+7] {反}": "dominated",        # the [3,+9] one
    "耐冷の革製スモール・シールド [3,+7] {r冷}": "dominated",       # the [3,+13] one
    "耐火の革製ラージ・シールド [6,+3] {r火}": "dominated",         # ドワーフの [10,+8] {+耐r火}
    "耐火の金属製ラージ・シールド [8,+4] {r火}": "dominated",
    "耐冷の金属製ラージ・シールド [8,+2] {r冷}": "dominated",
    "麻痺知らずのセスタス [5,+7] {麻}": "dominated",               # ★フィンゴルフィン
}


class N1a531ClearlyUseless1119RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.board = steps[0][1]()

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def verdict(self, item):
        return item_fate.clearly_useless(self.policy, self.board,
                                         replace(item, slot=item_fate.HOME_STOCK_SLOT))

    def shelf(self, name):
        return next(item for item in self.policy._home_knowledge_items if item.name == name)

    def test_each_owner_class_on_the_recorded_home(self):
        policy = self.policy
        self.assertIsNone(policy._home_full_relief)  # no full-Home relief: the classes always hold
        self.assertEqual(policy._own_book_tvals, frozenset())
        flagged = {item.name: verdict for item in policy._home_knowledge_items
                   if (verdict := self.verdict(item)) is not None}
        self.assertEqual(flagged, EXPECTED)

    def test_what_is_kept(self):
        for name in ("耐性のアミュレット", "可視透明の反魔法のアミュレット {視[魔}",
                     "耐冷の反テレポートのアミュレット {r冷[瞬}", "反射のアミュレット",
                     "耐カオスの指輪", "耐混乱の指輪", "能力維持の指輪", "殺戮の指輪 (+2,+6)",
                     "全感知のロッド", "周辺感知のロッド", "テレポート・アウェイのロッド",
                     "トラップ解除のロッド", "テレポート・アウェイの魔法棒 (0回分)",
                     "岩石溶解の魔法棒 (82回分)", "鑑定の杖 (7回分) {@0}",
                     "★知識の石 {明}", "*破壊*の巻物"):
            self.assertIsNone(self.verdict(self.shelf(name)), name)

    def test_the_zombie_holds_the_rings_abilities_permanently(self):
        sources = self.board.player.ability_sources
        for ability in ("resist_pois", "resist_neth", "hold_exp"):
            self.assertIn("permanent", sources[ability], ability)
        # Resist Confusion alone is outdone by Resist Chaos, but two ring slots need two.
        self.assertFalse(item_fate._dominated(self.policy, self.board, self.shelf("耐混乱の指輪")))

    def test_only_shelf_stock_is_judged(self):
        carried = next(item for item in self.board.inventory if item.name == "反魔法のアミュレット")
        self.assertIsNone(item_fate.clearly_useless(
            self.policy, self.board, replace(carried, slot=item_fate.HOME_STOCK_SLOT),
            carried=True))
        self.assertIsNone(item_fate.clearly_useless(self.policy, self.board, carried))

    def test_the_sweep_takes_a_clearly_useless_ware_first(self):
        policy, board = self.policy, self.board
        light = replace(board, inventory=tuple(
            item for item in board.inventory if item.weight < 50 or item.tval == 55)[:17])
        self.assertLess(policy._inventory_weight(light), policy._inventory_weight_limit(light))
        (ware, store, _value), _item = item_fate.sweep_ware(policy, light, policy._home_knowledge_items)
        self.assertEqual((ware.name, store), ("トラップ感知のロッド", 5))
        self.assertEqual(item_fate.clearly_useless(policy, light, ware), "unused-device")


if __name__ == "__main__":
    unittest.main()
