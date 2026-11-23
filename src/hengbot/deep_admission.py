"""The one answer to "may the character be on this 50F+ floor, arrived this way" (K2).

Owner 2026-11-04 「使える手段がある時だけ解く」, 2026-11-14 「50F以降で破壊手段なしの探索は許可しない」,
2026-11-18 「破壊を持っていないのに50F以降にいるのが不具合」: a floor of ``DEEP_FLOOR_DEPTH`` (50F) or
deeper is for a character holding the *Destruction* means (destruction_use.holds_means, or the
gate's own reading of it: the carried means, a loadout's means).  The one exception is the held
Castle (else Mountain) climb, owner 2026-11-22 「城の50Fに帰還してすぐ38〜42Fへ登る」 and 2026-11-23
「落とし戸などで着いたら登りと同じにすぐ45F以浅へ登る」 (deep_climb): its 50F landing is arrived on
(``LANDING``) and its floors of 50F or deeper are stood on only to climb at once.  A quest floor
keeps its own rules (``quest``).

Whole-bot maintainability review 2026-11-23 K2: eleven gates asked this with three predicates
of their own.  Each now asks ``verdict`` with its route and its own context -- what it reads as
the means and as the climb (a callable is asked only where the answer needs it, so a gate's
short-circuit is kept) -- and keeps every answer it gave (tests/test_deep_admission_1123.py,
the table of main 5fe531c0a).  The routes (``ROUTES``):

- ``intent``: a dive's intended depth (policy_constants.destruction_dive_permitted /
  permitted_dive_depth, and through them policy_observation._missing_required_abilities' label
  and policy_supply._intended_dive_depth).  No climb.
- ``recall``: the town's Word of Recall landing (destruction_means.departure_carried,
  deep_climb.departure_gaps, policy._destination_depth_allowed, policy._recall_destination_safe).
  The climb at its 50F landing (``climbing``: deep_climb.departure_admits).
- ``fallback-landing``: the unsafe-recall fallback's landing (policy_helpers
  ._fallback_landing_allowed).  The climb at its 50F landing (``climbing``: the picked
  Castle's deep_climb.admits).
- ``stairs``: a stair down from a dungeon floor (policy._deep_stair_refused, and through it
  deep_fall_guard.descent_refused).  No climb.  Below 50F a floor whose trap door (one floor or
  two) would land unadmitted, nothing guarding the fall (``exposed``: deep_fall_guard
  .descent_exposed), is refused too (``FALL``).
- ``trapdoor``: a floor change the policy did not choose: a trap door or a Teleport Level
  (deep_fall_guard.sanctioned, deep_climb.observe).  The climb at its 50F landing only.
- ``stand``: the floor stood on, whatever the way there (a restart's first board included:
  deep_climb._standing_without_means, destruction_use.means_spent).  The climb on every 50F+
  floor of its dungeon; a floor refused here is left (the climb held where the Castle or the
  Mountain can hold it, else the means-spent return), Angband's included.
- ``quest``: a quest floor stood on or entered (deep_climb): admitted, its own rules decide.
- ``deep-descent`` and ``departure-loop``: whether a dive reaches 50F+ at all, the means not
  asked (me_inn_refill.dive_reaches_deep, means_spent_loop.looping).
- ``loadout``: the optimizer's depth band of a loadout, its means the loadout's
  (equipment_optimizer.divable_depth, _meets_static_requirements).  No climb.

``DEEP_FLOOR_DEPTH`` is compared with a depth only here and in the readers listed by
scripts/deep_admission_lint.py (the other 50F+ rules: the teleport, the absorbed powers, the
launcher's score, the room light, ...).

Owner 2026-11-23 (b)-2 「入らない・着いたら登る側にそろえる」: without the means no route enters 50F+,
nor a floor whose trap door lands there unadmitted; a 50F+ floor stood on anyway is climbed from
(the Castle, the Mountain) to 45F or shallower, and only the climb's 50F landing is arrived on.
The routes still answer different questions of that one rule (a dive's intent and a stair never
take the climb's exception, the floor stood on takes it on every floor, a quest floor keeps its
own rules, the means-spent loop's stop is a net on any 50F+ departure): every gate's answer is
that rule's (tests/test_deep_admission_1123.py, tests/support/deep_admission_table.owner_answer).
"""
from __future__ import annotations

from dataclasses import dataclass

# The first of the deep floors, 50F (the owner's 「50F以降」).  policy_constants re-exports it.
DEEP_FLOOR_DEPTH = 50
# The deepest floor without the means (permitted_dive_depth's clamp).
DEEPEST_WITHOUT_MEANS = DEEP_FLOOR_DEPTH - 1
# The held climb's landing (deep_climb).
LANDING = DEEP_FLOOR_DEPTH

BELOW = "below"        # shallower than 50F: no 50F+ rule
MEANS = "means"        # the means is held (the gate's reading)
CLIMB = "climb"        # the held climb's exception
QUEST = "quest"        # a quest floor: its own rules
REFUSED = "refused"
FALL = "fall"          # shallower than 50F, refused: its trap door lands unadmitted (``exposed``)

CLIMB_NONE = "none"
CLIMB_LANDING = "landing"   # the climb's 50F landing only
CLIMB_FLOOR = "floor"       # every 50F+ floor of the climb's dungeon


@dataclass(frozen=True)
class Route:
    means: bool          # the means admits
    climb: str           # CLIMB_NONE / CLIMB_LANDING / CLIMB_FLOOR
    quest: bool = False  # always admitted (a quest floor)
    fall: bool = False   # below 50F, an ``exposed`` floor is refused (``FALL``)


ROUTES = {
    "intent": Route(means=True, climb=CLIMB_NONE),
    "recall": Route(means=True, climb=CLIMB_LANDING),
    "fallback-landing": Route(means=True, climb=CLIMB_LANDING),
    "stairs": Route(means=True, climb=CLIMB_NONE, fall=True),
    "trapdoor": Route(means=True, climb=CLIMB_LANDING),
    "teleport-level": Route(means=True, climb=CLIMB_LANDING),
    "stand": Route(means=True, climb=CLIMB_FLOOR),
    "quest": Route(means=True, climb=CLIMB_NONE, quest=True),
    "deep-descent": Route(means=False, climb=CLIMB_NONE),
    "departure-loop": Route(means=False, climb=CLIMB_NONE),
    "loadout": Route(means=True, climb=CLIMB_NONE),
}


@dataclass(frozen=True)
class Verdict:
    by: str

    @property
    def admitted(self) -> bool:
        return self.by not in (REFUSED, FALL)

    @property
    def deep(self) -> bool:
        """The floor is 50F or deeper (the 50F+ rule applies)."""
        return self.by not in (BELOW, FALL)

    @property
    def climb(self) -> bool:
        """Admitted by the held climb's exception (the means not held, or not asked)."""
        return self.by == CLIMB


def _ask(answer) -> bool:
    return bool(answer() if callable(answer) else answer)


def verdict(dungeon, depth: int, route: str, means=False, climbing=False,
            exposed=False) -> Verdict:
    """The 50F+ rule's answer for ``depth`` of ``dungeon`` reached by ``route``.

    ``means`` and ``climbing`` are the gate's readings (a bool, or a callable asked only when
    the answer needs it, the means before the climb).  ``climbing`` is the gate's reading of the
    held climb on ``dungeon`` (with its own conditions: the town, the landing's gaps).
    ``exposed`` (asked below 50F on a route that reads it) is the gate's reading of a floor whose
    trap door would land unadmitted, nothing guarding the fall.
    ``dungeon`` names the floor for the reader (the gates read the dungeon in ``climbing``)."""
    del dungeon  # the gates' readings carry it
    row = ROUTES[route]
    if depth < DEEP_FLOOR_DEPTH:
        return Verdict(FALL if row.fall and _ask(exposed) else BELOW)
    if row.quest:
        return Verdict(QUEST)
    if row.means and _ask(means):
        return Verdict(MEANS)
    if row.climb == CLIMB_LANDING and depth == LANDING and _ask(climbing):
        return Verdict(CLIMB)
    if row.climb == CLIMB_FLOOR and _ask(climbing):
        return Verdict(CLIMB)
    return Verdict(REFUSED)
