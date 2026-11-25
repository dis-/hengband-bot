"""The cells a walk keeps off, by name: the five combinations the walkers use.

Maintainability review of the dungeon decisions 2026-11-15, N2 (stage 3, no behaviour change):
the walks combined the same five parts in five ways, written out at each walker, so which walk
keeps off what was readable only by comparing the expressions.  Each combination now has a name
here, and the walker that used the expression calls it.  The parts, the order they are read in
and the type of the answer are the walker's before (``a | b | c`` reads ``a``, then ``b``, then
``c``; a set on the left gives a set).  Which walk should keep off what is the owner's question
(Q2/Q3 of the review), not this module's: the differences are kept and named.

The parts:

    retreat      ``policy._engagement_avoid_cells``: the engagement retreats' own cells (a set)
    left         ``left_cells.refused``: the cells an owner left (the shared record)
    route        ``policy._engagement_route_veto``: the area an engagement would fire again in
    unseen-area  ``policy._unseen_attack_area_veto``: an unseen attacker's area, as the walks veto it
    unseen-cells ``policy._unseen_attack_area_cells``: the same area, the explore's reading
    warning      ``policy._warning_refused_cells``: the cells a TR_WARNING prompt refused
    town-entrance ``policy._town_entrance_cells``: the town's store, building and quest entrance
                 cells but the player's own (``off_entrances``); empty outside town

The combinations (``COMBINATIONS``; tests/test_cross_rules.py pins each function to its row):

    walk               retreat (frozen) | left | route | unseen-area   policy._walk_veto (also the
                                                                       quest target search, the
                                                                       kill-all patrol's hunt, the
                                                                       oscillation break and the
                                                                       unknown probe: owner
                                                                       2026-11-15 Q3)
    retreat-left       retreat | left                                  the nearest-target BFS,
                                                                       the least visited neighbour
    route-left         route | left | town-entrance                    the loot walk's veto
    retreat-left-route retreat | left | route                          the descent route
    explore            retreat | left | warning | unseen-cells | route the explore's goals

The quest plans' own walks (quest25_battle, quest_room_sweep) read ``left_cells.refused_yx``
beside their own refused cells on their (y, x) maps; they are not combinations of these parts.
"""

from __future__ import annotations

from hengbot import left_cells

WALK = "walk"
RETREAT_LEFT = "retreat-left"
ROUTE_LEFT = "route-left"
RETREAT_LEFT_ROUTE = "retreat-left-route"
EXPLORE = "explore"

COMBINATIONS = {
    WALK: ("retreat", "left", "route", "unseen-area"),
    RETREAT_LEFT: ("retreat", "left"),
    ROUTE_LEFT: ("route", "left", "town-entrance"),
    RETREAT_LEFT_ROUTE: ("retreat", "left", "route"),
    EXPLORE: ("retreat", "left", "warning", "unseen-cells", "route"),
}


def walk(policy, snapshot):
    """Every walker's one veto (``policy._walk_veto``)."""
    return (frozenset(policy._engagement_avoid_cells) | left_cells.refused(policy, snapshot)
            | policy._engagement_route_veto(snapshot) | policy._unseen_attack_area_veto(snapshot))


def retreat_left(policy, snapshot):
    """The retreats' cells and the left cells (a set)."""
    return policy._engagement_avoid_cells | left_cells.refused(policy, snapshot)


def route_left(policy, snapshot):
    """The routes' engagement veto, the left cells and the town's entrances (``off_entrances``)."""
    return (policy._engagement_route_veto(snapshot) | left_cells.refused(policy, snapshot)
            | off_entrances(policy._town_entrance_cells(snapshot), snapshot))


def off_entrances(cells, snapshot):
    """The town's entrance cells (``policy._town_entrance_cells``: empty outside town) a walk
    that does not go in keeps off, the player's own cell excepted (a walk starts there).

    Stepping onto a store's cell enters it (player-move.cpp ``move_player_effect``: a STORE
    terrain sets ``command_new = SPECIAL_KEY_STORE``), so a walk to anything but that store
    crosses its page.  The goal walks keep off them already (``goal_route``'s first passes,
    ``_town_map_goal_route``); the loot walk did not: n1-b life-418 (2026-11-25 11:17-11:18,
    Lv42 Magic-Eater) walked seek-loot '1' from (33,91) onto the store 5 entrance (34,90) on a
    shortest route to an item at (44,98), left the page (shop:observe-and-leave) and stepped
    off it under town:kill-mob-approach '9', 18 rounds to town:blocked:stage-deadline:buy."""
    return frozenset(cells) - {snapshot.player.position}


def retreat_left_route(policy, snapshot):
    """The retreats' cells, the left cells and the routes' engagement veto (a set)."""
    return (policy._engagement_avoid_cells | left_cells.refused(policy, snapshot)
            | policy._engagement_route_veto(snapshot))


def explore(policy, snapshot):
    """The explore's avoided cells (a set): with the warning's refusals and the unseen
    attacker's area as the explore reads it."""
    return (policy._engagement_avoid_cells
            | left_cells.refused(policy, snapshot)
            | policy._warning_refused_cells
            | policy._unseen_attack_area_cells(snapshot)
            | policy._engagement_route_veto(snapshot))
