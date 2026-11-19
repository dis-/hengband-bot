"""A room-sweep plan looks for the remaining enemies with its detection before it waits or closes in.

Owner 2026-11-20 (verbatim): 「残りの敵を探す時は感知を使うこと」, and earlier for every KILL_ALL quest
(2026-11-13, kill_all_patrol): 「全滅クエストで作戦を終えても終わらない時は周回して探す・感知があれば感知して
探す」.  QUEST_33 (n1-c life-217, 2026-11-19): the Queens were never on the board (placed beyond the
telepathy's 20), the Gachapins only while within it, and the plan chose its waits and its approach
from the map's placements.

What the game shows (C:/hengband/src):

* ``detect_all`` (the Rod of Detection, cmd-item/cmd-zaprod.cpp; spell-kind/spells-detection.cpp:622)
  and ``detect_monsters_evil`` (the Staff of Detect Evil) mark every monster within
  DETECT_RAD_DEFAULT 30 (spell/spells-util.h:3; a third in a DARKNESS dungeon; the rod's Powerful
  Activation 45, cmd-zaprod.cpp:50) with MARK and SHOW (spells-detection.cpp:376-377, 422-423);
  Detect Evil only the EVIL races (hunt_target.REVEALS: the Queens are GOOD).
* The board shows a marked monster ("detected", bot/bot-json-output.cpp:524); the player's turn
  after the detection drops SHOW, the next one MARK and the monster leaves the board
  (core/player-processor.cpp:410-418).  So a detection shows the positions for the next board or
  two; the plan keeps them (``observe``: the last cell and game turn of every tracked monster the
  board showed, seen, sensed or detected).
* How long a kept cell holds: a monster gains speed_to_energy(speed) a game turn and moves at 100
  (monster-processor.cpp sweep_monster_process :676-683; core/speed-table.cpp), so in
  ``STALE_MOVES`` x 100 / energy game turns it may have made ``STALE_MOVES`` moves.  STALE_MOVES is 10,
  the Gachapins' vision: further than that it may have left the ground the wait reader judged it on
  (quest_wait_placement ``acts``).  A Queen (+10, 20 energy) holds 50 game turns, a +0 monster 100.

So (``missing``): a tracked race of the plan (``alignment_split.tracked_races``) has fewer members
known -- on the board, or kept and not stale -- than living (quest_alignment_split ``living``).  Then,
before the plan chooses where to wait or where to go (quest_room_sweep ``_advance``, quest_lure_approach),
the detection (``key``): the Magic-Eater's absorbed rows through me_powers (occasion ``QUEST_REMAINING``,
trigger ``quest-remaining-unseen``: the Detect Evil row, the absorbed Rod of Detection in its place when
usable, and the rod's own row, through Powerful Activation when safe -- owner 2026-11-01 「安全なら
強力発動で使う」), else a carried rod or staff (kill_all_patrol ``_detect_key``'s list), only for an
effect that reveals a missing race, and not again from where a detection covered within
``STALE_MOVES`` of the fastest missing race's moves (``due``).  The wait reader then reads the kept
cells in place of the placements (quest_wait_placement ``awaited``).
"""
from __future__ import annotations

from hengbot import quest_alignment_split, quest_exposure
from hengbot.model import Position
from hengbot.policy_constants import speed_energy

STALE_MOVES = 10
DETECT_REASON = "quest-strategy:detect-remaining"
DETECT_RAD = 30  # DETECT_RAD_DEFAULT


def _tracked(plan) -> tuple:
    split = quest_alignment_split.split_of(plan)
    return tuple(split["tracked_races"]) if split else ()


def stale_turns(policy, race: int) -> int:
    knowledge = policy._monrace_knowledge.get(race)
    energy = speed_energy(int(getattr(knowledge, "speed", 110) or 110))
    return STALE_MOVES * 100 // max(1, energy)


def observe(policy, snapshot, navigator, plan) -> None:
    """Every board: the last cell and game turn of each tracked monster the board shows; the races
    none of which lives are dropped."""
    races = _tracked(plan)
    if not races:
        return
    kept = dict(navigator.remain_seen)
    for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters):
        if monster.hostile and monster.race_id in races:
            kept[monster.index] = (monster.race_id, (monster.position.y, monster.position.x), int(snapshot.turn))
    living = {race: quest_alignment_split.living(policy, snapshot, navigator, plan, race) for race in races}
    for race, alive in living.items():
        entries = sorted((entry[2], index) for index, entry in kept.items() if entry[0] == race)
        for _turn, index in entries[:max(0, len(entries) - alive)]:
            del kept[index]   # more kept than living: the oldest are the dead ones
    navigator.remain_seen = kept


def kept_rows(policy, snapshot, navigator, plan) -> dict:
    """index -> (race, cell, turn) of the kept tracked monsters not on the board now and not stale."""
    shown = {monster.index for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)}
    return {index: entry for index, entry in navigator.remain_seen.items()
            if index not in shown and snapshot.turn - entry[2] <= stale_turns(policy, entry[0])}


def missing(policy, snapshot, navigator, plan) -> list:
    """The tracked races with members living whose cells are neither on the board nor kept fresh."""
    races = []
    kept = kept_rows(policy, snapshot, navigator, plan)
    for race in _tracked(plan):
        alive = quest_alignment_split.living(policy, snapshot, navigator, plan, race)
        known = sum(1 for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                    if monster.hostile and monster.race_id == race)
        known += sum(1 for entry in kept.values() if entry[0] == race)
        if alive > known:
            races.append(race)
    return races


def due(policy, snapshot, navigator, plan, reveals) -> bool:
    """A missing race this effect (``reveals``: flags -> bool) shows, and no detection of this
    plan's within the bound covers the player's cell (cast within half the radius, at most the
    fastest missing race's ``stale_turns`` ago)."""
    from hengbot import hunt_target

    races = [race for race in missing(policy, snapshot, navigator, plan)
             if reveals(hunt_target.race_flags(policy, race))]
    if not races:
        return False
    bound = min(stale_turns(policy, race) for race in races)
    here = (snapshot.player.position.y, snapshot.player.position.x)
    return not any(snapshot.turn - turn <= bound
                   and quest_exposure.game_distance(here, cell) <= DETECT_RAD // 2
                   for cell, turn in navigator.remain_detections)


def _note_cast(snapshot, navigator) -> None:
    here = (snapshot.player.position.y, snapshot.player.position.x)
    navigator.remain_detections = (*navigator.remain_detections, (here, int(snapshot.turn)))


def key(policy, snapshot, navigator, plan) -> str | None:
    """The detection of the missing races, else None (module docstring)."""
    from hengbot import hunt_target, kill_all_patrol, me_powers
    from hengbot.model import SV_STAFF_DETECT_EVIL, TVAL_STAFF

    if not _tracked(plan) or not missing(policy, snapshot, navigator, plan):
        return None
    if any(monster.hostile for monster in snapshot.visible_monsters):
        return None  # a fight on the board: its own rungs answer it
    cast = me_powers.power_key(policy, snapshot, me_powers.QUEST_REMAINING)
    if cast is not None:
        _note_cast(snapshot, navigator)
        return cast
    if snapshot.player.class_id == me_powers.PLAYER_CLASS_MAGIC_EATER:
        return None  # the absorbed rows answer through me_powers (its hostile and charge rules)
    # Another class: a carried rod or staff as kill_all_patrol uses it, for an effect that shows a
    # missing race (the rod any, the staff the EVIL ones).
    effects = ["detect-all"] + (["detect-evil"] if any(
        item.tval == TVAL_STAFF and item.sval == SV_STAFF_DETECT_EVIL for item in snapshot.inventory) else [])
    if any(due(policy, snapshot, navigator, plan, hunt_target.REVEALS[effect]) for effect in effects):
        used = kill_all_patrol._detect_key(policy, snapshot)
        if used is not None:
            policy.last_reason = DETECT_REASON
            _note_cast(snapshot, navigator)
            return used
    return None


def trigger_due(ctx, power) -> bool:
    """me_powers' ``quest-remaining-unseen`` trigger: the quest floor's plan misses a race this row's
    effect reveals (``due``)."""
    from hengbot import hunt_target

    policy, snapshot = ctx.policy, ctx.snapshot
    quest_id = policy._active_fixed_quest_id(snapshot)
    profile = None if quest_id is None else policy.approved_quest_strategy(quest_id)
    plan = None if profile is None else profile.engagement_plan.get("room_sweep")
    navigator = None if plan is None else policy._quest_navigators.get(quest_id)
    reveals = hunt_target.REVEALS.get(power.effect)
    if navigator is None or reveals is None:
        return False
    return due(policy, snapshot, navigator, plan, reveals)
