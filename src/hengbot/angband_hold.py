"""From Angband 50F on the destination is Angband; only a dungeon lord's kill changes it.

Owner 2026-11-19 (verbatim): 「鉄獄50F以降は浅い階層へのフォールバックをやめる。行き先を変えるのはダンジョンの
主討伐のみとする。」  n1-c life-217 (Magic-Eater Lv41, Angband's recall landing 80, 11-19 07:00-11:00)
alternated between Angband 80F and the Castle 64F: the 81F speed gate kept every Angband dive on 80F,
so each dive was no depth progress, and after five of them the no-depth-progress valve switched to
the deepest entered landing under 80 (the Castle 64, above the fallback depth floor 60) for a lease of
5, 10, 20 dives (alternate_lease); each lease ended on Angband again (the deepest destination).  The
same hour earned 1.74x the experience, 1.52x the items and 1.15x the gold at 80F.

A character is held (``held``) once Angband's recall is open (and the Q2 hold does not refuse it) and
its Angband recall landing -- the save's max level, never lowered by the bot except to the 95F cap
(angband_cap) -- is at ``HOLD_DEPTH`` or deeper.  For a held character:

- ``_pick_alternate_dungeon`` (policy_helpers) offers Angband or nothing (``pick``): the
  over-extension and no-depth-progress valves switch to nothing (the Castle/Mountain dive of
  dive_floor.pick is never reached); the guardian valve and the unsafe-recall fallback of a dungeon
  other than Angband (a lord-kill trip refused or bounced) go back to Angband; with Angband itself
  refused no landing is picked -- the depth gates themselves are not relaxed.
- The one exception, owner 2026-11-19 (verbatim) 「この場合だけ城40F付近を許す」: Angband's landing
  refused because survival items or abilities are missing (the *Destruction* means, telepathy, the
  resists: the depth gates of ``_activate_safe_recall_fallback``), the 11-17 Castle band (else the
  Mountain) is explored as before (dive_floor.pick_refused, 38-42) to gather the items and the money,
  and Angband is taken again once its landing qualifies (``settle`` below, alternate_lease.challenge).
- ``alternate_lease.deepest_destination`` takes Angband only.
- ``settle``: on every town board a held switch other than Angband (one made before this rule, or
  restored from the alternate-dungeon record), or a leased Angband switch, is dropped; the ordinary
  selection then takes Angband, or the conquest target.  The Castle band of the exception is kept
  while Angband's landing does not qualify (``alternate_lease.angband_qualifies``).

Not changed: the conquest target (``_conquest_target``, the dungeon lord's kill: the owner's one
reason to change the destination), the Angband 95F cap and its climb (angband_cap), the taken kill
quests, the fundraising trips and the Zul trips (no fallback for depth).
"""

from __future__ import annotations

from hengbot import random_quest_hold
from hengbot.model import DUNGEON_ANGBAND

# Owner 2026-11-19 「鉄獄50F以降」.
HOLD_DEPTH = 50


def held(policy, snapshot) -> bool:
    """The character's Angband recall landing is at 50F or deeper and Angband may be entered.

    Not while a recall toward Angband is refused for its depth outside the finale's expedition
    (angband_cap ``deep_recall_refused``, owner 2026-11-21 「帰還の深さが96F以上なら遠征以外で鉄獄へ
    帰還しない」): Angband is then no destination, and the ordinary fallback picks another dungeon."""
    from hengbot import angband_cap  # import cycle (angband_cap reads angband_finale)
    if angband_cap.deep_recall_refused(snapshot, DUNGEON_ANGBAND, policy):
        return False
    return (bool(snapshot.angband_recall_unlocked)
            and not random_quest_hold.entry_refused(snapshot, DUNGEON_ANGBAND)
            and policy._dungeon_entry_depth(snapshot, DUNGEON_ANGBAND, via_recall=True)
            >= HOLD_DEPTH)


def pick(*, left: int | None, valve: bool) -> int | None:
    """``_pick_alternate_dungeon``'s answer for a held character.

    ``left`` is the dungeon the pick leaves (the refused or the guardian-bounced one), ``valve`` a
    switch made because a depth was too hard (the over-extension or no-depth-progress valve)."""
    if valve or left == DUNGEON_ANGBAND:
        return None
    return DUNGEON_ANGBAND


def settle(policy, snapshot) -> bool:
    """On a town board: drop a held fallback switch of a held character.  True when dropped."""
    from hengbot import alternate_lease, dive_floor  # alternate_lease imports this module

    alternate = getattr(policy, "_alternate_dungeon", None)
    reason = getattr(policy, "_alternate_dungeon_reason", None)
    if (not snapshot.in_town or alternate is None or not held(policy, snapshot)
            or (alternate == DUNGEON_ANGBAND and reason not in alternate_lease.LEASED_REASONS)):
        return False
    # Owner 2026-11-19 「この場合だけ城40F付近を許す」: the refused landing's Castle band stays
    # until Angband's landing qualifies again.
    if (dive_floor.refused_dive_held(policy, snapshot)
            and not alternate_lease.angband_qualifies(policy, snapshot)):
        return False
    policy._alternate_dungeon = None
    policy._alternate_dungeon_reason = None
    alternate_lease.forget(policy)
    setattr(policy, dive_floor.STATE, None)
    return True
