"""Equipment review E4: the only owned source of a depth ability is kept, and owned gear is not bought.

Owner answers of the equipment review 2026-11-22 (verbatim choices):

* Q3 「深さの条件を満たす唯一の品は全ての深さで優先して残し（売らない・闇市の資金にしない）」:
  ability_sources ``sole_depth_source``, read by item_fate's disposal gates (``fate``, ``held``,
  ``gear_tier`` -- the Black Market fund's exception included) and the junk class;
* Q5 「自宅に同じ能力の品があれば取り出して使い店では買わない。店の品が装備の評価で上なら買い替えとして
  買ってよい」: ability_gear reads the destination gate with the target's pieces counted and closes an
  ability with a shelf row only when no carried or Home piece gives it, unless the row outdoes them
  (item_fate ``outdone_by``).

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
* the n1-c 218 shelf rows (no shelf of that visit carried resist_chaos), made from the Home census's
  flail row as store rows: a Ring of Resist Chaos (another slot kind than the flail), and the flail
  itself one point of to-hit better (an upgrade of the same kind); their price is 1 gold so the
  survival reserve admits them;
* the row-1 character dump, written again after the posted dump as test_n1c_218_chaos_home_1121
  does (the game writes it; the journal does not hold it).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import fields, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from hengbot import ability_gear, ability_sources, bm_destruction_fund, item_fate
from hengbot.model import StoreItem
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
TR_RES_CHAOS = 62
TVAL_RING = 45
FLAIL = "(混沌)ヘヴィ・フレイル"
WAKIZASHI = "(祝福)脇差し"
CONF_RING = "耐混乱の指輪"
BALL = "(防衛者)鎖つき鉄球"
BOOTS = "★アンバーの王女フローラの軟革ブーツ"
SEARCH_ROW = 5


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
        with mock.patch.object(ability_sources, "sole_depth_source", lambda *_args: False):
            self.assertEqual(item_fate.gear_tier(policy, board, ring), item_fate.ROOM)

    def test_a_worn_source_makes_the_home_piece_not_the_only_one(self):
        policy, board = self.policy, self.board
        ball = next(item for item in policy._home_knowledge_items if item.name.startswith(BALL))
        boots = next(item for item in board.equipment if item.name.startswith(BOOTS))
        self.assertTrue(boots.is_cursed)
        self.assertIn(TR_RES_CHAOS, boots.known_flags)
        self.assertFalse(ability_sources.sole_depth_source(policy, board, ball))
        self.assertEqual(item_fate.fate(policy, board, ball, item_fate.SHELF), item_fate.ROOM_SALE)


class OwnedAbilityNotBoughtRecordedTest(ArrivalCase):
    FIXTURE = "n1c-218-chaos-home-1121"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.flail = next(owned for owned in cls.policy._equipment_catalog.items
                         if owned.origin == "home" and owned.item.name.startswith(FLAIL))
        census = next(item for item in cls.policy._home_knowledge_items
                      if item.name.startswith(FLAIL))
        common = {field.name for field in fields(StoreItem)} - {"letter", "price", "exported_fields"}
        shelf = StoreItem(letter="a", price=1, **{name: getattr(census, name) for name in common})
        cls.ring = replace(shelf, name="耐混沌の指輪", tval=TVAL_RING, sval=1,
                           known_flags=frozenset({TR_RES_CHAOS}), damage_dice_num=0,
                           damage_dice_sides=0, to_h=0, to_d=0, weight=1, price=1, count=1,
                           is_ego=False, is_artifact=False)
        cls.better_flail = replace(shelf, letter="b", to_h=shelf.to_h + 1, count=1)

    def rows(self, *items):
        flags = ability_gear._open_flags(self.policy, self.board)
        return ability_gear._rows(self.policy, self.board, SimpleNamespace(items=list(items)), flags)

    def test_the_arrival_misses_resist_chaos_and_the_home_flail_gives_it(self):
        policy, board = self.policy, self.board
        self.assertEqual(policy._equipment_departure_destination_depth(board), 49)
        self.assertIn("resist_chaos", ability_gear._landing_missing(policy, board))
        self.assertIn(TR_RES_CHAOS, ability_gear._open_flags(policy, board))
        self.assertIn(self.flail.id, [owned.id for owned in ability_sources.owned_unworn_sources(
            policy, "resist_chaos")])

    def test_a_shelf_ring_is_not_bought_while_the_home_flail_gives_it(self):
        self.assertEqual(self.rows(self.ring), [])
        # Before E4 (no owned source asked): the ring was bought.
        with mock.patch.object(ability_sources, "owned_unworn_sources", lambda *_args: []):
            self.assertEqual(self.rows(self.ring), [self.ring])

    def test_an_upgrade_of_the_home_flail_is_bought(self):
        self.assertTrue(item_fate.outdone_by(self.flail.item, self.better_flail))
        self.assertEqual(self.rows(self.ring, self.better_flail), [self.better_flail])


class OwnedAbilityAfterSearchRecordedTest(ArrivalCase):
    """The same arrival replayed to the visit's first search (row 5, recorded keys posted)."""
    FIXTURE = "n1c-218-chaos-home-1121"

    def test_after_the_search_wears_the_flail_nothing_is_open(self):
        policy = self.policy
        dump = Path(policy._character_dump_path).read_bytes()
        for recorded, supply in self.steps[:SEARCH_ROW + 1]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                policy.choose_key(board)
            posted = recorded["key"]
            if posted:
                policy.confirm_key_posted(posted)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, posted):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": posted})
            if recorded["reason"] == "periodic:character-dump":
                # DECLARED CONSTRUCTED (module docstring): the game writes the dump.
                Path(policy._character_dump_path).write_bytes(dump)
        self.assertIn("resist_chaos", ability_sources.target_abilities(policy, board))
        self.assertNotIn("resist_chaos", ability_gear._landing_missing(policy, board))
        self.assertNotIn(TR_RES_CHAOS, ability_gear._open_flags(policy, board))


del ArrivalCase

if __name__ == "__main__":
    unittest.main()
