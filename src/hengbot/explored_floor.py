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

What the window counts (1118): the cells the visit's map has shown (the union of
``_remembered_known_t`` over its explore decisions), the known map the threshold below was chosen
on (impl_threshold.py sums the board's grid-map runs).  It counted the cells swept by the
player's own light (``_remembered_marked_t``) and started again whenever the map shrank: on the
Glass castle 60F (n1-c life-216, 2026-11-18 03:53-04:24, 10,232 explore decisions) the glass
walls show far rooms long before the light reaches them, so the swept cells went on growing
(04:14:26-04:23:50: +868 swept, +341 known) and the window fired only at 04:24:18; the 20 own
*Destruction*s of its first 17 minutes each shrank the map and started it again.  Counted on the
known map and never shrinking (a *Destruction* forgets cells the visit had known; showing them
again is no new ground), the same record stalls 300 explore decisions after the bot's restart
at 04:13 (27 cells, 0.44%).  Its 700-1,000 open frontiers are no part of the window: about 280
of them lie behind glass walls (GLASS_WALL: LOS without PROJECTION or MOVE, a wall the walk
cannot cross) and no walk reaches them; the reachable rest border floor shown but not yet swept.

Both ends need a full window first (``explored``): the explore's "nothing left" on one board is
no explored floor while the visit has walked less than a window (see ``explored``).

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
of the 39,349 saved.  The loot condition delays the cut while an item the walk reaches is left
to fetch; loot no walk reaches is entered by sealed_loot's ways first, if it can be (n1-c life-217).

The return is the floor's normal end, not an escape: ``return:recall`` is no relocation the
escape count reads (reasons ``return:*``), so the over-extension streak does not move
(over_extension, owner 2026-11-16 Q3 「数えない（今のまま）」 for the rule-made returns), and the
trigger is no survival one, so the recall wait collects what it reaches (recall_wait_reach).

Owner 2026-11-26 (「…いずれも、ゲーム内選択に関して私の以前の指示を破ることを許可する。」): an
explored dead-end floor of 50F and deeper is left by its stairs instead, for a new level of the
same depth by way of the floor above, ``deep_stairs.EXTRA_FLOORS`` times a trip (deep_stairs: 49%
of the no-descend floors' returns were this one, one level a recall round trip).
"""

from __future__ import annotations

from hengbot import deep_stairs, dive_floor, return_start, ring_hunt, sealed_loot
from hengbot.policy_constants import DEEP_FLOOR_DEPTH

TRIGGER = "explored-dead-end-floor"
# The read's reason: the planned town return's (reasons ``return:*``, no escape).
REASON = "return:recall"
# The explore decisions the growth is read over, and the growth (of the known cells) below which
# the map counts as no longer growing.  The table in the docstring.
WINDOW = 300
GROWTH_RATIO = 0.005
# {"floor": floor_key, "seen": every cell the visit's map has shown (the union of
#  ``_remembered_known_t`` over its explore decisions), "counts": the size of ``seen`` at each of
#  the last WINDOW + 1 explore decisions}
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
    """An explore decision on this floor: the cells the map knows join the visit's ``seen`` and its
    size joins the window.  The player's own *Destruction* forgets its circle from the map
    (destruction_use.forget_circle); the cells the explore then shows there again were known
    before and are no new ground, so the window neither shrinks nor starts again."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.get("floor") != snapshot.floor_key:
        memory = {"floor": snapshot.floor_key, "counts": ()}
    seen = memory.get("seen")
    if seen is None:
        seen = set()
    seen |= policy._remembered_known_t
    setattr(policy, MEMORY, {"floor": snapshot.floor_key, "seen": seen,
                             "counts": (*memory["counts"], len(seen))[-(WINDOW + 1):]})


def stalled(policy, snapshot) -> bool:
    """The last WINDOW explore decisions grew the known map by less than GROWTH_RATIO of it."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.get("floor") != snapshot.floor_key:
        return False
    counts = memory["counts"]
    return len(counts) > WINDOW and counts[-1] - counts[0] < GROWTH_RATIO * counts[-1]


def explored(policy, snapshot, *, exhausted: bool) -> bool:
    """The floor's exploration is done (owner 2026-11-17 「探索が済んだら」).

    Both ends ask for a full window first: WINDOW explore decisions on this floor visit.  Then the
    window must have stalled, or (``exhausted``) the explore found nothing to walk to.  The
    explore's "nothing" is no reachable frontier on this one board, which is no explored floor
    while the map is still growing: 2026-11-18, 3 of the 10 explored-dead-end-floor returns read
    it so -- n1-c life-216 14/50F (02:56:01) after 2 explore decisions, sealed in by its own
    *Destruction* and a Stone to Mud walk, 31 frontiers open; n1-b life-411 Angband 80F (03:47:07)
    after 143, its last 100 having grown the known map from 1,855 to 2,254 cells, 144 frontiers
    open and a summoner sensed; n1-c Angband 80F (03:09:32) after 101 (1,337 to 3,395), right
    after a Stone to Mud walk to sealed loot.  Such a floor is the ladder's below as before (the
    secret walls, the stairs, the stuck escape)."""
    # Supervisor 2026-11-28: a Ring of Speed hunt floor whose feeling rules the ring out is done
    # with at once (ring_hunt; the loot it would hold the floor for is the ring piles only).
    if ring_hunt.finished(policy, snapshot):
        return True
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.get("floor") != snapshot.floor_key or len(memory["counts"]) <= WINDOW:
        return False
    return exhausted or stalled(policy, snapshot)


def _reachable_loot(policy, snapshot) -> bool:
    """A loot candidate the walk reaches (sealed_loot's reach: the known floor joined to the
    player)."""
    candidates = policy._loot_candidates(snapshot)
    return bool(candidates) and bool(candidates & sealed_loot.reach(policy, snapshot))


def unreachable_loot_key(policy, snapshot) -> str | None:
    """On an explored dead-end floor (the window stalled) whose remembered loot no walk reaches,
    the owner's way into it (sealed_loot ``key``: the melt into a walled pocket, 11-13; the one
    mapping of an enclosure the map does not know, 11-18), else None.

    n1-c life-217 (Angband 95F, 2026-11-20 19:04-19:34): a helm sensed inside a block of grids the
    map did not know held the floor's Recall while the explore, steered to the frontiers nearest
    it (loot_frontier), crossed the cave for half an hour and grew the map by 2 cells in its last
    213 decisions; sealed_loot was asked only once the explore found nothing at all, which that
    floor's 253 open frontiers never gave, until the floor-dwell watcher stopped the bot."""
    if not explored(policy, snapshot, exhausted=False) or not dead_end(policy, snapshot):
        return None
    candidates = policy._loot_candidates(snapshot)
    if not candidates or candidates & sealed_loot.reach(policy, snapshot):
        return None
    return sealed_loot.key(policy, snapshot)


def recall_key(policy, snapshot, *, exhausted: bool) -> str | None:
    """Start the return and read Word of Recall on an explored dead-end floor, else None.  The
    countdown that follows is the return's own wait (policy ``_return_to_town_key``).

    ``exhausted``: the explore found nothing left (the stairs would be taken next); ``explored``
    reads it only after a full window of explore decisions on the floor."""
    if not explored(policy, snapshot, exhausted=exhausted) or not dead_end(policy, snapshot):
        return None
    if not policy._stuck_escape_permitted(snapshot, policy._is_forgetting_maze(snapshot),
                                          policy._is_completed_forgetting_maze(snapshot)):
        return None
    if policy._floor_navigation_exit_locked(snapshot):
        return None
    # While the explore still walks, a remembered item the walk reaches holds the floor (the loot
    # owner above takes it once its blocker lifts).  An item no walk reaches holds it no longer:
    # the stalled window is the explore opening no way to it (owner 2026-11-13 「その品の方へ探索
    # を寄せる」, loot_frontier), and the owner's ways into such loot (sealed_loot, 11-13 and 11-18)
    # have been asked just before (``unreachable_loot_key``).  With nothing left to explore the
    # loot owner above has found no way to any of them this decision.
    if not exhausted and _reachable_loot(policy, snapshot):
        return None
    # At 50F and deeper the floor is left by its stairs for a new level of the same depth,
    # EXTRA_FLOORS times a trip (deep_stairs, owner 2026-11-26: the one-floor recall trips).
    stairs = deep_stairs.key(policy, snapshot)
    if stairs is not None:
        return stairs
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
