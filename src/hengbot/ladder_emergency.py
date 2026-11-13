"""The emergency layer of the dungeon ladder (dungeon_ladder.LADDER, layer "emergency").

``HengbotPolicy._decide`` asks this layer where its rows stand: below the committed hunt
(above-emergency), above the summoner shots and every layer below.  The emergency consumables
first (survival may always pre-empt a lower-priority owner), then the quiet recall, the sensed
T1 leave's *Destruction*, the absorbed THREAT powers, the item-destroying breeder's leave,
starvation, the paralyzer prevention and the faster confuser's leave.  The rungs are asked
top-down and the first key returned wins, as in ``_decide``; ``PASS`` hands the decision on
to the layers below.
scripts/dungeon_ladder_lint.py reads the rows here (dungeon_ladder.LAYER_MODULES), so the table
still states this order.

``emergency_hostiles`` are ``_decide``'s, computed once per decision (the summoner shots read
them as well) and passed in unchanged, by name.
"""
from __future__ import annotations

from hengbot import confuser_contact, me_powers, return_yield, sent_away_t1, threat_tiers
from hengbot.dungeon_ladder import PASS


def key(policy, snapshot, *, emergency_hostiles, paralyzers, physical_hostiles, physical_adjacent):
    """The emergency layer's answer, or PASS when none of its rungs acts."""
    emergency = policy._town_producer_entry("_emergency_item", lambda: policy._emergency_item(snapshot, emergency_hostiles))
    if emergency is not None:
        if policy._choke_plan_active(snapshot):
            policy._release_choke_plan("hp-emergency")
        if policy.last_reason.startswith(
            ("emergency:", "unseen-recall:", "guardian:")
        ):
            # Survival may always pre-empt a lower-priority owner.
            policy._escape_state.enter("emergency", policy.last_reason)
        # For the town hold: the hostiles the emergency ladder weighed.
        policy._declare_triggers(emergency_hostiles)
        return emergency
    if policy._escape_state.owner == "emergency":
        # The emergency ladder is exempt from sibling hysteresis: the
        # established post-teleport handoff must happen immediately.
        policy._escape_state.release()
    quiet_recall = return_yield.quiet_recall_key(policy, snapshot)
    if quiet_recall is not None:
        return quiet_recall
    # Owner 2026-11-09 B / 2026-11-10: the sensed T1 leave's *Destruction* before any
    # rung below the emergency consumables (n1-b life-377, threat_tiers).
    sensed_destruction = threat_tiers.sensed_t1_destruction_key(policy, snapshot)
    if sensed_destruction is not None:
        return sensed_destruction
    # Class 16 sends an unbeatable hostile in range away (me_powers THREAT)
    # only once the emergency ladder above has declined: survival first.
    threat_power = me_powers.threat_key(policy, snapshot)
    if threat_power is not None:
        # Owner 2026-11-09 E: a T1 sent away is remembered; its vanishing returns to town.
        sent_away_t1.note(policy, snapshot)
        return threat_power

    item_destroying_breeder_exit = policy._town_producer_entry(
        "_item_destroying_breeder_leave_key",
        lambda: policy._item_destroying_breeder_leave_key(snapshot),
    )
    if item_destroying_breeder_exit is not None:
        return item_destroying_breeder_exit

    mana_survival = policy._town_producer_entry("_mana_food_survival_override_key", lambda: policy._mana_food_survival_override_key(snapshot))
    if mana_survival is not None:
        return mana_survival

    paralyzer_prevention = policy._town_producer_entry("_paralyzer_prevention_key", lambda: policy._paralyzer_prevention_key(
        snapshot, paralyzers, physical_adjacent
    ))
    if paralyzer_prevention is not None:
        return paralyzer_prevention
    # Owner 2026-11-14 「混乱する前に離れるだけ」 (n1-b life-392): a faster confuser whose blow
    # reaches before the next action is left by Teleportation, above the summoner shots.
    confuser_leave = confuser_contact.leave_key(policy, snapshot, physical_hostiles)
    if confuser_leave is not None:
        return confuser_leave
    return PASS
