"""The one cleanup of a store sale's progress (maintainability review 2026-11-18 S2 / (a)-7).

A sale's progress lives in four policy attributes: the last emitted sale (``_last_sell_sig``),
the posted batch (``_batch_sell_pending``), the attempt count across boards
(``_store_sell_attempt``, three refuse the ware: ``SELL_ATTEMPT_LIMIT``) and the count of
unchanged boards after an emit (``_store_sell_stuck_count``).  They were reset by hand at each
end of a sale, each site its own subset, and one forgotten part stopped the bot: the observed
full-Home relief sale left the attempt count, so the next stack of the same name was refused
unsent (n1-a life-530 2026-11-18 03:53, dbaee9b130).

``end`` is that reset in one place.  Every end forgets the last emitted sale; each caller names
the other parts its end forgets, as it did before (no behaviour change).
"""
from __future__ import annotations

from typing import Any


def end(policy: Any, *, batch: bool = False, attempt: bool = False, stuck: bool = False) -> None:
    """Forget the last emitted sale, and the posted batch, attempt count, stuck count asked for."""
    policy._last_sell_sig = None
    if batch:
        policy._batch_sell_pending = None
    if attempt:
        policy._store_sell_attempt = None
    if stuck:
        policy._store_sell_stuck_count = 0
