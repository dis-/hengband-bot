"""What a dive brought back: the kept items the over-extension judgement reads.

Owner 2026-11-15 (verbatim): 「持ち帰るべき有効な品を5つ以上拾う、に条件を引き上げる。壊す、
捨てる品をカウントしない。」  Asked why n1-c (life-214, Angband 49F, about fifty dives in two hours,
most of them 20-60 s) never fell back to a shallower depth: a dive with more than
``OVEREXTEND_LOOT_MAX`` pickups reset the over-extended streak (``over_extension.judge_dive``),
and every pickup decision counted -- a pile whose items the game's auto-destroy took on the spot
(自動破壊, src/autopick/autopick.cpp autopick_pickup_items), a piece it destroyed when identified
(destroy_identify, src/spell-kind/spells-perception.cpp), junk the bot destroyed right after
(``junk_destroy_now``), a device absorbed.  At 16:06 a dive of six pickups that kept four items
reset the streak at 2.

Counted now, at the dive's end (its town arrival board), from what is actually carried there:

- an acquisition is a dungeon board of the dive on which the units of an item kind (tval,
  sval) carried -- the pack and the worn slots together, so wielding a find or swapping gear
  moves nothing -- rose above the board before (a pickup, the game's auto-pickup, several
  items of one ``g`` each counted);
- a kind's acquisitions count up to the units of it kept: carried at arrival and not junk
  (``_junk_class``, the one predicate of what is never kept), less what the dive started
  with.  An item destroyed or dropped on the way is no longer carried, so it does not count,
  nor do consumables used up and ammunition shot and picked up again (the kind has no more
  units than the dive started with).

The number counted is ``_dive_kept_loot``; ``_dive_loot`` stays the dive's acquisitions so
far for the viewer.  A process that started in the dungeon begins the dive on its first board
(``policy_observation._observe``) as before; a policy without a recorded start (restored from
an older checkpoint) counts nothing kept.
"""

from __future__ import annotations

from collections import Counter

START = "_dive_start_units"
LAST = "_dive_pack_units"
ACQUIRED = "_dive_acquisitions"


def _kind(item) -> tuple:
    return (item.tval, item.sval)


def _units(snapshot) -> Counter:
    units: Counter = Counter()
    for item in (*snapshot.inventory, *snapshot.equipment):
        units[_kind(item)] += max(1, item.count)
    return units


def start(policy, snapshot) -> None:
    """The first dungeon board of a dive: what it starts with, nothing acquired yet."""
    units = _units(snapshot)
    setattr(policy, START, units)
    setattr(policy, LAST, units)
    setattr(policy, ACQUIRED, Counter())
    policy._dive_loot = 0


def board(policy, snapshot) -> None:
    """A dungeon board of the dive: the kinds whose carried units rose since the board before."""
    before = getattr(policy, LAST, None)
    units = _units(snapshot)
    setattr(policy, LAST, units)
    if before is None:
        return
    acquired = getattr(policy, ACQUIRED, None)
    if acquired is None:
        acquired = Counter()
        setattr(policy, ACQUIRED, acquired)
    for kind, count in units.items():
        if count > before.get(kind, 0):
            acquired[kind] += 1
            policy._dive_loot = getattr(policy, "_dive_loot", 0) + 1


def kept(policy, snapshot) -> int:
    """The dive's acquisitions still carried, not junk, on its town arrival board."""
    start_units = getattr(policy, START, None)
    acquired = getattr(policy, ACQUIRED, None)
    if start_units is None or not acquired:
        return 0
    carried: Counter = Counter()
    valid: Counter = Counter()
    for item in (*snapshot.inventory, *snapshot.equipment):
        kind = _kind(item)
        if kind not in acquired:
            continue
        carried[kind] += max(1, item.count)
        if policy._junk_class(snapshot, item) is None:
            valid[kind] += max(1, item.count)
    total = 0
    for kind, times in acquired.items():
        gained = min(carried[kind] - start_units.get(kind, 0), valid[kind])
        if gained > 0:
            total += min(times, gained)
    return total


def end(policy) -> None:
    """The dive is judged: forget its record."""
    for name in (START, LAST):
        setattr(policy, name, None)
    setattr(policy, ACQUIRED, Counter())
