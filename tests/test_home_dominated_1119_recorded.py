"""Clearly dominated equipment, artifacts too, is sold from the Home (owner 2026-11-19).

Owner 2026-11-19 「自宅の満杯問題で問題を起こしすぎなので根本解決すること」 (PROPOSAL
C:\\hengband-backups\\pdca\\home-full-root-1119).  Stage 1 found n1-b life-411's Home of 239
stacks keeping 236 the fate may not move (95 top-ten pieces, 89 artifacts): it could never get
back to the cap of 200.  Asked, the owner answered 「アーティファクトであっても明確な下位互換は売る」.

item_fate ``_dominated`` (the jewelry rule of 「耐性のアミュレットの下位互換」, generalised to every
equipment slot of the ranking): a piece another kept piece of its slot kind is at least as good
as on every axis the equipment evaluation reads (``_at_most``: every ability and no drawback
added, every pval ability, to-hit, to-dam, AC and to-AC; melee of one kind and weight with dice
and proficiency; a launcher of one kind; armour no heavier) is sold, artifact or not, once the
kind's worn slots of kept pieces dominate it.  A piece whose abilities are not all shown is
never dominated.  The fate (``item_fate.fate``) is the one gate: the Home ledger and the cap
tidy shed what it sells.

Recorded: n1-b life-411's town arrival of 2026-11-19 (tests/fixtures/quest32-one-turn-kill-1119/
n1b-411, the Magic-Eater's 239-stack Home with a current census).  The cap tidy's sale finder
(policy_home ``_home_full_sale_candidate``, the real decision path the relief and the tidy
choose their wares on) answers for the recorded pieces.

DECLARED CONSTRUCTED: three Home artifacts made from the worn body armour ★革製スケイル・メイル
『サルケットス』 (+3,+3) [11,+25] (+3): one with lower to-AC (dominated by the worn piece: sold),
one with lower to-AC but Resist Time the worn piece lacks (kept), one not *identified* (kept).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import home_ledger, item_fate
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "quest32-one-turn-kill-1119" / "n1b-411"
TR_RES_TIME = 143
TVAL_BODY_SOFT = 36


class HomeDominated1119RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.board = steps[0][1]()
        cls.summary = home_ledger.summary(cls.policy, cls.board)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def shelf(self, name):
        return next(item for item in self.policy._home_knowledge_items if item.name == name)

    def fate(self, item):
        return item_fate.fate(self.policy, self.board, item, item_fate.SHELF)

    def test_the_recorded_home_sheds_its_dominated_pieces(self):
        policy, board = self.policy, self.board
        self.assertTrue(policy._home_knowledge_current)
        self.assertEqual(self.summary["home"], {"count": 239, "cap": 200})
        for name in ("影のクローク [6,+10] {r閃暗}", "影のクローク [6,+5] {r閃暗}",
                     "レッドドラゴン・スケイルメイル (-2) [40,+16] {r火}",
                     "ドラゴン・ブーツ [5,+19] {r暗}",
                     "高精度のライト・クロスボウ (x3) (1.20turn) (+25,+12)",
                     "耐性のアミュレット {r酸電火冷}"):
            item = self.shelf(name)
            probe = replace(item, slot=item_fate.HOME_STOCK_SLOT)
            self.assertEqual(item_fate.clearly_useless(policy, board, probe), "dominated", name)
            self.assertEqual(self.fate(item), item_fate.SELL, name)
            self.assertIsNotNone(policy._home_full_sale_candidate(board, item), name)
        # Their betters stay: the best of each kind, and the pieces only one kept piece outdoes
        # where two may be worn (rings, weapons).
        for name in ("影のクローク [6,+12] {r閃暗}", "ドラゴン・ブーツ [5,+25] {r冷暗水呪}",
                     "レッドドラゴン・スケイルメイル (-2) [40,+17] {r火}"):
            self.assertEqual(self.fate(self.shelf(name)), item_fate.HOME, name)

    def test_the_ledger_counts_what_the_dominance_frees(self):
        # 236 kept before: 14 more pieces are clearly dominated (none of them an artifact: no
        # Home artifact of n1-b's is outdone on every axis), and 15 devices leave to be absorbed
        # (tests/test_me_home_devices_1119_recorded), so 207 stay and the Home is 7 stacks over
        # the cap with only kept stock left.
        summary = self.summary
        self.assertEqual(summary["fates"]["sell"], 17)
        self.assertEqual(summary["kept"], 207)
        self.assertEqual(summary["artifacts"], 89)
        self.assertFalse(summary["fits"])
        self.assertEqual(summary["shed"]["count"], 17)
        self.assertEqual(summary["shed"]["short"], 7)

    def constructed(self, **changes):
        """DECLARED CONSTRUCTED (module docstring): a Home artifact from the worn body armour."""
        worn = next(item for item in self.board.equipment if item.tval == TVAL_BODY_SOFT)
        self.assertTrue(worn.is_artifact and worn.fully_known)
        item = replace(worn, slot=item_fate.HOME_STOCK_SLOT, name="★テストの鎧 [11,+20] (+3)",
                       to_a=worn.to_a - 5, **changes)
        policy = self.policy
        before = policy._home_knowledge_items
        policy._home_knowledge_items = [*before, item]
        self.addCleanup(setattr, policy, "_home_knowledge_items", before)
        return item

    def test_a_dominated_artifact_is_sold(self):
        item = self.constructed()
        self.assertEqual(item_fate.clearly_useless(self.policy, self.board, item), "dominated")
        self.assertEqual(self.fate(item), item_fate.SELL)
        self.assertIsNotNone(self.policy._home_full_sale_candidate(self.board, item))

    def test_an_artifact_with_an_ability_of_its_own_is_kept(self):
        worn = next(item for item in self.board.equipment if item.tval == TVAL_BODY_SOFT)
        self.assertNotIn(TR_RES_TIME, worn.known_flags)
        item = self.constructed(known_flags=worn.known_flags | {TR_RES_TIME})
        self.assertFalse(item_fate._dominated(self.policy, self.board, item))
        self.assertEqual(self.fate(item), item_fate.HOME)

    def test_an_artifact_not_fully_known_is_kept(self):
        item = self.constructed(fully_known=False)
        self.assertFalse(item_fate._dominated(self.policy, self.board, item))
        self.assertNotEqual(self.fate(item), item_fate.SELL)

    def test_a_worn_piece_is_carried(self):
        for item in self.board.equipment:
            self.assertEqual(item_fate.fate(self.policy, self.board, item, item_fate.WORN),
                             item_fate.CARRY)


if __name__ == "__main__":
    unittest.main()
