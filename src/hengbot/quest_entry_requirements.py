"""Reviewed quest-specific relaxations of the shared preparation gate.

Profiles without an entry_requirements contract retain the ordinary checks.
These predicates affect readiness only; in-quest light and retreat stay shared.
"""


def allows_overweight(profile) -> bool:
    requirements = profile.required_force.get("entry_requirements", {}) if profile and profile.quest_id == 1 else {}
    return requirements.get("allow_overweight", False) is True


def carried_torch_entry_ready(snapshot, profile) -> bool:
    requirements = profile.required_force.get("entry_requirements", {}) if profile and profile.quest_id == 1 else {}
    minimum = requirements.get("carried_torch_min_fuel")
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
