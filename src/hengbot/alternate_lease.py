"""The over-extension switch is a lease: after its dives the original destination is tried again.

Owner 2026-11-11 (PLAN-50F C3, the answer 「5回で本来の行き先へ戻す」, verbatim):
「切り替え先に5回潜ったら、一度本来の行き先へ戻す。そこでまた厳しければ、次は10回、その次は20回と
切り替えの期間を延ばす。」  Before, a switch made because a depth was too hard
(``over_extended_dives``, ``no_depth_progress``) ended only with a new conquest, so all three
viewing characters stayed on the Orc cave 23F (alternate-dungeon.json, 2026-11-10).

And where the original destination is (C5, the answer 「一番深い帰還先」, verbatim):
「帰還先の中で一番深い所（今ならメインのダンジョンの70階）で稼ぐ。」  When the lease ends the target
is the deepest recall destination that passes every landing check (``_recall_destination_safe``:
the depth requirements, a guardian floor the kit cannot pass -- the floor above it is allowed
since C2 -- and P3's T1 guardian bottom floor), among the entered dungeons and Angband once its
recall is open, held as the target (reason ``deepest_destination``, no lease of its own) until
the next switch or conquest.  A conquest target whose landing may be taken keeps its priority.

- A switch from the original destination starts a lease of 5 dives, the next one after a lease
  ended 10, then 20 (doubling); a step down from one leased alternate to another keeps the
  lease and counts again from 0.  A new conquest forgets the lease (the switch ends anyway).
- Only finished normal dives of the alternate count (``dive_ended``).
- The lease and its dives are carried across restarts by ``alternate_dungeon_record``.

Owner 2026-11-17 (verbatim): 「深さの決定について。定期的に一番深い鉄獄にチャレンジするようにしたい」,
and asked how often, 「町に戻るたびに条件を見て挑む」.  Once a switch was made nothing ended it when
Angband became a landing the character may take again (castle-climb-1117: n1-a's Castle band).
``challenge`` is that check, on the town board a dive ends on, before this board's valves: when
Angband at its recall depth passes every landing check (``angband_qualifies``: the same filter as
the deepest destination of C5 -- the cumulative depth requirements with the *Destruction* means and
telepathy from 50F and the 81F speed gate, the guardian floor and P3's T1 bottom floor, the fallback
depth floor -- and the Q2 hold), the held alternate dungeon is dropped (its dives, the
Castle/Mountain dive or climb) and the ordinary selection takes Angband.  Owner 2026-11-18: not
while an over-extension switch's lease runs (「潜りすぎの期限の間は鉄獄に挑まない」; after it ends,
``settle``, every return checks again) nor while a conquest target with a beatable guardian waits
(「制覇できる守護者がいれば制覇が先」).  Angband already held as the alternate is left as it is.
When Angband does not qualify nothing changes.  The drop is no over-extension evidence: the streaks,
the over-extended depth and the lease length stay.
"""
from __future__ import annotations

from hengbot import angband_hold, dive_floor, fallback_depth_floor, random_quest_hold
from hengbot.dungeon_knowledge import exploration_destination_allowed
from hengbot.model import DUNGEON_ANGBAND, DUNGEON_CHAMELEON_CAVE, DUNGEON_YEEK_CAVE

LEASED_REASONS = frozenset({"over_extended_dives", "no_depth_progress"})
FIRST_LEASE = 5
DEEPEST_REASON = "deepest_destination"


def _leased(policy) -> bool:
    return (policy._alternate_dungeon is not None
            and policy._alternate_dungeon_reason in LEASED_REASONS)


def diverts(policy, snapshot) -> bool:
    """A held alternate leads the dives away from the target the observation selected.

    Angband held as the alternate while its recall is open is that target itself: the guardian
    valve's Angband first (reason ``guardian_valve``, owner 2026-11-07) and the deepest
    destination a lease ends on (``deepest_destination``, C5) hold it, without a lease, only to
    keep a demoted conquest target away.  n1-c life-214 (2026-11-15, Angband 49F): held as
    ``guardian_valve`` it blocked the no-depth-progress switch for 91 dives of Angband that
    never went deeper.  A leased Angband alternate is a switch still running and diverts.
    """
    alternate = policy._alternate_dungeon
    return alternate is not None and not (
        alternate == DUNGEON_ANGBAND and snapshot.angband_recall_unlocked and not _leased(policy))


def switched(policy, previous_alternate, previous_reason) -> None:
    """The valve just set a leased alternate: its lease and a fresh dive count."""
    lease = getattr(policy, "_alternate_lease", 0) or 0
    if previous_alternate is not None and previous_reason in LEASED_REASONS:
        lease = lease or FIRST_LEASE       # a step down keeps the running lease
    else:
        lease = FIRST_LEASE if lease <= 0 else lease * 2
    policy._alternate_lease = lease
    policy._alternate_dives = 0


def dive_ended(policy, dungeon_id, normal_dive: bool) -> None:
    if normal_dive and _leased(policy) and dungeon_id == policy._alternate_dungeon:
        policy._alternate_dives = getattr(policy, "_alternate_dives", 0) + 1


def forget(policy) -> None:
    policy._alternate_lease = 0
    policy._alternate_dives = 0


def deepest_destination(policy, snapshot) -> int | None:
    """The deepest recall destination this character may land on now (C5).

    None when it would land under the fallback depth floor (owner 2026-11-13
    「フォールバックは最新到達-20Fまでにする。」, ``fallback_depth_floor``).

    Owner 2026-11-19 「鉄獄50F以降は浅い階層へのフォールバックをやめる」: Angband only for a
    character held at Angband 50F+ (angband_hold)."""
    best, best_depth = None, -1
    candidates = list(snapshot.entered_dungeon_ids or ())
    if snapshot.angband_recall_unlocked and DUNGEON_ANGBAND not in candidates:
        candidates.append(DUNGEON_ANGBAND)
    if angband_hold.held(policy, snapshot):
        candidates = [DUNGEON_ANGBAND]
    for did in candidates:
        if not _destination_takeable(policy, snapshot, did):
            continue
        depth = policy._dungeon_entry_depth(snapshot, did, via_recall=True)
        if depth > best_depth or (depth == best_depth and did < best):
            best, best_depth = did, depth
    if best is None or not fallback_depth_floor.landing_allowed(policy, snapshot, best_depth):
        return None
    return best


def _destination_takeable(policy, snapshot, did) -> bool:
    """``did``'s recall landing passes every landing check but the fallback depth floor."""
    info = policy._dungeon_knowledge.get(did)
    return not (info is None or not exploration_destination_allowed(did)
                or did in (DUNGEON_CHAMELEON_CAVE, DUNGEON_YEEK_CAVE)
                or (did == DUNGEON_ANGBAND and not snapshot.angband_recall_unlocked)
                or not policy._can_fight_in_dungeon(did)
                or (did in snapshot.conquered_dungeon_ids
                    and {"MAZE", "FORGET"}.issubset(info.flags))
                or not policy._recall_destination_safe(snapshot, did))


def angband_qualifies(policy, snapshot) -> bool:
    """Angband at its recall depth is a landing this character may take now (owner 2026-11-17).

    The deepest destination's filter (``_destination_takeable``: ``_recall_destination_safe``
    reads the cumulative depth requirements, the 50F *Destruction* means, the 81F speed gate and
    the blocked guardian floors), the fallback depth floor on the landing, and the Q2 hold."""
    if random_quest_hold.entry_refused(snapshot, DUNGEON_ANGBAND, policy):
        return False
    if not _destination_takeable(policy, snapshot, DUNGEON_ANGBAND):
        return False
    return fallback_depth_floor.landing_allowed(
        policy, snapshot, fallback_depth_floor.landing_depth(policy, snapshot, DUNGEON_ANGBAND))


def _challengeable_alternate(policy, snapshot) -> bool:
    """An alternate dungeon other than Angband is held that the challenge may drop: no lease of an
    over-extension switch is running (owner 2026-11-18 「潜りすぎの期限の間は鉄獄に挑まない」) and no
    conquest target with a beatable guardian waits (「制覇できる守護者がいれば制覇が先」).  Angband
    held as the alternate is Angband already and keeps its reason and lease."""
    alternate = policy._alternate_dungeon
    return (alternate is not None and alternate != DUNGEON_ANGBAND and not _leased(policy)
            and policy._conquest_target(snapshot) is None)


def challenge(policy, snapshot) -> bool:
    """On the town board a dive ends on: go back to Angband when it qualifies (owner 2026-11-17
    「町に戻るたびに条件を見て挑む」).  True when the held alternate was dropped; the ordinary
    selection then takes Angband (its recall is open and no conquest target waits)."""
    if (not snapshot.in_town or not _challengeable_alternate(policy, snapshot)
            or not angband_qualifies(policy, snapshot)):
        return False
    policy._alternate_dungeon = None
    policy._alternate_dungeon_reason = None
    policy._alternate_dives = 0
    setattr(policy, dive_floor.STATE, None)
    return True


def settle(policy, snapshot) -> bool:
    """On a town board: end a lease whose dives are done.  True when it ended."""
    if not snapshot.in_town or not _leased(policy):
        return False
    lease = getattr(policy, "_alternate_lease", 0) or FIRST_LEASE
    policy._alternate_lease = lease
    if getattr(policy, "_alternate_dives", 0) < lease:
        return False
    end(policy, snapshot)
    return True


def end(policy, snapshot) -> None:
    """End the switch: the original destination is taken again (C5).

    Also how ``fallback_depth_floor.settle`` ends a switch that lands under its floor."""
    policy._alternate_dungeon = None
    policy._alternate_dungeon_reason = None
    policy._alternate_dives = 0
    policy._target_empty_dives = 0
    policy._guardian_bounce_dives = 0
    policy._no_depth_progress_dives = 0
    # A conquest target whose landing the character may take keeps its priority (its guardian
    # is beatable); one refused there (n1-b's Mountain 50F, P3's T1 guardian) does not.
    conquest = policy._conquest_target(snapshot)
    if conquest is not None and policy._recall_destination_safe(snapshot, conquest):
        return
    deepest = deepest_destination(policy, snapshot)
    if deepest is None:
        return
    policy._alternate_dungeon = deepest
    policy._alternate_dungeon_reason = DEEPEST_REASON
    policy._conquest_committed = None
