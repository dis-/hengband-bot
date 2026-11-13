"""A fallback destination lands no shallower than the deepest floor reached minus 20.

Owner 2026-11-13 (verbatim): 「n1-cがまた23Fに落ちている。フォールバックは最新到達-20Fまでにする。」
n1-c life-205 (Lv46 Magic-Eater; recall landings Angband 80, dungeon 12 62, dungeon 20 60,
the Mountain 50, the Orc cave 23, ...): over-extended at the Mountain 50F, the valve took the
deepest entered landing below 50 that passed its checks -- the Orc cave 23F -- and the doubling
lease (alternate_lease) kept it there for 80 dives, while Angband 80, 62 and 60 were all safe
landings.

The deepest reached (「最新到達」) is the deepest saved recall landing of any dungeon
(``Snapshot.dungeon_recall_depths``: the game's per-dungeon ``max_level``, kept in the save and
never lowered by the bot -- the executor refuses the reset-recall-depth question) deeper than
that dungeon's entry floor (a rumor-opened dungeon sits at its entry floor unreached), and the
in-memory watermark ``_deepest_level`` when it is deeper (a board without the progress block).
``_deepest_level`` alone is not it: a restarted process seeds it from the recall target's depth
only (n1-c's arrival policy above held 23).

The floor is applied in one predicate, ``landing_allowed``, read by
``_fallback_landing_allowed`` (every candidate of ``_pick_alternate_dungeon``: the over-extension
valve, the no-depth-progress valve, the unsafe-recall and guardian valves of
``_activate_safe_recall_fallback``, the guardian rumor's pick and what it waits for, the
excluded-destination fallback of the observation and of the town recall destination) and by the
guardian valve's Angband first (``_guardian_valve_angband_acceptable``) and by the deepest
recall destination a lease ends on (``alternate_lease.deepest_destination``, C5: the deepest
destination still lowers the dive when every deeper one is refused).  ``settle`` ends a held
switch whose landing is under the floor (one made before this rule, or restored from the
alternate-dungeon record) the way a finished lease ends (``alternate_lease.end``).

When nothing at or below the floor passes, no switch is made: the existing next rules decide (the
original destination's own refusals, the unsafe-recall fallback's fundraising and its named stop).

Not read here (owner answers 2026-11-13: 「Q2 前は当てない」「征服には当てない」): the
random-quest hold's deepest open floor before Q2 (``depth_floor=False``; its own next rule is the
Yeek cave, shallower still) and the conquest target; nor the quest targets, the fundraising trips
to the Yeek cave and the Zul trips.
"""

from __future__ import annotations

FALLBACK_DEPTH_SPAN = 20


def deepest_reached(policy, snapshot) -> int:
    """The deepest floor this character has reached (「最新到達」).

    A saved landing at its dungeon's entry floor is not counted: an inn rumor opens a dungeon by
    setting its max level to the entry floor without the character going there
    (src/store/rumor.cpp ``set_max_level(dungeon.mindepth)``; the Chameleon cave 30 of n1-c
    life-205 and of the Lv8 life-313 board).  A landing deeper than the entry floor was reached
    (src/dungeon/dungeon-processor.cpp raises it only on arrival); one of a dungeon the knowledge
    does not hold cannot be told apart and is not counted either."""
    reached = [getattr(policy, "_deepest_level", 0)]
    for did, depth in snapshot.dungeon_recall_depths.items():
        info = policy._dungeon_knowledge.get(did)
        if info is not None and depth > info.min_depth:
            reached.append(depth)
    return max(reached)


def floor(policy, snapshot) -> int:
    """The shallowest landing a fallback may take."""
    return deepest_reached(policy, snapshot) - FALLBACK_DEPTH_SPAN


def landing_allowed(policy, snapshot, landing_depth: int) -> bool:
    return landing_depth >= floor(policy, snapshot)


def landing_depth(policy, snapshot, dungeon_id: int) -> int:
    """The recall landing of ``dungeon_id`` (the saved depth, else its entry floor)."""
    return policy._dungeon_entry_depth(snapshot, dungeon_id, via_recall=True)


def settle(policy, snapshot) -> bool:
    """On a town board: end a held switch that lands under the floor.  True when ended."""
    from hengbot import alternate_lease  # alternate_lease reads this module

    alternate = policy._alternate_dungeon
    if (not snapshot.in_town or alternate is None
            or landing_allowed(policy, snapshot, landing_depth(policy, snapshot, alternate))):
        return False
    alternate_lease.end(policy, snapshot)
    return True
