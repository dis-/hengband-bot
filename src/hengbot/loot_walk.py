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

The other way round, a fetch beginning while the ordinary walk holds its target, is one hand-over
and no alternation (the begun fetch then holds until it ends, and the ordinary walk goes on); it
is left as it was: a rule that held the ordinary walk there changed which board the use was made
on in recorded replays that do not loop (tests/test_n1b_397_deep_stuck_1115_recorded.py).

``life_danger`` ends the hold: the 即死 projection (threat_tiers ``instant_death``, design 3.1)
or a strong hostile in view (the tiers' reading of the hostiles in view, T1 or T2).  The rungs
above the walks (the emergency ladder, the escapes) answer before any loot walk as before:
nothing here moves a walk above them.
"""

from __future__ import annotations

from hengbot import destruction_loot


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
