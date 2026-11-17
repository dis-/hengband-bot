"""Owner 2026-11-17/18: every return to town challenges Angband's deepest landing when it qualifies.

Owner (verbatim): 「深さの決定について。定期的に一番深い鉄獄にチャレンジするようにしたい」, and asked how
often, 「町に戻るたびに条件を見て挑む」.  Before, a switch once made (the unsafe-recall fallback's
Castle band) held the destination although Angband's own landing had become one the character may
take (castle-climb-1117).  Owner 2026-11-18: 「制覇できる守護者がいれば制覇が先」 and
「潜りすぎの期限の間は鉄獄に挑まない」.

``alternate_lease.challenge`` runs on the town board a dive ends on, before that board's valves:
when ``alternate_lease.angband_qualifies`` (the deepest destination's landing filter -- the
cumulative depth requirements with the 50F *Destruction* means and telepathy, the 81F speed gate,
the blocked guardian floors -- the fallback depth floor and the Q2 hold), a held alternate dungeon
with no running lease is dropped while no conquest target waits, and the ordinary selection takes
Angband.

Recorded:
* n1-a life-530: tests/fixtures/n1a-530-castle-climb-1117 (the 22:13:09 town-arrival checkpoint,
  its 12 journal rows replayed as recorded).  Angband 50 lacks the *Destruction* means and
  telepathy, so the Castle band switch stays.
* n1-c life-216: tests/fixtures/n1c-216-angband-challenge-1117
  (tests/extract_n1c_216_angband_challenge_1117_fixture.py), the 17:15:15 town-arrival checkpoint
  and its arrival board: the Glass castle (60) as the conquest target, 2,609,342 gold, Angband's
  landing 80 passing every check.  The Glass castle has no final guardian, so it is no conquest
  target (owner 2026-11-18): the latch is dropped.  The Mountain's beatable guardian is the
  conquest target then (「制覇できる守護者がいれば制覇が先」); with it conquered too (constructed),
  Angband 80 is taken.

DECLARED CONSTRUCTED:
* the n1-a return: the Castle switch made on the recorded town board (as
  test_n1a_530_castle_climb_1117_recorded does), the fundraising set cleared, and the previous floor
  set to the Castle 42 so the town board is the board a Castle dive ends on;
* the n1-a variant with the means: telepathy added to the player's abilities, the first pack slot
  replaced by a known staff of *Destruction* with 10 charges and the device skill raised to 200 (the
  staff's success 80%+);
* the n1-c control: the Mountain added to the conquered dungeons;
* the n1-a leased variant: that Castle switch relabelled an over-extension switch with a lease of 5
  and 2 dives made.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import alternate_lease, destruction_use, dive_floor, fallback_depth_floor
from hengbot.model import DUNGEON_ANGBAND, SV_STAFF_DESTRUCTION, TVAL_STAFF
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
CASTLE, MOUNTAIN, GLASS_CASTLE = dive_floor.DUNGEON_CASTLE, dive_floor.DUNGEON_MOUNTAIN, 20


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


class N1a530CastleBandTest(unittest.TestCase):
    """Angband 50 refused (no *Destruction* means, no telepathy): the Castle band stays."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.arrival, _journal, steps = load(FIXTURES / "n1a-530-castle-climb-1117",
                                            Path(cls.scratch.name))
        policy = copy.deepcopy(cls.arrival)
        boards = []
        for recorded, supply in steps:
            board = supply()
            boards.append(board)
            key, reason = decide(policy, board)
            assert (key, reason) == (recorded["key"], recorded["reason"]), recorded
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
        cls.town = boards[0]

    @classmethod
    def tearDownClass(cls):
        cls.arrival._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def returned(self):
        """DECLARED CONSTRUCTED (the module docstring): the Castle switch, back from its 42."""
        policy = copy.deepcopy(self.arrival)
        self.assertEqual(policy._activate_safe_recall_fallback(self.town, 50), CASTLE)
        policy._fundraising_mode = None
        policy._planned_mining_runs = None
        policy._fundraising_purpose_record = None
        policy._floor_key = (CASTLE, 42, 0)
        return policy

    def with_means(self, board):
        """DECLARED CONSTRUCTED (the module docstring): telepathy and a reliable staff."""
        staff = replace(board.inventory[0], count=1, tval=TVAL_STAFF,
                        sval=SV_STAFF_DESTRUCTION, aware=True, known=True, charges=10)
        player = replace(board.player, abilities=board.player.abilities | {"telepathy"},
                         device_skill=200)
        return replace(board, player=player, inventory=(staff, *board.inventory[1:]))

    def test_a_angband_50_does_not_qualify(self):
        policy, board = self.returned(), self.town
        self.assertEqual(policy._dungeon_entry_depth(board, DUNGEON_ANGBAND, via_recall=True), 50)
        self.assertEqual(policy._missing_required_abilities(board, 50),
                         {"destruction", "telepathy"})
        self.assertFalse(alternate_lease.angband_qualifies(policy, board))
        self.assertFalse(alternate_lease.challenge(policy, board))

    def test_b_the_return_keeps_the_castle_band(self):
        policy, board = self.returned(), self.town
        decide(policy, board)
        self.assertEqual((policy._target_dungeon_id, policy._alternate_dungeon,
                          policy._alternate_dungeon_reason), (CASTLE, CASTLE, "safe_fallback"))
        self.assertEqual(getattr(policy, dive_floor.STATE), (CASTLE, 38))

    def test_c_with_the_means_and_telepathy_angband_is_taken(self):
        policy = self.returned()
        board = self.with_means(self.town)
        self.assertTrue(destruction_use.holds_means(policy, board))
        self.assertEqual(policy._missing_required_abilities(board, 50), frozenset())
        self.assertIsNone(policy._conquest_target(board))
        lease = policy._alternate_lease
        decide(policy, board)
        # Unfixed: (CASTLE, CASTLE, "safe_fallback") and the band held.
        self.assertEqual((policy._target_dungeon_id, policy._alternate_dungeon,
                          policy._alternate_dungeon_reason), (DUNGEON_ANGBAND, None, None))
        self.assertEqual(policy._target_dungeon_reason, "angband_recall_unlocked")
        self.assertTrue(alternate_lease.angband_qualifies(policy, board))
        self.assertIsNone(getattr(policy, dive_floor.STATE))
        self.assertIsNone(dive_floor.climb_dungeon(policy))
        # No over-extension evidence: the over-extended depth and the lease length stay.
        self.assertEqual(policy._last_overextended_depth, 49)
        self.assertEqual(policy._alternate_lease, lease)

    def test_control_a_running_lease_is_not_challenged(self):
        # Owner 2026-11-18 「潜りすぎの期限の間は鉄獄に挑まない」.  DECLARED CONSTRUCTED (docstring).
        policy = self.returned()
        policy._alternate_dungeon_reason = "over_extended_dives"
        policy._alternate_lease, policy._alternate_dives = alternate_lease.FIRST_LEASE, 2
        board = self.with_means(self.town)
        self.assertTrue(alternate_lease.angband_qualifies(policy, board))
        self.assertFalse(alternate_lease.challenge(policy, board))
        self.assertEqual((policy._alternate_dungeon, policy._alternate_dungeon_reason),
                         (CASTLE, "over_extended_dives"))

    def test_control_not_a_return(self):
        # A town board that ends no dive (the previous board in town) asks nothing.
        policy = self.returned()
        policy._floor_key = self.town.floor_key
        decide(policy, self.with_means(self.town))
        self.assertEqual(policy._alternate_dungeon, CASTLE)


class N1c216GlassCastleTest(unittest.TestCase):
    """The Glass castle conquest target, Angband 80 qualifying: Angband is challenged."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.arrival, _journal, steps = load(FIXTURES / "n1c-216-angband-challenge-1117",
                                            Path(cls.scratch.name))
        cls.recorded, supply = steps[0]
        cls.board = supply()
        cls.prepared = copy.deepcopy(cls.arrival)

    @classmethod
    def tearDownClass(cls):
        cls.arrival._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_a_the_arrival_board(self):
        policy, board = copy.deepcopy(self.prepared), self.board
        self.assertTrue(board.in_town)
        self.assertNotEqual(policy._floor_key[1], 0)  # the board a dive ends on
        self.assertEqual((policy._target_dungeon_id, policy._target_dungeon_reason,
                          policy._alternate_dungeon, policy._conquest_committed),
                         (GLASS_CASTLE, "conquest", None, GLASS_CASTLE))
        self.assertGreater(board.player.gold, 2_000_000)
        self.assertEqual({did: board.dungeon_recall_depths[did]
                          for did in (DUNGEON_ANGBAND, GLASS_CASTLE)},
                         {DUNGEON_ANGBAND: 80, GLASS_CASTLE: 60})
        self.assertEqual(fallback_depth_floor.floor(policy, board), 60)
        self.assertEqual(policy._missing_required_abilities(board, 80), frozenset())
        self.assertTrue(policy._recall_destination_safe(board, DUNGEON_ANGBAND))
        self.assertTrue(alternate_lease.angband_qualifies(policy, board))

    def test_b_no_guardian_no_conquest(self):
        # Owner 2026-11-18 「ガラスの城にはガーディアンがいないが考慮されているか？」: the Glass castle
        # has no final guardian (lib/edit/DungeonDefinitions.jsonc id 20), so it is no conquest
        # target and its latch is dropped.  The Mountain's guardian (468, its last floor 50) is
        # beatable on this board, so by 「制覇できる守護者がいれば制覇が先」 the Mountain is the
        # conquest target, and Angband 80 waits until it is conquered.
        policy, board = copy.deepcopy(self.prepared), self.board
        self.assertEqual(policy._dungeon_knowledge[GLASS_CASTLE].guardian_id, 0)
        self.assertEqual(policy._dungeon_knowledge[DUNGEON_ANGBAND].guardian_id, 0)
        mountain = policy._dungeon_knowledge[MOUNTAIN]
        self.assertEqual((mountain.guardian_id, mountain.max_depth), (468, 50))
        self.assertNotIn(MOUNTAIN, board.conquered_dungeon_ids)
        self.assertTrue(policy._guardian_fight_viable(board, mountain))
        decide(policy, board)
        # Unfixed: (GLASS_CASTLE, "conquest", GLASS_CASTLE).
        self.assertEqual((policy._target_dungeon_id, policy._target_dungeon_reason,
                          policy._conquest_committed), (MOUNTAIN, "conquest", MOUNTAIN))
        self.assertIsNone(policy._alternate_dungeon)

    def test_control_no_beatable_guardian_left_angband_is_taken(self):
        # DECLARED CONSTRUCTED: the Mountain conquered too (no beatable guardian left).
        policy = copy.deepcopy(self.prepared)
        board = replace(self.board, conquered_dungeon_ids=(
            *self.board.conquered_dungeon_ids, MOUNTAIN))
        decide(policy, board)
        self.assertEqual((policy._target_dungeon_id, policy._conquest_committed),
                         (DUNGEON_ANGBAND, None))


if __name__ == "__main__":
    unittest.main()
