"""Equipment review E6: 「この品は要るか」 has one answer (item_need).

Equipment review 2026-11-22 (maintainability-review-equip-1122, finding 4): the definitions of
「要らない」 -- the sale-value ranking (item_fate ``gear_tier``), the copy of the search's choice
(spare_gear ``released``), the downgrade of the kept pieces (item_fate ``_dominated``), the plain
gear worse than the chosen loadout (``_plain_gear_surplus``), the search's dominance prune reused
for disposal (``_is_disposable_dominated_armour``), the downgrade of the worn launcher
(``_is_disposable_dominated_launcher``), the weapon worse than the wielded one
(``_find_weapon_sale``) -- each had its own exceptions, and the weapon sale and the launcher ground
did not ask owner Q3's 「深さの条件を満たす唯一の品」.  Every one of them now asks item_need's
``keep_reason`` first.

Recorded (town arrivals, tests/fixtures):

* n1-b life-413 2026-11-22 (n1b-413-launcher-flip-1122): a Magic-Eater wielding the high-grade
  ★ドワーフのロッホアーバー・アックス, no telepathy worn; the Home's ★影のジャックのクローク
  is the only telepathy piece (sole-depth-source), ★ロビンフッドのショート・ボウ waits for its
  ammunition (launcher-waiting);
* n1-a life-531 2026-11-22 (n1a-531-castle-climb-1122-fundraise): a warrior; the Home's
  強速射のショート・ボウ is dominated by the worn launcher (dominated-launcher), the Q34 pieces
  are tagged (quest-tagged);
* n1-c life-219 2026-11-22 (n1c-219-flipflop-1122): the visit's target wears the carried
  金属製ラージ・シールド (target-loadout).
* n1-c life-218 2026-11-21 (n1c-218-chaos-home-1121): the Home's (混沌)ヘヴィ・フレイル.

On these recorded boards the unified answer changes no disposal answer (gear_tier, fate,
clearly_useless, the junk class, both dominance grounds, the weapon sale: compared with the gate
read as E5's only-source keep); the behaviour changes show on the constructed boards below.

DECLARED CONSTRUCTED:

* n1-b 413: a plain ヌンチャク (2d3) carrying TR_TELEPATHY in the pack and the Home census
  without ★影のジャックのクローク (its other telepathy source) -- the only telepathy the character owns, worse than the wielded axe: the Weapon Smith's inferior-weapon sale took it
  before E6.  The expected damage (``weapon_expected_dps``) answers None on the replayed boards
  (so the inferior-weapon sale stays closed there), so the comparison is given: the axe 100, the
  nunchaku 10;
* n1-a 531: the visit's target loadout wearing the Home's 強速射のショート・ボウ
  (``item_need.target_piece`` answering True for it);
* n1-c 218: the Home census without the (祝福)脇差し (the flail the only resist_chaos piece, as in
  the E4 test), and the flail with TR_NO_TELE added.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import ability_sources, item_fate, item_need, policy_equipment, spare_gear
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
TR_TELEPATHY = 79
TR_NO_TELE = 68


def _arrival(name, scratch):
    with contextlib.redirect_stdout(io.StringIO()):
        policy, _journal, steps = load(FIXTURES / name, Path(scratch))
    return policy, steps


def _named(items, prefix):
    return next(item for item in items if item.name.startswith(prefix))


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

    def home(self, prefix):
        return _named(self.policy._home_knowledge_items, prefix)


class MagicEaterRecordedTest(ArrivalCase):
    FIXTURE = "n1b-413-launcher-flip-1122"

    def test_the_recorded_verdicts_name_their_reasons(self):
        policy, board = self.policy, self.board
        cloak = self.home("★影のジャックのクローク")
        bow = self.home("★森の狩人ロビンフッドのショート・ボウ")
        self.assertEqual(item_need.need(policy, board, cloak),
                         item_need.Need(item_need.KEEP, "sole-depth-source"))
        self.assertEqual(item_need.need(policy, board, bow),
                         item_need.Need(item_need.CARRY, "launcher-waiting"))
        self.assertEqual(item_fate.gear_tier(policy, board, cloak), item_fate.KEEP)
        self.assertEqual(item_need.need(policy, board, board.equipment[0]).reason, "worn")

    def test_the_only_telepathy_weapon_is_not_sold_as_an_inferior_spare(self):
        policy, board = self.policy, self.board
        self.assertNotIn("telepathy", board.player.abilities)
        self.assertTrue(policy._equipped_weapon_high_grade(board))
        template = self.home("(防衛者)ヌンチャク")
        # DECLARED CONSTRUCTED (module docstring): a plain telepathy nunchaku in the pack.
        nunchaku = replace(template, slot="v", name="ヌンチャク (2d3) {テ}", is_ego=False,
                           to_h=0, to_d=0, to_a=0, pval=0, fully_known=True, pseudo_feeling="",
                           known_flags=frozenset({TR_TELEPATHY}))
        probe = replace(board, inventory=(*board.inventory, nunchaku))
        census = [item for item in policy._home_knowledge_items
                  if not item.name.startswith("★影のジャックのクローク")]
        home = mock.patch.object(policy, "_home_knowledge_items", census)
        home.start()
        self.addCleanup(home.stop)
        axe = board.equipment[0]
        dps = lambda _board, item, _ac, _cal: 100.0 if item is axe else 10.0  # noqa: E731
        patch = mock.patch.object(policy_equipment, "weapon_expected_dps", dps)
        patch.start()
        self.addCleanup(patch.stop)
        self.assertTrue(policy._inferior_weapon_spare(probe, nunchaku))
        self.assertTrue(ability_sources.sole_depth_source(policy, probe, nunchaku))
        self.assertEqual(item_need.keep_reason(policy, probe, nunchaku), "sole-depth-source")
        self.assertIsNone(policy._find_weapon_sale(probe))
        self.assertEqual(item_need.need(policy, probe, nunchaku).level, item_need.KEEP)
        # Before E6 the weapon sale asked no keep: the Weapon Smith took the only telepathy.
        with mock.patch.object(item_need, "needed", lambda *_args: False):
            self.assertEqual(policy._find_weapon_sale(probe).name, nunchaku.name)


class WarriorRecordedTest(ArrivalCase):
    FIXTURE = "n1a-531-castle-climb-1122-fundraise"

    def test_the_dominated_launcher_is_spare_unless_the_target_wears_it(self):
        policy, board = self.policy, self.board
        bow = self.home("強速射のショート・ボウ")
        self.assertEqual(item_need.need(policy, board, bow),
                         item_need.Need(item_need.SPARE, item_need.GROUND_DOMINATED_LAUNCHER))
        self.assertTrue(policy._is_disposable_dominated_launcher(board, bow))
        # DECLARED CONSTRUCTED: the visit's target loadout wears it.
        worn_by_target = lambda _policy, item: item.name == bow.name  # noqa: E731
        with mock.patch.object(item_need, "target_piece", worn_by_target):
            self.assertEqual(item_need.need(policy, board, bow),
                             item_need.Need(item_need.CARRY, "target-loadout"))
            self.assertFalse(policy._is_disposable_dominated_launcher(board, bow))
            self.assertEqual(item_fate.gear_tier(policy, board, bow), item_fate.KEEP)
            self.assertEqual(item_fate.fate(policy, board, bow, item_fate.SHELF), item_fate.HOME)

    def test_the_q34_pieces_are_kept(self):
        policy, board = self.policy, self.board
        for piece in policy._home_knowledge_items:
            if "Q34" in piece.name:
                with self.subTest(piece=piece.name):
                    self.assertEqual(item_need.keep_reason(policy, board, piece), "quest-tagged")
                    self.assertEqual(item_fate.gear_tier(policy, board, piece), item_fate.KEEP)


class TargetPieceRecordedTest(ArrivalCase):
    FIXTURE = "n1c-219-flipflop-1122"

    def test_the_target_shield_stays_carried_and_kept(self):
        policy, board = self.policy, self.board
        shield = _named(board.inventory, "金属製ラージ・シールド")
        self.assertEqual(item_need.carry_reason(policy, board, shield), "target-loadout")
        self.assertEqual(item_need.keep_reason(policy, board, shield), "target-loadout")
        self.assertFalse(spare_gear.released(policy, board, shield))
        self.assertEqual(item_fate.gear_tier(policy, board, shield), item_fate.KEEP)
        with mock.patch.object(item_need, "target_piece", lambda *_args: False):
            # Off the target the shield is ordinary spare gear for the Home deposit.
            self.assertIsNone(item_need.carry_reason(policy, board, shield))
            self.assertTrue(spare_gear.released(policy, board, shield))


class NoTeleportSourceRecordedTest(ArrivalCase):
    FIXTURE = "n1c-218-chaos-home-1121"

    def test_a_piece_no_exploration_loadout_wears_is_not_the_only_source(self):
        policy, board = self.policy, self.board
        flail = self.home("(混沌)ヘヴィ・フレイル")
        census = [item for item in policy._home_knowledge_items
                  if not item.name.startswith("(祝福)脇差し")]
        with mock.patch.object(policy, "_home_knowledge_items", census):
            self.assertTrue(ability_sources.sole_depth_source(policy, board, flail))
        cursed = replace(flail, known_flags=flail.known_flags | {TR_NO_TELE})
        census = [cursed if item is flail else item for item in census]
        with mock.patch.object(policy, "_home_knowledge_items", census):
            self.assertFalse(ability_sources.sole_depth_source(policy, board, cursed))
            self.assertIsNone(item_need.keep_reason(policy, board, cursed))


del ArrivalCase

if __name__ == "__main__":
    unittest.main()
