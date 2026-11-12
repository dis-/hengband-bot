"""The one departure readiness table (town rebuild stage 1, owner 2026-11-12).

Owner 2026-11-12 「1〜3まで一気に進める」, stage 1 「出発の判断を1つの表に」:
per supply item, what the pack holds (``have``), what the departure needs
(``need``), where it comes from (``stores``) and whether a source is still
actionable (``obtainable``) -- read at ONE depth, the planned depth
(``_planned_depth``) the purchases, the Home retention and the ordinary
departure gate already read.

Before this table the same questions were answered in four places that drifted
apart: the ordinary departure gate (``_town_departure_conjuncts``), the forced
departure's minimum (``_departure_minimum``, which re-read every supply at the
visit's landing depth as well and kept its own copy of the recall count), the
procurement rows (``procurement_requirements``, which asked for Identify staff
charges an absorbed staff already answers, and listed Teleportation and Cure
Critical Wounds only from 2F while the gate asks for them from 1F) and the
town end's leaf-to-label map (``town_terminal.LEAF_SUPPLY_LABELS``, matched by
label strings).  They now read this table; none recomputes a target.

A *leaf* is a departure-gate leaf that a supply answers (``recall_departure_ready``
...); its ``met`` is the gate's own predicate.  Its ``items`` are the
procurement rows that supply it.  Items without a leaf (the mining kit, an
identification source, *Destruction* uses, quest carry) are procurement rows
only: no departure leaf reads them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from hengbot.model import Snapshot
from hengbot.policy_constants import (
    FOOD_STOCK_TARGET,
    FOOD_TYPE_MANA,
    STAFF_IDENTIFY_MIN_CHARGES,
    STAFF_IDENTIFY_MIN_DEPTH,
)


# The departure leaves a supply answers, in the procurement rows' order.
SUPPLY_LEAVES = (
    "recall_departure_ready",
    "food_ready",
    "light_ready",
    "teleport_ready",
    "cure_critical_ready",
    "remove_curse_ready",
    "identify_staff_ready",
)

# The quest-carry procurement labels (``_quest_carry_status`` names).
QUEST_CARRY_LABELS = {
    "launcher": "Quest launcher",
    "throwing_items.lit_torch": "Quest throwing torches",
    "throwing_items.shot": "Quest shots",
    "throwing_items.arrow": "Quest arrows",
    "throwing_items.bolt": "Quest bolts",
    "throwing_items.launcher_ammo": "Quest launcher ammunition",
    "required_scrolls.light": "Quest Light scrolls",
    "required_scrolls.teleport": "Quest Teleport scrolls",
    "utility_tools.wall_breach": "Quest wall-breach tools",
}


@dataclass(frozen=True)
class SupplyItem:
    """One procurement row: a countable supply and its departure target."""

    label: str
    have: int
    need: int
    # The supply-ledger kind (``SupplyStatus.kind``); None for an item the
    # ledger does not keep (a lantern, torches, Identify staff charges ...).
    kind: str | None = None
    # For a ledger kind: whether Home or a store may still supply it.
    obtainable: bool = True
    stores: tuple[int, ...] = ()

    @property
    def short(self) -> bool:
        return self.have < self.need

    @property
    def stocked_out(self) -> bool:
        """Short, of a ledger kind, with no actionable source this visit."""
        return self.short and self.kind is not None and not self.obtainable


class SupplyLeaf:
    """A departure leaf a supply answers: the gate's verdict and its items.

    Both are read only when asked for: the departure gates read ``met`` alone
    and the procurement rows read ``items`` alone, as they always did.
    """

    _UNREAD = object()

    def __init__(self, leaf: str, met: Callable[[], bool | None],
                 items: Callable[[], list[SupplyItem]]) -> None:
        self.leaf = leaf
        self._met = met
        self._met_read: Any = self._UNREAD
        self._items = items
        self._read: tuple[SupplyItem, ...] | None = None

    @property
    def met(self) -> bool | None:
        if self._met_read is self._UNREAD:
            self._met_read = self._met()
        return self._met_read

    @property
    def items(self) -> tuple[SupplyItem, ...]:
        if self._read is None:
            try:
                self._read = tuple(self._items())
            except (AttributeError, TypeError, ValueError):
                self._read = ()
        return self._read


class ReadinessTable:
    """The departure supply readiness of one board at one depth."""

    def __init__(self, depth: int, leaves: dict[str, SupplyLeaf],
                 extra: Callable[[], list[SupplyItem]]) -> None:
        self.depth = depth
        self.leaves = leaves
        self._extra = extra
        self._extra_read: tuple[SupplyItem, ...] | None = None

    @property
    def extra(self) -> tuple[SupplyItem, ...]:
        """The procurement items no departure leaf reads (read on demand)."""
        if self._extra_read is None:
            self._extra_read = tuple(self._extra())
        return self._extra_read

    def met(self, leaf: str) -> bool | None:
        return self.leaves[leaf].met

    def items(self) -> list[SupplyItem]:
        """Every procurement item, in the procurement rows' order."""
        ordered = [item for name in SUPPLY_LEAVES[:-1]
                   for item in self.leaves[name].items]
        # The mining kit and identification source rows precede the Identify
        # staff row, as procurement_requirements always listed them.
        mining = [item for item in self.extra if item.label in _BEFORE_IDENTIFY_STAFF]
        rest = [item for item in self.extra if item.label not in _BEFORE_IDENTIFY_STAFF]
        return [*ordered, *mining, *self.leaves["identify_staff_ready"].items, *rest]

    def leaf_kinds(self, leaf: str) -> set[str]:
        """The supply-ledger kinds that supply ``leaf``."""
        entry = self.leaves.get(leaf)
        return set() if entry is None else {item.kind for item in entry.items
                                            if item.kind is not None}

    def stocked_out(self, leaf: str) -> bool:
        """Whether a short ledger supply of ``leaf`` has no actionable source.

        The stock-out mining run answers such a leaf (town_terminal
        ``stockout_mining_supply_terminal``)."""
        entry = self.leaves.get(leaf)
        return entry is not None and any(item.stocked_out for item in entry.items)

    def procurement_rows(self) -> list[dict[str, int | str]]:
        """The unmet procurement rows (``procurement_requirements``)."""
        rows = []
        for item in self.items():
            if not item.short:
                continue
            row: dict[str, int | str] = {
                "item": item.label, "current": item.have, "target": item.need,
                "missing": item.need - item.have,
            }
            if item.kind is not None and not item.obtainable:
                row["blocked_reason"] = "no-actionable-supplier"
            rows.append(row)
        return rows


_BEFORE_IDENTIFY_STAFF = frozenset({
    "Treasure Detection scrolls", "Digging tool", "*Identify* source", "Identify source",
})


def _guarded(predicate: Callable[[], Any]) -> bool | None:
    """A leaf verdict; a missing input is unknown (None), never permission."""
    try:
        value = predicate()
    except (AttributeError, TypeError, ValueError):
        return None
    return None if value is None else bool(value)


def _ledger_item(label: str, status) -> SupplyItem:
    return SupplyItem(label, status.count, status.required_departure, status.kind,
                      status.obtainable, status.stores)


def readiness_table(policy: Any, board: Snapshot, *, pure: bool = False) -> ReadinessTable:
    """Read the departure supply readiness of ``board`` at the planned depth.

    ``pure`` is the forced departure's read (``_departure_minimum``): the
    fixed-quest head is not cached (``_identify_staff_ready``).
    """
    depth = policy._planned_depth()
    read: dict[str, Any] = {}

    def ledger_of(kind: str):
        if "ledger" not in read:
            read["ledger"] = policy._supply_ledger(board, depth)
        return read["ledger"][kind]

    leaves: dict[str, SupplyLeaf] = {}

    def leaf(name: str, met: Callable[[], Any], items: Callable[[], list[SupplyItem]]):
        # The forced departure's minimum reads a missing input as unknown;
        # the ordinary gate lets it raise, as its predicates always did.
        leaves[name] = SupplyLeaf(
            name, (lambda: _guarded(met)) if pure else met, items)

    # Each verdict is the policy's own supply predicate over the same ledger
    # (count >= the departure target at the planned depth); the table names
    # them once.
    leaf("recall_departure_ready", lambda: policy._recall_departure_ready(board),
         lambda: [_ledger_item("Word of Recall scrolls", ledger_of("recall"))])

    mana = board.player.food_type == FOOD_TYPE_MANA
    leaf("food_ready", lambda: policy._food_ready(board),
         lambda: [_ledger_item("Device charges for food" if mana else "Food rations",
                               ledger_of("food"))])

    def light_items() -> list[SupplyItem]:
        if depth >= 2:
            return [SupplyItem("Brass lantern", int(policy._owns_lantern(board)), 1),
                    _ledger_item("Flasks of oil", ledger_of("oil"))]
        if policy._owns_lantern(board):
            return [_ledger_item("Flasks of oil", ledger_of("oil"))]
        return [SupplyItem("Usable light sources", policy._count_usable_torches(board),
                           FOOD_STOCK_TARGET)]

    leaf("light_ready", lambda: policy._light_ready(board), light_items)
    leaf("teleport_ready", lambda: policy._teleport_ready(board),
         lambda: [_ledger_item("Teleport scrolls", ledger_of("teleport"))])
    leaf("cure_critical_ready", lambda: policy._cure_critical_ready(board),
         lambda: [_ledger_item("Cure Critical Wounds potions", ledger_of("cure"))])

    def curse_items() -> list[SupplyItem]:
        kind = policy._required_remove_curse_kind(board)
        if kind is None:
            return []
        return [_ledger_item("*Remove Curse* scrolls" if kind == "star-remove-curse"
                             else "Remove Curse scrolls", ledger_of(kind))]

    leaf("remove_curse_ready", lambda: policy._required_remove_curse_kind(board) is None,
         curse_items)

    def identify_met() -> bool:
        return (policy._identify_staff_ready(board, cache_fixed_quest_head=False) if pure
                else policy._identify_staff_ready(board))

    def identify_items() -> list[SupplyItem]:
        # The leaf asks for the charges unless an absorbed staff answers it,
        # from STAFF_IDENTIFY_MIN_DEPTH or for a quest that carries the staff
        # (_identify_staff_ready); the row is the leaf's, not a second rule.
        if policy._identify_staff_absorbed(board):
            return []
        strategy = (policy._carry_procurement_strategy(board, cache_fixed_quest_head=False)
                    if pure else policy._carry_procurement_strategy(board))
        quest = strategy is not None and bool(
            strategy.engagement_plan.get("carry_identify_staff"))
        if depth < STAFF_IDENTIFY_MIN_DEPTH and not quest:
            return []
        return [SupplyItem("Identify staff charges",
                           policy._total_identify_staff_charges(board),
                           STAFF_IDENTIFY_MIN_CHARGES)]

    leaf("identify_staff_ready", identify_met, identify_items)
    return ReadinessTable(depth, leaves, lambda: _extra_items(policy, board, depth, pure))


def _extra_items(policy: Any, board: Snapshot, depth: int, pure: bool) -> list[SupplyItem]:
    """The procurement items no departure leaf reads."""
    items: list[SupplyItem] = []
    mining = policy._fundraising_mining_requirements(board)
    if mining is not None:
        detection_target, digger_target = mining
        items.append(SupplyItem("Treasure Detection scrolls",
                                policy._count_treasure_detection_scrolls(board),
                                detection_target))
        items.append(SupplyItem("Digging tool", policy._digging_tool_count(board),
                                digger_target))
    if policy._identification_need is not None:
        full = policy._identification_need == "full"
        source = policy._find_identification_source(
            board, full=full,
            reliable_only=policy._identification_requires_reliable_source(board))
        items.append(SupplyItem("*Identify* source" if full else "Identify source",
                                int(source is not None), 1))
    destruction_target = policy._required_destruction_uses(board)
    if destruction_target:
        items.append(SupplyItem("*Destruction* uses", policy._total_destruction_uses(board),
                                destruction_target))
    strategy = (policy._carry_procurement_strategy(board, cache_fixed_quest_head=False)
                if pure else policy._carry_procurement_strategy(board))
    if strategy is not None:
        for name, status in policy._quest_carry_status(board, strategy.required_force).items():
            if name in policy._abandoned_quest_carry_requirements:
                continue
            items.append(SupplyItem(QUEST_CARRY_LABELS.get(name, f"Quest carry: {name}"),
                                    int(status["measured"]), int(status["required"])))
    return items


def leaf_supply_kinds(policy: Any, board: Snapshot, leaf: str) -> set[str]:
    """The ledger kinds supplying ``leaf`` (empty for a leaf no supply answers)."""
    if leaf not in SUPPLY_LEAVES:
        return set()
    return readiness_table(policy, board).leaf_kinds(leaf)

