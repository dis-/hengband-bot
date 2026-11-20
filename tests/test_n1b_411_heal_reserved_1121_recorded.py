"""n1-b life-411: the low-HP heal refused by a parked Home deposit, no key (2026-11-21 03:21).

life-411 (Magic-Eater Lv 50, Angband 95F, bot fadb10501) read Word of Recall and waited for it
(``return:wait-recall``).  On the last board (turn 11214213) the ESP-sensed 灰色の掠奪者 cast a
nether ball (「地獄球の呪文を唱えた」) and HP fell 771 -> 695 of 1153.  The damaged wait was
rewritten to a step (``_forbid_wait_while_damaged``, ``no-wait:least-visited``) and the low-HP
walk gate answered it with a Potion of Healing (``item:heal``).  The quaff composed no key:
the 12 体力回復の薬 {@4} were reserved by ``home-full-retry``.  At the town visit before
(arrival 03:19:04) the Home was full and one surplus potion's deposit was parked for a later
visit (policy_home._defer_home_full_deposit); that ledger, signature-wide, travelled into the
dungeon and owned every Healing potion against every sink but a deposit.  The decision posted
no key and the CLI stopped with no-key-exhausted.

The fix (item_reservation.CONSUMPTION_SINKS): the parked deposit owns the transfer to the Home,
not the use; a quaff, read, eat or device use of the stack is not refused by it.  The ledger
still refuses a sale or a wield (test_n1c_214_equip_departure_1116_recorded).

Recorded (tests/fixtures/n1b-411-heal-reserved-1121.json.xz, see
tests/extract_n1b_411_heal_reserved_1121_fixture.py): the 29 player-turn boards of the ring,
their decision rows, and the retry ledger of the town-arrival checkpoint.  The boards are
decided through the public ``choose_key`` with the ledger held.

DECLARED RECONSTRUCTED: the skill reply the process remembered (as in
test_n1b_411_anaguma_close_1119_recorded); nothing else is set on the policy.
"""
import tests  # noqa: F401 -- isolate live runtime files

import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import item_reservation
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-heal-reserved-1121.json.xz"
HEALING = (75, 37)
WAITING = 7  # the first row of the recorded return:wait-recall run (turn 11214150)


class N1b411HealReserved1121RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.scratch = TemporaryDirectory()
        policy = _policy(Path(cls.scratch.name), cls.monrace)
        boards = [parse_snapshot(raw, cls.monrace) for raw in cls.data["boards"]]
        policy.prime(boards[0])
        # DECLARED RECONSTRUCTED (module docstring): the skill reply.
        policy._skill_exp_cache = (0, 0, boards[0].player.level, policy._town_visit_epoch)
        # The recorded retry ledger the arrival checkpoint carried out of the town.
        policy._home_full_retry_deposits = tuple(
            (tuple(signature), *rest) for signature, *rest in cls.data["retry_deposits"])
        cls.replayed = []
        for board in boards:
            key = policy.choose_key(policy.with_known_skill_exp(board))
            cls.replayed.append((key, policy.last_reason))
        cls.policy, cls.boards = policy, boards

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def healing(self, board):
        return next(item for item in board.inventory if (item.tval, item.sval) == HEALING)

    # ------------------------------------------------------------ the record

    def test_the_record_waits_for_recall_then_posts_no_heal(self):
        recorded = [(row["key"], row["reason"]) for row in self.data["decisions"]]
        self.assertEqual(recorded[-1], (None, "item:heal"))
        self.assertIn(("rf", "deep-teleport:recall"), recorded)
        self.assertEqual(recorded[WAITING:-1], [("5", "return:wait-recall")] * (len(recorded) - 1 - WAITING))
        last = self.boards[-1]
        self.assertTrue(last.player.recalling)
        self.assertEqual((last.player.hp, last.player.max_hp), (695, 1153))
        self.assertEqual(self.boards[-2].player.hp, 771)
        self.assertEqual(last.dungeon_level, 95)
        # The ledger parks one Healing potion; the pack carries the whole stack of 12.
        (signature, count, deposit), = self.data["retry_deposits"]
        self.assertEqual((tuple(signature[1:]), count, deposit), (HEALING, 11, 1))
        potion = self.healing(last)
        self.assertEqual(potion.count, 12)
        self.assertEqual(self.policy._item_signature(potion), tuple(signature))

    def test_the_recall_wait_before_the_hit_replays_as_recorded(self):
        """The wait rows (the boards before them only prime the policy: the record's absorbed
        powers, *Destruction* and the Recall read, are not reconstructed)."""
        recorded = [(row["key"], row["reason"]) for row in self.data["decisions"]]
        self.assertEqual(self.replayed[WAITING:-1], recorded[WAITING:-1])

    # ------------------------------------------------------------ the pins

    def test_the_low_hp_heal_is_quaffed_with_the_deposit_parked(self):
        """The stop's board: the heal composes its quaff instead of an empty key."""
        potion = self.healing(self.boards[-1])
        self.assertEqual(self.replayed[-1], ("q" + potion.slot, "item:heal"))
        self.assertIsNotNone(self.policy._home_full_retry_deposits)

    def test_the_parked_deposit_still_owns_the_transfer(self):
        board = self.boards[-1]
        potion = self.healing(board)
        for work in (("shop-sell", "sell"), ("consumption", "destroy")):
            verdict = item_reservation.item_reserved_by_other(self.policy, board, potion, work)
            self.assertEqual(verdict.owner, "home-full-retry", work)
        for sink in ("quaff", "read", "eat"):
            self.assertIsNone(item_reservation.item_reserved_by_other(
                self.policy, board, potion, ("consumption", sink)), sink)


if __name__ == "__main__":
    unittest.main()
