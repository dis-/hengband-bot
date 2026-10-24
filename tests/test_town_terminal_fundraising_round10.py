"""Town fundraising refusals preserve the skipped run body's confirmation.

Constructed context: the goldburn town board, income mode and the existing
scavenge eligibility verdict. No carried kit is added; the terminal refuses.
"""

import tests  # noqa: F401

import unittest
from unittest.mock import patch

from hengbot import town_terminal as tt
from hengbot.model import STORE_ALCHEMIST
from test_goldburn_shopping_constructed import board
from test_town_terminal_departure import policy_on


def outcome(rung, mode, allow_scavenge, enforce):
    snap = board()
    policy = policy_on(snap)
    policy._fundraising_mode = mode
    policy._planned_mining_runs = 1
    policy._town_store_attempted[STORE_ALCHEMIST] = snap.turn
    offers = []
    decl = tt.TERMINALS[rung]

    def body():
        if enforce:
            raise AssertionError("a refused run must not dispatch its body")
        return policy._fundraising_key(snap, [])

    with patch.dict(tt.TERMINALS, {
            rung: decl._replace(mode=tt.ENFORCE if enforce else tt.SHADOW)}), \
            patch.object(policy, "_offer_execution_no_step",
                         side_effect=lambda **kw: offers.append(kw)), \
            patch.object(policy, "_detectionless_scavenge_allowed",
                         return_value=allow_scavenge):
        key = policy._town_producer_entry(rung, body)
    return (key, offers, policy._fundraising_mode, policy._planned_mining_runs,
            policy._town_restock_suppressed, dict(policy._town_store_attempted))


class FundraisingRefusalConfirmationTest(unittest.TestCase):
    def test_run_rungs_keep_the_body_confirmation_in_every_town_mode(self):
        for rung in ("_fundraising_key#1", "_fundraising_key#2"):
            for mode, allow in (("prepare", False), ("mine", False),
                                ("scavenge", False), ("scavenge", True)):
                with self.subTest(rung=rung, mode=mode, allow=allow):
                    shadow = outcome(rung, mode, allow, False)
                    enforce = outcome(rung, mode, allow, True)
                    self.assertEqual(enforce, shadow)
                    self.assertIsNone(enforce[0])
                    if mode == "prepare":
                        self.assertEqual(enforce[1][0]["cause"], "fundraising-mode-inactive")
                    elif mode != "scavenge" or allow:
                        self.assertEqual(enforce[1][0]["cause"], "outside-mining-floor")
                    else:
                        self.assertEqual(enforce[1], [])
                        self.assertEqual(enforce[2], "prepare")
                        self.assertIsNone(enforce[3])
                        self.assertNotIn(STORE_ALCHEMIST, enforce[5])

    def test_departure_dispatcher_does_not_borrow_a_run_confirmation(self):
        snap = board()
        policy = policy_on(snap)
        policy._fundraising_mode = "prepare"
        rung = "_town_special_key"
        decl = tt.TERMINALS[rung]
        with patch.dict(tt.TERMINALS, {rung: decl._replace(mode=tt.ENFORCE)}), \
                patch.object(policy, "_offer_execution_no_step") as offer:
            key = policy._town_producer_entry(
                rung, lambda: self.fail("refused departure must not dispatch"),
                family="departure")
        self.assertIsNone(key)
        offer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
