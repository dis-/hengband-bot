"""Enum values and module paths retired from the policy, readable only from old pickles.

A checkpoint pickled before the equipped C-sheet calibration can carry a
``HomeVisitKind("calibration-restore")`` or ``ClaimOwner("calibration")``.  The
members no longer exist, so unpickling would fail before the checkpoint upgrade
could inspect the state.  ``_missing_`` returns a retired pseudo-member instead:
it compares equal to no live member, is not iterated or counted, and the shared
checkpoint upgrade (``policy_state.normalize_policy_state``) removes every
retired value before a decision reads the state.
"""
from __future__ import annotations

from enum import Enum
import sys
from types import ModuleType

_RETIRED: dict[tuple[type, str], Enum] = {}


def retired_member(cls: type, value: str, name: str) -> Enum:
    """Return the cached retired pseudo-member ``name`` of ``cls``."""
    key = (cls, value)
    member = _RETIRED.get(key)
    if member is None:
        member = str.__new__(cls, value)
        member._name_ = name
        member._value_ = value
        member._sort_order_ = -1
        _RETIRED[key] = member
    return member


def is_retired(value: object) -> bool:
    """True for a pseudo-member created by :func:`retired_member`."""
    return (
        isinstance(value, Enum)
        and value._name_ not in type(value)._member_map_
    )


def retired_module(name: str, **attributes: object) -> None:
    """Keep a deleted module's pickled class paths loadable.

    A checkpoint pickles each object under its class's module path; after
    the module is deleted, unpickling would fail before the checkpoint
    upgrade could inspect the state.  The retired path is registered as a
    module with no file holding the current classes under their old names,
    so ``pickle`` resolves them and the restored objects are current ones.
    """
    if name in sys.modules:
        return
    module = ModuleType(name, "Retired module path, readable only from old pickles.")
    module.__dict__.update(attributes)
    sys.modules[name] = module
