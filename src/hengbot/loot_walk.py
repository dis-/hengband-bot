"""The loot walk commitment: a begun walk to an item is not taken over by another loot walk.

Owner 2026-11-18 (the whole-bot maintainability review's Q3, the chosen option 「命の危険が無ければ
取り終える」): 「取りに歩き始めたら、命の危険（即死の見込み・見える強敵）が出ない限り、取り終えるまで
ほかの歩きに譲らない。今の回数の上限（40回）は残す。」

The loot walks keep the commitments they already had; this module is the one reader that makes
them hold against each other (no new state):

- destruction_loot's fetch: ``MEMORY`` "fetch", the cell where a non-urgent *Destruction* was due
  when the fetch began; the valuable piles a use there may delete are walked to and picked up
  one after another (destruction_loot ``continue_fetch``), bounded by its ``DECISIONS_MAX``
  (the owner's 40) and withheld by a hostile in view (owner 2026-11-18 「見える敵がいなければ」).
- the ordinary loot walk (policy_identification ``_normal_loot_key``: seek-loot, the return
  sweep and the Recall wait's return:seek-loot), committed to ``policy._loot_target``.

``normal_yield_key``: the ordinary walk asked while the fetch is committed continues the fetch
instead of walking toward its own target (a pile underfoot it still picks up: no walk).  n1-b
life-411 (Magic-Eater Lv50, Angband 95F, 2026-11-19 05:41:23, loop-detected, build
bot-d66100109): the fetch began at (15,121) where the use on the sensed ストーム・ワーム was due
and walked west to the Ice Ball wand at (13,117); there the T1 was not read strong, the fetch's
rung (threat_tiers ``sensed_t1_destruction_key``) did not ask destruction_loot, and seek-loot
(later the Recall wait's return:seek-loot) stepped east toward (13,122); at (13,118) the use was
due again and the fetch stepped west: 40 alternations until the loop detector.

``fetch_yield_key``: the other way round, destruction_loot asked to begin a place or a fetch
(``key``) while the ordinary walk is walking toward its target (``MEMORY``: the target, the reason
and the walk's path bound, noted by ``note_walk`` on the board the walk stepped) continues the
ordinary walk instead; the use waits for it within destruction_loot's ``DECISIONS_MAX``, and a
use with nothing to begin is made as before.  n1-b life-397 (60F, 2026-11-15, recorded replay
tests/test_n1b_397_deep_stuck_1115_recorded.py): seek-loot was walking to its pile when the
use on the sensed T1 came due and the fetch took the board over to another pile.

``approach_yield_key``: the approach to *Destruction* (threat_tiers ``approach_key`` and
``remembered_approach_key``: a walk, never an escape, reasons.WALK) about to step while a loot walk
is begun continues the loot walk instead: the committed fetch (``normal_yield_key``), else the
ordinary walk in progress (``fetch_yield_key``, counted in destruction_loot's ``DECISIONS_MAX``).
The use itself is not held (destruction_use ``loot_then_use`` asks it first, as before), only the
approach's step.  The owner's words are 「ほかの歩きに譲らない」, and 2026-11-17's
「価値の高い品は先に拾ってから撃つ」 puts the pickup before the use as well.  n1-c life-217
(Magic-Eater Lv42, Angband 80F, 2026-11-19 12:40, loop-detected, build bot-23df91ff8,
tests/test_n1c_217_approach_loot_1119_recorded.py): seek-loot was walking to the rod at (16,46);
at (14,36) 蛇たちの父『イグ』 (14,23) was 13 off, the use due, destruction_loot asked to begin its
fetch and continued the ordinary walk ('9' to (13,37)); at (13,37) it was 14 off, the use not
due, and the approach stepped '1' straight back without asking the walk: about 40 decisions, a
ping-pong escalation and a Word of Recall read until the loop detector.

``life_danger`` ends the hold: the 即死 projection (threat_tiers ``instant_death``, design 3.1)
or a strong hostile in view (the tiers' reading of the hostiles in view, T1 or T2).  The rungs
above the walks (the emergency ladder, the escapes) answer before any loot walk as before:
nothing here moves a walk above them.
"""

from __future__ import annotations

from hengbot import destruction_loot

# {"floor": floor_key, "target": Position (policy._loot_target when the walk stepped),
#  "reason": str (seek-loot, return:seek-loot ...), "max_path_distance": int | None}: the
# ordinary loot walk in progress (``note_walk``), None when it is not walking.
MEMORY = "_loot_walk_memory"


def life_danger(policy, snapshot) -> bool:
    """The owner's 命の危険: the 即死 projection, or a strong (T1, T2) hostile in view."""
    from hengbot import threat_tiers  # import cycle

    if threat_tiers.instant_death(policy, snapshot).holds:
        return True
    in_view = policy._strategic_hostiles(snapshot)
    return bool(in_view) and threat_tiers.tier_of(policy, snapshot, in_view) in (
        threat_tiers.T1, threat_tiers.T2)


def normal_yield_key(policy, snapshot) -> str | None:
    """The committed fetch's next step or pickup, asked by the ordinary walk before its own step;
    None when no fetch is committed on this floor, or it ends here (none left, the bound, the
    approach's gates, ``life_danger``: destruction_loot ``continue_fetch`` drops it)."""
    return destruction_loot.continue_fetch(policy, snapshot)


def note_walk(policy, snapshot, target, reason, max_path_distance) -> None:
    """The ordinary walk stepped toward ``target`` (policy_identification ``_normal_loot_key``)."""
    setattr(policy, MEMORY, {"floor": snapshot.floor_key, "target": target, "reason": reason,
                             "max_path_distance": max_path_distance})


def forget_walk(policy) -> None:
    """The ordinary walk did not step on this board (it picked up, yielded or found nothing)."""
    setattr(policy, MEMORY, None)


def walk_in_progress(policy, snapshot) -> dict | None:
    """The ordinary walk's ``MEMORY`` while it still holds its target on this floor."""
    memory = getattr(policy, MEMORY, None)
    if (memory is None or memory.get("floor") != snapshot.floor_key
            or memory.get("target") is None or memory["target"] != policy._loot_target):
        return None
    return memory


def fetch_yield_key(policy, snapshot) -> str | None:
    """The ordinary walk's next step or pickup, asked by destruction_loot before it begins a place
    or a fetch; None when the ordinary walk is not walking toward a target on this floor, on
    ``life_danger``, or when the walk itself ends here (its own answer is None)."""
    memory = walk_in_progress(policy, snapshot)
    if memory is None:
        return None
    if life_danger(policy, snapshot):
        forget_walk(policy)
        return None
    return policy._normal_loot_key(
        snapshot, policy._strategic_hostiles(snapshot),
        max_path_distance=memory["max_path_distance"], seek_reason=memory["reason"])


def approach_yield_key(policy, snapshot) -> str | None:
    """The begun loot walk's next step or pickup, asked by the approach to *Destruction* before
    its own step (module docstring): the committed fetch, else the ordinary walk in progress
    within destruction_loot's bound; None when neither is begun (or either ends here)."""
    held = normal_yield_key(policy, snapshot)
    if held is not None:
        return held
    return destruction_loot.walk_held(policy, snapshot)
