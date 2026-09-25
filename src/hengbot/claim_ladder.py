"""The claim ladder: who may take a decision from whom (stage S2b.1).

``SOL-DESIGN-ownership-contract.md`` rev 10.1, "Rev 10: S2b specified" and
"Rev 10.1".  **Record-only.**  Nothing here is read by a producer, by
``_decide`` or by the driver: the policy's declaration point
(``policy._record_decision_claim``) asks it for the rank of the decision it is
recording, and the offline reader (``ownership_metrics.ladder_numbers``) asks
the same functions about rows written before the ladder existed.  No key,
reason or decision can depend on it.

The ladder ranks rungs, not families (rev 10.1 item 1)
------------------------------------------------------
``_decide`` re-evaluates its producers top-down on every board, and one family
answers at several separated rungs (positioning, escape, combat, survival,
departure, detectors, floor-loot, quest-request, equipment-txn ...).
``CLAIM_LADDER`` is therefore an ordered tuple of **rungs**, each naming its
producer (the method ``_decide`` calls) and the census family of the reasons
that call site emits.  Four sections, highest priority first:

``rewrite``   the post-decision rewrites of design 3.3.1 and ``bookkeeping``,
              produced in ``choose_key`` / ``_choose_key`` outside ``_decide``
              (rev 10.1 item 1): ``detectors``, then ``town-plan``, then
              ``bookkeeping`` -- the order in which a later rewrite overrides an
              earlier one.
``decide``    every ``@claims``-marked producer call inside ``_decide``, in
              the order ``_decide`` consults them
              (``tests/test_ownership_s2b1_ladder.py`` pins that order against
              the source), plus four unmarked dispatcher calls (``marked`` is
              ``False``) whose reasons would otherwise have no rung of their own:
              the emergency ladder, the mana-food override, the paralyzer
              stand-off and the quest navigator.  Each rung has its own rank,
              except the town errand rungs below.
``town``      town errand families that no ``_decide`` call site names, and the
              town half of ``departure``.
``fallback``  ``idle`` and the two catch-alls, below everything.

Town errands share one rank (rev 10.1 item 2)
---------------------------------------------
Every rung whose family is a town errand family (``TOWN_ERRAND_FAMILIES``), the
town departure rung and the town call of ``_fundraising_key`` have the same
rank, ``TOWN_RANK``, below every dungeon rung: none of them may take a walk or
an operation from another without closing it.  The exception is
``equipment-txn`` while it owns a transaction (after the strip, the claim's
``non_discardable``): it keeps the rank of its own ``_decide`` rungs (5765 /
5799), above the other errands.  Nothing sets ``non_discardable`` yet (design
3.1 left it for the producers that migrate in S3), so until then every
``equipment-txn`` decision ranks as a town errand.

From a decision to its rung
---------------------------
A decision is known by its census family and its reason -- a row written
before the ladder existed carries exactly those -- so ``rung_of`` answers from
them alone, and the live writer and the offline reader use the same function
(rev 10.1 item 11):

1. an ``equipment-txn`` claim that is ``non_discardable`` is the transaction
   owner's rung;
2. otherwise, among the rungs of the family, the one with the longest reason
   prefix the reason starts with (the first such rung on a tie);
3. otherwise the family's single ``ordinary`` rung.  A producer called at
   several sites that emit the same reasons (``_return_to_town_key`` at the
   contested threat rung, the breeder walk-out and the ordinary return) cannot
   be told apart by its reason; its rows take the ordinary site's rank and the
   other sites carry no reason prefix.

Preemption and violation (rev 10 items 2 and 4, rev 10.1 item 6)
----------------------------------------------------------------
``owner_change`` is the one comparison: a held Reach/Observe claim given way
to another owner is a *preemption* only when the new decision ranks strictly
higher (so every push is by a strictly higher rank and the stack is bounded by
the number of ranks); survival that does not outrank it *replaces* it
(``survival-displaced``, exempt, not a violation); anything else is a
*violation*.  A store-operation or transaction ``Observe`` claim is never
suspended: giving it way is always a violation (its families are migrated in
S3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hengbot.claim_goal_typing import FLOOR_CHANGE


GOAL_REACH = "Reach"
GOAL_OBSERVE = "Observe"

SECTION_REWRITE = "rewrite"
SECTION_DECIDE = "decide"
SECTION_TOWN = "town"
SECTION_FALLBACK = "fallback"

# Rev 10 item 1 / rev 10.1 item 2: the families that share one town rank.
TOWN_ERRAND_FAMILIES = frozenset({
    "home-errand",
    "home-scan",
    "home-visit",
    "shop-sell",
    "shop-buy",
    "store-router",
    "equipment-opt",
    "equipment-txn",
    "calibration",
    "identification",
    "curse-enchant",
    "cross-town",
    "rumor",
})
# Rev 10.1 item 8: the families migrated in S3, reported on their own lines
# and excluded from the S2b.2 gate.  ``departure in town`` is the town
# departure rung (``is_s3_rung``).
S3_FAMILIES = frozenset({
    "store-router",
    "shop-buy",
    "shop-sell",
    "home-visit",
    "home-errand",
    "home-scan",
    "equipment-txn",
    "calibration",
    "identification",
    "curse-enchant",
})
# Rev 10.1 item 9: the families whose Reach/Observe claims record the monsters
# that triggered them.
TRIGGER_FAMILIES = frozenset({
    "positioning", "hunt", "esp-threat", "combat", "escape",
})

# S2b.2 round 2 (design 3.3's plumbing): the rungs of ``_decide`` that ask
# ``policy._claim_bar_skips`` before they run and are not called while a bar a
# claim of theirs earned stands (switch on only).  A gated rung is one a bar
# can carry -- ``rung_of`` gives it a threat-triggered Reach/Observe reason --
# and that cannot answer survival, since whether an answer is survival is
# known only after the rung has run.  ``tests/test_ownership_s2b2_bar.py``
# pins this set against the wiring in the source.
BAR_GATED_RUNGS = frozenset({
    "_detected_threat_preparation_key",
    "_breeder_breakthrough_key",
    "_choke_engagement_key",
    "_breeder_breakthrough_escape_key",
})

PREEMPTION = "preemption"
VIOLATION = "violation"
# Survival that does not outrank the holder replaces it (not a violation).
SURVIVAL_DISPLACED = "survival-displaced"
SCOPE_IN = "in-scope"
SCOPE_S3 = "S3"


@dataclass(frozen=True)
class Rung:
    """One rung: a producer call site and the family its reasons belong to.

    ``reasons``           reason prefixes that identify this call site among
                          the family's rungs (empty: only its position).
    ``ordinary``          the family's rung for a reason no prefix claims.
    ``marked``            (``decide``) the call is an ``@claims``-marked
                          ``self`` method; otherwise ``producer`` is the call
                          as written (``navigator.decide``).
    ``owns_transaction``  (``equipment-txn``) the rung that holds a stripped
                          character; matched by ``non_discardable`` only.
    ``town``              a ``decide`` rung outside the town errand families
                          that still shares the town rank (fundraising's town
                          call).
    """

    producer: str
    family: str
    section: str
    reasons: tuple[str, ...] = ()
    ordinary: bool = False
    marked: bool = True
    owns_transaction: bool = False
    town: bool = False
    rank: int = field(default=-1, compare=False)
    # ``producer``, or ``producer#n`` for the n-th call site of a producer
    # ``_decide`` calls more than once: the rung's unique name in a row.
    name: str = field(default="", compare=False)

    @property
    def shares_town_rank(self) -> bool:
        if self.section == SECTION_TOWN:
            return True
        if self.section != SECTION_DECIDE or self.owns_transaction:
            return False
        return self.town or self.family in TOWN_ERRAND_FAMILIES


def _rewrite(producer, family, *reasons, ordinary=False):
    return Rung(producer, family, SECTION_REWRITE, tuple(reasons), ordinary)


def _decide(producer, family, *reasons, ordinary=False, marked=True,
            owns_transaction=False, town=False):
    return Rung(
        producer, family, SECTION_DECIDE, tuple(reasons), ordinary, marked,
        owns_transaction, town,
    )


def _town(producer, family, *reasons, ordinary=True):
    return Rung(producer, family, SECTION_TOWN, tuple(reasons), ordinary)


def _fallback(producer, family, *reasons):
    return Rung(producer, family, SECTION_FALLBACK, tuple(reasons), True)


# The line numbers in the comments are ``policy.py`` at 43802ae4; the test
# compares the order with the source itself, never with these numbers.
_RUNGS: tuple[Rung, ...] = (
    # -- rewrite: after the ladder has spoken (design 3.3.1) ------------------
    _rewrite("_refuse_no_progress_cycle", "detectors", ordinary=True),
    _rewrite("_forbid_wait_while_damaged", "detectors", "no-wait:"),
    _rewrite("_break_positional_oscillation", "detectors", "nav:"),
    _rewrite("_break_livelock", "detectors"),
    _rewrite("_bound_escape_wait", "detectors"),
    _rewrite("_town_procurement_decision", "town-plan", ordinary=True),
    _rewrite("_skill_exp_request_key", "bookkeeping", "periodic:skill-exp"),
    _rewrite("_periodic_game_save_key", "bookkeeping", ordinary=True),
    _rewrite(
        "_periodic_character_dump_key", "bookkeeping",
        "periodic:character-dump", "town:character-dump",
    ),
    # -- decide: the order _decide consults them ------------------------------
    _decide("_equipment_transaction_town_key", "equipment-txn",
            owns_transaction=True),                                    # 5765
    _decide("_equipment_transaction_town_owner_key", "equipment-txn",
            owns_transaction=True),                                    # 5799
    _decide("_town_order_step4_key", "quest-request"),                 # 5883
    _decide("_esp_threat_hunt_key", "esp-threat", ordinary=True),      # 5986
    _decide("_summoner_ranged_kill_key", "combat",
            "summoner:ranged-kill"),                                   # 5991
    _decide("_emergency_item", "escape",
            "emergency:", "unseen-recall:", "guardian:teleport-to-cover",
            marked=False),                                             # 5996
    _decide("_mana_food_survival_override_key", "survival",
            "survival:mana-", marked=False),                           # 6011
    _decide("_paralyzer_prevention_key", "positioning",
            "threat:paralyzer-avoid", "paralyzer-guard:",
            marked=False),                                             # 6015
    _decide("_unseen_retreat_intercept_key", "positioning"),           # 6021
    _decide("_unseen_retreat_key", "escape", "unseen:"),               # 6026
    _decide("_detected_threat_preparation_key", "positioning",
            "detected:", ordinary=True),                               # 6031
    _decide("_return_to_town_key", "departure"),                       # 6043
    _decide("_dark_locomotion_key", "detectors", "dark:"),             # 6056
    _decide("_breakout_restore_weapon_key", "detectors",
            "breakout:restore-combat-weapon"),                         # 6079
    _decide("_survival_gate_key", "survival"),                         # 6087
    _decide("_chest_processing_key", "floor-loot"),                    # 6116
    _decide("navigator.decide", "quest-sweep", "quest-strategy:",
            ordinary=True, marked=False),                              # 6125
    _decide("_town_kill_mob_key", "survival", "town:kill-mob"),        # 6156
    _decide("_breeder_breakthrough_key", "escape",
            "breeder-breakthrough:recall",
            "breeder-breakthrough:wait-recall"),                       # 6170
    _decide("_choke_engagement_key", "positioning", "melee:choke"),    # 6178
    _decide("_ranged_attack_key", "combat"),                           # 6194
    _decide("_fruitless_disengage_key", "escape",
            "combat:disengage", "combat:fruitless"),                   # 6204
    _decide("_breeder_breakthrough_escape_key", "escape",
            "breeder-breakthrough:"),                                  # 6247
    _decide("_melee_swarm_combat_key", "positioning"),                 # 6264
    _decide("_flee_step", "survival", "status-threat:"),               # 6302
    _decide("_blocking_escape_melee_key", "escape",
            "combat:disengage-clear-path"),                            # 6351
    _decide("_flee_step", "escape", "flee", ordinary=True),            # 6362
    _decide("_direction_key", "escape", "flee:cornered-attack"),       # 6387
    _decide("_direction_key", "combat", "melee", ordinary=True),       # 6469
    _decide("_ranged_attack_key", "combat", "ranged:"),                # 6476
    _decide("_flee_step", "positioning", "threat:reposition"),         # 6494
    _decide("_hunt_step", "hunt", "hunt:quest-target"),                # 6513
    _decide("_survival_gate_key", "survival", "survival:",
            "weak-fainting", ordinary=True),                           # 6524
    _decide("_mana_food_loot_key", "survival", "mana-food:"),          # 6528
    _decide("_kill_quest_floor_recovery_key", "quest-request",
            "quest:regen:"),                                           # 6534
    _decide("_home_disposal_processing_key", "home-visit",
            "home-disposal:", ordinary=True),                          # 6538
    _decide("_town_restore_weapon_key", "equipment-txn"),              # 6598
    _decide("_fixed_quest_key", "quest-request"),                      # 6606
    _decide("_town_space_deposit_key", "store-router"),                # 6610
    _decide("_victory_loot_key", "floor-loot", "victory:"),            # 6614
    _decide("_conquest_loot_key", "floor-loot", "conquest:"),          # 6618
    _decide("_fixed_quest_key", "quest-request", "fixedquest:",
            ordinary=True),                                            # 6622
    _decide("_stat_restore_quaff_key", "survival", "restore:"),        # 6626
    _decide("_experience_potion_quaff_key", "survival",
            "experience:"),                                            # 6632
    _decide("_stat_gain_quaff_key", "survival", "stat-gain:"),         # 6638
    _decide("_town_order_step4_key", "quest-request", "bounty:"),      # 6642
    _decide("_fundraising_key", "fundraising", "fundraise:",
            ordinary=True),                                            # 6652
    _decide("_chest_processing_key", "floor-loot", "chest:"),          # 6690
    _decide("_normal_loot_key", "departure", "return:seek-loot"),      # 6709
    _decide("_navigation_livelock_key", "detectors",
            "livelock:ascend", "livelock:recall-escape",
            "livelock:seek-", "livelock:teleport-explore"),            # 6726
    _decide("_return_to_town_key", "departure"),                       # 6739
    _decide("_return_to_town_key", "departure", "return:",
            ordinary=True),                                            # 6756
    _decide("_shopping_approach_key", "equipment-txn",
            "equipment-transaction:acquire-home-catalog",
            "equipment-transaction:travel-home"),                      # 6788
    _decide("_town_equipped_identification_key", "identification",
            ordinary=True),                                            # 6796
    _decide("_town_device_processing_key", "identification",
            "identify:device"),                                        # 6804
    _decide("_heavy_curse_inscription_key", "equipment-txn"),          # 6818
    _decide("_town_remove_curse_key", "curse-enchant",
            ordinary=True),                                            # 6822
    _decide("_town_enchant_launcher_key", "curse-enchant"),            # 6826
    _decide("_town_random_teleport_suppression_key",
            "equipment-txn"),                                          # 6830
    _decide("_calibration_town_key", "calibration", ordinary=True),    # 6839
    _decide("_equipment_transaction_town_key", "equipment-txn",
            ordinary=True),                                            # 6847
    _decide("_normal_loot_key", "floor-loot", "seek-loot", "loot:",
            ordinary=True),                                            # 6855
    _decide("_shopping_approach_key", "store-router",
            ordinary=True),                                            # 6923
    # Its own site writes ``town:blocked:overflow-no-legal-disposal``, which
    # ranks here, not at town-plan's rewrite rung; the shop-sell
    # ``town:destroy-overflow`` it passes to ``_verified_destroy_key`` ranks
    # at shop-sell's town rung below.
    _decide("_town_overflow_destroy_key", "town-plan",
            "town:blocked:overflow-no-legal-disposal"),                # 6940
    _decide("_fundraising_key", "fundraising", "town:",
            town=True),                                                # 6980
    _decide("_released_restock_store_key", "store-router"),            # 6993
    # S2b.1b: the uncommitted WEAK / MEDIUM hunt is produced only here (the
    # rest slot, ``policy_combat._esp_threat_rest_key``), below the combat
    # rungs; without its prefixes it ranked at the committed STRONG hunt's
    # rung (5986) and a swing that took the walk over read as a violation.
    # ``esp-threat:hunt-strong`` is emitted at both sites and keeps the
    # ordinary rung (see ``rung_of``).
    _decide("_esp_threat_rest_key", "esp-threat",
            "esp-threat:hunt-weak", "esp-threat:hunt-medium"),         # 7015
    _decide("_flee_step", "positioning",
            "threat:avoid-engagement"),                                # 7114
    _decide("_descent_step", "departure",
            "seek-downstairs", "approach-descent"),                    # 7128
    _decide("_hunt_step", "departure", "clear-descent"),               # 7135
    _decide("_hunt_step", "hunt", "hunt", ordinary=True),              # 7155
    _decide("_breakout_restore_weapon_key", "detectors"),              # 7202
    _decide("_explore_step", "detectors", "breakout:", "stuck:"),      # 7248
    _decide("_immobile_breeder_giveup_key", "explore", "explore:"),    # 7283
    _decide("_explore_step", "explore", "explore", "search", "probe",
            "seek-secret-wall", ordinary=True),                        # 7288
    _decide("_start_kill_quest_regeneration", "quest-request",
            "quest:regen:exhausted"),                                  # 7344
    # -- town: errands no _decide call site names; departure in town --------
    _town("town-errand:home-errand", "home-errand"),
    _town("town-errand:home-scan", "home-scan"),
    _town("town-errand:shop-buy", "shop-buy"),
    _town("town-errand:shop-sell", "shop-sell"),
    _town("town-errand:equipment-opt", "equipment-opt"),
    _town("town-errand:cross-town", "cross-town"),
    _town("town-errand:rumor", "rumor"),
    _town(
        "town-errand:departure", "departure",
        "town:", "depart", "repetition-depart", "wilderness:",
        ordinary=False,
    ),
    # -- fallback -------------------------------------------------------------
    _fallback("fallback:idle", "idle", "policy:", "wait"),
    _fallback("fallback:misc", "misc"),
    _fallback("fallback:unregistered", "unregistered"),
)


def _ranked(rungs: tuple[Rung, ...]) -> tuple[tuple[Rung, ...], int]:
    """Give every rung its rank; returns the ladder and ``TOWN_RANK``."""
    rewrite_families: list[str] = []
    for rung in rungs:
        if rung.section == SECTION_REWRITE and rung.family not in rewrite_families:
            rewrite_families.append(rung.family)
    next_rank = len(rewrite_families)
    dungeon: dict[int, int] = {}
    for position, rung in enumerate(rungs):
        if rung.section == SECTION_DECIDE and not rung.shares_town_rank:
            dungeon[position] = next_rank
            next_rank += 1
    town_rank = next_rank
    calls: dict[str, int] = {}
    for rung in rungs:
        calls[rung.producer] = calls.get(rung.producer, 0) + 1
    seen: dict[str, int] = {}
    ranked = []
    for position, rung in enumerate(rungs):
        seen[rung.producer] = seen.get(rung.producer, 0) + 1
        name = (
            rung.producer
            if calls[rung.producer] == 1
            else f"{rung.producer}#{seen[rung.producer]}"
        )
        if rung.section == SECTION_REWRITE:
            rank = rewrite_families.index(rung.family)
        elif position in dungeon:
            rank = dungeon[position]
        elif rung.shares_town_rank:
            rank = town_rank
        else:
            rank = town_rank + 1
        ranked.append(Rung(
            rung.producer, rung.family, rung.section, rung.reasons,
            rung.ordinary, rung.marked, rung.owns_transaction, rung.town, rank,
            name,
        ))
    return tuple(ranked), town_rank


CLAIM_LADDER, TOWN_RANK = _ranked(_RUNGS)
FALLBACK_RANK = TOWN_RANK + 1

_BY_FAMILY: dict[str, tuple[Rung, ...]] = {}
_BY_NAME: dict[str, Rung] = {}
for _rung in CLAIM_LADDER:
    _BY_FAMILY[_rung.family] = (*_BY_FAMILY.get(_rung.family, ()), _rung)
    _BY_NAME[_rung.name] = _rung
del _rung


def rung_named(name: str | None) -> Rung | None:
    """The rung a row or a claim names, if the ladder still has it."""
    return _BY_NAME.get(name) if name else None


def ladder_families() -> frozenset[str]:
    return frozenset(_BY_FAMILY)


def decide_rungs(ladder: tuple[Rung, ...] = CLAIM_LADDER) -> tuple[Rung, ...]:
    """The rungs the order test compares with ``_decide``'s calls."""
    return tuple(rung for rung in ladder if rung.section == SECTION_DECIDE)


def ordinary_rung(family: str) -> Rung | None:
    for rung in _BY_FAMILY.get(family, ()):
        if rung.ordinary:
            return rung
    return None


def rung_of(
    family: object, reason: str | None, *, non_discardable: bool = False
) -> Rung:
    """The rung a decision of this census family and reason came from.

    The one function the live writer and the offline reader both use (rev
    10.1 item 11).  ``family`` may be a ``ClaimOwner`` or its string value.
    """
    name = str(getattr(family, "value", family) or "unregistered")
    rungs = _BY_FAMILY.get(name)
    if not rungs:
        return ordinary_rung("unregistered")
    if non_discardable:
        for rung in rungs:
            if rung.owns_transaction:
                return rung
    normalized = reason or "policy:none"
    best: Rung | None = None
    best_length = -1
    for rung in rungs:
        if rung.owns_transaction:
            continue
        for prefix in rung.reasons:
            if normalized.startswith(prefix) and len(prefix) > best_length:
                best, best_length = rung, len(prefix)
    if best is not None:
        return best
    return ordinary_rung(name) or ordinary_rung("unregistered")


def rung_of_claim(
    family: object, rung_name: str | None, *, non_discardable: bool = False
) -> Rung:
    """A held claim's rung: the one it recorded, else its family's ordinary.

    A claim restored from a checkpoint pickled before the ladder carries no
    rung name; its family's ordinary rung is the honest answer.
    """
    return rung_named(rung_name) or rung_of(
        family, None, non_discardable=non_discardable
    )


def claim_rank(
    family: object, reason: str | None, *, non_discardable: bool = False
) -> int:
    return rung_of(family, reason, non_discardable=non_discardable).rank


def is_s3_rung(rung: Rung) -> bool:
    """Rev 10.1 item 8: an S3 family, or ``departure`` in town."""
    return rung.family in S3_FAMILIES or (
        rung.family == "departure" and rung.section == SECTION_TOWN
    )


def pair_scope(held: Rung, new: Rung) -> str:
    """A pair with an S3 rung on either side is reported on the S3 lines."""
    return SCOPE_S3 if is_s3_rung(held) or is_s3_rung(new) else SCOPE_IN


def never_suspended(goal_kind: str | None, goal_source: str | None) -> bool:
    """Rev 10.1 item 6: a store-operation or transaction Observe claim."""
    return goal_kind == GOAL_OBSERVE and goal_source != FLOOR_CHANGE


def owner_change(
    *,
    held_rank: int,
    held_goal_kind: str | None,
    held_goal_source: str | None,
    held_survival: bool,
    new_rank: int,
    new_survival: bool,
) -> str:
    """Preemption, survival displacement or violation, for a held open
    Reach/Observe claim given way to another owner.

    * Rev 10 item 2 / rev 10.1 item 5: only a strictly higher rank suspends
      the holder (``PREEMPTION``), survival or not -- every push is by a
      strictly higher rank, which is what bounds the stack by the number of
      ranks.
    * Survival that does not rank strictly higher cannot suspend the holder;
      it *replaces* it (``SURVIVAL_DISPLACED``): the holder is released, and
      because survival is exempt (design 3.2, rev 9 item 3) it is not a
      violation.
    * Rev 10.1 item 6: a store-operation or transaction Observe claim is
      never suspended nor exempted; giving it way is a violation.
    * Anything else is a violation (rev 10 item 4).

    ``held_survival`` is part of the signature for the reader's records; a
    held survival claim is suspended or dropped like any other.
    """
    del held_survival
    if never_suspended(held_goal_kind, held_goal_source):
        return VIOLATION
    if new_rank < held_rank:
        return PREEMPTION
    if new_survival:
        return SURVIVAL_DISPLACED
    return VIOLATION


def nests_over(*, top_rank: int, new_rank: int) -> bool:
    """Rule (iii): only a new owner ranked strictly above the top nests."""
    return new_rank < top_rank


def resumable_index(stack, owner, goal, non_discardable: bool = False):
    """Where in the stack a claim of this owner and goal is suspended.

    The topmost match anywhere in the stack, not only the top (a claim can be
    buried under ones a later decision outranks), or ``None``.
    """
    for index in range(len(stack) - 1, -1, -1):
        claim = stack[index]
        if (
            claim.owner == owner
            and claim.goal == goal
            and claim.non_discardable == non_discardable
        ):
            return index
    return None
