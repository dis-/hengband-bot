"""Which work a Home pass charges to the visit's need attempts.

``_report_town_stop_pass`` charges one attempt to each category the plan put
on a stop.  A Home pass, though, performs one operation and leaves
(``home:leave-after-one-operation``), so a pass that only deposited an
overload had not tried the identification take at all.  n1-c life-115
(2026-11-03 07:21, build 7219d480d): five such Home passes used up the
one-attempt budget of identification-withdrawal, the claim retired and the
town end stopped under town:blocked:unmet:home_candidate_resolved with the
unknown Home long sword, five Identify scrolls carried and eight free slots.
Owner 2026-10-31 「当然だが、預けた装備を取り出して鑑定する処理が別途必要」:
a visit that can identify takes the item out and identifies it.

A category whose Home work is a filed Home errand is charged only by a pass
for which that errand was filed; every other category is charged as before.
"""

from __future__ import annotations

from typing import Any

from hengbot.policy_constants import STORE_HOME
from hengbot.town_visit import town_visit

# Home-stop category -> the Home errand purposes that perform its work.
ERRAND_WORK = {
    "identification-withdrawal": frozenset({"identification", "identification-catalog"}),
}


def note_filed(policy: Any, purpose: str) -> None:
    """A Home errand of ``purpose`` was filed for the next Home pass."""
    town_visit(policy).home_pass_errand_purposes.add(purpose)


def charged(policy: Any, store_type: int, categories: tuple[str, ...]) -> tuple[str, ...]:
    """The ``categories`` this pass charges; a Home pass consumes its filings."""
    if store_type != STORE_HOME:
        return categories
    filed = town_visit(policy).home_pass_errand_purposes
    result = tuple(category for category in categories
                   if category not in ERRAND_WORK or ERRAND_WORK[category] & filed)
    filed.clear()
    return result
