"""Whether a town owner may take the board: its terminal's admission (ROOT-FIX S1).

Design: plans/DESIGN-town-claim-rootfix-1023.md.  A town rung declares the
last action it intends on a board (``intended_terminal``).  Each terminal kind
splits into a material read (``gather_*``), a pure verdict that returns the
admission *and* its refusal codes from the same branch (``verdict_*``), and
the commit that only the terminal's own call site performs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Admission:
    """ADMIT, or REFUSED with the declared codes that refused the terminal."""

    admitted: bool
    codes: tuple[str, ...] = ()


ADMIT = Admission(True)


def refused(codes) -> Admission:
    return Admission(False, tuple(dict.fromkeys(codes)))


@dataclass(frozen=True)
class QuestEntryMaterial:
    """Frozen inputs of the fixed-quest entry verdict."""

    quest_id: int
    morivant_deposits: bool = False
    q34: bool = False
    readiness_reason: str | None = None
    kill_descent_allowed: bool = True
    equipment_ready: bool = True
    equipment_codes: tuple[str, ...] = ()


def gather_quest_entry(policy: Any, board: Any, quest_id: int, *,
                       commit: bool = False,
                       kill_descent: bool = False) -> QuestEntryMaterial:
    """Read the entry material; ``commit`` only for the entry's own call site."""
    expedition = policy._morivant_full_identify
    if expedition is not None and expedition.temporary_deposits:
        return QuestEntryMaterial(quest_id, morivant_deposits=True)
    kill_ok = (policy._kill_quest_descent_allowed(board)
               if kill_descent else True)
    if policy._opening_q34_active(board) and quest_id == 34:
        sink: list[dict] = []
        ready = policy._evaluate_fixed_quest_readiness(
            board, quest_id, require_target_town=True,
            commit=commit, telemetry_sink=sink)
        return QuestEntryMaterial(
            quest_id, q34=True, kill_descent_allowed=kill_ok,
            readiness_reason=(
                None if ready else sink[0].get("reason", "unready")))
    info = policy._quest_knowledge.get(quest_id)
    quest = board.quests.get(quest_id)
    depth = max(1, info.level if info is not None else quest.level if quest is not None else 1)
    codes: list[str] = []
    if commit:
        # The entry's own call site: the historical call and its commits.
        ready = policy._equipment_departure_ready(board, destination_depth=depth)
    else:
        ready = policy._equipment_departure_ready(
            board, destination_depth=depth, commit=False, codes=codes)
    return QuestEntryMaterial(
        quest_id, kill_descent_allowed=kill_ok,
        equipment_ready=ready, equipment_codes=tuple(codes))


def verdict_quest_entry(material: QuestEntryMaterial) -> Admission:
    """Pure: each refusing branch returns its own codes."""
    if material.morivant_deposits:
        return refused(("morivant-temporary-deposits",))
    if not material.kill_descent_allowed:
        return refused(("kill-descent",))
    if material.q34:
        if material.readiness_reason is None:
            return ADMIT
        return refused((material.readiness_reason,))
    if material.equipment_ready:
        return ADMIT
    return refused(material.equipment_codes)
