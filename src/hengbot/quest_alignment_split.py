"""A KILL_ALL floor whose GOOD and EVIL summoners must never face each other: ``room_sweep.alignment_split``.

QUEST_33 (クローン地獄), owner 2026-11-19: 「Q33の戦略を作って。goodとevilの召喚持ちが相対すると
お互いに召喚して収拾がつかなくなることに留意して立案すること。急いで受ける必要のあるクエストでは
ないので戦力は過剰に要求して良い。」

The game's side (C:/hengband/src):

* Who fights whom: ``MonsterEntity::is_hostile_to_melee`` (system/monster-entity.cpp) makes two
  monsters hostile when one's ``sub_align`` is GOOD and the other's EVIL
  (``check_sub_alignments``); two monsters both hostile to the player are otherwise at peace.
  ``sub_align`` is the race's GOOD/EVIL flags, except that a summoned monster of a race with
  neither takes its summoner's (monster-floor/one-monster-placer.cpp): the ants a GOOD 『クイーン・
  アント』 summons are GOOD, the hydras and undead an EVIL one summons are EVIL.  A summoner
  never brings a race hostile to itself (monster/monster-util.cpp: ``summoner_m_idx`` and
  ``monster_has_hostile_to_other_monster``).
* When it casts at a monster: ``cast_spell`` (monster/monster-processor.cpp) tries the player
  first when aware, then ``monst_spell_monst`` (melee/melee-spell.cpp), whose target is any
  hostile-aligned monster the caster can ``projectable`` to (melee-spell-flags-checker.cpp
  ``check_melee_spell_projection``), summons included (``check_pet`` strips them from pets
  only).  A summon cast at a monster lands beside that monster (mspell-summon.cpp, ``y``/``x``
  are the target's), each a group: so a GOOD and an EVIL summoner in each other's line feed each
  other's fight with new monsters, every one of them a KILL_ALL target too
  (dungeon/quest-completion-checker.cpp ``count_all_hostile_monsters`` counts every hostile on
  the floor, summoned or placed).
* When it acts at all: ``decide_process_continue`` (monster-processor.cpp) processes a monster
  only while the player is within its ``vision`` (``aaf``), or in the player's line within
  MAX_PLAYER_SIGHT, or while it holds a target.  A monster out of all three does nothing, casts
  nothing at anyone.

So the floor is walked where at most one side acts: a cell is refused while a living GOOD
summoner and a living EVIL summoner would both be within their own vision of the player
standing on it (``refused_cells``).  The plan's own order brings the EVIL summoners to the player
from where every GOOD one sleeps out of reach, then the GOOD ones; with one side dead the refusal
ends.  Where a summoner is: on the board when it is seen or sensed, else on its placement until
its kill line is read (``tracked_races``, counted from the game's kill lines as Q2 counts them,
q2_kill_credit).  A race of the board that summons (MonraceKnowledge.can_summon) and has a side
counts as well (the floor's random monsters).

The abort, owner 2026-11-17 「固定クエストの失敗処理はそんなに手厚くしなくていい」: one rung, only for a
plan that names ``facing_casts_to_abort``.  QUEST_33 no longer does (owner 2026-11-19 「召喚を何度
受けても放棄しない」, quest_summon_answer): the count is still kept (summon_response) for the record.  A summon
whose named caster has no line of fire to the player while a monster of the other side is in its
line (``facing``; summon_response counts it, the one reader of summon messages) is a cast at a
monster: once ``facing_casts_to_abort`` of them are read on the floor, Word of Recall is read and
the quest fails.  The count is summon_response's rule 3 number (owner 2026-11-04 「3回」), and the
reading of an out-of-line cast as monster against monster is the owner's of 2026-11-16 (rule 3's
「術者から射線が通る時だけ数える」 was decided on two casters fighting each other).  A summoned
monster of a side-less race carries its summoner's side in the game but not on the board: the races
of ``good_summons_symbols`` (S_ANT's 'a') count as GOOD for ``facing``.
"""

from __future__ import annotations

from collections import Counter

from hengbot import quest_exposure
from hengbot.item_reservation import decision_memo
from hengbot.model import Position
from hengbot.q2_kill_credit import _killed as kill_line

GOOD = "good"
EVIL = "evil"
# The battlefield's kinds a line passes over (TerrainDefinitions.jsonc LOS and PROJECTION): the
# pits and lavas do, a tree does not (TREE has neither flag), a closed door does not.
_SIGHT_KINDS = frozenset({"floor", "exit", "shallow_water", "deep_water", "passage", "pit", "lava"})
# The kinds a walk of the plan may stand on (quest_plan_base._terrain_of).
_STAND_KINDS = frozenset({"floor", "exit", "door", "passage", "shallow_water", "tree"})


def split_of(plan) -> dict | None:
    value = plan.get("alignment_split") if isinstance(plan, dict) else None
    return value if isinstance(value, dict) else None


def valid(value) -> bool:
    """The schema (quest_strategies reads it at load)."""
    def integer(item) -> bool:
        return isinstance(item, int) and not isinstance(item, bool)

    return (isinstance(value, dict)
            and isinstance(value.get("tracked_races"), list)
            and all(integer(item) and item > 0 for item in value["tracked_races"])
            and ("facing_casts_to_abort" not in value
                 or (integer(value["facing_casts_to_abort"]) and value["facing_casts_to_abort"] > 0))
            and isinstance(value.get("good_summons_symbols", []), list)
            and all(isinstance(item, str) and len(item) == 1
                    for item in value.get("good_summons_symbols", [])))


def valid_stops(plan) -> bool:
    """Each stop's ``after_races_dead``, where given, is a list of tracked races."""
    split = split_of(plan) or {}
    tracked = set(split.get("tracked_races", ()))
    stops = [*plan.get("stands", ()), *plan.get("last_targets", ())] if isinstance(plan, dict) else []
    return all(
        isinstance(stop.get("after_races_dead", []), list)
        and set(stop.get("after_races_dead", [])) <= tracked
        for stop in stops if isinstance(stop, dict))


def side(knowledge) -> str | None:
    """GOOD or EVIL by the race's flags; neither or both: None."""
    flags = getattr(knowledge, "flags", frozenset())
    good, evil = "GOOD" in flags, "EVIL" in flags
    if good == evil:
        return None
    return GOOD if good else EVIL


def _cell(position: Position) -> tuple[int, int]:
    return position.y, position.x


def _known(snapshot) -> list:
    return [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
            if monster.hostile]


# -- the kill lines ------------------------------------------------------------------


def observe(policy, snapshot, navigator, plan) -> None:
    """Every board of the floor: the tracked races' kill lines (each board once)."""
    from hengbot import quest_sweep_record

    split = split_of(plan)
    if split is None:
        return
    # The kills a previous process read on this floor (a bot restart, quest_sweep_record).
    quest_sweep_record.take(policy, snapshot, navigator)
    board = (snapshot.turn, tuple(snapshot.messages))
    if navigator.split_board == board:
        return
    navigator.split_board = board
    names = {
        name: race
        for race in split["tracked_races"]
        for name in getattr(policy._monrace_knowledge.get(race), "names", ())
        if name
    }
    kills = Counter(navigator.split_kills)
    turns = list(navigator.split_kill_turns)
    for message in snapshot.messages:
        killed = kill_line(message)
        if killed is not None and killed[0] in names:
            kills[names[killed[0]]] += killed[1]
            turns.extend([(names[killed[0]], int(snapshot.turn))] * killed[1])
    navigator.split_kills = dict(kills)
    navigator.split_kill_turns = tuple(turns)


# -- where each side's summoners are ----------------------------------------------------


def summoners(policy, snapshot, navigator, plan) -> list[tuple[str, tuple[int, int], int]]:
    """(side, cell, vision) of every living summoner the plan weighs: those on the board,
    then each tracked race's placements its kill lines and the board do not account for."""
    split = split_of(plan)
    if split is None:
        return []
    rows: list[tuple[str, tuple[int, int], int]] = []
    seen: Counter[int] = Counter()
    for monster in _known(snapshot):
        knowledge = policy._monrace_knowledge.get(monster.race_id)
        mark = side(knowledge)
        if mark is None or not knowledge.can_summon:
            continue
        rows.append((mark, _cell(monster.position), int(knowledge.vision)))
        seen[monster.race_id] += 1
    for race in split["tracked_races"]:
        knowledge = policy._monrace_knowledge.get(race)
        mark = side(knowledge)
        if mark is None:
            continue
        cells = [cell for cell, placed in navigator.battlefield.monster_placements if placed == race]
        left = len(cells) - int(navigator.split_kills.get(race, 0)) - seen[race]
        rows.extend((mark, cell, int(knowledge.vision)) for cell in cells[:max(0, left)])
    return rows


def contact_cells(policy, snapshot, navigator, plan) -> frozenset:
    """The cells from which a living GOOD summoner and a living EVIL one would both act."""
    split = split_of(plan)
    if split is None:
        return frozenset()

    def compute() -> frozenset:
        rows = summoners(policy, snapshot, navigator, plan)
        goods = [(cell, vision) for mark, cell, vision in rows if mark == GOOD]
        evils = [(cell, vision) for mark, cell, vision in rows if mark == EVIL]
        if not goods or not evils:
            return frozenset()

        def acts(spot, sides) -> bool:
            return any(quest_exposure.game_distance(spot, cell) <= vision for cell, vision in sides)

        return frozenset(
            spot for spot, kind in navigator.battlefield.terrain.items()
            if kind in _STAND_KINDS and acts(spot, goods) and acts(spot, evils))

    return decision_memo(policy, "quest_alignment_split.contact_cells", snapshot,
                         (navigator.quest_id, tuple(sorted(navigator.split_kills.items()))), compute)


def living(policy, snapshot, navigator, plan, race: int) -> int:
    """A tracked race's members still alive: its placements less its kill lines, or more when
    the board shows more."""
    placed = sum(1 for _, placed in navigator.battlefield.monster_placements if placed == race)
    on_board = sum(1 for monster in _known(snapshot) if monster.race_id == race)
    return max(placed - int(navigator.split_kills.get(race, 0)), on_board)


def stop_waits(policy, snapshot, navigator, plan, stop) -> bool:
    """A stop of a later phase (``after_races_dead``) while one of those races lives."""
    if split_of(plan) is None:
        return False
    return any(living(policy, snapshot, navigator, plan, race) > 0
               for race in stop.get("after_races_dead", ()))


def refused_cells(policy, snapshot, navigator, plan) -> frozenset:
    """The contact cells a walk may not enter: every one but the player's own (a walk starts
    there; ``leave_goals`` takes him out)."""
    return contact_cells(policy, snapshot, navigator, plan) - {_cell(snapshot.player.position)}


def leave_goals(policy, snapshot, navigator, plan) -> set[Position]:
    """Standing in contact (a teleport's landing, a monster's TELE_TO): the cells out of it,
    else nothing."""
    contact = contact_cells(policy, snapshot, navigator, plan)
    if _cell(snapshot.player.position) not in contact:
        return set()
    return {Position(*spot) for spot, kind in navigator.battlefield.terrain.items()
            if kind in {"floor", "passage"} and spot not in contact}


# -- the casts at a monster -------------------------------------------------------------


def _monster_side(policy, monster, split) -> str | None:
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    mark = side(knowledge)
    if mark is None and getattr(knowledge, "symbol", "") in split.get("good_summons_symbols", ()):
        return GOOD
    return mark


# TerrainDefinitions.jsonc ids: what a burnt tree leaves (effect-feature.cpp affect_feature: TREE ->
# BRAKE one time in three, else GRASS; both LOS, PROJECTION and MOVE) and the floor Stone to Mud leaves.
_OPENED_TERRAIN_IDS = frozenset({1, 89, 94})


def board_terrain(navigator, snapshot) -> dict:
    """The quest map as it is now: a tree burnt or a wall melted (the board shows the grid as
    floor, grass or brake, or the plan opened it: ``navigator.opened_cells``) is floor."""
    terrain = dict(navigator.battlefield.terrain)
    opened = set(getattr(navigator, "opened_cells", ()))
    for spot, kind in navigator.battlefield.terrain.items():
        if kind not in {"tree", "wall"}:
            continue
        grid = snapshot.grid_at(Position(*spot))
        if spot in opened or (grid is not None and grid.known and grid.terrain_id in _OPENED_TERRAIN_IDS):
            terrain[spot] = "floor"
    return terrain


def _sight(navigator, snapshot) -> dict:
    """The map as the game's lines cross it, through the doors the board shows open and the trees
    and walls the board shows gone (``board_terrain``)."""
    terrain = {}
    for spot, kind in board_terrain(navigator, snapshot).items():
        if kind == "door":
            grid = snapshot.grid_at(Position(*spot))
            kind = "floor" if grid is not None and grid.known and not grid.is_closed_door else "wall"
        terrain[spot] = "floor" if kind in _SIGHT_KINDS else "wall"
    return terrain


def facing(policy, snapshot, caster_name: str, plain_name) -> bool:
    """The caster named in a summon line stands in the line of a monster of the other side
    (this floor's plan only).  ``plain_name`` is summon_response's reading of a name."""
    quest_id = policy._active_fixed_quest_id(snapshot)
    profile = None if quest_id is None else policy.approved_quest_strategy(quest_id)
    plan = None if profile is None else profile.engagement_plan.get("room_sweep")
    split = split_of(plan)
    navigator = None if profile is None else policy._quest_navigators.get(quest_id)
    if split is None or navigator is None:
        return False
    known = _known(snapshot)
    name = plain_name(caster_name)
    sight = None
    for caster in known:
        if plain_name(caster.name) != name:
            continue
        mark = _monster_side(policy, caster, split)
        if mark is None:
            continue
        for other in known:
            other_mark = _monster_side(policy, other, split)
            if other is caster or other_mark is None or other_mark == mark:
                continue
            sight = sight if sight is not None else _sight(navigator, snapshot)
            if quest_exposure.projectable(sight, _cell(caster.position), _cell(other.position)):
                return True
    return False


def abort_due(policy, plan) -> bool:
    from hengbot import summon_response

    split = split_of(plan)
    return (split is not None and "facing_casts_to_abort" in split
            and summon_response.facing_casts(policy) >= int(split["facing_casts_to_abort"]))


def abort_key(policy, snapshot, plan) -> str | None:
    """The fight has begun between the sides: Word of Recall (the quest fails)."""
    from hengbot import once_quest_recall, quest_plan_base

    if not abort_due(policy, plan):
        return None
    return once_quest_recall.read_key(policy, snapshot, quest_plan_base.RECALL_REASON, deliberate=True)
