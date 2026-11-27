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
  Not for Angband refused for its 96F+ recall depth outside the finale's expedition
  (``deep_refused``, owner 2026-11-21 「帰還の深さが96F以上なら遠征以外で鉄獄へ帰還しない」): the town
  prepares the expedition or stops by name (finale_hold), no dungeon is picked.
- ``alternate_lease.deepest_destination`` takes Angband only.
- ``settle``: on every town board a held switch other than Angband (one made before this rule, or
  restored from the alternate-dungeon record), or a leased Angband switch, is dropped; the ordinary
  selection then takes Angband, or the conquest target.  The Castle band of the exception is kept
  while Angband's landing does not qualify (``alternate_lease.angband_qualifies``).

Not changed: the Angband 95F cap and its climb (angband_cap), the taken kill quests, the
fundraising trips and the Zul trips (no fallback for depth).

The conquest target (``_conquest_target``, the dungeon lord's kill), the owner's one reason to
change the destination, is narrowed by the supervisor on 2026-11-26 under the owner's leave of that
day 「…いずれも、ゲーム内選択に関して私の以前の指示を破ることを許可する。」: none while the held
character's real blocker is a depth gate (``depth_gated``: Angband's landing may be taken but the
floor below it asks a gate the character does not own; the hunt opens no gate, and the measured reason above -- 80F earned 1.74x
the experience of the Castle 64F -- favours Angband's landing), and each target has a budget
(conquest_budget).  n1-c life-222 (2026-11-25 07:40-15:05) recalled 119 times to the Mountain 50F
for 大鷲王『ソロンドール』 while the 81F speed +25 gate held it at Angband 80F.  Nothing measured
kept the conquest for a held character: the 11-19 rule's measurement compared Angband with the
Castle's fallback dives, not with a lord's hunt.
"""

from __future__ import annotations

from hengbot import random_quest_hold
from hengbot.model import DUNGEON_ANGBAND

# Owner 2026-11-19 「鉄獄50F以降」.
HOLD_DEPTH = 50


def held(policy, snapshot) -> bool:
    """The character's Angband recall landing is at 50F or deeper and Angband may be entered.

    Also while a recall toward Angband is refused for its depth outside the finale's expedition
    (``deep_refused``, owner 2026-11-21 「帰還の深さが96F以上なら遠征以外で鉄獄へ帰還しない」): the 11-19
    rule still allows no other dungeon (``pick`` answers nothing for the refused Angband), and the
    town prepares the expedition instead (finale_hold).  This read was false then, and the ordinary
    fallback took the Castle 64F (n1-b life-416 2026-11-23 21:10-21:16)."""
    return (bool(snapshot.angband_recall_unlocked)
            and not random_quest_hold.entry_refused(snapshot, DUNGEON_ANGBAND, policy)
            and policy._dungeon_entry_depth(snapshot, DUNGEON_ANGBAND, via_recall=True)
            >= HOLD_DEPTH)


def depth_gated(policy, snapshot) -> bool:
    """A held character (``held``) that may level at Angband's recall landing but whose floor
    below it asks a depth gate (policy_constants ``required_depth_gates``: the resistances,
    telepathy, *Destruction*, speed +25 from 81F) the character does not own, worn, carried or at
    Home (``owned``, the town's destination reading).  Not when the landing itself is gated (the
    survival exception's Castle band gathers the items there, 「この場合だけ城40F付近を許す」) and
    not past the 95F cap: the cap, not a gate, ends the descent there (angband_cap; the finale's
    preparation forbids the hunt, finale_prep)."""
    if not held(policy, snapshot):
        return False
    from hengbot import angband_cap  # import cycle (angband_cap reads angband_finale)
    landing = policy._dungeon_entry_depth(snapshot, DUNGEON_ANGBAND, via_recall=True)
    # The speed ceiling (angband_cap ``speed_ceiling``, 2026-11-27) is a gate's cap: the floor
    # levelled at is the ceiling, the gated one below it (n1-b life-419 hunted the Castle's and the
    # Dark cave's guardians with its landing 81 one floor past the ceiling 80).
    ceiling = getattr(policy, angband_cap.CEILING, None)
    if ceiling is not None and angband_cap.cap(DUNGEON_ANGBAND, policy) == ceiling:
        landing = min(landing, ceiling)
    elif angband_cap.capped_at(DUNGEON_ANGBAND, landing + 1, policy):
        return False
    return (not policy._missing_required_abilities(snapshot, landing, owned=True)
            and bool(policy._missing_required_abilities(snapshot, landing + 1, owned=True)))


def deep_refused(policy, snapshot) -> bool:
    """Angband's recall is refused for its depth outside the finale's expedition (angband_cap
    ``deep_recall_refused``): not the survival exception's refusal (「この場合だけ城40F付近を許す」),
    so no Castle band either."""
    from hengbot import angband_cap  # import cycle (angband_cap reads angband_finale)
    return angband_cap.deep_recall_refused(snapshot, DUNGEON_ANGBAND, policy)


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
    from hengbot import finale_bm_tour  # import cycle
    if reason == finale_bm_tour.DIVE_REASON:
        # Owner 2026-11-25: the 96F+ finale's dive for its gold is no fallback (finale_bm_tour
        # ``settle_dive`` ends it).
        return False
    # Owner 2026-11-19 「この場合だけ城40F付近を許す」: the refused landing's Castle band stays
    # until Angband's landing qualifies again.
    # Not for the 96F+ refusal (``deep_refused``): no fallback at all there.
    if (dive_floor.refused_dive_held(policy, snapshot)
            and not deep_refused(policy, snapshot)
            and not alternate_lease.angband_qualifies(policy, snapshot)):
        return False
    policy._alternate_dungeon = None
    policy._alternate_dungeon_reason = None
    alternate_lease.forget(policy)
    setattr(policy, dive_floor.STATE, None)
    return True
