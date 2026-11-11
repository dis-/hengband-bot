"""The Potion of Heroism when the character has no lasting fear resistance (owner 2026-11-11).

Owner: 「恐怖耐性がないとき、戦闘時必要ならヒーローの薬を使用するようにしたい。持ち歩く数は仮に15服
とする。」  Answer to when it is drunk: 「恐怖になった時と強敵の前」 -- 「恐怖になって殴れなくなった時
に飲む。加えて、恐怖の呪文を持つ強い相手（T2 以上の戦い）と戦い始める時に先に飲む。」

Game (C:/hengband/src): SV_POTION_HEROISM (sv-potion-types.h, 32) quaffs ``heroism(25)``
(object-use/quaff/quaff-effects.cpp:118 -> spells-status.cpp: ``set_fear(0)``, hero 25+1d25 turns,
+10 HP).  ``has_resist_fear`` counts the hero and berserk states (player-status-flags.cpp), so
while the bar shows ``heroism`` no fear lands; the potion is sold by the Temple (store/
articles-on-sale.cpp, the regular stock and the random table), not the Alchemist.

Lasting fear resistance is the ``resist_fear`` ability from the equipment or the character
(``ability_sources`` equipment/permanent: TR_RES_FEAR, the race and class flags and the FEARLESS
mutation, player_flags).  The temporary source (hero, berserk, tim_res_fear, the ultimate
resistance) is not lasting.  With a lasting one nothing is bought and nothing carried is kept.

 * ``carry_target``: the carried stock the town buys and the retention keeps (15, else 0): the
   Temple errand and the purchase rung ``tail:heroism`` are optional (never a departure
   condition) and spend only the gold above the full departure resupply (owner 2026-10-08).
   A potion stored at Home is not taken out: an optional take bound into the Home batch made
   n1-a life-508's Home visit step off an uncomposable take (a follow-up if wanted).
 * ``cures_fear`` / ``afraid_key``: afraid, a blow is the answer and the game refuses it, a potion
   is carried: drink it (combat_answer.adjacent_attack; policy._should_flee's fear clause and
   survival_preemption read ``cures_fear``, so the board reaches that answer instead of the flee).
 * ``fight_filter``: in place of an attack (an attack row of the reasons registry, never a walk,
   a flee or a word-rule row) in a T2-or-worse engagement (``strong``: also one past the
   projection's cost cap) with an awake fear caster (SCARE spell) in it, while not hero: drink
   first; the next attack once the hero state has ended drinks again.

``fear_covered`` is this module's minimal stand-in for the threat implementer's helper of the
same meaning (2026-11-11, worktree threat-heal-credit-1111): unify the two once both land.
"""

from __future__ import annotations

from hengbot import reasons
from hengbot.item_reservation import reserved_item_command
from hengbot.model import SV_POTION_HEROISM, TVAL_POTION

CARRY_TARGET = 15
BASE_COST = 35  # BaseitemDefinitions.jsonc id 257 「ヒーロー」, when the costs are not loaded
POTION = (TVAL_POTION, SV_POTION_HEROISM)
LASTING_SOURCES = frozenset({"equipment", "permanent"})
HERO_BAR_KEYS = frozenset({"heroism", "berserk"})
FEAR_SPELL = "SCARE"

AFRAID_REASON = "heroism:afraid"
FEAR_CASTER_REASON = "heroism:fear-caster"
RETENTION_BRANCH = "heroism-carry"
CATEGORY = "heroism"  # the town need and the purchase rung's category


def lasting_fear_resistance(snapshot) -> bool:
    """Fear resistance that does not run out: equipment or the character (not hero/berserk)."""
    player = snapshot.player
    sources = player.ability_sources.get("resist_fear")
    if sources is not None:
        return bool(sources & LASTING_SOURCES)
    # A flat (pre-per-source) emitter: the ability without a hero state on the bar.
    return "resist_fear" in player.abilities and not hero_active(snapshot)


def hero_active(snapshot) -> bool:
    """The bar shows hero or berserk (or a temporary fear resistance): no fear lands now."""
    player = snapshot.player
    if HERO_BAR_KEYS & set(player.status_bar or ()):
        return True
    return "temporary" in player.ability_sources.get("resist_fear", frozenset())


def is_heroism(item) -> bool:
    return item.tval == TVAL_POTION and item.sval == SV_POTION_HEROISM and getattr(item, "aware", True)


def carried(snapshot) -> int:
    return sum(item.count for item in snapshot.inventory if is_heroism(item))


def carry_target(snapshot) -> int:
    """The carried stock wanted: 15 without a lasting fear resistance, else none."""
    return 0 if lasting_fear_resistance(snapshot) else CARRY_TARGET


def carry_shortage(snapshot) -> int:
    return max(0, carry_target(snapshot) - carried(snapshot))


def fear_covered(snapshot) -> bool:
    """Fear is handled: a lasting resistance, the hero state, or a potion to drink."""
    return lasting_fear_resistance(snapshot) or hero_active(snapshot) or carried(snapshot) > 0


def _potion(policy, snapshot):
    return policy._find_exact_potion(snapshot, SV_POTION_HEROISM)


def _drink_possible(policy, snapshot) -> bool:
    return (not snapshot.in_town and snapshot.store is None and not snapshot.inside_arena
            and not snapshot.player.paralyzed
            and policy._can_fight_in_dungeon(snapshot.floor_key[0])
            and _potion(policy, snapshot) is not None)


def cures_fear(policy, snapshot) -> bool:
    """Afraid, and a carried potion would end it where a blow is allowed."""
    return snapshot.player.afraid and _drink_possible(policy, snapshot)


def _drink(policy, snapshot, reason) -> str | None:
    key = reserved_item_command(policy, snapshot, "quaff", _potion(policy, snapshot))
    if key is not None:
        policy.last_reason = reason
    return key


def afraid_key(policy, snapshot, adjacent) -> str | None:
    """The drink in place of the blow fear refuses (the blow would hurt one of ``adjacent``)."""
    from hengbot import attack_expectation
    if not cures_fear(policy, snapshot) or all(
            attack_expectation.blows_cannot_hurt(policy, snapshot, monster) for monster in adjacent):
        return None
    return _drink(policy, snapshot, AFRAID_REASON)


def _fighting(reason) -> bool:
    """An attack of the registry: not a walk, a flee, a Recall's strike or a word-rule oddity."""
    row = reasons.lookup(reason)
    return (row is not None and row.attack and row.kind is None
            and not row.rule.startswith("word rule"))


def fear_casters(policy, hostiles) -> list:
    return [monster for monster in hostiles
            if not monster.asleep
            and (knowledge := policy._monrace_knowledge.get(monster.race_id)) is not None
            and FEAR_SPELL in knowledge.abilities]


def strong(assessment) -> bool:
    """T2 or worse, or past the projection's cost cap: an engagement too large to grade is no
    weaker than T2 (n1-b life-370: some sixty Black Knights sensed, the assessment skipped)."""
    from hengbot import threat_tiers
    return (assessment.tier in (threat_tiers.T1, threat_tiers.T2)
            or (assessment.tier is None and assessment.skipped == "cost"))


def fight_filter(policy, snapshot, key):
    """The drink in place of an attack on a strong fear caster (owner 「強敵の前」)."""
    from hengbot import threat_tiers
    if (key is None or not hasattr(snapshot, "visible_monsters")
            or threat_tiers.outside_design(snapshot)
            or not _fighting(policy.last_reason)
            or lasting_fear_resistance(snapshot) or hero_active(snapshot)
            or not _drink_possible(policy, snapshot)):
        return key
    hostiles = threat_tiers.engagement(policy, snapshot)
    if not fear_casters(policy, hostiles):
        return key
    if not strong(threat_tiers.tiered(policy, snapshot, hostiles)):
        return key
    drink = _drink(policy, snapshot, FEAR_CASTER_REASON)
    return key if drink is None else drink
