"""The Potion of Resistance (owner 2026-11-05): when it is drunk, and when it is not.

Owner's option 「危ない敵と戦う時に飲む」: 「見えている敵がこの5属性のブレスか球を持ち、3ターンの予想が
今の HP の半分以上の時に飲みます。効いている間は飲みません。」  Added the same day: 「耐性の薬を飲んでも
勝ち目がないなら飲まずに逃走や破壊を優先する。」  (Buying it: policy_shop's Black Market buy-out.)

The two conditions stand side by side as the option says them: the prediction is the ladder's
material threat over every hostile, not the breath's share of it, so a melee-heavy prediction
with such an enemy in view still counts.

Game (C:/hengband/src): quaff-effects.cpp resistance() adds 21-40 turns of opposition to each of
the five elements.  One layer is (per + 2) / 3 on top of a permanent resistance
(player-status-resist.cpp), and with both no inventory damage in the four of
player-damage.cpp.  A quaff has no blind or confused refusal (quaff-execution.cpp).

「効いている間」 is read from the status bar the player sees (``status_bar``, the keys resist_acid
... of bot-json-output.cpp): nothing is remembered, so a restart loses nothing and a lapse shows
on the next board.  An enemy counts for the elements not yet on the bar: fire already on it does
not drink for a fire breather, and a lapsed element drinks again for the enemy that has it.  An
element the player is immune to counts for nothing (poison has no immunity in the game).

「勝ち目がない」 is the judgement other rules already use: ``_engagement_is_winnable`` (what
_should_flee and me_powers' unbeatable-in-range ask: the turns to clear the hostiles at the
player's best attack, and the operational prediction over those turns against the current HP),
asked of the board as it would be after the drink, with me_powers' ``best_expected``.  The answer
then is what summon_response's leave takes: *Destruction* where destruction_use's gates pass,
else a Scroll of Teleportation; none of those leaves the board to the rungs below.

The rung stands after the survival rungs and the answer to the summons, before every attack
(policy._choose_key; quest_find_exit and quest_room_sweep ask it at the same place in their own
order).  On the shared ladder the flee and status-threat rungs stand below it, so it yields to
them (``ladder_key``).
"""

from __future__ import annotations

from dataclasses import replace
from typing import NamedTuple

from hengbot import destruction_use, me_ranged_first, threat_tiers
from hengbot.item_reservation import reserved_item_command
from hengbot.model import SV_POTION_RESISTANCE, TVAL_POTION
from hengbot.policy_constants import OPPOSITION_ABILITY


QUAFF_REASON = "resist-potion:quaff"
LEAVE_REASON = "resist-potion:no-chance-teleport"


class Element(NamedTuple):
    bar: str             # the status bar's key while the opposition runs
    immunity: str        # player.immunities
    spells: frozenset    # the race's breath and ball


ELEMENTS = tuple(
    Element(f"resist_{name}", name, frozenset({f"BR_{name.upper()}", f"BA_{name.upper()}"}))
    for name in ("acid", "elec", "fire", "cold", "pois")
)


def _held(snapshot):
    return next((item for item in snapshot.inventory
                 if item.tval == TVAL_POTION and item.sval == SV_POTION_RESISTANCE and item.aware),
                None)


def _uncovered(player, abilities) -> bool:
    """The race has a breath or ball of an element neither on the bar nor immune."""
    bar = player.status_bar or ()
    return any(element.spells & abilities and element.bar not in bar
               and element.immunity not in player.immunities for element in ELEMENTS)


def _such_enemy_in_view(policy, snapshot) -> bool:
    """An awake visible hostile the drink would answer; no bar to read is no drink."""
    if snapshot.player.status_bar is None:
        return False
    knowledge = policy._monrace_knowledge
    return any(
        monster.hostile and not monster.asleep and monster.race_id in knowledge
        and _uncovered(snapshot.player, knowledge[monster.race_id].abilities)
        for monster in snapshot.visible_monsters)


def _winnable_after_the_drink(policy, snapshot, hostiles) -> bool:
    player = snapshot.player
    after = replace(snapshot, player=replace(player, abilities=player.abilities | {OPPOSITION_ABILITY}))
    return policy._engagement_is_winnable(
        after, hostiles, damage_against=lambda each: me_ranged_first.best_expected(policy, after, each))


def _leave_key(policy, snapshot) -> str | None:
    used = destruction_use.key(policy, snapshot)
    if used is not None:
        return used
    scroll = policy._escape_scroll(snapshot, teleport_only=True)
    if scroll is None:
        return None
    policy.last_reason = LEAVE_REASON
    return policy._read_key(snapshot, scroll)


def _verdict(policy, snapshot):
    """(the potion, winnable after the drink) when the rule applies to the board, else None."""
    potion = _held(snapshot)
    if potion is None or not _such_enemy_in_view(policy, snapshot):
        return None
    hostiles = policy._physical_hostiles(snapshot)
    if not policy._is_material_threat(snapshot, hostiles):
        return None
    return potion, _winnable_after_the_drink(policy, snapshot, hostiles)


def _drink(policy, snapshot, potion) -> str | None:
    policy.last_reason = QUAFF_REASON
    return reserved_item_command(policy, snapshot, "quaff", potion)


def key(policy, snapshot) -> str | None:
    """The drink, the leave when the drink would not save the fight, else None."""
    verdict = _verdict(policy, snapshot)
    if verdict is None:
        return None
    potion, winnable = verdict
    return _drink(policy, snapshot, potion) if winnable else _leave_key(policy, snapshot)


def drink_key(policy, snapshot) -> str | None:
    """``key``'s drink alone: a plan whose own order goes before the leave asks the leave after it
    (``leave_key``).  Owner 2026-11-07 on Quest 25: 「Q25内部でのテレポートの優先度を下げる。少なくとも
    幽体ティラノサウルスとの単独戦闘から逃げることは避けなければ絶対にクリアできない」."""
    verdict = _verdict(policy, snapshot)
    if verdict is None or not verdict[1]:
        return None
    return _drink(policy, snapshot, verdict[0])


def leave_key(policy, snapshot) -> str | None:
    """``key``'s leave alone (*Destruction* or Teleportation when the drink would not save the
    fight), for a plan that asks it below its own order."""
    verdict = _verdict(policy, snapshot)
    if verdict is None or verdict[1]:
        return None
    return _leave_key(policy, snapshot)


def ladder_key(policy, snapshot, strategic_hostiles, strategic_adjacent, physical_hostiles) -> str | None:
    """``key`` on the shared ladder, whose flee and status-threat rungs come first.

    Threat tiers plan step 6 (owner OQ-9, C-1; 3.4): outside the quest plans the potion is drunk
    only as part of a selected supply fight, a T2 with a selected target whose supply plan
    spends the resistance (or whose plan is past the cost cap, every supply winning); against
    any other enemy the bot leaves: T1, and a T2 with no selected target, read the no-chance
    leave.  A T3 fight is fought without supplies (no drink, no leave).  Where the tiers do not
    act (a plan floor asks ``key``, unchanged by D1) or do not decide, ``key`` as on 11-05."""
    if (policy._unresisted_melee_status_threats(snapshot, physical_hostiles)
            or policy._should_flee(snapshot, strategic_hostiles, strategic_adjacent)):
        return None
    verdict = _verdict(policy, snapshot)
    if verdict is None:
        return None
    hostiles = policy._physical_hostiles(snapshot)
    if not threat_tiers.acts_here(policy, snapshot):
        return key(policy, snapshot)
    tiers = threat_tiers.tiered(policy, snapshot, hostiles)
    if tiers.tier == threat_tiers.T1 or (tiers.tier == threat_tiers.T2 and not tiers.selected):
        if not threat_tiers.leave_decided_here(policy, snapshot):
            return None  # a floor that leaving fails the quest: the quest's rules decide
        return _leave_key(policy, snapshot)
    if tiers.tier == threat_tiers.T2:
        plan = tiers.supply_plan
        if plan is None or plan.resistance > 0:
            return _drink(policy, snapshot, verdict[0])
        return None
    if tiers.tier == threat_tiers.T3:
        return None
    return key(policy, snapshot)
