"""Equipment review E4: the only owned source of a depth ability is kept.

Owner answers of the equipment review 2026-11-22 (verbatim choices):

* Q3 「深さの条件を満たす唯一の品は全ての深さで優先して残し（売らない・闇市の資金にしない）」:
  ability_sources ``sole_depth_source``, read by item_fate's disposal gates (``fate``, ``held``,
  ``gear_tier`` -- the Black Market fund's exception included) and the junk class.

Q5 (owned gear is not bought; the whole-set exception) is tests/test_equip_e4b_shelf_evaluation_1122_recorded.

Recorded:

* n1-c life-218's town arrival of 2026-11-21 21:00:41 (tests/fixtures/n1c-218-chaos-home-1121):
  resist_chaos missing from the worn kit for the Mountain's 49; the Home holds two resist_chaos
  weapons, the (混沌)ヘヴィ・フレイル and the (祝福)脇差し (so neither is the only one);
* n1-c life-219's town arrival of 2026-11-22 01:34 (tests/fixtures/n1c-219-flipflop-1122): the worn
  耐混乱の指輪 {呪われている} is the only resist_conf piece (its slot rank kept it only for room
  before E4); the Home's (防衛者)鎖つき鉄球 gives resist_chaos and so do the worn (cursed) ★Flora
  boots: two sources, so the ball keeps the ranking's room-sale.

DECLARED CONSTRUCTED:

* the Black Market fund naming a piece (``bm_destruction_fund.releases`` answering True: no shelf of
  the staff was seen on that visit; its exception sells every rank of a spare melee weapon) -- the
  exception is read inside ``gear_tier``, after the only-source keep;
* the n1-c 218 Home census without the (祝福)脇差し, as after the fund sold it: the flail is then
  the only resist_chaos piece;
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import ability_sources, bm_destruction_fund, item_fate, item_need
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
TR_RES_CHAOS = 62
FLAIL = "(混沌)ヘヴィ・フレイル"
WAKIZASHI = "(祝福)脇差し"
CONF_RING = "耐混乱の指輪"
BALL = "(防衛者)鎖つき鉄球"
BOOTS = "★アンバーの王女フローラの軟革ブーツ"


def _arrival(name, scratch):
    with contextlib.redirect_stdout(io.StringIO()):
        policy, _journal, steps = load(FIXTURES / name, Path(scratch))
    return policy, steps


def _chaos_pieces(policy, board):
    return [item.name for item in (*board.equipment, *board.inventory,
                                   *policy._home_knowledge_items)
            if TR_RES_CHAOS in item.known_flags]


class ArrivalCase(unittest.TestCase):
    FIXTURE = None

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, cls.steps = _arrival(cls.FIXTURE, cls.scratch.name)
        cls.board = cls.steps[0][1]()

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()


class SoleSourceKeptRecordedTest(ArrivalCase):
    FIXTURE = "n1c-218-chaos-home-1121"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        home = cls.policy._home_knowledge_items
        cls.flail = next(item for item in home if item.name.startswith(FLAIL))
        cls.wakizashi = next(item for item in home if item.name.startswith(WAKIZASHI))
        # DECLARED CONSTRUCTED (module docstring): the census after the fund sold the wakizashi.
        cls.census_after = [item for item in home if item is not cls.wakizashi]

    def test_two_home_pieces_give_resist_chaos_and_neither_is_the_only_one(self):
        policy, board = self.policy, self.board
        self.assertNotIn("resist_chaos", board.player.abilities)
        self.assertEqual(sorted(_chaos_pieces(policy, board)),
                         sorted([self.flail.name, self.wakizashi.name]))
        self.assertFalse(ability_sources.sole_depth_source(policy, board, self.flail))
        with mock.patch.object(bm_destruction_fund, "releases", lambda *_args: True):
            # The fund's exception may take either (only the only one is kept).
            self.assertEqual(item_fate.gear_tier(policy, board, self.wakizashi), item_fate.ANY)

    def test_once_the_wakizashi_is_gone_the_flail_is_kept_from_every_sale(self):
        policy, board, flail = self.policy, self.board, self.flail
        with mock.patch.object(policy, "_home_knowledge_items", self.census_after),                 mock.patch.object(bm_destruction_fund, "releases", lambda *_args: True):
            self.assertTrue(ability_sources.sole_depth_source(policy, board, flail))
            self.assertEqual(item_fate.gear_tier(policy, board, flail), item_fate.KEEP)
            self.assertEqual(item_fate.fate(policy, board, flail, item_fate.SHELF), item_fate.HOME)
            self.assertTrue(item_fate.held(policy, board, flail, "home-visit", "home-full-sale"))
            self.assertIsNone(policy._junk_class(board, flail))
            # Before E4 (the only-source keep answered False) the fund sold it.
            with mock.patch.object(ability_sources, "sole_depth_source", lambda *_args: False):
                self.assertEqual(item_fate.gear_tier(policy, board, flail), item_fate.ANY)
                self.assertEqual(item_fate.fate(policy, board, flail, item_fate.SHELF),
                                 item_fate.SELL)


class WornSourceRecordedTest(ArrivalCase):
    FIXTURE = "n1c-219-flipflop-1122"

    def test_the_worn_cursed_conf_ring_is_the_only_one_and_kept(self):
        policy, board = self.policy, self.board
        ring = next(item for item in board.equipment if item.name.startswith(CONF_RING))
        self.assertTrue(ring.is_cursed)
        self.assertTrue(ability_sources.sole_depth_source(policy, board, ring))
        self.assertEqual(item_fate.gear_tier(policy, board, ring), item_fate.KEEP)
        self.assertEqual(item_need.keep_reason(policy, board, ring), "sole-depth-source")
        with mock.patch.object(ability_sources, "sole_depth_source", lambda *_args: False):
            # Equipment review E6: a worn piece is needed too (item_need), so the ranking keeps
            # it; before E6 its rank left it for room (a worn piece is never sold either way).
            self.assertEqual(item_need.keep_reason(policy, board, ring), "worn")
            self.assertEqual(item_fate.gear_tier(policy, board, ring), item_fate.KEEP)
            with mock.patch.object(item_need, "keep_reason", lambda *_args: None):
                self.assertEqual(item_fate.gear_tier(policy, board, ring), item_fate.ROOM)

    def test_a_worn_source_makes_the_home_piece_not_the_only_one(self):
        policy, board = self.policy, self.board
        ball = next(item for item in policy._home_knowledge_items if item.name.startswith(BALL))
        boots = next(item for item in board.equipment if item.name.startswith(BOOTS))
        self.assertTrue(boots.is_cursed)
        self.assertIn(TR_RES_CHAOS, boots.known_flags)
        self.assertFalse(ability_sources.sole_depth_source(policy, board, ball))
        self.assertEqual(item_fate.fate(policy, board, ball, item_fate.SHELF), item_fate.ROOM_SALE)


del ArrivalCase

if __name__ == "__main__":
    unittest.main()
