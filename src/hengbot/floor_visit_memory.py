"""The memories of one floor visit that the next visit of the same floor key must not read.

The floor key is (dungeon, level, quest): every visit of a depth has the same key, and every
Word of Recall lands on a level the game generates anew (spells-world.cpp: the recall's floor
change saves no floor to come back to).  The floor change (policy_observation ``_observe``)
already forgets the remembered map, the loot and most per-floor latches, and the modules with a
``forget_floor_visit`` are called there; the memories below were keyed by the floor key alone
and survived the town between two visits, so a fresh level read the earlier levels' facts.

n1-c life-207 (Magic-Eater Lv46, ガラスの城 60F, 2026-11-14 04:00-04:30, the owner's
「帰還の条件がおかしい気がする」): area_mapping's memory had gathered the *Destruction* circles of
sixteen and more earlier 60F levels, so each new 60F level read as destroyed around the player
from its first board: ``me-power:after-destruction:map-area`` was cast on arrival, the circles'
sure radius read as explored ground (stuck:wander, seek-secret-wall and search right after
arrival, then ``stuck:recall-escape``), and sealed_pocket's ``stuck:destroyed-circle-teleport``
read a Teleportation on arrival (04:26:08: it landed in the next fight and the dive returned).
The same root as summoner_wait's D46 (its own ``forget_floor_visit``).

One table: each row is the attribute, what makes the empty value it starts the visit with
(``None`` for an absent memory), and the owner module whose memory it is.  ``forget`` is
called on every floor change.  Not here: the destruction_use memory (its ``entitled_floor`` is
set again on every board while the means is held, before the floor change is observed), and the
Anaguma latches (the anaguma module's own work, being changed on another branch).
"""
from __future__ import annotations

VISIT_MEMORIES = (
    ("_area_mapping_memory", None, "area_mapping"),
    ("_destroyed_circle_teleport", None, "sealed_pocket"),
    ("_sealed_pocket_memory", None, "sealed_pocket"),
    ("_lit_floor_memory", None, "dark_recall"),
    ("_hazard_entry", None, "damaging_ground"),
    ("_esp_tier_hold", None, "esp_tier_hold"),
    ("_loot_frontier_tried", None, "loot_frontier"),
    ("_loot_unreachable_note", None, "loot_frontier"),
    ("_hunt_progress_floor", None, "policy_combat._hunt_step"),
    ("_summoner_counter_targets", frozenset, "policy_combat"),
    ("_locked_doors", set, "locked_doors"),
    ("_stuck_doors", set, "locked_doors"),
    # Owner 2026-11-15 (maintainability review Q7 「階が変わったら全部消す」): every memory keyed by
    # the floor key alone, so a later level of the same key read it (deep_teleport's goals
    # reached when stuck, n1-b life-397's 60F).
    ("_deep_stuck_reached", None, "deep_teleport"),
    ("_anaguma_retry", None, "anaguma"),
    ("_anaguma_refused", None, "anaguma"),
    ("_hazard_crossing", None, "damaging_ground"),
    ("_hazard_given_up", None, "damaging_ground"),
    ("_me_missile_unlearned_floor", None, "me_ranged_first"),
    ("_blind_strike_memory", None, "blind_strike"),
    ("_short_blind_onset", None, "status_cure"),
    ("_blind_cure_turn", None, "status_cure"),
    ("_confusion_cure_turn", None, "status_cure"),
    ("_confusion_relapse_floor", None, "status_cure"),
    ("_blind_cure_futile_floor", None, "status_cure"),
    ("_blind_attacker_floor", None, "status_cure"),
    ("_quest_sweep_engage_commit", None, "quest_sweep_target"),
    ("_speed_dose_memory", None, "speed_dose"),
    ("_tunnel_attempt_memory", None, "tunnel_feasibility"),
    ("_mining_scroll_used_floor", None, "policy_fundraising"),
    ("_mining_abort_floor", None, "policy_fundraising"),
    ("_fundraising_exit_latch", None, "policy_fundraising"),
    ("_unviable_quest_floor", None, "policy"),
    ("_escape_wait_budget_floor", None, "policy"),
    ("_quest_regen_exhausted_floor", None, "policy"),
    ("_combat_outcome_floor", None, "policy_combat"),
    ("_strong_fight_speed_floor", None, "policy_combat"),
    ("_breeder_engagement_floor", None, "policy_combat"),
    ("_breeder_breakthrough_frontier_floor", None, "policy_combat"),
    ("_unseen_last_hit_floor", None, "policy_identification"),
    ("_unseen_hit_pending_floor", None, "policy_observation"),
    ("_q2_breeder_last_seen_floor", None, "policy_quest"),
    ("_explored_floor_window", None, "explored_floor"),
    ("_destruction_loot_memory", None, "destruction_loot"),
    ("_recall_wait_clock", None, "recall_wait_reach"),
)

# The memories that keep the floor key on purpose, or that the floor change forgets already
# (scripts/cross_rule_lint.py: every policy attribute stored with the floor key is a row of
# VISIT_MEMORIES or here, with the reason).
KEPT = {
    "_breeder_fled_floor": "the walk out of a breeder floor goes on over the floors above it",
    "_breakout_dig_floor": "the digger is put away again once the floor it was taken out on is left",
    "_choke_outcome_floor": "the floor change sets it to the new floor",
    "_breeder_breakthrough_floor": "the floor change forgets it",
    "_fruitless_disengage_floor": "the floor change forgets it",
    "_fixed_quest_speed_floor": "the floor change sets it for a fixed quest's floor",
    "_recent_since_teleport": "the floor change forgets it",
    "_mining_viability_pending_floor": "the floor change forgets it",
    "_unseen_retreat_floor": "the floor change forgets it (_clear_unseen_retreat)",
    "_immobile_summoner_memory": "summoner_wait.forget_floor_visit at the floor change",
    "_sensed_approach_memory": "threat_tiers.forget_floor_visit at the floor change",
    "_enclosure_teleport_read": "retreat_enclosure.forget_floor_visit at the floor change",
    "_breeder_floor_record": "a write cache of the breeder record file, no judgement reads it",
    "_fled_floor_pending": "fled_floor_stairs reads it at the floor change itself",
    "_q2_phase_last_move": "the floor change forgets it",
    "_pending_loot_pickup": "the floor change forgets it",
    "_status_threat_latch": "the floor change forgets it",
    "_blind_cure_escape_carry": "owed on the board right after the cure only, by its deadline turn",
    "_emergency_consumable_issue_watch": "the watch of a posted key, read on the next board",
    "_ranged_target_macro_signature": "the signature of a posted macro, read on the next board",
    "_skill_request_board_messages": "the messages of the board a skill request answered",
    "_look_floor_key": "the look probe's own board",
    "_floor_key": "the floor the policy stands on (the floor change is read from it)",
    # Not the policy's: ``self`` there is another object keeping its own floor.
    "floor_key": "exploration_ledger's own floor, reset by the ledger on a new floor",
    "last_floor": "flight_recorder's own floor (diagnostics)",
    "left_bound": "quest_navigator's binding of the board, read only on the cell and floor bound",
}


def forget(policy) -> None:
    """A new floor visit: none of the earlier visits' memories of the table."""
    for name, empty, _owner in VISIT_MEMORIES:
        setattr(policy, name, None if empty is None else empty())
