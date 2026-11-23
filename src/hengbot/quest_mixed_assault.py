"""The sides already mixed and summoning at each other: hasten there and kill one side by force
(``room_sweep.alignment_split.when_mixed``).

QUEST_33 (クローン地獄).  The plan keeps a GOOD and an EVIL summoner from facing each other
(quest_alignment_split: no walk enters a cell where both act; the 段2 lure disengages when a Queen and
a Gachapin come to the same place, quest_lure_approach).  n1-c life-221 (2026-11-23 13:00-13:58) found
them past that: the last Queen and the three Gachapins in the east rooms, a Gachapin with the Queens'
ants beside it (巨大シロアリ at [20,56] by the Gachapin at [20,57], 巨大黒アリ at [22,56] by the one at
[22,57]), about forty ants killed on the way.  Asked 「善と悪の召喚持ちがすでに同じ部屋に混ざって互いに
召喚し合っている時、どうしますか？」, the owner (2026-11-23, verbatim): 「加速して向かい、強引に邪悪側を
排除する。」  While they are not mixed the split and the lure's disengage stay as they were.

What the game does (C:/hengband/src):

* A monster casts at a hostile-aligned monster it can ``projectable`` to within the spell range
  (melee/melee-spell.cpp ``monst_spell_monst``, melee-spell-flags-checker.cpp
  ``check_melee_spell_projection``, MAX_RANGE 18), and a summon cast at a monster lands beside that
  monster (mspell-summon.cpp).  GOOD and EVIL are hostile to each other (monster-entity.cpp
  ``check_sub_alignments``); a summoned monster of a race with neither takes its summoner's side
  (monster-floor/one-monster-placer.cpp): the Queens' ants are GOOD, the Gachapins' hydras EVIL.  A
  summon lands within 2 of its target (monster-floor/monster-summon.cpp ``summon_specific``:
  ``mon_scatter(..., 2)``).  So the sides are mixed and summoning at each other (``mixed_now``) when a
  summoned monster of one side -- a race with no side of its own, read by the plan's
  ``good_summons_symbols`` / ``evil_summons_symbols`` (quest_alignment_split ``_monster_side``) -- stands
  within ``SUMMON_SCATTER`` of an awake summoner of the other side: that side's summoner has cast at it,
  and it casts back (a sleeping one does nothing, ``decide_process_continue``; n1-c life-221 at [7,72],
  4492304: a fire ant beside the sleeping Spawn of Tsathoggua).  A summoner in a line with a monster of
  the other side only (a random monster passing, the player's own walk bringing them in sight) is not
  yet mixed: the split and the lure answer that.
* Each kill of either side is a KILL_ALL target (dungeon/quest-completion-checker.cpp
  ``complete_kill_all`` completes on the death of the last hostile, ``count_all_hostile_monsters``):
  while both sides summon, the floor's count grows.  With one side dead nobody on the floor is hostile
  to the other (the player's own fight remains).
* *Destruction* is refused on a fixed quest floor (spell-kind/spells-floor.cpp ``destroy_area`` returns
  false; destruction_use keeps it so): no part of this answer.  Even elsewhere it deletes monsters
  without the death that ``complete_kill_all`` is called from (monster-death.cpp).

The answer, once mixed (latched on the navigator, ``mixed_assault``, until the side to kill is dead:
its tracked summoner races ``living`` 0 and none of it on the board):

1. not hasted: the haste (speed_dose, the plan's own rule ``always_hasted``: the absorbed Speed, else a
   potion);
2. a monster of that side beside the player: the blow (combat_answer);
3. one in view or firing at the player: the shot, summoners first, then the nearest (quest_plan_base
   ``_shot``: me_ranged_first's choice by the shared expected value, me_device_attacks ``use_value``,
   with the area attack first where it out-damages every one-target answer over the group);
4. else a walk toward the nearest of them known on the board or kept fresh by the detections
   (quest_detect_remaining ``kept_rows``), over the cells where both sides act (they are mixed:
   ``split=False``), round the warning's and the owners' refusals.

The survival rungs of the plan stay above it (quest_room_sweep ``key``: the summon answer, the 即死
escape, the cures, the withdrawal line, the heal, the haste); on a quiet board below the rest ratio
the rest comes first.  While mixed, the lure of 段2 and the walk out of a contact cell give way to it.
"""

from __future__ import annotations

from hengbot import combat_answer, quest_alignment_split, quest_exposure, quest_plan_base, speed_dose
from hengbot.model import Position

FIELD = "when_mixed"
ASSAULT_EVIL = "assault_evil"
ASSAULTS = {ASSAULT_EVIL: quest_alignment_split.EVIL}
WALK_REASON = "quest-strategy:mixed-assault-walk"
# A walk is tried toward this many of the nearest targets before the rung gives way.
WALK_TRIES = 3
SUMMON_SCATTER = 2  # monster-summon.cpp summon_specific: mon_scatter(..., 2)
_NEIGHBOURS = tuple((dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)


def valid(value) -> bool:
    """The schema (quest_alignment_split.valid reads it)."""
    return value in ASSAULTS


def _side(plan) -> str | None:
    split = quest_alignment_split.split_of(plan)
    return None if split is None else ASSAULTS.get(split.get(FIELD))


def _known(snapshot) -> list:
    return [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters) if monster.hostile]


def mixed_now(policy, snapshot, navigator, plan) -> bool:
    """A summoned monster of one side within ``SUMMON_SCATTER`` of an awake summoner of the other side
    on the board: the one side has summoned at it (module docstring)."""
    split = quest_alignment_split.split_of(plan)
    if split is None:
        return False
    summoners, summoned = [], []
    for monster in _known(snapshot):
        mark = quest_alignment_split._monster_side(policy, monster, split)
        if mark is None:
            continue
        knowledge = policy._monrace_knowledge.get(monster.race_id)
        cell = (monster.position.y, monster.position.x)
        if getattr(knowledge, "can_summon", False) and not monster.asleep:
            summoners.append((mark, cell))
        if quest_alignment_split.side(knowledge) is None:
            summoned.append((mark, cell))   # the side read from the plan's summons symbols
    return any(mark != other and quest_exposure.game_distance(cell, spot) <= SUMMON_SCATTER
               for mark, cell in summoners for other, spot in summoned)


def _side_living(policy, snapshot, navigator, plan, side) -> bool:
    split = quest_alignment_split.split_of(plan)
    tracked = any(quest_alignment_split.side(policy._monrace_knowledge.get(race)) == side
                  and quest_alignment_split.living(policy, snapshot, navigator, plan, race) > 0
                  for race in split["tracked_races"])
    return tracked or any(quest_alignment_split._monster_side(policy, monster, split) == side
                          for monster in _known(snapshot))


def observe(policy, snapshot, navigator, plan) -> None:
    """Every board: latch the assault when the sides are seen mixed; release it when its side is dead."""
    side = _side(plan)
    if side is None:
        return
    if not navigator.mixed_assault:
        if mixed_now(policy, snapshot, navigator, plan):
            navigator.mixed_assault = True
        return
    if not _side_living(policy, snapshot, navigator, plan, side):
        navigator.mixed_assault = False


def active(policy, snapshot, navigator, plan) -> bool:
    return _side(plan) is not None and bool(navigator.mixed_assault)


def _targets(policy, snapshot, navigator, plan, side) -> list[tuple[bool, tuple[int, int], object]]:
    """(summoner, cell, monster or None) of the side to kill: on the board, then the tracked ones the
    detections keep fresh (quest_detect_remaining ``kept_rows``)."""
    from hengbot import quest_detect_remaining

    split = quest_alignment_split.split_of(plan)
    rows = []
    for monster in _known(snapshot):
        if quest_alignment_split._monster_side(policy, monster, split) == side:
            knowledge = policy._monrace_knowledge.get(monster.race_id)
            rows.append((bool(getattr(knowledge, "can_summon", False)),
                         (monster.position.y, monster.position.x), monster))
    for race, cell, _turn in quest_detect_remaining.kept_rows(policy, snapshot, navigator, plan).values():
        knowledge = policy._monrace_knowledge.get(race)
        if quest_alignment_split.side(knowledge) == side:
            rows.append((bool(getattr(knowledge, "can_summon", False)), tuple(cell), None))
    return rows


def key(policy, snapshot, navigator, plan, board, *, quiet: bool = False) -> str | None:
    """The assault's step on this board (module docstring), else None."""
    side = _side(plan)
    if (side is None or not navigator.mixed_assault or snapshot.player.blind or snapshot.player.confused):
        return None
    if quiet and snapshot.player.hp_ratio < float(plan.get("rest_below_ratio", 0)):
        return None  # a quiet board: the plan's rest first
    split = quest_alignment_split.split_of(plan)
    targets = _targets(policy, snapshot, navigator, plan, side)
    if not targets:
        return None
    if not policy._player_hasted(snapshot):
        hasted = speed_dose.key(policy, snapshot, quest_plan_base.SPEED_REASON)
        if hasted is not None:
            return hasted
    here = snapshot.player.position

    def order(monster):
        knowledge = policy._monrace_knowledge.get(monster.race_id)
        return (not getattr(knowledge, "can_summon", False), here.distance_to(monster.position))

    reachable = sorted((monster for monster in (*board.in_view, *board.firing)
                        if quest_alignment_split._monster_side(policy, monster, split) == side), key=order)
    beside = [monster for monster in reachable if here.distance_to(monster.position) <= 1]
    if beside:
        answer = combat_answer.adjacent_attack(policy, snapshot, beside[:1], quest_plan_base.MELEE_REASON)
        if answer is not None and answer.key is not None:
            return answer.key
    for monster in reachable:
        if (shot := quest_plan_base._shot(policy, snapshot, monster)) is not None:
            return shot
    from hengbot import quest_room_sweep  # it asks this module for its rung

    cells = sorted({(not summons, quest_exposure.game_distance((here.y, here.x), cell), cell)
                    for summons, cell, _monster in targets})
    for _summons, _distance, cell in cells[:WALK_TRIES]:
        goals = {Position(cell[0] + dy, cell[1] + dx) for dy, dx in _NEIGHBOURS}
        path = quest_room_sweep._path(policy, navigator, plan, snapshot, goals, board.occupied, split=False)
        if (stepped := quest_plan_base._path_step(policy, snapshot, path, WALK_REASON)) is not None:
            return stepped
    return None
