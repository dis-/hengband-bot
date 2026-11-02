"""Observe the claims the town hold closes (the hold keeps no closing record).

Until structure stage 2 B slice 4 the decision claim row carried the claim a
decision closed (``closed_claim``).  The row is gone; a test that pins which
claim a board closes, and how, watches the register's one ending seam
instead: every ``complete`` / ``release`` / ``expire`` / ``retire`` of the
standing claim and every ``close_suspended`` passes through
``ClaimRegister._note_ended``.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from hengbot.town_terminal import CLOSING_EVENTS, ClaimRegister


@contextmanager
def recorded_closings():
    """Yield a list that collects every claim closed inside the block, in order."""
    closed = []
    original = ClaimRegister._note_ended

    def note(register, claim):
        if claim is not None and claim.closed in CLOSING_EVENTS:
            closed.append(claim)
        return original(register, claim)

    with patch.object(ClaimRegister, "_note_ended", note):
        yield closed


def requester_families(policy):
    """The families that asked for the current store visit (sorted)."""
    return sorted(getattr(getattr(policy, "_store_visit", None), "requester_families", ()))
