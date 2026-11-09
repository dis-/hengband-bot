"""The viewing bots' town stops of 2026-11-09 after 08:00 (town-stops-1109b).

Recorded: the town-arrival checkpoints of the incident captures and their
journals (tests/extract_town_stops_1109b_fixtures.py).  Every decision goes
through the public ``choose_key`` on the restored arrival policy; each key is
acknowledged as posted the way the CLI does (``confirm_key_posted`` and the
staged prompt chain), as tests/replay_town_arrival.py replays a visit
(``RecordedVisit`` of tests/test_stops_1109_town_recorded.py).

DECLARED for every replay: a row whose recorded decision the replay does not
reproduce is fed with the recorded key posted (the recorded boards follow);
the pins name the rows they assert.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from hengbot import equipment_optimizer, me_powerful_activation
from hengbot.model import STORE_HOME
from hengbot.policy_constants import STORE_STUCK_LIMIT
from tests.test_stops_1109_town_recorded import RecordedVisit

FIXTURES = Path(__file__).with_name("fixtures") / "town-stops-1109b"


class Visit(RecordedVisit):
    fixtures = FIXTURES


class JunkSweepTakeAtEntranceTest(Visit):
    """n1-a life-497 2026-11-09 08:46 town:blocked:owner-retired-burst.

    The Home junk sweep chose the shelf's 切れ味のダガー for sale (relief mode
    sale, its Home errand filed) and left Home for the entrance's atomic take
    (row 16, home:junk-sweep-withdraw).  On the outside board the town-item
    processing took the relief's pending Home item for a failed
    identification withdrawal and deferred it, and the rebuilt errand plan
    put the Magic shop first (row 17, shop:approach '&'); in that store the
    sweep left again for Home, and Home -> Magic -> Home -> Alchemist ...
    went on until the owner retirements (rows 16-31 of the record).

    Fix: the relief's filed take keeps Home first in the plan, as every
    queued Home take does (``_next_required_store_type``).

    DECLARED WALL: the record predates C (a611ad3296, owner 2026-11-09
    「Q34 の武器は未鑑定で握らない」); with it the unidentified Q34 weapons wait
    for identification and row 6 takes one of them out of Home instead of the
    recorded take, so the visit never reaches the sweep.  C's tval set is
    emptied for the whole replay; the relief, the plan and the
    identification processing under test are untouched.
    """

    fixture = "i497"

    def setUp(self):
        super().setUp()
        wall = mock.patch.object(equipment_optimizer, "Q34_WIELD_IDENTIFY_FIRST_TVALS", frozenset())
        wall.start()
        self.addCleanup(wall.stop)

    def test_recorded_rows_replay_to_the_sweep_take(self):
        self.assertEqual([self.journal[row]["reason"] for row in (15, 16, 17)], [
            "shop:travel", "home:junk-sweep-withdraw", "shop:approach"])
        self.assertEqual(self.journal[17]["key"], "\x1b`n&.")
        self.assertEqual(self.replay_to(17), [])
        relief = self.policy._home_full_relief
        self.assertTrue(relief["sweep"])
        self.assertEqual(relief["mode"], "sale")
        self.assertTrue(self.policy._home_full_relief_take_filed())

    def test_the_sweep_take_runs_at_the_home_entrance(self):
        self.replay_to(17)
        _board, key, reason = self.decide(17)
        self.assertEqual(reason, "home-errand:atomic-withdraw:full-home-sale")
        self.assertTrue(key.startswith("5"), key)
        self.assertEqual(self.policy._shopping_approach_store_type, STORE_HOME)


class RefusedDepositAwaitBesideSleeperTest(Visit):
    """n1-a life-497 2026-11-09 11:31 town:blocked:survival:identify_staff_ready.

    Row 10 posted the Home deposit 'dr21\rdpdd\x1b' of the arrows, the
    追加攻撃のモーニングスター and a potion; the game answered
    「我が家にはもう置く場所がない。」 for the morning star (the arrows and the
    potion stacked).  The released deposit keeps the Home visit in flight
    until its outside observation ends (STORE_STUCK_LIMIT boards, then the
    full-Home relief of the refused entry), and its own owner waits for it
    (home:atomic-deposit-await-confirmation).  That owner answered only with
    no hostile in view: a sleeping ブラックマーケットのエージェント 7 cells away
    kept it silent, every store approach was refused (acquire_store_visit),
    the town end stepped off (row 11) and stopped with the Identify staff
    short (14 of 20 charges, the Magic shop never visited, row 14).  The
    same stop recurred at 11:32 after the restart.

    Fix: a sleeping hostile does not keep the waiting owner silent.
    """

    fixture = "j497"

    def test_recorded_rows_replay_to_the_refusal(self):
        self.assertEqual(self.replay_to(11), [])
        self.assertEqual(self.journal[10]["key"], "dr21\rdpdd\x1b")
        self.assertEqual(self.journal[11]["reason"], "town:entrance-step-off:town:end-step-off")
        self.assertEqual(self.journal[14]["reason"], "town:blocked:survival:identify_staff_ready")
        hostiles = self.policy._physical_hostiles(self.board(11))
        self.assertEqual([(monster.race_id, monster.asleep) for monster in hostiles], [(14, True)])

    def test_the_deposit_wait_is_answered_beside_the_sleeper(self):
        self.replay_to(11)
        _board, _key, reason = self.decide(11)
        self.assertTrue(self.policy._home_full_refused)
        self.assertTrue(reason.endswith("home:atomic-deposit-await-confirmation"), reason)
        for row in (12, 13, 14):
            _board, key, reason = self.decide(row)
            self.assertEqual((key, reason), ("5", "home:atomic-deposit-await-confirmation"))

    def test_the_wait_ends_in_the_relief_not_the_stop(self):
        self.replay_to(14)
        board, _key, _reason = self.decide(14)
        # DECLARED: the record ends at row 14; its outside board is decided
        # again, ten game turns a decision, as the waited turns leave it.
        for _ in range(STORE_STUCK_LIMIT):
            if self.policy._home_atomic_deposit_pending is None:
                break
            board = replace(board, turn=board.turn + 10, messages=())
            self.post(self.policy.choose_key(board))
        self.assertIsNone(self.policy._home_atomic_deposit_pending)
        self.assertIsNotNone(self.policy._home_full_relief)
        # The visit moved on from the released deposit (a store approach).
        self.assertNotEqual(self.policy.last_reason, "home:atomic-deposit-await-confirmation")
        self.assertFalse(self.policy.last_reason.startswith("town:blocked"), self.policy.last_reason)


class PowerfulIdentifyCostCoveredTest(Visit):
    """n1-c life-179 2026-11-09 08:16 (and life-180 11:22, 12:14, 12:15)
    town:blocked:owner-retired-burst: the Powerful Activation *Identify* cost
    counted as a hit, town:seek-shelter after every use, the taken piece lost
    its hold and was shelved again until the Home visits ran out -- cause D of
    stops-1109-town (22e78a2ee6, ``me_powerful_activation.own_cost``).  Pinned
    here from this record: row 0 is the bot's own use, row 1 its first board.
    """

    fixture = "d179"

    def test_the_use_cost_is_no_hit(self):
        _board, key, reason = self.decide(0)
        self.assertEqual((key, reason), (self.journal[0]["key"], "me-powerful:identify"))
        self.assertEqual(self.journal[1]["reason"], "town:seek-shelter")
        board, _key, reason = self.decide(1)
        self.assertNotEqual(reason, "town:seek-shelter")
        self.assertFalse(self.policy._took_damage)
        self.assertTrue(me_powerful_activation.spare_identify_ready(self.policy, board))


if __name__ == "__main__":
    unittest.main()
