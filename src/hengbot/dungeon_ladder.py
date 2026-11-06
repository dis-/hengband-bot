"""The dungeon decision ladder, in order: one place that says who returns over whom.

``HengbotPolicy._decide`` asks its rungs top-down and the first key returned wins, so a
rung returns over every rung below it.  Nothing but that order of ``return`` stated the
priority, and the owner's rules were lost in it: the summon rules of 2026-11-04 never ran on
plan floors because quest_find_exit and quest_room_sweep return above them (4b04bafa56).

Why a table with a check, not only a list derived from the source: the order itself is
read from the AST (scripts/dungeon_ladder_lint.py), and the lint fails whenever this table
disagrees, so nobody keeps two lists by memory.  What the source cannot say is written here:
each rung's layer, what the layer returns over, where an owner rule stands in each floor
owner, and why a rung stands ahead of a rule.  A reorder is therefore a table diff in the
same commit, for a reviewer to see.

The table decides nothing about the order; the one thing read from it at run time is the
list of rungs survival_preemption refuses.  ``--print`` of the lint lists the rows.

Rows: ``entry`` goes through ``_town_producer_entry`` (named by its rung name), ``direct`` is
called without it (so no gate of the entry applies), ``inline`` is a reason set in
``_decide`` itself followed by a return.  A rung may have several rows.
"""
from __future__ import annotations

from typing import NamedTuple


class Rung(NamedTuple):
    name: str
    kind: str
    preempted: bool = False  # survival_preemption refuses it while a hostile attacks
    exempt: str = ""  # why it is not, for a rung the completeness check asks about


class Layer(NamedTuple):
    name: str
    returns_over: str
    rungs: tuple[Rung, ...]


def _rungs(kind, names, exempt):
    return tuple(Rung(name, kind, False, exempt) for name in names)


def E(*names, exempt=""):
    return _rungs("entry", names, exempt)


def D(*names, exempt=""):
    return _rungs("direct", names, exempt)


def I(*names, exempt=""):  # noqa: E743 (the row's kind, as E and D)
    return _rungs("inline", names, exempt)


def P(*names):
    """Through the entry, and refused by survival_preemption while a hostile attacks."""
    return tuple(Rung(name, "entry", True) for name in names)


# Why a rung above the combat rungs may take a board on which a hostile attacks.
ANSWERS_DANGER = "answers danger itself"
FIGHTS = "attacks, or arms for the fight in contact"
NO_ATTACKER = "its own test declines with a hostile about or a hit just taken"
QUEST_FLOOR = "a quest floor: survival_preemption.preempts never refuses there"
TOWN_ONLY = "town only: survival_preemption.preempts never refuses there"
WALK_OUT = "the approved walk-out past breeders (survival_preemption's docstring)"
# No rule says so: named for the owner's question (D21 asked of these, not answered).
NOT_DECIDED = "walks or shoots while attacked: not refused, and no rule decided it"


LADDER = (
    Layer("global-map", "everything: the global map is a distinct command space", (
        *E("_wilderness_survival_key"),
    )),
    Layer("plan-above-survival", "the emergency ladder and everything below; each answers "
          "survival and the summons inside itself (FLOOR_PLANS)", (
        *E("quest_find_exit.key", "quest_room_sweep.key"),
    )),
    Layer("above-emergency", "the emergency ladder and everything below", (
        *E("_esp_threat_hunt_key"),
    )),
    Layer("emergency", "the summons rules, floor avoidance, combat and all below", (
        *E("_emergency_item", exempt=ANSWERS_DANGER),
        *D("return_yield.quiet_recall_key", exempt=NO_ATTACKER),
        *D("me_powers.threat_key", exempt=ANSWERS_DANGER),
        *E("_item_destroying_breeder_leave_key", "_mana_food_survival_override_key",
           "_paralyzer_prevention_key", exempt=ANSWERS_DANGER),
    )),
    # Owner 2026-11-06 「命に関わる時の後へ回す」: below the emergency ladder.
    Layer("summoner-shots", "the summons rules, floor avoidance, combat and all below", (
        *E("_summoner_ranged_kill_key", exempt=FIGHTS),
    )),
    Layer("floor-avoidance", "light, the approved quest floor, combat and all below", (
        *D("summon_response.key", "destruction_use.sight_trigger_key", "resist_potion.ladder_key",
           exempt=ANSWERS_DANGER),
        *D("immobile_ranged_kill.key", exempt=NOT_DECIDED),
        *E("_immobile_summoner_key", exempt=NOT_DECIDED),
        *D("immobile_threat_memory.step_out_key", exempt=NOT_DECIDED),
        *E("_unseen_retreat_intercept_key", exempt=FIGHTS),
        *E("_unseen_retreat_key", exempt=ANSWERS_DANGER),
        *E("_detected_threat_preparation_key", exempt=NO_ATTACKER),
        *P("_return_to_town_key#1"),
    )),
    Layer("light", "the approved quest floor, combat and all below", (
        *E("_darkness_recovery_key", exempt=ANSWERS_DANGER),
        *D("me_powers.power_key:DARK", exempt=NO_ATTACKER),
        *P("_dark_locomotion_key"),
    )),
    Layer("opening", "the approved quest floor, combat and all below", (
        *P("_opening_q34_town_key", "_dig_to_known_downstairs_key"),
        *E("_breakout_restore_weapon_key#1", exempt=FIGHTS),
    )),
    Layer("plan-approved-quest", "every layer below, unconditionally on an approved quest "
          "floor: navigator.decide's return ends the ladder there", (
        *E("_survival_gate_key#1", exempt=ANSWERS_DANGER),
        *I("refill-light", "quest:blocked:enter", exempt=QUEST_FLOOR),
        *P("_chest_processing_key#1"),
        *D("once_quest_recall.tick_rest_before_navigator", exempt=QUEST_FLOOR),
        *E("navigator.decide", exempt=QUEST_FLOOR),
    )),
    Layer("pre-combat", "the flee, melee and ranged rungs and all below", (
        *E("_mining_loadout_rollback_key", exempt=FIGHTS),
        *D("speed_dose.key", exempt=QUEST_FLOOR),
        *E("_wilderness_survival_key", exempt=ANSWERS_DANGER),
        *E("_town_kill_mob_key", exempt=TOWN_ONLY),
        *I("confused:wait", exempt=NO_ATTACKER),
        *E("_breeder_breakthrough_key", exempt=WALK_OUT),
        *E("_choke_engagement_key", "_ranged_attack_key#1", exempt=FIGHTS),
        *E("_fruitless_disengage_key", "_mining_unbeatable_unique_abort_key",
           "_unprofitable_unique_disengage_key", exempt=NOT_DECIDED),
        *E("_fundraising_combat_equipment_key", exempt=FIGHTS),
        *P("_finish_mining_floor"),
        *E("_breeder_breakthrough_escape_key", exempt=WALK_OUT),
        *E("_melee_swarm_combat_key", exempt=FIGHTS),
    )),
    Layer("combat", "safe-now maintenance, objectives, rest, descent and idle", (
        *E("_escape_by_stairs"),
        *I("status-threat:stairs"),
        *D("destruction_use.key"),
        *I("status-threat:scroll"),
        *E("_flee_step#1"),
        *I("status-threat:retreat"),
        *D("destruction_use.key"),
        *I("status-threat:scroll", "status-threat:wait"),
        *E("_escape_by_stairs"),
        *I("flee:stairs-quest-fail|flee:stairs"),
        *E("_blocking_escape_melee_key"),
        *I("combat:disengage-clear-path"),
        *D("town_last_stand.key", "me_ranged_first.outpaced_afraid_key"),
        *E("_flee_step#2"),
        *I("flee"),
        *D("destruction_use.key"),
        *I("flee:scroll"),
        *D("combat_answer.adjacent_attack"),
        *I("flee:wait", "summoner:stairs-quest-fail|summoner:stairs", "summoner:retreat"),
        *E("_fundraising_combat_equipment_key"),
        *D("combat_answer.adjacent_attack", "disenchant_avoid.retreat_key"),
        *E("_ranged_attack_key#2"),
        *I("return:None"),
        *D("hold_key"),
        *E("_flee_step#3"),
        *I("threat:reposition"),
        *D("destruction_use.key"),
        *I("threat:scroll", "threat:wait"),
        *E("_hunt_step#1"),
        *I("hunt:quest-target"),
    )),
    Layer("safe-now", "objectives, rest, descent and idle", (
        *E("_survival_gate_key#2", "_mana_food_loot_key"),
        *D("me_powers.power_key:FLOOR", "area_mapping.after_destruction_key",
           "area_mapping.picked_up_scroll_key", "quest_target_search.detection_key",
           "magic_eater.absorb_key"),
        *E("junk_destroy_now.destroy_now_key", "consumable_policy.use_now_key"),
    )),
    Layer("objectives", "rest, descent and idle; town and dungeon rungs interleaved", (
        *P("_kill_quest_floor_recovery_key"),
        *D("hunt_target.route_key"),
        *E("_home_disposal_processing_key", "_town_cancel_unsafe_recall_key"),
        *I("town:wait-recall-step-off", "town:wait-recall", "town:eat-before-travel",
           "town:seek-shelter", "town:recover"),
        *E("_town_restore_weapon_key"),
        *P("_fixed_quest_key#1"),
        *E("_town_space_deposit_key"),
        *P("_victory_loot_key", "_conquest_loot_key", "_fixed_quest_key#2"),
        *E("_stat_restore_quaff_key", "_experience_potion_quaff_key", "_stat_gain_quaff_key",
           "_town_order_step4_key#2"),
        *D("_dungeon_equipment_identify_key"),
        *P("_fundraising_key#1"),
        *E("_pack_pressure_identify_key", "_full_pack_destroy_key"),
        *P("_chest_processing_key#2", "_normal_loot_key#1"),
        *E("_navigation_livelock_key"),
        *P("_return_to_town_key#2"),
        *E("_worthless_junk_destroy_key"),
        *P("_return_to_town_key#3"),
        *E("_home_catalogue_work_key"),
        *I("equipment-transaction:acquire-home-catalog"),
        *E("_shopping_approach_key#1", "_town_equipped_identification_key"),
        *D("_town_item_processing_key"),
        *E("_town_device_processing_key", "_heavy_curse_inscription_key",
           "_town_remove_curse_key", "_town_enchant_launcher_key",
           "_town_random_teleport_suppression_key", "_equipment_transaction_town_key#2"),
        *P("_normal_loot_key#2"),
        *I("restore-lantern", "wield-light", "refill-light", "refill-light"),
        *E("_town_special_key", "_home_full_knowledge_key"),
        *I("shop:approach"),
        *E("_shopping_approach_key#2", "_town_destroy_key", "_town_overflow_destroy_key",
           "_town_special_key"),
        *I("home:atomic-withdraw-pending-hold"),
        *P("_fundraising_key#2"),
        *E("_released_restock_store_key", "_recall_restock_key"),
    )),
    Layer("rest", "descent and idle", (
        *E("_esp_threat_rest_key"),
        *D("me_powers.power_key:REST"),
        *I("rest"),
    )),
    Layer("descent", "idle", (
        *I("descend"),
        *E("direct-descent"),
        *I("return:None"),
        *D("_avoid_engagement_key"),
        *P("_descent_step"),
        *E("_hunt_step#2"),
        *I("clear-descent"),
        *E("_entrance_travel_key"),
    )),
    Layer("idle", "the rest of this layer, in order", (
        *I("eat"),
        *E("_hunt_step#3"),
        *I("hunt"),
        *D("_stuck_escape_key", "sealed_pocket.after_destruction_key"),
        *E("oscillating-probe"),
        *I("probe", "search"),
        *P("_explore_step#1"),
        *I("breakout:seek-frontier"),
        *D("town_end_key", "_stuck_escape_key"),
        *I("search"),
        *P("_immobile_breeder_giveup_key", "_explore_step#2"),
        *I("explore"),
        *E("_immobile_summoner_exit_key", "frontier-probe"),
        *I("probe", "search"),
        *D("quest_target_search.loop_key", "me_powers.power_key:SECRET_SEARCH"),
        *I("search", "seek-secret-wall"),
        *E("_start_kill_quest_regeneration"),
        *I("stuck:ascend", "stuck:seek-stairs"),
        *E("idle-fallback"),
    )),
)

# After the ladder has answered, _choose_key passes its key through these, in order; each may
# put another in its place, so a rung's return is not always what is posted.
# Ahead of the whole ladder, in ``_choose_key`` before ``_decide`` is asked, so above the
# survival and summons rules; each with its reason.
BEFORE_DECIDE = (
    ("arena.fight_key",
     "floor.inside_arena only.  The survival rungs' scrolls, potions and carried devices are "
     "refused there (cmd_limit_arena), summons do not exist there (check_mspell_arena), there "
     "is no way off the floor before the end, and a character beaten there does not die "
     "(decide_arena_death): the owner heals by absorbed powers and fights, so survival is its "
     "own first rung.  Every other floor passes by untouched."),
)

AFTER_DECIDE = (
    "_flee_sustain_key", "_strong_fight_speed_filter", "me_powers.fight_key",
    "_periodic_game_save_key", "_periodic_character_dump_key", "periodic_magic_eater_powers_key",
    "_break_positional_oscillation", "_break_livelock", "_bound_escape_wait",
    "_forbid_wait_on_town_entrance", "_suppress_pending_stair_command",
)

# What a rung of a floor plan is, in the rule check below.
SURVIVAL = "survival"  # answers danger to the player's life
SUMMONS = "summons"  # the owner's summon rules
FIRST = "first"  # stands ahead of the summons; says why at the plan
OWN = "own"  # the plan's own order and whatever else must come after both


class Branch(NamedTuple):
    """One key-returning branch of a plan's ``key``, its ``or`` operands in order."""
    board: str
    rungs: tuple[tuple[str, str], ...]
    enemy: bool = True  # False: no enemy to survive on this board, by the branch's own test


class FloorPlan(NamedTuple):
    rung: str
    module: str
    branches: tuple[Branch, ...]


# A plan rung returns above the emergency ladder, so the owner's rules must be asked inside it.
FLOOR_PLANS = (
    FloorPlan("quest_find_exit.key", "quest_find_exit", (
        # Leaving is the plan's end: "the quest is done and the danger behind".
        Branch("the exit is beside the player", (("_step_on_exit", FIRST),)),
        Branch("on a cell the casters reach", (
            ("_below_line_recall", SURVIVAL), ("_heal", SURVIVAL),
            ("summon_response.key", SUMMONS), ("resist_potion.key", OWN),
            # A walk to a choke under way goes on before the exit walk (owner 2026-11-06).
            ("_choke_walk_under_way", OWN), ("_advance", OWN))),
        Branch("no enemy for the line", (
            ("summon_response.key", SUMMONS), ("resist_potion.key", OWN), ("_rest", OWN),
            ("_to_choke", OWN),
            ("_wait_after_fight", OWN), ("_advance", OWN)), enemy=False),
        Branch("an enemy for the line", (
            ("_below_line_recall", SURVIVAL), ("_engaged_survival", SURVIVAL),
            ("summon_response.key", SUMMONS), ("resist_potion.key", OWN), ("_fight", OWN),
            ("_choke_walk_under_way", OWN), ("_advance", OWN))),
    )),
    FloorPlan("quest_room_sweep.key", "quest_room_sweep", (
        Branch("no enemy", (
            # The plan's potion when due; the light may show the summons their caster.
            ("quest_room_light.floor_potion_key", FIRST), ("_unseen_light", FIRST),
            ("summon_response.key", SUMMONS), ("resist_potion.key", OWN), ("_restore", OWN),
            ("_out_of_line", OWN),
            ("quest_find_exit._rest", OWN), ("_ambush_key", OWN), ("_advance", OWN)), enemy=False),
        Branch("an enemy", (
            ("quest_find_exit._cure", SURVIVAL), ("_leave_by_exit", SURVIVAL),
            ("_give_up", SURVIVAL), ("_below_line", SURVIVAL), ("quest_find_exit._heal", SURVIVAL),
            ("quest_find_exit._speed", SURVIVAL), ("quest_room_light.floor_potion_key", FIRST),
            ("_unseen_light", FIRST), ("summon_response.key", SUMMONS),
            ("resist_potion.key", OWN), ("_light_key", OWN), ("_fight", OWN))),
    )),
)


class OwnerRule(NamedTuple):
    """A rule that must run before a plan's own order, and where it stands.

    ``rung`` is the rule on the shared ladder.  Each rung of ``ahead`` returns over it there,
    with the reason.  Each plan of FLOOR_PLANS asks the rule inside itself; a plan rung of the
    ladder not in FLOOR_PLANS must stand below ``rung`` (``below_rule``).
    """
    name: str
    said: str
    rung: str
    role: str
    ahead: dict[str, str]
    below_rule: tuple[str, ...]


_ABOVE_EMERGENCY = {
    "_wilderness_survival_key": "the global map's own survival rung",
    "quest_find_exit.key": "a plan answers survival inside itself (FLOOR_PLANS)",
    "quest_room_sweep.key": "a plan answers survival inside itself (FLOOR_PLANS)",
    "_esp_threat_hunt_key": "a committed hunt drinks by its own estimate (owner 2026-09-22); "
                            "whether it stays here is the review's open question",
}

OWNER_RULES = (
    OwnerRule(
        "survival", "生存処理を優先しなければキャラクタは死亡する。当然の結果。 (2026-10-30)",
        "_emergency_item", SURVIVAL, _ABOVE_EMERGENCY, ("navigator.decide",)),
    OwnerRule(
        "summons", "召喚した本人を先に撃つ・見えない召喚が2回で離れる・同じ階で3回で帰還 (2026-11-04)",
        "summon_response.key", SUMMONS, {
            **_ABOVE_EMERGENCY,
            "_emergency_item": "survival first (summon_response's docstring)",
            "return_yield.quiet_recall_key": "the owner's emergency recall when nothing awake is in view",
            "me_powers.threat_key": "sends away what cannot be beaten: survival",
            "_item_destroying_breeder_leave_key": "leaves a breeder that destroys the kit: survival",
            "_mana_food_survival_override_key": "starvation: survival",
            "_paralyzer_prevention_key": "the blow that ends the game: survival",
            "_summoner_ranged_kill_key": "shoots the summoner itself, after survival "
                                         "(owner 2026-11-06 「命に関わる時の後へ回す」); "
                                         "a summons rule due on the board skips it",
        }, ("navigator.decide",)),
)


# From the emergency ladder to the combat rungs: every rung here is refused while a hostile
# attacks, or says why not.  The survival rule of D21, as a check instead of a hand list.
SURVIVAL_CHECKED_LAYERS = (
    "emergency", "summoner-shots", "floor-avoidance", "light", "opening", "plan-approved-quest", "pre-combat",
)


def preempted_names() -> frozenset[str]:
    """survival_preemption.PREEMPTED_RUNGS: the rungs its gate refuses."""
    return frozenset(rung.name for rung in rows() if rung.preempted)


def rows() -> tuple[Rung, ...]:
    """Every rung of the ladder in order."""
    return tuple(rung for layer in LADDER for rung in layer.rungs)


def returns_over(rung_name: str) -> tuple[Rung, ...]:
    """What the first row of ``rung_name`` returns over: every row below it."""
    ladder = rows()
    first = next(index for index, rung in enumerate(ladder) if rung.name == rung_name)
    return ladder[first + 1:]
