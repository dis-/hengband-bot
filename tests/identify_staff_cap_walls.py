"""Declared wall: recorded boards under the pre-2026-10-03 Identify-staff cap.

USER DECISION 2026-10-03 (verbatim): 「鑑定の杖の所持数を4本以内にしたい」,
and for the case below 20 charges 「少ない杖から手放し買い直す」 (「4本を超えた
分は回数の少ない杖から売る（売れなければ自宅に預ける）。20回分に届かない時は、
回数の一番少ない杖を手放して店の回数の多い杖に買い替える。20回分の必須はその
まま。」).

The classC2 capture (2026-10-01) carries 「鑑定の杖 (5x 4回分)」: five staves,
twenty charges.  Under the four-staff cap the fifth staff is released, so on
that overweight board the Home weight remedy now deposits one staff instead of
four iron shots.  That pin's subject is the weight/guardian remedy, not the
staff count, so it is proven under the rule it was recorded with: the cap at
five staves (STAFF_IDENTIFY_MAX_COUNT = 5), which also disables the swap
because twenty charges are ready.  Nothing else changes.  The new choice on the
same unwalled board is pinned in
tests/test_classC2_departure_recorded.py::IdentifyStaffCapDivergenceTest.
"""
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import hengbot.policy as policy_module
import hengbot.policy_constants as constants_module
import hengbot.policy_supply as supply_module

PRE_DECISION_STAFF_IDENTIFY_MAX_COUNT = 5


@contextmanager
def pre_four_staff_cap_rule():
    """Run with the recorded-era five-staff cap in every module that reads it."""
    with ExitStack() as stack:
        for module in (constants_module, policy_module, supply_module):
            stack.enter_context(patch.object(
                module, "STAFF_IDENTIFY_MAX_COUNT",
                PRE_DECISION_STAFF_IDENTIFY_MAX_COUNT,
            ))
        yield
