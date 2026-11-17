"""A floor the dive goes no deeper from is left by Word of Recall once its exploration has run dry.

Owner 2026-11-17 (the 50F+ efficiency study's 第1位, verbatim 「適当な閾値を決めて、探索が済んだら
帰還する。閾値は任せる。」): on a floor below which the bot does not descend (``dead_end``: the
dungeon's last floor, the floor above a guardian the kit cannot pass, the fallback dive's target,
a floor whose next one asks an ability the character lacks -- Angband 80F before speed +25, the
Castle's 64F above its guardian), the explore went on until nothing was left and then took the
up stairs to draw a new floor (ladder_idle "Nothing to explore: take any known stairs").  Now
the floor counts as explored when the map has stopped growing (``WINDOW`` explore decisions in
a row added less than ``GROWTH_RATIO`` of the known cells, and no remembered floor item is left
the loot owner would fetch) or nothing is left to explore (the loot owner above found no way to
any item); then the return starts (``TRIGGER``) and Word of Recall is read (not the up stairs).

Owner 2026-11-11 C6 (1) rejected a fixed cut (「400判断で階を切り上げる」): this cut is the map's
growth, not a count of decisions on the floor.

The threshold, from n1-c life-216's snapshots at 50F+ (2026-11-16 17:50 to 11-17 15:30,
C:/hengband-backups/pdca/deep-efficiency-1117/impl_threshold.py): 50 visits of Angband 80F and
the Castle's 64F ended by the up stairs, 131,231 decisions (38% of the 342,889 at 50F+).  The
window counts the explore moves (a step with no awake hostile in view, 77% of those decisions):

=====================  ======  ===============  ====  =====  ======  ===========
window / growth        fired   decisions saved  map   exp    pickups  at (median)
=====================  ======  ===============  ====  =====  ======  ===========
100 moves / 0.5%       49/50   90,515 (26%)     29%   51%    57%     35% of visit
200 moves / 0.5%       45/50   55,373 (16%)     14%   26%    33%     56%
**300 moves / 0.5%**   34/50   39,349 (11.5%)   11%   18%    23%     66%
500 moves / 0.5%       17/50   18,428 (5.4%)     5%    8%    11%     75%
=====================  ======  ===============  ====  =====  ======  ===========

(saved: the decisions after the cut, share of all 50F+ decisions; map / exp / pickups: the share
of the visits' totals that came after it.)  At 300 the cut falls in the tail (two thirds into the
visit) and the time it gives up yields per decision 0.38 of the visits' map, 0.6 of their
experience and 0.77 of their pickups, while a new floor's first tenth yields the most (REPORT
2.1); 200 cuts in the middle of the visit (half its experience per decision lost), 500 rarely
fires.  A return costs about 250 decisions (two recall waits and a town visit): 34 x 250 = 8,500
of the 39,349 saved.  The loot condition delays the cut while an item is left to fetch.

The return is the floor's normal end, not an escape: ``return:recall`` is no relocation the
escape count reads (reasons ``return:*``), so the over-extension streak does not move
(over_extension, owner 2026-11-16 Q3 「数えない（今のまま）」 for the rule-made returns), and the
trigger is no survival one, so the recall wait collects what it reaches (recall_wait_reach).
"""

from __future__ import annotations

from hengbot import dive_floor, return_start
from hengbot.policy_constants import DEEP_FLOOR_DEPTH

TRIGGER = "explored-dead-end-floor"
# The read's reason: the planned town return's (reasons ``return:*``, no escape).
REASON = "return:recall"
# The explore decisions the growth is read over, and the growth (of the known cells) below which
# the map counts as no longer growing.  The table in the docstring.
WINDOW = 300
GROWTH_RATIO = 0.005
# {"floor": floor_key, "counts": the known-cell count at each of the last WINDOW + 1 explore decisions}
MEMORY = "_explored_floor_window"


def dead_end(policy, snapshot) -> bool:
    """The dive goes no deeper from this floor: the next one is no floor any stair down is taken
    to, whatever the stair (policy ``_is_descent_target``'s refusals of the destination).  50F
    and deeper only (DEEP_FLOOR_DEPTH): the study and its threshold are of those floors."""
    if (snapshot.in_town or snapshot.dungeon_level < DEEP_FLOOR_DEPTH
            # A floor the unsafe-recall fallback's Castle climbs from is none: its way on is the
            # up stairs (dive_floor.climbing, owner 2026-11-17), not Word of Recall.
            or dive_floor.climbing(policy, snapshot)):
        return False
    dungeon = snapshot.floor_key[0]
    below = snapshot.dungeon_level + 1
    info = policy._dungeon_knowledge.get(dungeon)
    return bool(
        (info is not None and 0 < info.max_depth < below)
        or policy._guardian_floor_blocked(snapshot, dungeon, below)
        or dive_floor.capped(policy, snapshot, below)
        or policy._missing_required_abilities(snapshot, below))


def note_explore(policy, snapshot) -> None:
    """An explore decision on this floor: the known map's size joins the window.  A shrink (the
    player's own *Destruction* forgets its circle) starts the window again."""
    known = len(policy._remembered_marked_t)
    memory = getattr(policy, MEMORY, None)
    counts = () if memory is None or memory.get("floor") != snapshot.floor_key else memory["counts"]
    if counts and known < counts[-1]:
        counts = ()
    setattr(policy, MEMORY, {"floor": snapshot.floor_key, "counts": (*counts, known)[-(WINDOW + 1):]})


def stalled(policy, snapshot) -> bool:
    """The last WINDOW explore decisions grew the known map by less than GROWTH_RATIO of it."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.get("floor") != snapshot.floor_key:
        return False
    counts = memory["counts"]
    return len(counts) > WINDOW and counts[-1] - counts[0] < GROWTH_RATIO * counts[-1]


def recall_key(policy, snapshot, *, exhausted: bool) -> str | None:
    """Start the return and read Word of Recall on an explored dead-end floor, else None.  The
    countdown that follows is the return's own wait (policy ``_return_to_town_key``).

    ``exhausted``: the explore found nothing left (the stairs would be taken next); otherwise the
    window must have stalled."""
    if not (exhausted or stalled(policy, snapshot)) or not dead_end(policy, snapshot):
        return None
    if not policy._stuck_escape_permitted(snapshot, policy._is_forgetting_maze(snapshot),
                                          policy._is_completed_forgetting_maze(snapshot)):
        return None
    if policy._floor_navigation_exit_locked(snapshot):
        return None
    # While the explore still walks, a remembered item it may yet open a way to holds the floor
    # (owner 2026-11-13 「その品の方へ探索を寄せる」, loot_frontier).  With nothing left to explore
    # the loot owner above has found no way to any of them this decision.
    if not exhausted and policy._loot_candidates(snapshot):
        return None
    recall = policy._find_recall_scroll(snapshot)
    if recall is None or not policy._can_read_scrolls(snapshot):
        return None
    # The scroll itself, as the stuck escape reads it: the return's own rung would take an up
    # stair underfoot first (return:ascend), the very end of the floor this replaces.
    return_start.start(policy, TRIGGER)
    policy.last_reason = REASON
    return policy._town_producer_entry(
        "_read_dungeon_recall_scroll_key",
        lambda: policy._read_dungeon_recall_scroll_key(snapshot, recall), family="departure")
