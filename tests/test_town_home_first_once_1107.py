"""Home first is asked once per ware and town visit.

n1-a life-492 (2026-11-06 16:24-16:25, town:blocked:owner-retired-burst): a
drained-WIS warrior wanted 賢さ復活の薬 at the Alchemist.  The Home list (read
this visit) held one, so the town plan went to Home; the Home pass deposited,
read the list again and swept junk (its take left the list stale), but did not
bring the potion.  Back at the Alchemist the stale list made the observed
page's composition yield to Home again (shop:home-first-yields-to-current-
visit), so the bot walked to Home a second time; there the home-scan owner's
Escape and the progress seam's walks (labelled town-progress-invariant:defect:
..., owned by the detectors, with no route credit) retired three times.

The boards are constructed from policy_fixtures (DECLARED CONSTRUCTED): an
Alchemist entrance three cells from Home, the observed Alchemist page offering
the potion, and the Home list holding one.
"""
import tests  # noqa: F401 -- live runtime-file isolation, also for bare module runs

import unittest
from dataclasses import replace

from policy_fixtures import grid, item, player, store_item
from hengbot.model import (
    PLAYER_CLASS_WARRIOR,
    STORE_ALCHEMIST,
    STORE_HOME,
    SV_POTION_RESTORE_WIS,
    TVAL_POTION,
    Position,
    Snapshot,
    StoreState,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import StoreVisit


ENTRANCE = Position(10, 10)
HOME = Position(10, 7)
POTION = store_item("a", TVAL_POTION, SV_POTION_RESTORE_WIS, price=478,
                    name="Restore Wisdom")
HOME_POTION = item("h", TVAL_POTION, SV_POTION_RESTORE_WIS, name="Restore Wisdom")
PAGE = StoreState(STORE_ALCHEMIST, [POTION], page_top=0)


def board(position=ENTRANCE):
    return Snapshot(
        player(position.y, position.x, class_id=PLAYER_CLASS_WARRIOR, gold=20000,
               drained_stats=("wis",)),
        {
            ENTRANCE: replace(grid(10, 10), store_number=STORE_ALCHEMIST),
            Position(10, 9): grid(10, 9),
            Position(10, 8): grid(10, 8),
            HOME: replace(grid(10, 7), store_number=STORE_HOME),
        },
        [],
        floor_key=(0, 0, 0),
        town_flag=True,
        inventory=[],
    )


class HomeFirstOnceTest(unittest.TestCase):
    def test_second_home_first_after_a_home_pass_buys_the_shelf(self):
        policy = HengbotPolicy()
        # DECLARED CONSTRUCTED: the skill list is known, so the ~f request
        # does not take the boards.
        policy._skill_exp_request_key = lambda _snapshot: None
        policy._floor_key = (0, 0, 0)
        first = board()
        policy.choose_key(first)
        # The Home pass: the list read there holds the potion, the pass ends,
        # and the junk sweep's take leaves the list stale.
        policy.consume_home_knowledge((HOME_POTION,))
        policy._report_town_stop_pass(first, STORE_HOME, goal_satisfied=False)
        policy._invalidate_home_observation()
        # Back at the Alchemist with its page observed.
        policy._shop_observation = (PAGE, policy._decision_sequence)
        policy._store_visit = StoreVisit("town-errand", "shopping", STORE_ALCHEMIST)
        policy._shopping_approach_store_type = STORE_ALCHEMIST
        policy._shopping_approach_goal = ENTRANCE

        policy.choose_key(board())

        # Live: composition_refusal shop:home-first-yields-to-current-visit
        # and the walk back to Home.
        self.assertNotEqual(
            policy._shop_selector_diagnostics.get("composition_refusal"),
            "shop:home-first-yields-to-current-visit",
        )
        self.assertEqual(policy._home_gate_telemetry["branch"],
                         "wrapper-home-settled-this-visit")
        self.assertTrue(policy.last_reason.endswith("shop:one-shot-buy"),
                        policy.last_reason)

    def test_redirected_store_walk_is_measured_as_locomotion(self):
        policy = HengbotPolicy()
        reason = ("town-progress-invariant:defect:"
                  "home:request-knowledge-scan=>home:request-knowledge-scan")
        policy.last_reason = reason
        policy._shopping_approach_store_type = STORE_HOME
        policy._shopping_approach_goal = HOME
        vectors = []
        for position in (Position(10, 9), Position(10, 8)):
            policy._decision_sequence += 1
            # The store walk the progress seam ran on this decision.
            policy._staged_shop_approach = (
                object(), policy._decision_sequence, STORE_HOME, position, "4",
                "home:request-knowledge-scan")
            vectors.append(policy._town_arbiter_progress_vector(board(position), reason))
        # Live 16:25:17-18: the same durable vector on every step, scored no
        # progress until the detectors retired.
        self.assertNotEqual(vectors[0], vectors[1])
        self.assertEqual(vectors[1][-1][:2], ("locomotion", "detectors"))


if __name__ == "__main__":
    unittest.main()
