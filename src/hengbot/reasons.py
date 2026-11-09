"""The registry of decision reasons whose attributes other modules read.

A decision's reason is a plain string in ``policy.last_reason``.  Two readers act on what a
reason *is*, not on the one reason they were written for:

* the per-dive escape count (policy_observation): an escape counted at the read
  (``EMERGENCY``), or once its effect is observed, a new position or floor
  (``RELOCATING``); the second of a dive returns to town (owner 2026-10-02 「逃走も緊急脱出に
  数える」, 2026-11-09 「全部の逃げを数える」);
* the breeder window (breeder_stalemate): whether the action attacked (``attack``).

Before this table those attributes were literal sets (policy_constants) and a guess from the
words of the reason (breeder_stalemate ``ATTACK_REASON_WORDS``), and nothing tied a new reason
to them: a new teleport left out of the set silently did not count.  Here every reason of the
escape vocabulary (``ESCAPE_WORDS``) is declared with its kind, the module(s) that produce it
and the owner rule or the reason for the kind; scripts/reason_registry_lint.py reads every
reason the source can send and fails on one of that vocabulary the table does not know
(tests/test_reason_registry.py runs it).  Add a row in the same commit as a new reason.

Kinds (the escape count reads only the first two):

``EMERGENCY``      counted at the read (``policy_constants.EMERGENCY_ESCAPE_REASONS``).
``RELOCATING``     counted once its effect is observed (``RELOCATING_ESCAPE_REASONS``).
``EXCLUDED``       a relocation deliberately not counted; ``rule`` says why (owner answer).
``WALK``           a walking retreat, a wait or a step toward an exit: never counted (owner
                   2026-11-09 「歩いての後退は数えない」).
``NOT_ESCAPE``     the vocabulary without an escape from enemies: town and shop travel, the
                   planned returns, a purchase, a gear change.
``OWNER_QUESTION`` a relocation from enemies that no owner answer covers yet.  Not counted, as
                   before the registry; listed for the owner (the 2026-11-09 registry report).
``None``           an entry that only carries ``attack``.

``attack`` is the breeder window's 「実際に攻撃した手」 (owner 2026-11-08): the decision chose an
attack.  It reproduces, reason for reason, the word guess it replaces (2c8f8d71f5), including
its oddities, which are marked ``word rule`` below and listed in the registry report: this
table changes no decision.

A row's ``pattern`` is a reason, or an ``fnmatch`` pattern for the reasons the source builds
(``f"esp-threat:leave-{...}"``); ``lookup`` takes an exact row first, else the longest
(the most specific) pattern row that matches.
"""
from __future__ import annotations

from fnmatch import fnmatchcase
from typing import NamedTuple

EMERGENCY = "emergency"
RELOCATING = "relocating"
EXCLUDED = "excluded"
WALK = "walk"
NOT_ESCAPE = "not-escape"
OWNER_QUESTION = "owner-question"
KINDS = (EMERGENCY, RELOCATING, EXCLUDED, WALK, NOT_ESCAPE, OWNER_QUESTION, None)
COUNTED = (EMERGENCY, RELOCATING)

# The escape vocabulary: a reason with one of these words must have a row.  Every counted row
# has one of them (tests/test_reason_registry.py), so the vocabulary covers the registry.
ESCAPE_WORDS = ("teleport", "phase", "recall", "stairs", "ascend", "scroll", "flee", "escape",
                "leave", "disengage")


class Reason(NamedTuple):
    pattern: str
    kind: str | None
    attack: bool
    producers: tuple
    rule: str


ROWS: list[Reason] = []


def _rows(kind, producers, rule, *patterns, attack=False) -> None:
    producers = (producers,) if isinstance(producers, str) else tuple(producers)
    ROWS.extend(Reason(pattern, kind, attack, producers, rule) for pattern in patterns)


# ================================================================ counted at the read
# The emergency ladder (policy_combat._emergency_item, policy._decide's emergency rungs) and the
# blind teleport of threat_tiers.blind_teleport_key, which builds ``reason + ":absorbed-power"``
# and ``reason + "-staff"``.
_RULE_EMERGENCY = "the emergency ladder's escapes: counted at the read (EMERGENCY_ESCAPE_REASONS)"
_rows(EMERGENCY, ("policy", "policy_combat", "threat_tiers"), _RULE_EMERGENCY,
      "emergency:teleport", "emergency:teleport:absorbed-power", "emergency:teleport-staff",
      "emergency:phase", "emergency:stairs")
_rows(EMERGENCY, ("policy", "once_quest_recall"), _RULE_EMERGENCY, "emergency:recall")
_rows(EMERGENCY, "policy_combat", _RULE_EMERGENCY, "emergency:seek-upstairs")

# ================================================================ counted once relocated
# User 2026-10-02 13:4x 「逃走も緊急脱出に数える」: the relocating escapes from an unresisted
# confusion/paralysis attacker join the per-dive emergency count once their effect is
# observed (new position or floor); a walking retreat (status-threat:retreat) never counts.
_RULE_STATUS = "user 2026-10-02 「逃走も緊急脱出に数える」 (status-threat relocations)"
_rows(RELOCATING, ("policy", "policy_combat"), _RULE_STATUS, "status-threat:scroll")
_rows(RELOCATING, "policy", _RULE_STATUS, "status-threat:stairs")

# Owner 2026-11-09 (question A of the n1-b deaths life-355/350/346, 「全部の逃げを数える」:
# 「テレポート・フェイズ・階段など、敵から離れるために使った逃げは理由を問わず数え、2回で帰還
# する（歩いての後退は数えない）。」): every relocating escape from enemies joins the count the
# way the status-threat relocations above do.  The list is the deaths-1109-rules report's.
_RULE_ALL = "owner 2026-11-09 A 「全部の逃げを数える」"
# the emergency ladder's variants not counted at the read
_rows(RELOCATING, ("once_quest_recall", "policy"), _RULE_ALL, "emergency:recall-quest-fail")
_rows(RELOCATING, ("policy_combat", "policy_supply"), _RULE_ALL, "emergency:stairs-quest-fail")
_rows(RELOCATING, "policy", _RULE_ALL, "emergency:stairs-down")
# the flee rung (policy._decide_dungeon) and the threat reposition's cornered read
_rows(RELOCATING, "policy", _RULE_ALL, "flee:scroll", "flee:stairs", "flee:stairs-quest-fail",
      "threat:scroll")
# the sensed T1 leave (threat_tiers.sensed_t1_leave_key, SENSED_LEAVE_PREFIX + ...)
_rows(RELOCATING, "threat_tiers", _RULE_ALL,
      "sensed-t1:teleport", "sensed-t1:teleport:absorbed-power", "sensed-t1:teleport-staff",
      "sensed-t1:phase", "sensed-t1:stairs", "sensed-t1:recall")
# the exposed summoner's up stairs (policy).  summoner:stairs is also the reason of
# _immobile_summoner_exit_key's up stairs (policy_combat), which the owner's list leaves out
# (EXCLUDED below): one string, so both count (registry report, question).
_rows(RELOCATING, ("policy", "policy_combat"), _RULE_ALL, "summoner:stairs")
_rows(RELOCATING, "policy", _RULE_ALL, "summoner:stairs-quest-fail")
# the summoner hold's teleport (summoner_wait.HOLD_TELEPORT_REASON)
_rows(RELOCATING, "summoner_wait", _RULE_ALL, "summoner:hold-teleport")
# the answer to the summons (summon_response) and the no-chance Resistance leave (resist_potion)
_rows(RELOCATING, "summon_response", _RULE_ALL, "summons:leave-teleport")
_rows(RELOCATING, ("summon_response", "once_quest_recall"), _RULE_ALL, "summons:recall")
_rows(RELOCATING, "resist_potion", _RULE_ALL, "resist-potion:no-chance-teleport")
# the item-destroying breeders' leave (policy_combat._item_destroying_breeder_leave_key)
_rows(RELOCATING, "policy_combat", _RULE_ALL,
      "breeder-item-damage:stairs", "breeder-item-damage:teleport-level",
      "breeder-item-damage:teleport", "breeder-item-damage:recall")
# the fruitless fight's disengage (policy_navigation) and the breeder breakthrough's leave
_rows(RELOCATING, "policy_navigation", _RULE_ALL, "combat:disengage-stairs", "combat:disengage-recall")
_rows(RELOCATING, "policy_combat", _RULE_ALL, "breeder-breakthrough:ascend", "breeder-breakthrough:recall")

# ================================================================ relocations not counted
_rows(EXCLUDED, "destruction_use",
      "owner 2026-11-04 「破壊の回数だけでは帰還しない」: it removes the enemies rather than "
      "leaving them (destruction_use: emergency:destruction[:<sight trigger>][:absorbed-power])",
      "emergency:destruction*")
_rows(EXCLUDED, ("me_powers", "sent_away_t1"),
      "the absorbed Teleport Other moves the enemy, not the player (owner 2026-11-09 E handles it)",
      "me-power:*:teleport-away")
_rows(EXCLUDED, "policy_combat",
      "a town return already; over_extension's answer 6 keeps it uncounted",
      "esp-threat:leave-*")
_RULE_PLAN = "the quest plan's own teleport: answer 11 「作戦が先」"
_rows(EXCLUDED, "policy_quest", _RULE_PLAN,
      "quest-strategy:opening-teleport", "quest-strategy:q22-opening-teleport",
      "quest-strategy:q2-teleport-reset")
_rows(EXCLUDED, "quest_room_sweep", _RULE_PLAN, "quest-strategy:sweep-teleport")
_rows(EXCLUDED, "quest25_battle", _RULE_PLAN, "quest25:teleport")
_rows(EXCLUDED, "breeder_quest", _RULE_PLAN + " (Q2's breeder breakthrough)", "breeder-breakthrough:teleport")
_rows(NOT_ESCAPE, "policy_quest",
      "the Q2 plan's phases (q2-phase-<race>: a step of the sweep; q2-light-phase-<race>: the Light "
      "scroll read): \"phase\" is the plan's stage, not Phase Door",
      "quest-strategy:q2-phase-*", "quest-strategy:q2-light-phase-*")
_RULE_SUMMONER_EXIT = ("_immobile_summoner_exit_key leaves a floor explored around an immobile "
                       "summoner by the ordinary floor rules (owner 2026-11-02 「通常の階の決まりで離れる」)")
_rows(EXCLUDED, "policy_combat", _RULE_SUMMONER_EXIT,
      "summoner:stairs-down", "summoner:teleport-level", "summoner:recall")
_rows(WALK, "policy_combat", _RULE_SUMMONER_EXIT,
      "summoner:seek-downstairs", "summoner:seek-upstairs", "summoner:wait-recall")
_RULE_STUCK = "stuck / livelock relocations: no enemy prompted them"
_rows(EXCLUDED, ("policy", "retreat_enclosure", "policy_navigation"), _RULE_STUCK,
      "stuck:ascend", "stuck:enclosed-teleport", "stuck:recall-escape", "stuck:teleport-escape",
      "stuck:walled-off-recall", "livelock:ascend", "livelock:recall-escape", "livelock:teleport-explore")
_rows(WALK, ("policy", "policy_navigation"), _RULE_STUCK,
      "stuck:seek-stairs", "livelock:seek-upstairs", "breakout:dig-to-stairs")
_rows(EXCLUDED, "policy_combat", "a reposition to fight the guardian from cover, not a leave",
      "guardian:teleport-to-cover")
_rows(EXCLUDED, "policy_supply", "the starving leave of a locked quest floor: no enemy prompted it",
      "survival:ascend", "survival:stairs-quest-fail")
_rows(EXCLUDED, ("policy", "policy_quest"), "the quest regeneration's floor change (a plan, no enemy)",
      "quest:regen:ascend")

# ================================================================ walks and waits
_RULE_WALK = "owner 2026-11-09 「歩いての後退は数えない」: a walk, a wait or a step toward an exit"
_rows(WALK, "policy", _RULE_WALK, "flee", "flee:wait", "status-threat:retreat", "threat:reposition",
      "no-wait:flee")
_rows(WALK, "threat_tiers", _RULE_WALK, "sensed-t1:walk")
_rows(WALK, ("policy_combat", "summoner_wait"), _RULE_WALK, "summoner:retreat")
_rows(WALK, ("policy", "policy_combat", "policy_navigation", "attack_answer", "blind_strike"), _RULE_WALK,
      "combat:disengage", "combat:disengage-", "combat:disengage-armed", "combat:disengage-clear-path",
      "combat:disengage-cut-through", "combat:disengage-explore", "combat:disengage-hold",
      "combat:disengage-search-upstairs", "combat:disengage-seek-upstairs", "combat:disengage-step",
      "combat:disengage-wait", "combat:disengage-wait-recall", "combat:disengage-*")
_rows(WALK, ("policy", "policy_combat"), _RULE_WALK,
      "emergency:clear-escape-path", "breeder-breakthrough:clear-escape-path",
      "breeder-breakthrough:seek-upstairs", "breeder-breakthrough:wait-recall",
      "breeder-item-damage:seek-stairs")
_rows(WALK, "policy_navigation", _RULE_WALK + " (exploration toward the down stairs)", "seek-downstairs")
# combat:disengage-melee strikes; the word rule reads its "disengage" as no attack.
_rows(WALK, ("attack_answer", "blind_strike"), _RULE_WALK + "; it strikes (word rule: no attack)",
      "combat:disengage-melee")

# ================================================================ the vocabulary without an escape
_RULE_TOWN = "town, shop, home and wilderness travel: no dive escape"
_rows(NOT_ESCAPE, ("policy_town", "policy_shop", "policy_home", "policy", "town_hold", "town_arbiter",
                   "cli", "policy_equipment", "policy_instore", "dungeon_shop", "purchase_rungs",
                   "input_executor"), _RULE_TOWN,
      "town:*", "shop:*", "home:*", "home-disposal:*", "store:*", "bounty:*", "claim:*",
      "outpost-fare:*", "mandatory:*", "tail:*", "supply-ledger:*", "equipment:*",
      "equipment-transaction:*", "suppress-random-teleport:*",
      "random-teleport-suppression-unactionable-current-loadout", "escape:take-off-anti-teleport",
      "posting-contract:*", "failed:recall-destination-unchosen", "recall-destination-unchosen",
      "survival:leave-wrong-store", "survival:mana-leave-wrong-store", "no-wait:leave-store",
      "fixedquest:q2-teleport", "fixedquest:q2-teleport-step-off", "quest25:quest25-druj-anti-teleport",
      "quest-carry:*", "random-teleport", "no-recall")
_rows(NOT_ESCAPE, ("policy", "policy_town", "policy_combat", "dark_recall", "once_quest_recall", "town_hold"),
      "the planned town return (return:*), not an escape from enemies",
      "return:*")
_rows(NOT_ESCAPE, ("policy", "policy_fundraising", "policy_combat", "town_hold"),
      "the fundraising (mining / scavenging) return: no dive", "fundraise:*", "fundraising:recall-stockout")
_rows(NOT_ESCAPE, ("policy", "policy_combat", "blind_strike"),
      "blind with a Recall already read: strike, heal, move or stay until it fires",
      "unseen-recall:blind-stay", "unseen-recall:heal", "unseen-recall:move")
_rows(NOT_ESCAPE, "me_powers", "the absorbed detection when the stairs are needed and unknown",
      "me-power:stairs-needed-and-unknown:*")

# ================================================================ questions for the owner
# Relocations from enemies that no owner answer names (the registry report, 2026-11-09).  They
# are not counted, as before the registry.
_rows(OWNER_QUESTION, "policy_combat",
      "the no-wait rung reads Teleportation / Phase Door under a material threat "
      "(policy_combat, 'Rejecting an idle turn'): a relocation from enemies, not counted",
      "no-wait:escape-scroll")
_rows(OWNER_QUESTION, "policy",
      "the unprofitable unique's disengage (policy._unprofitable_unique_disengage_key) renames the "
      "fruitless fight's combat:disengage-stairs / -recall, which count, to these, which do not",
      "combat:avoid-unprofitable-unique-stairs", "combat:avoid-unprofitable-unique-recall")
_rows(WALK, "policy", _RULE_WALK + " (the unprofitable unique's disengage, renamed)",
      "combat:avoid-unprofitable-unique-seek-upstairs", "combat:avoid-unprofitable-unique-search-upstairs",
      "combat:avoid-unprofitable-unique-wait-recall")
_rows(OWNER_QUESTION, "quest25_battle",
      "Q25 after its Recall is read (owner 2026-11-09 「段をやめ射線外で待つ」): the start stair, "
      "taken while the Recall is active; the Recall read itself is the escape counted. Answer 11 "
      "「作戦が先」 may cover it; not counted",
      "quest25:recall-exit")
_rows(WALK, ("quest25_battle", "quest_room_sweep"), _RULE_WALK + " (Q25 waiting for its Recall)",
      "quest25:recall-exit-walk", "quest25:recall-wait")
# "fire" of the casters' line of fire: the word rule read an attack.  Kept (registry report).
_rows(WALK, "quest25_battle", _RULE_WALK + " (Q25 out of the casters' fire; word rule: attack, kept)",
      "quest25:recall-out-of-fire", attack=True)
_rows(None, "quest25_battle", "word rule: a step / rest out of the casters' fire read an attack (kept)",
      "quest25:step-out-of-fire", "quest25:rest-out-of-fire", attack=True)
_rows(OWNER_QUESTION, ("town_arbiter", "town_hold"),
      "the wilderness's escape scroll / flee / Recall (outside a dive): not counted",
      "wilderness:escape-scroll", "wilderness:flee", "wilderness:recall", "wilderness:wait-recall")

# ================================================================ attacks (breeder window)
_RULE_ATTACK = "owner 2026-11-08 「20回の判定は、実際に攻撃した手だけで数える」: an attack"
_rows(None, ("policy", "policy_combat", "combat_answer", "blind_strike", "arena", "unseen_strike",
             "speed_dose", "policy_quest", "status_cure"), _RULE_ATTACK,
      "melee", "melee:choke", "melee:esp-threat-hunt", "no-wait:attack", "no-wait:melee",
      "arena:blind-strike", "arena:melee", "arena:unseen-strike", "arena:unseen-strike:absorbed-power",
      "emergency:blind-strike", "emergency:cornered-attack", "emergency:cornered-attack:absorbed-power",
      "emergency:unseen-strike", "emergency:unseen-strike:absorbed-power",
      "unseen:strike", "unseen:strike:absorbed-power", "unseen:strike-dark",
      "unseen:strike-dark:absorbed-power", "unseen:strike-return", "unseen:strike-return:absorbed-power",
      "stuck:walled-off-strike", "town:kill-mob", "town:kill-mob-friendly",
      attack=True)
_rows(None, ("policy_combat", "policy", "magic_eater", "me_device_attacks", "me_q1_torch", "breeder_area_attack",
             "policy_quest", "quest25_battle", "summon_response", "policy_supply"), _RULE_ATTACK,
      "ranged:fire", "ranged:fire-offset", "ranged:fire-target", "ranged:aim-wand", "ranged:throw-oil",
      "ranged:throw-torch", "ranged:magic-eater-device", "ranged:breeder-area", "ranged:breeder-area:*",
      "quest-strategy:melee", "quest-strategy:q2-fire", "quest-strategy:q2-melee-corpse-attack",
      "quest-strategy:ranged-fire", "quest-strategy:ranged-fire:magic-eater",
      "quest-strategy:ranged-light-area", "quest-strategy:ranged-light-area:absorbed-power",
      "quest-strategy:throw-never-move-blocker", "quest-strategy:throw-torch", "quest25:shot",
      "summoner:ranged-kill", "summoner:ranged-kill:can-summon", "summoner:ranged-kill:named-caster",
      "supply-fight:aim-wand", "supply-fight:fire-good-ammo", "supply-fight:read-attack-scroll",
      attack=True)
# Escape-vocabulary attacks: their kind is no escape, their action strikes.
_rows(WALK, ("combat_answer", "blind_strike", "policy_quest", "speed_dose"), _RULE_ATTACK + " (cornered)",
      "flee:cornered-attack", "flee:cornered-attack:absorbed-power", attack=True)
_rows(NOT_ESCAPE, ("blind_strike", "policy_combat", "policy_quest", "speed_dose"),
      _RULE_ATTACK + " (blind, a Recall read)",
      "unseen-recall:blind-strike", "unseen-recall:strike", "unseen-recall:strike:absorbed-power",
      attack=True)
# The word rule's oddities, kept so that no decision changes (registry report): no attack is
# sent, but a word of the old list is in the reason ("shot" in oneshot, "melee", "kill", "fire").
_RULE_WORDS = "word rule: no attack is sent, the old word guess read one (kept; registry report)"
_rows(None, "oneshot_breath", _RULE_WORDS, "oneshot-breath:quaff", attack=True)
# combat:disengage-melee strikes and reads no attack ("disengage"); renamed by the unprofitable
# unique's disengage it loses that word and reads one ("melee").  Kept as the word rule read them.
_rows(None, "policy", "word rule: the renamed combat:disengage-melee (kept; registry report)",
      "combat:avoid-unprofitable-unique-melee", attack=True)
_rows(None, ("policy_combat", "policy_fundraising", "mining_loadout"), _RULE_WORDS,
      "melee:restore-weapon", "melee:restore-weapon:*", "melee:rearm-empty-hand", attack=True)
_rows(None, "policy_shop", _RULE_WORDS + " (a carry shortage's category)", "quest-carry:throwing_items*",
      attack=True)
_rows(None, ("policy_quest", "town_terminal"), _RULE_WORDS, "toughest-kill-time", "kill-descent",
      "quest:readiness:toughest-kill-time", "quest:readiness:kill-descent", attack=True)
# The depth gate's refusal names the missing abilities; resist_fire has "fire".
_rows(None, "policy", _RULE_WORDS, "depth-gate:destination-*:missing-*resist_fire*", attack=True)
_rows(None, "policy_town", _RULE_WORDS,
      "fundraising:no-safe-destination:depth-gate:destination-*:missing-*resist_fire*", attack=True)


# ---------------------------------------------------------------- lookups
_EXACT: dict[str, Reason] = {}
_PATTERNS: list[Reason] = []
for _row in ROWS:
    if any(mark in _row.pattern for mark in "*?["):
        _PATTERNS.append(_row)
    else:
        _EXACT.setdefault(_row.pattern, _row)
_PATTERNS.sort(key=lambda row: -len(row.pattern))   # stable: equal lengths keep the table's order


def lookup(reason: str | None) -> Reason | None:
    """The row of ``reason``: its exact row, else the longest pattern row that matches."""
    if not reason:
        return None
    row = _EXACT.get(reason)
    if row is not None:
        return row
    return next((row for row in _PATTERNS if fnmatchcase(reason, row.pattern)), None)


def escape_shaped(reason: str) -> bool:
    """``reason`` has a word of the escape vocabulary, so it needs a row."""
    return any(word in reason for word in ESCAPE_WORDS)


def is_attack(reason: str | None) -> bool:
    """The decision under ``reason`` attacked (the breeder window's ``attack``)."""
    row = lookup(reason)
    return row is not None and row.attack


def reasons_of(kind: str) -> frozenset:
    """The exact reasons of ``kind`` (the counted kinds have no pattern rows)."""
    return frozenset(row.pattern for row in ROWS if row.kind == kind)
