"""Admit every untaken quest's supplies in a test of the supply plumbing.

Owner 2026-11-19 「条件がそろってから買い自宅に置く」 (quest_supply_gate): an untaken quest's
carry is procured only once its other acceptance conditions are met.  The constructed and
recorded boards of the carry plumbing tests (purchase, retention, departure) predate that rule
and do not all meet those conditions; they test what happens once the carry is asked.
"""
from unittest.mock import patch


def admit_all(case) -> None:
    patcher = patch("hengbot.quest_supply_gate.other_conditions_met", return_value=True)
    patcher.start()
    case.addCleanup(patcher.stop)
