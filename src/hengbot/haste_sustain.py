"""70-90F's speed +10: held permanently, or sustained for the dive (supervisor 2026-11-27).

Owner 2026-11-27 (verbatim): 「70Fより上で加速+10を得るのはそれなりに困難である。もしもそれに拘るのであれば
どうやって加速+10を得るのか明確にする必要がある。」 and 「大きく加速を得るためにはスピードの指輪が一番簡単だが、
これの生成階層は80Fである。私の指定でリスクを取って80Fに行かせていたのはこのためである。」  The 2026-11-26
row (policy_constants ``MID_SPEED_GATE_*``: permanent +10 from 70F) had no dependable source shallower
than 70F (lib/edit: the Speed boots ego of EgoDefinitions id 59 rolls randint1(pval) below 50F,
object-ego.cpp:347; the Ring of Speed is a level-80 kind, BaseitemDefinitions id 136; the +10
artifacts are rarity 15-120), so it parked such characters at Angband 69F (angband_cap's speed ceiling)
where the ring is out of depth.  Of the nine 76-80F deaths at permanent +9 or less behind that row,
all carried absorbed Speed (35-99 charges); five died hasted, four unhasted.

The row now reads (``row_met``, the one answer the depth gates and the speed ceiling read): the
permanent speed meets it, or the character holds enough Speed doses for the dive (``uses``: the
Magic-Eater's absorbed Speed while reliable, me_capability; and the carried Potions of Speed -- the
two the one dose, speed_dose, takes).  The town departs with ``DIVE_HASTE_USES``; on the floor the row
holds down to ``RETURN_RESERVE_USES``, below which the floor's gap starts the ordinary resist-gap town
return (policy_town).  91F+ keeps its permanent +25 (angband_cap's ceiling at 90F; the row covers 80-90F since owner 2026-11-28 「80Fから90Fまでは危険度に大きな変化はない。」).

The doses (cmd-usestaff.cpp:240 / cmd-zaprod.cpp:147 set_acceleration(randint1(30) + 15) for the staff
the Magic-Eater casts, quaff-effects.cpp:382 set_acceleration(randint1(25) + 15) for the potion, one
tick per TURNS_PER_TICK 10 game turns, system/gamevalue.h:13) last at least 16 ticks, 160 game turns
(me_powers ``HASTE_MIN_GAME_TURNS``).  The upkeep (``after_ladder``) keeps the haste up on such a floor:
with an awake hostile in view or sensed, a decided ordinary action (a fight, a walk, a rest) gives way
to the dose when the haste is off, and to a recast of the absorbed power once the shortest haste of
the last dose has run (a potion drunk while hasted adds only 5 ticks, quaff-effects.cpp:378, so it waits
for the haste to end).  Escapes, heals and cures keep their boards.
"""
from __future__ import annotations

import math

from hengbot import haste_read, me_capability, speed_dose
from hengbot.model import SV_POTION_SPEED, SV_STAFF_SPEED

# The p90 length of a dive at Angband 70-80F, recall down to recall up: 191 game minutes of the 133
# such dives in n1-b life-419 (75) and n1-c life-222 (58) playrecord-SOAK.txt (median 56, p75 122);
# a game day is TURNS_PER_TICK x TOWN_DAWN = 100,000 game turns (system/gamevalue.h:12-13).
DIVE_GAME_TURNS = 191 * 100_000 // 1440
# Doses the upkeep cadence asked on n1-c life-223's Angband 61-69F decisions (2026-11-27, 112,933
# game turns): one per board with a hostile in view or predicted, at most one per HASTE_MIN_GAME_TURNS.
MEASURED_DOSES = 163
MEASURED_GAME_TURNS = 112_933
# The doses one p90 dive takes: 20.
DIVE_HASTE_USES = math.ceil(DIVE_GAME_TURNS * MEASURED_DOSES / MEASURED_GAME_TURNS)
# On the floor the row holds down to this many doses (the town return's own haste).
RETURN_RESERVE_USES = 2
# me_powers HASTE_MIN_GAME_TURNS: the shortest haste of a dose, in game turns.
RENEW_GAME_TURNS = 160
REASON = "haste-sustain:dose"
MEMORY = "_haste_sustain_last_dose"
# The decided actions the upkeep's dose takes the place of: a fight or an ordinary step.  Every
# other reason (an escape, a heal, a cure, a return) keeps its board.
ORDINARY_PREFIXES = ("melee", "ranged:", "hunt", "summoner:ranged-kill", "explore", "seek-",
                     "search", "rest", "descend", "deep-stairs", "loot", "pickup", "walk")


def uses(policy, snapshot) -> int:
    """The Speed doses the one dose (speed_dose) can take: the absorbed Speed's charges while the
    power is reliable, and the carried Potions of Speed."""
    absorbed = (me_capability.charges(policy, snapshot, "staff", SV_STAFF_SPEED)
                if me_capability.reliable(policy, snapshot, ("staff", SV_STAFF_SPEED)) else 0)
    return absorbed + policy._exact_potion_count(snapshot, SV_POTION_SPEED)


def sustained(policy, snapshot) -> bool:
    """Enough doses for the row: ``DIVE_HASTE_USES`` in town, ``RETURN_RESERVE_USES`` on a floor."""
    need = DIVE_HASTE_USES if getattr(snapshot, "in_town", False) else RETURN_RESERVE_USES
    return uses(policy, snapshot) >= need


def row_met(policy, snapshot, row) -> bool:
    """A depth speed row (policy_constants ``SPEED_GATES``: (label, permanent speed)) is met: the
    permanent speed reaches it, or, for the 70-90F row, the haste is sustained (``sustained``)."""
    from hengbot.policy_constants import MID_SPEED_GATE_LABEL  # import cycle
    from hengbot.speed_valuation import permanent_player_speed

    label, need = row
    if permanent_player_speed(snapshot) >= need:
        return True
    return label == MID_SPEED_GATE_LABEL and policy is not None and sustained(policy, snapshot)


def _relies_on_doses(policy, snapshot) -> bool:
    """On a floor of the 70-90F row whose permanent speed the row does not meet."""
    from hengbot.policy_constants import MID_SPEED_GATE_LABEL, speed_gate
    from hengbot.speed_valuation import permanent_player_speed

    if getattr(snapshot, "in_town", True) or snapshot.dungeon_level <= 0:
        return False
    row = speed_gate(snapshot.dungeon_level)
    return (row is not None and row[0] == MID_SPEED_GATE_LABEL
            and permanent_player_speed(snapshot) < row[1])


def _awake_hostile(snapshot) -> bool:
    return any(monster.hostile and not monster.asleep
               for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters))


def after_ladder(policy, snapshot, key):
    """The upkeep's dose in place of the decided ordinary action (module docstring), else ``key``."""
    if (key is None or not _relies_on_doses(policy, snapshot) or not _awake_hostile(snapshot)
            or not (policy.last_reason or "").startswith(ORDINARY_PREFIXES)):
        return key
    last = getattr(policy, MEMORY, None)
    if haste_read.hasted(policy, snapshot):
        recent = (last is not None and last[0] == snapshot.floor_key
                  and snapshot.turn - last[1] < RENEW_GAME_TURNS)
        if last is None or recent or not speed_dose.cast_available(policy, snapshot):
            return key
    dose = speed_dose.key(policy, snapshot, REASON)
    if dose is None:
        return key
    setattr(policy, MEMORY, (snapshot.floor_key, snapshot.turn))
    return dose
