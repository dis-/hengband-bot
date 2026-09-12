"""Typed shared authority for town purchase eligibility and emission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PurchaseContext:
    snapshot: object


@dataclass(frozen=True)
class PurchaseMatch:
    rung_id: str
    category: str
    item_identity: tuple[object, ...]
    current: int | None = None
    target: int | None = None
    shortage: int | None = None
    rationale: str = ""


@dataclass(frozen=True)
class PurchaseRung:
    rung_id: str
    category: str
    matcher: Callable[[PurchaseContext, object], PurchaseMatch | None]

    def match(self, context: PurchaseContext, item: object) -> PurchaseMatch | None:
        return self.matcher(context, item)


@dataclass(frozen=True)
class PurchaseSelection:
    match: PurchaseMatch
    item: object
    supplier: int
    context: PurchaseContext
    quantity: int

