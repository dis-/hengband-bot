"""What a quest would like carried in, if the Home has it: ``consumable_plan.optional_carry``.

Owner 2026-11-05 「Q25の必須要件に啓蒙の薬は入れていないが、自宅にある場合は受注前に持ち出して」.  The field
names potions (QUEST_POTION_SVALS) and how many.  It is no requirement and no acceptance condition: it
buys nothing, blocks no departure, and the quest is accepted without it.

 * ``before_acceptance``: asked by the fixed-quest rung once the quest is ready and about to be
   requested.  With one in the known Home catalogue it files the Home errand and the rung stands aside;
   the need ``CATEGORY`` routes the visit there (never blocking), and on the next board with the potion
   carried the rung requests the quest.  One filing per town visit, so a refused, failed or stopped
   withdrawal (``release_stopped``) ends with the quest accepted.
 * ``scan_key``: the Home catalogue is known only once scanned.  With a scan owed
   (``_home_catalogue_scan_owed``, ``~9``, no game turn) the rung asks for it first; the scan's own
   bookkeeping ends the owing whatever comes back.  Not current with none owed, nothing is known to be
   there and the quest is accepted.
 * ``retained``: while that quest is the one being prepared or taken, the carried count stays out of the
   Home deposit, the weight relief and the sales (the one retention authority), so the withdrawal is not
   undone.  ``wanted_kind`` keeps the stored one out of the Home disposal.

The readiness chain reads retention (policy_quest._quest_strategy_for_errand_or_floor), so nothing here
but ``before_acceptance``, which the rung calls after its own readiness, may ask readiness.
"""

from __future__ import annotations

from hengbot.home_errand import HomeErrandRequest
from hengbot.model import TVAL_POTION
from hengbot.policy_constants import PACK_CAPACITY, QUEST_POTION_SVALS
from hengbot.town_visit import town_visit

PURPOSE = "quest-optional-carry"
CATEGORY = "quest-optional-carry-home"
RETENTION_BRANCH = "quest-optional-carry"


def _wanted(profile) -> dict[int, int]:
    """sval -> count of the profile's optional carry."""
    field = {} if profile is None else profile.consumable_plan.get("optional_carry", {})
    return {QUEST_POTION_SVALS[name]: int(count) for name, count in field.items()}


def _prepared(policy, snapshot) -> dict[int, int]:
    return _wanted(policy._carry_procurement_strategy(snapshot, cache_fixed_quest_head=False)
                   or policy._quest_strategy_for_errand_or_floor(snapshot))


def wanted_kind(policy, snapshot, item) -> bool:
    """``item`` is of a kind the quest being prepared would like carried in."""
    return item.tval == TVAL_POTION and item.aware and item.sval in _prepared(policy, snapshot)


def retained(policy, snapshot, item) -> int:
    """How much of this pack stack stays with the player for that quest."""
    if not wanted_kind(policy, snapshot, item):
        return 0
    return min(item.count, _prepared(policy, snapshot)[item.sval])


def _carried(snapshot, sval: int) -> int:
    return sum(item.count for item in snapshot.inventory
               if item.tval == TVAL_POTION and item.aware and item.sval == sval)


def _stored(policy, sval: int):
    """An addressable stack of the kind in the current Home catalogue."""
    if not policy._home_knowledge_current:
        return None
    return next((item for index, item in enumerate(policy._home_knowledge_items)
                 if index < policy._home_knowledge_valid_before
                 and item.tval == TVAL_POTION and item.aware and item.sval == sval
                 and policy._item_signature(item) not in policy._deferred_home_items), None)


def routed(policy) -> bool:
    """The errand is on foot: its need routes the visit to Home."""
    errand = policy._home_errand
    return bool(errand.active and errand.request is not None and errand.request.purpose == PURPOSE)


def release_stopped(policy) -> bool:
    """A stopped Home errand holds the whole bot by name; this one is no condition of anything."""
    errand = policy._home_errand
    if errand.request is None or errand.request.purpose != PURPOSE:
        return False
    errand.release_stopped()
    return True


def _file(policy, snapshot, profile) -> bool:
    if len(snapshot.inventory) >= PACK_CAPACITY or not policy._home_available(snapshot):
        return False
    for sval, count in _wanted(profile).items():
        missing = count - _carried(snapshot, sval)
        stored = _stored(policy, sval) if missing > 0 else None
        if stored is not None:
            return policy._file_home_errand(
                snapshot,
                HomeErrandRequest(policy._item_signature(stored), min(missing, stored.count), "home-catalog", PURPOSE),
                knowledge_current=policy._home_knowledge_current)
    return False


def _missing(policy, snapshot, profile) -> bool:
    return any(count > _carried(snapshot, sval) for sval, count in _wanted(profile).items())


def scan_key(policy, snapshot, quest_id: int) -> str | None:
    """The owed Home catalogue, when this quest would look in it."""
    if (policy._home_knowledge_current or not policy._home_catalogue_scan_owed()
            or not policy._home_available(snapshot)
            or not _missing(policy, snapshot, policy.approved_quest_strategy(quest_id))):
        return None
    return policy._town_producer_entry(
        "home-full-knowledge", lambda: policy._home_full_knowledge_key(snapshot), family="home-scan")


def before_acceptance(policy, snapshot, quest_id: int) -> bool:
    """True while the rung stands aside for the withdrawal."""
    if routed(policy):
        return True
    visit = town_visit(policy)
    if visit.optional_carry_filed or policy._home_errand.active:
        return False
    if _file(policy, snapshot, policy.approved_quest_strategy(quest_id)):
        visit.optional_carry_filed = True
        return True
    return False
