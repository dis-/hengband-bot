"""#47 D52: the slow town trips of the Magic-Eater staff sequence (2026-11-01).

Owner: 「n1-cの街での動きが遅いように見えた。要検査」 and 「街での移動は可能な限り
トラベルコマンドを活用して」.  n1-c life-074 (build bot-f9c921d32; decisions
4870-5335 of C:\\hengband-backups\\pdca\\captures\\n1c-tower-trips-1101\\
life-074-decisions-tail.jsonl.gz) spent 16886 -> 5393 gold and three minutes
on one stage: four Tower trips and eight inn fares, every leg walked one
decision per cell.

1. Buy round.  Stage 2 left for the Tower as soon as the observed shelf lacked
   a carried stage's missing staffs (``carried and _stocked_out``), before the
   other towns' shelves were looked at; Morivant's own shelf was looked at only
   after its Tower visit; the stage-1 Tower left Morivant without looking at
   its shelf.  Fixed: one buy round per stage (``_round_open``): this town's
   Magic shelf, the Outpost's, the other visited towns' that the spare gold
   pays, Morivant last, then one Tower visit.

The life-074 boards are gone (the 01:41 restart truncated its state log), so
the checks replay the recorded boards of the same decisions in earlier lives:
life-054 (tests/fixtures/me-nokey-20261031.json.gz, ring rows 104-108, the
Outpost after its Magic shop: four stage-2 staffs carried, Detect Evil not on
the shelf, 60,981 gold, every town visited) and life-067 / life-068
(tests/fixtures/me-staff-loops-20261031.json.gz: the stage-1 Tower, and the
Morivant arrival with Door/Stair Location carried).  Every decision is the
public ``choose_key``; every key goes through the production executor
(test_me_nokey_1031_recorded.PostedKey).  DECLARED CONSTRUCTED where a case
says so: shelves the round has seen (``searched_towns``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from unittest.mock import patch

from hengbot import me_staff_sequence as sequence
from hengbot.model import STORE_MAGIC
from tests import test_me_nokey_1031_recorded as nokey
from tests import test_me_staff_loops_1031_recorded as loops

TELMORA = 1


def loops_policy(name):
    case = loops.CASE[name]
    return case, loops.new_policy(case, loops.CASE["inn"]["skill"], record=case["sequence"])


class BuyRoundTest(nokey.PostedKey):
    """Root 1: the stage buys every staff the round's shelves sell first."""

    def test_outpost_board_looks_at_the_other_towns_before_the_tower(self):
        # life-054 row 108 (the recorded record).  Unfixed:
        # me-staff:travel-morivant (the carried four to the Tower, Detect Evil
        # never looked for in Telmora or Angwil).
        policy = nokey.staff_policy(nokey.staff_board(0))
        nokey.drive_staff_boards(policy, 3)
        raw = nokey.staff_board(4)
        with patch.object(policy, "_town_teleport_key", wraps=policy._town_teleport_key) as leg:
            key = nokey.decide(policy, raw, nokey.CASE["staff"]["skill"])
        self.assertEqual(policy.last_reason, "me-staff:search-staff", key)
        self.assertEqual(leg.call_args.args[1], TELMORA)  # Morivant last: its Tower ends the round
        self.post(policy, raw, key)

    def test_stage1_tower_looks_at_morivants_shelf_first(self):
        # life-067 at the Tower after stage 1.  Unfixed: me-staff:return-to-shop
        # (the Outpost, without a look at the shelf beside the Tower).
        case, policy = loops_policy("inn")
        raw = case["boards"][0]
        key = loops.decide(policy, raw)
        self.assertTrue(policy.last_reason.startswith("shop:"), (key, policy.last_reason))
        self.assertEqual(policy._shopping_approach_store_type, STORE_MAGIC)
        self.post(policy, raw, key)

    def test_morivant_arrival_looks_at_its_shelf_before_the_tower(self):
        # life-068 Morivant arrival, the recorded record: the Outpost's shelf
        # seen in this wait (searched_towns 0), Morivant's not (272191 is
        # before shelf_after_turn 272317); Door/Stair carried short, Trap
        # Location missing.  Unfixed: me-staff:approach-tower.
        case, policy = loops_policy("tower")
        sequence.state(policy).searched_towns.update({0: 322575, 2: 272191})
        raw = case["boards"][0]
        key = loops.decide(policy, raw)
        self.assertTrue(policy.last_reason.startswith("shop:"), (key, policy.last_reason))
        self.assertEqual(policy._shopping_approach_store_type, STORE_MAGIC)
        self.post(policy, raw, key)


if __name__ == "__main__":
    unittest.main()
