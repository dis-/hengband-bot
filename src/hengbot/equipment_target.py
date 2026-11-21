"""The intended loadout of this visit: the one place that reads and writes the search's target.

Equipment review 2026-11-22 (maintainability-review-equip-1122, stage E2): the loadout search
(``policy_equipment._prepare_equipment_optimization``) stores its result, the target, in
``_equipment_optimization_preparation`` and its input signature in
``_equipment_optimization_signature``; seven modules read the target and force a re-search by
assigning the signature, each by the attribute.  E2 gathers both behind this module without
changing what any of them does:

- readers ask :func:`loadout_target` (and :func:`loadout_target_blockers` /
  :func:`loadout_target_result`, the two reads most callers make of it);
- the search itself keeps its memo through :func:`loadout_search_signature` /
  :func:`record_loadout_search`;
- every other writer stays where it is but calls a named function here --
  :func:`invalidate_loadout_search` (a forced re-search), :func:`replace_loadout_target` (the
  target rewritten, the signature kept), :func:`set_unsearched_loadout_target` (a target not
  produced by a search: the signature forgotten), :func:`clear_loadout_target` (both forgotten).

The names are unique in the package: the town work census resolves calls by bare name.

Stage E3 freezes the target per visit here; ``scripts/equipment_writer_lint.py`` fails a direct
read or write of the two attributes outside this module and pins, per module, the calls of the
writers.
"""

from __future__ import annotations

# The policy's two attributes (rows of state_registry, owner "equipment_target").
TARGET_STATE = "_equipment_optimization_preparation"
SIGNATURE_STATE = "_equipment_optimization_signature"

# The writer functions, by name (scripts/equipment_writer_lint.py pins their callers).
TARGET_WRITERS = frozenset({"init_loadout_target", "record_loadout_search", "replace_loadout_target",
                            "set_unsearched_loadout_target", "clear_loadout_target"})
SEARCH_RESETTERS = frozenset({"invalidate_loadout_search", "forget_loadout_search_in_state"})


def init_loadout_target(policy) -> None:
    """A new policy: no target, no search memo."""
    policy._equipment_optimization_signature = None
    policy._equipment_optimization_preparation = None


# --- readers -------------------------------------------------------------------------------

def loadout_target(policy):
    """The intended loadout of this visit: the search's last preparation, or None."""
    return getattr(policy, TARGET_STATE, None)


def loadout_target_blockers(policy) -> tuple:
    """The target's blockers (``()`` with no target)."""
    return getattr(loadout_target(policy), "blockers", ())


def loadout_target_result(policy):
    """The target's search result (None with no target or no result)."""
    return getattr(loadout_target(policy), "result", None)


def loadout_search_signature(policy):
    """The input signature the stored target was searched with (None: re-search)."""
    return getattr(policy, SIGNATURE_STATE, None)


# --- writers -------------------------------------------------------------------------------

def record_loadout_search(policy, signature, preparation) -> None:
    """The search's own store: the target and the signature it was searched with."""
    policy._equipment_optimization_signature = signature
    policy._equipment_optimization_preparation = preparation


def invalidate_loadout_search(policy) -> None:
    """Force the next decision to search again; the stored target stays readable."""
    policy._equipment_optimization_signature = None


def replace_loadout_target(policy, preparation) -> None:
    """The target rewritten in place (re-planned, re-keyed); the search memo is kept."""
    policy._equipment_optimization_preparation = preparation


def set_unsearched_loadout_target(policy, preparation) -> None:
    """A target the search did not produce for the current signature: store it, re-search next."""
    policy._equipment_optimization_signature = None
    policy._equipment_optimization_preparation = preparation


def clear_loadout_target(policy) -> None:
    """No target and no search memo."""
    policy._equipment_optimization_signature = None
    policy._equipment_optimization_preparation = None


def forget_loadout_search_in_state(state: dict) -> None:
    """A restored state whose calibration is stale: drop the search memo (policy_state)."""
    state[SIGNATURE_STATE] = None
