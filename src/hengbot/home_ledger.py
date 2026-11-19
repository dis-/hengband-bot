"""The one ledger of what the character owns and each item's fate (Home root fix, stage 1).

Owner 2026-11-19 「自宅の満杯問題で問題を起こしすぎなので根本解決すること」 (PROPOSAL
C:\\hengband-backups\\pdca\\home-full-root-1119, 3-1 and 3-6 stage 1): the worn equipment, the
pack and the Home census in one list, each row's fate from ``item_fate.fate``, recorded once per
town visit beside the answers of today's Home deciders (``_home_full_sale_candidate``,
``_home_full_discard_candidate``) so the stages after it can see where they disagree.

Record only: nothing here is read on the decision path.  The summary (``summary``) is the
decision log's ``home_ledger`` field on the decision that took it (``report``):

* ``home``: the Home's stack count and the cap (``HOME_KEEP_CAP``, owner 2026-11-19 「200件（空き
  40）」);
* ``fates``: the Home stacks per fate, and ``pack`` the carried stacks per fate;
* ``kept``: the Home stacks no tidy may take (fate ``home``, ``identify``, ``use-now``), by kind in
  ``kept_kinds``, of which ``top10`` the ranked gear the owner's ranking keeps and
  ``artifacts``; ``fits`` whether they stay within the cap;
* ``shed``: the stacks the first visit would move out to reach the cap, in the cap's order
  (destroy, sell, ranks 11-20 cheapest first), counted by fate and by kind, and ``short`` the
  stacks still over the cap when only kept stock is left, after the Magic-Eater's devices taken out
  to absorb (fate ``absorb``, owner 2026-11-19, counted in ``absorb``; the tidy sheds its own
  count over the cap regardless, home_cap.begin);
* ``restore_mana`` (a Magic-Eater): the Potions of Restore Mana held against the 99F/100F rocket
  target (restore_mana_target, owner 2026-11-20), and the absorbed rocket count it reads;
* ``disagree``: Home stacks whose fate and today's deciders differ (``fate-only``: the fate moves
  it, no decider would; ``decider-only``: a decider would, the fate keeps it), with up to
  ``EXAMPLES`` names each.
"""
from __future__ import annotations

from typing import Any

from hengbot import item_fate

# Owner 2026-11-19 「200件（空き40）」: the Home keeps at most this many stacks; the 40 above it
# (of powerup_home's 240, store.cpp store_get_stock_capacity) are always free for deposits.
HOME_KEEP_CAP = 200
HOME_DEPOSIT_ROOM = 40
EXAMPLES = 8
DECIDER_SAMPLE = 60

# The policy attribute: {"epoch": the town visit recorded, "note": (decision sequence, summary)}.
STATE = "_home_ledger"

# What the tidy moves out first (PROPOSAL 3-2, owner answers 2 and 4: no supplies' spares).
SHED_ORDER = (item_fate.DESTROY, item_fate.SELL, item_fate.ROOM_SALE)
KEPT_FATES = frozenset({item_fate.HOME, item_fate.IDENTIFY, item_fate.USE_NOW})

_KINDS = (
    ((19,), "launcher"), ((20,), "digger"), ((16, 17, 18), "ammo"), ((21, 22, 23), "weapon"),
    ((30, 31, 32, 33, 34, 35, 36, 37, 38), "armour"), ((40, 45), "jewelry"), ((39,), "light"),
    ((55, 65, 66), "device"), ((70,), "scroll"), ((75,), "potion"), ((80,), "food"),
)


def kind(item: Any) -> str:
    """A short kind name for the record (object/tval-types.h)."""
    for tvals, name in _KINDS:
        if item.tval in tvals:
            return name
    return "book" if 90 <= item.tval <= 120 else "other"


def rows(policy: Any, snapshot: Any) -> list:
    """(where, item, fate) for every worn, carried and Home stack."""
    ledger = [(item_fate.WORN, item, item_fate.CARRY) for item in snapshot.equipment]
    ledger += [(item_fate.PACK, item, item_fate.fate(policy, snapshot, item, item_fate.PACK))
               for item in snapshot.inventory]
    ledger += [(item_fate.SHELF, item, item_fate.fate(policy, snapshot, item, item_fate.SHELF))
               for item in policy._home_knowledge_items]
    return ledger


def _decider_moves(policy: Any, snapshot: Any, item: Any) -> bool:
    """Today's Home deciders would sell or destroy this Home stack."""
    return bool(policy._home_full_sale_candidate(snapshot, item) is not None
                or policy._home_full_discard_candidate(snapshot, item) is not None)


def _name(item: Any) -> str:
    return str(getattr(item, "name", "") or f"{item.tval}:{item.sval}")


def summary(policy: Any, snapshot: Any) -> dict:
    """The ledger's record of this board (module docstring)."""
    ledger = rows(policy, snapshot)
    shelf = [(item, fate) for where, item, fate in ledger if where == item_fate.SHELF]
    pack = [fate for where, _, fate in ledger if where == item_fate.PACK]
    fates = {name: sum(1 for _, fate in shelf if fate == name) for name in item_fate.FATES}
    kept = [item for item, fate in shelf if fate in KEPT_FATES]
    top10 = sum(1 for item in kept
                if item_fate.SLOT_BY_TVAL.get(item.tval) is not None and item.is_equipment
                and not item.is_ammo and not item.is_artifact and item.known)
    absorbed = sum(1 for _, fate in shelf if fate == item_fate.ABSORB)
    excess = max(0, len(shelf) - HOME_KEEP_CAP)
    order = sorted(
        ((SHED_ORDER.index(fate), item_fate.sale_value(policy, item), policy._item_signature(item),
          item, fate) for item, fate in shelf if fate in SHED_ORDER),
        key=lambda row: row[:3])
    shed = order[:excess]
    by_fate: dict = {}
    by_kind: dict = {}
    for _, _, _, item, fate in shed:
        by_fate[fate] = by_fate.get(fate, 0) + 1
        by_kind[kind(item)] = by_kind.get(kind(item), 0) + 1
    fate_only = [_name(item) for item, fate in shelf
                 if fate in SHED_ORDER and not _decider_moves(policy, snapshot, item)]
    # The deciders are slow: the kept stock is asked only up to ``DECIDER_SAMPLE`` stacks.
    decider_only = [_name(item) for item, fate in
                    [row for row in shelf if row[1] == item_fate.HOME][:DECIDER_SAMPLE]
                    if _decider_moves(policy, snapshot, item)]
    from hengbot import restore_mana_target
    mana = restore_mana_target.plan(policy, snapshot)
    return {
        **({"restore_mana": {key: mana[key] for key in ("held", "target", "rockets")}}
           if mana is not None else {}),
        "home": {"count": len(shelf), "cap": HOME_KEEP_CAP},
        "fates": fates,
        "pack": {name: pack.count(name) for name in item_fate.FATES if pack.count(name)},
        "kept": len(kept),
        "kept_kinds": {name: sum(1 for item in kept if kind(item) == name)
                       for name in sorted({kind(item) for item in kept})},
        "top10": top10,
        "artifacts": sum(1 for item in kept if item.is_artifact),
        "fits": len(kept) <= HOME_KEEP_CAP,
        "absorb": absorbed,
        "shed": {"count": len(shed), "fates": by_fate, "kinds": by_kind,
                 "short": max(0, excess - len(shed) - absorbed)},
        "disagree": {"fate-only": len(fate_only), "fate-only-examples": fate_only[:EXAMPLES],
                     "decider-only": len(decider_only), "decider-sample": DECIDER_SAMPLE,
                     "decider-only-examples": decider_only[:EXAMPLES]},
    }


def observe(policy: Any, snapshot: Any) -> None:
    """Record the ledger once per town visit, on the first board with a current Home census."""
    if not snapshot.in_town or not policy._home_knowledge_current:
        return
    epoch = getattr(policy, "_town_visit_epoch", None)
    state = getattr(policy, STATE, None)
    if epoch is None or (state is not None and state.get("epoch") == epoch):
        return
    note = (getattr(policy, "_decision_sequence", None), summary(policy, snapshot))
    setattr(policy, STATE, {"epoch": epoch, "note": note})


def report(policy: Any) -> dict | None:
    """The decision log's ``home_ledger`` field of this decision, else None."""
    state = getattr(policy, STATE, None)
    note = state.get("note") if state is not None else None
    if note is None or note[0] != getattr(policy, "_decision_sequence", None):
        return None
    return note[1]
