"""Drop hunting: the monsters whose drops can close the unmet speed row are killed, not erased.

Supervisor 2026-11-28, under the owner's 2026-11-26 permission to change in-game choices from
measured numbers; the owner's suggestion of the day (verbatim): 「対案として、ドロップ数の多いモンス
ターを倒す、great dropのモンスターを倒す、レベルの高いモンスターを倒す、などがある。採用は強制しない。
検討して。」  The investigator's replication of the game's selection (2026-11-28,
C:/hengband-backups/pdca/captures/drop-hunt-1128):

* under the good filter the only rings are Speed and Lordly Protection
  (object/object-kind-hook.cpp:176-177); a drop's object level is (dungeon level + race level) / 2
  (monster-floor/monster-death.cpp:389), its kind is chosen at that level + 10 for AM_GOOD and
  + 15 for AM_GREAT (floor/floor-object.cpp:59-73 ``get_base_floor``; DROP_GREAT sets both,
  monster-death.cpp:214-224), and the Ring of Speed's allocation depth is 80
  (lib/edit/BaseitemDefinitions.jsonc id 136, angband_cap ``RING_OF_SPEED_DEPTH``): below a kind
  level of 80 no drop is one.  One good or great item at 80 is a usable Ring of Speed (pval 8+,
  uncursed) 1 in 213 (an ordinary one 1 in 870), so a good dropper pays only from the level line
  on (``level_line``): many drops alone, or a high level alone, do not;
* per kill at 80F the expected usable rings are 0.075 (Great Wyrm of Many Colours) to 0.026;
* n1-b life-419 (Magic-Eater CL50, 3.5 hours at 78-80F under the speed ceiling): 211 sightings of
  L60+ good droppers, 35 read T2/T3 by the bot, 28 of those on boards its *Destruction* flashed,
  1 killed (0.15-0.35 usable rings an hour left, 3-7x the floor's rate).  The rule that erased
  them was the 2026-11-09 summoner and shrieker leave (threat_tiers ``_worsens_leave``, through
  ``leave_due``): me_powers' THREAT occasion read it as unbeatable and asked the
  *Destruction* before the Teleport Away (destruction_use ``before_teleport_away``), the flee
  rung's cornered *Destruction* (ladder_combat) took it, or the emergency ladder's exposed
  summoner escape (policy_combat ``summoner_open``); the rest were lethal boards.

A hunt target (``target``), every test from the board and the bot's own models:

1. the speed row is unmet (depth_gap_gear ``speed_row``, the one answer to it);
2. the race drops good or great (DROP_GOOD / DROP_GREAT), does not multiply, is not RES_ALL
   (owner 2026-11-18: in effect unkillable), the monster is a hostile, not a pet;
3. the race level is at least ``level_line`` for the floor and the drop quality;
4. its own tier, alone and from contact (as threat_tiers ``on_the_way`` reads a 強敵), is T2 or T3,
   and the board is not 即死 (threat_tiers ``instant_death``);
5. the actions to kill it (T3: the free attacks' ``free_turns``; T2: the winning supply plan's
   turns) are at most ``KILL_ACTIONS_MAX``, and the p95 damage projected over them stays below the
   HP less the plan's reserve (threat_projection ``plan_reserve``, the reading's own ``reserve``).

A unique is judged the same: one that passes is a target, one that does not keeps the
2026-11-23 rule (threat_tiers ``lone_good_drop_t2``).

What a target changes (the callers ask here): the 2026-11-09 leave keeps it (threat_tiers
``kill_before_leave``), the emergency ladder's exposed-summoner escape does not fire for it
(policy_combat), and a use of *Destruction* that waits for no blow (destruction_use
``loot_then_use`` with ``loot``) is held while one is in view inside its worst radius
(``holds_use``), for at most ``HOLD_DECISIONS_MAX`` decisions a floor visit.  The fight is the
existing combat ladder's.  The 即死 board and the emergency ladder's lethal readings fire as
before, and the 11-08 leave's use (``loot`` False: an awake T1 sensing the player) is not held.

Abort: a target that fails a test on a later board while it is shown (summons arrived and the
actions grew past the limit, the HP fell, the board turned 即死) is dropped for the floor visit
(``MEMORY`` "dropped"): the rules before this module answer it from then on.
"""

from __future__ import annotations

from hengbot import depth_gap_gear
from hengbot.item_reservation import decision_memo

# lib/edit/BaseitemDefinitions.jsonc id 136 (ring 「スピード」) allocation depth 80
# (angband_cap.RING_OF_SPEED_DEPTH, read here at call time).
# floor/floor-object.cpp:59-73 get_base_floor: AM_GREAT -> object_level + 15 (a monster drop
# passes no rq_mon_level), AM_GOOD -> object_level + 10.
GOOD_KIND_BOOST = 10
GREAT_KIND_BOOST = 15
# The actions to kill a target (supervisor 2026-11-28: the investigator measured a median 434
# damage per action of this bot against the large monsters, n1-b life-419 decision log).
KILL_ACTIONS_MAX = 10
# The decisions a floor visit's hunt may hold a use of *Destruction* that waits for no blow:
# the scene bound of destruction_loot (``DECISIONS_MAX`` 40), so no hold lasts for good.
HOLD_DECISIONS_MAX = 40
# {"floor": floor_key, "hunted": set of (index, race_id) read a target, "dropped": set of
#  (index, race_id) dropped after failing a test while shown, "holds": int}
MEMORY = "_drop_hunt_memory"


def _memory(policy, snapshot) -> dict:
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory.get("floor") != snapshot.floor_key:
        memory = {"floor": snapshot.floor_key, "hunted": set(), "dropped": set(), "holds": 0}
        setattr(policy, MEMORY, memory)
    return memory


def level_line(depth: int, great: bool) -> int:
    """The lowest race level whose good (``great``: great) drop on ``depth`` is chosen at the Ring
    of Speed's allocation depth or deeper: (depth + level) // 2 + boost >= RING_OF_SPEED_DEPTH,
    i.e. level >= 2 * (RING_OF_SPEED_DEPTH - boost) - depth (140 - depth good, 130 - depth great)."""
    from hengbot.angband_cap import RING_OF_SPEED_DEPTH  # import cycle
    boost = GREAT_KIND_BOOST if great else GOOD_KIND_BOOST
    return 2 * (RING_OF_SPEED_DEPTH - boost) - depth


def active(policy, snapshot) -> bool:
    """The speed row is unmet and the tiers decide here (threat_tiers ``leave_decided_here``)."""
    from hengbot import threat_tiers  # import cycle
    return (snapshot.dungeon_level > 0 and depth_gap_gear.speed_row(policy, snapshot) is not None
            and threat_tiers.leave_decided_here(policy, snapshot))


def race_qualifies(policy, snapshot, monster) -> bool:
    """Tests 2 and 3: the race data (lib/edit/MonraceDefinitions.jsonc) and the level line."""
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    if knowledge is None or monster.pet or not monster.hostile or monster.can_multiply:
        return False
    flags = knowledge.flags
    if "MULTIPLY" in flags or "RES_ALL" in flags:
        return False
    if "DROP_GREAT" in flags:
        great = True
    elif "DROP_GOOD" in flags:
        great = False
    else:
        return False
    return knowledge.level >= level_line(snapshot.dungeon_level, great)


def kill_reading(policy, snapshot, monster):
    """(actions to kill ``monster`` alone, the p95 damage over them, the reserve), from its own
    reading from contact (T3: the free attacks; T2: the winning supply plan), else None (T1, past
    the cost cap, no free attack)."""
    from hengbot import threat_tiers  # import cycle
    reading = threat_tiers.tiered(policy, snapshot, [monster], contact=True)
    if reading.tier == threat_tiers.T3 and reading.free_turns is not None:
        incoming = (reading.free_incoming if reading.free_incoming is not None
                    else (reading.free_incoming_bounds or (None, None))[1])
        if incoming is None:
            return None
        return reading.free_turns, incoming, reading.reserve
    if reading.tier == threat_tiers.T2 and reading.supply_plan is not None:
        return reading.supply_plan.turns, reading.supply_plan.incoming, reading.reserve
    return None


def passes(policy, snapshot, monster) -> bool:
    """Tests 4 and 5 on this board (the module docstring)."""
    from hengbot import threat_tiers  # import cycle
    if threat_tiers.instant_death(policy, snapshot).holds:
        return False
    read = kill_reading(policy, snapshot, monster)
    if read is None:
        return False
    actions, incoming, reserve = read
    return actions <= KILL_ACTIONS_MAX and incoming < snapshot.player.hp - reserve


def target(policy, snapshot, monster) -> bool:
    """``monster`` is a hunt target on this board (the module docstring); one read a target
    that fails a test while shown is dropped for the floor visit."""
    if not active(policy, snapshot) or not race_qualifies(policy, snapshot, monster):
        return False
    key = (monster.index, monster.race_id)

    def compute():
        memory = _memory(policy, snapshot)
        if key in memory["dropped"]:
            return False
        if passes(policy, snapshot, monster):
            memory["hunted"].add(key)
            return True
        if key in memory["hunted"]:
            memory["dropped"].add(key)
        return False

    return decision_memo(policy, "drop-hunt-target", snapshot, key, compute)


def targets(policy, snapshot, monsters) -> frozenset:
    """The indices of ``monsters`` that are hunt targets."""
    return frozenset(monster.index for monster in monsters if target(policy, snapshot, monster))


def covers(policy, snapshot, monsters) -> bool:
    """Every one of ``monsters`` (at least one) is a hunt target: an escape from them is not due
    (the emergency ladder's exposed summoners)."""
    monsters = list(monsters)
    return bool(monsters) and all(target(policy, snapshot, monster) for monster in monsters)


def holds_use(policy, snapshot, leaving, *, loot: bool) -> bool:
    """A use of *Destruction* that waits for no blow (``loot``) leaving ``leaving`` is held on this
    board: a hunt target in view lies within its worst radius (destruction_use ``worst_radius``),
    the board is not 即死 (destruction_loot ``urgent``), within ``HOLD_DECISIONS_MAX`` (one count a
    decision)."""
    if not loot or not active(policy, snapshot):
        return False
    from hengbot import destruction_loot, destruction_use  # import cycle
    radius = destruction_use.worst_radius(policy, snapshot, leaving)
    shown = [monster for monster in snapshot.visible_monsters
             if destruction_use.in_worst_radius(snapshot, monster, radius=radius)]
    if not any(target(policy, snapshot, monster) for monster in shown):
        return False
    if destruction_loot.urgent(policy, snapshot):
        return False

    def counted():
        memory = _memory(policy, snapshot)
        if memory["holds"] >= HOLD_DECISIONS_MAX:
            return False
        memory["holds"] += 1
        return True

    return decision_memo(policy, "drop-hunt-hold", snapshot, None, counted)
