"""Reviewed quest-specific relaxations of the shared preparation gate.

Profiles without an entry_requirements contract retain the ordinary checks.
These predicates affect readiness only; in-quest light and retreat stay shared.
"""


def _entry_requirements(profile) -> dict:
    # A profile without quest_id/required_force (a stand-in approved strategy) has no contract.
    if getattr(profile, "quest_id", None) != 1:
        return {}
    return getattr(profile, "required_force", {}).get("entry_requirements", {})


def allows_overweight(profile) -> bool:
    return _entry_requirements(profile).get("allow_overweight", False) is True


def carried_torch_entry_ready(snapshot, profile) -> bool:
    minimum = _entry_requirements(profile).get("carried_torch_min_fuel")
    if getattr(profile, "quest_id", None) == 34:
        minimum = profile.required_force.get("entry_requirements", {}).get(
            "carried_torch_min_fuel_by_class", {}).get(str(snapshot.player.class_id))
    return bool(minimum is not None and any(
        item.is_torch and item.known and item.count > 0 and item.fuel >= minimum
        and not item.is_cursed and not item.is_broken
        for item in snapshot.inventory
    ))


def allows_overweight_travel(policy, snapshot) -> bool:
    from hengbot.policy_constants import QUEST_STATUS_UNTAKEN, QUEST_STATUS_TAKEN
    quest = policy._fixed_quest_head(snapshot)
    return bool(quest is not None and quest.status in {QUEST_STATUS_UNTAKEN, QUEST_STATUS_TAKEN}
                and allows_overweight(policy.approved_quest_strategy(quest.id)))


def entry_damage_ratio(profile, class_id, default) -> float:
    """Apply a reviewed class budget to the existing threat calculation."""
    plan = profile.engagement_plan if profile is not None else {}
    return float(plan.get("max_damage_ratio_by_class", {}).get(
        str(class_id), plan.get("max_damage_ratio", default)))


def entry_melee_check(profile, class_id, telemetry, candidates, controlled):
    """Use the force gate's reference AC for a reviewed mobile-only fight.

    Controlled stationary targets are killed by the profile's throwing route;
    their HP is not a melee kill-time requirement for this class.
    """
    plan = profile.engagement_plan if profile is not None else {}
    output, hp = telemetry["melee_output"], telemetry["toughest_hp"]
    if class_id in plan.get("force_melee_against_mobile_by_class", ()):
        hp = max((monster.max_hp for _, race, monster in candidates
                  if race not in controlled), default=0)
        output = telemetry["strategy_force"]["dps"]["measured"]
    return output, hp
