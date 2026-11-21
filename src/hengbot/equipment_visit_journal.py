"""The town visit's equipment journal: every loadout search, every wear and take-off, and the
named stop on a slot's round trip (equipment review 2026-11-22, stage E0).

Owner 2026-11-22 「街の保守性大丈夫？破綻してない？」 -> 「点検から始めて」; the review
(maintainability-review-equip-1122) found no single "loadout this visit aims at": the loadout
search re-runs whenever its signature changes, twenty-odd places wear and take off gear outside
it, and the past defects (the twilight robe, the weapon hand, the chaos item put in Home, the
launcher A->B->A) were pairs of deciders disagreeing inside one visit.  Owner 2026-11-22 on E0:
「決まりは足さず、着け直しを記録。往復が起きたら停止して直す。」  So this module adds no rule
about which gear to wear; it records, and it stops on the one shape the owner named.

What it records (one small rotation-bounded jsonl beside the decision log,
``equipment-visit.jsonl``, and the visit's rows in memory for the stop capture,
``flight_recorder.policy_state``):

- ``search``: a loadout search that ran (``policy_equipment`` stored a fresh result), with the
  signature fields that changed since the stored one (``SIGNATURE_FIELDS``; ``no-previous``
  when a force-reset or the first search left none) and the target's added/removed item ids;
- ``prepared`` / ``post``: a wear or take-off composed by the single exit
  (``_equipment_wield`` / ``_equipment_takeoff``) and then confirmed posted, with its slot,
  item, goal and the writer (the module:function that called the exit);
- ``equipment-rewear``: a slot now holds an item that was taken off earlier in this town visit
  (any slot), read from the observed boards;
- ``equipment-slot-flipflop:<slot>``: the slot's worn items in this visit, consecutive repeats
  and empty boards collapsed, end A, B, A (A != B).  An empty slot between does not count
  (the calibration strip takes everything off and puts the same gear back: A, -, A is no round
  trip).

The stop.  ``observe`` (every public decision, ``choose_key``) reads the board into the trails;
``held_stop`` (at the head of ``_choose_key``) returns ``STOP_PREFIX + slot`` while the round
trip's worn state stands in the same visit, when ``FLIPFLOP_STOPS`` is on; the
decision then sends nothing under that reason (a policy final stop, ``policy_constants
POLICY_FINAL_STOP_PREFIXES``) and the incident capture carries this journal.  The round trip is
the observed one: the third wear has been posted and seen.  Out of town nothing is tracked (the
digger swap's weapon -> digger -> weapon is the mining cycle's own).
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from hengbot.flight_recorder import jsonable, rotate_log
from hengbot.item_identity import stable_identity
from hengbot.model import TVAL_ARROW, TVAL_BOLT, TVAL_SHOT

STATE = "_equipment_visit_journal"
PATH = "_equipment_journal_path"
FILE_NAME = "equipment-visit.jsonl"
ROTATE_BYTES = 16 * 1024 ** 2
GENERATIONS = 3
VISIT_ROWS = 160          # rows of the visit kept in memory for the stop capture (the newest)
STOP_PREFIX = "town:blocked:equipment-slot-flipflop:"
FLIPFLOP_EVENT = "equipment-slot-flipflop"
REWEAR_EVENT = "equipment-rewear"
# Owner 2026-11-22 「往復が起きたら停止して直す」: the round trip is a named stop.  False turns it
# back into a record only (the event row stays).
FLIPFLOP_STOPS = True
_AMMUNITION = frozenset({TVAL_SHOT, TVAL_ARROW, TVAL_BOLT})
# policy_equipment's search signature: its leading positional fields, then tagged pairs.
SIGNATURE_FIELDS = ("owned-catalog", "identification-exempt", "home-scan-complete", "worn",
                    "obtainable-ammunition")
# The functions that are the exit itself (the writer is the first frame outside them).
_EXIT_FUNCTIONS = frozenset({"_equipment_wield", "_equipment_takeoff", "_wield_weapon_key",
                             "note_prepared"})


def _matches(left: tuple | None, right: tuple | None) -> bool:
    """``equipment_mutation.same_item`` on two identities (knowledge-gated parts may be None)."""
    if left is None or right is None:
        return left is None and right is None
    return (left[0] == right[0] and left[1] == right[1]
            and (left[2] is None or right[2] is None or left[2] == right[2])
            and (left[3] is None or right[3] is None or left[3] == right[3]))


def _new(epoch) -> dict:
    return {"epoch": epoch, "worn": None, "trail": {}, "taken_off": [], "rows": [],
            "prepared": None, "stop": None, "searches": 0, "posts": 0}


def journal(policy: Any) -> dict:
    """This visit's journal (a new one when the town visit changed)."""
    state = getattr(policy, STATE, None)
    epoch = getattr(policy, "_town_visit_epoch", None)
    if not isinstance(state, dict) or (epoch is not None and state.get("epoch") != epoch):
        state = _new(epoch)
        setattr(policy, STATE, state)
    return state


def _journal_write(policy: Any, row: dict) -> None:
    path = getattr(policy, PATH, None)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        rotate_log(path, ROTATE_BYTES, GENERATIONS)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError as exc:
        print(f"equipment-visit-journal write failed: {type(exc).__name__}: {exc}",
              file=sys.stderr)


def _journal_row(policy: Any, snapshot: Any, kind: str, **fields) -> dict:
    """One row: written to the file, and kept in memory (the newest VISIT_ROWS) for the capture.
    Out of town the rows join the last visit's journal; their ``epoch`` is None."""
    state = journal(policy)
    row = jsonable({
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "kind": kind,
        "epoch": getattr(policy, "_town_visit_epoch", None),
        "decision": getattr(policy, "_decision_sequence", None),
        "turn": getattr(snapshot, "turn", None),
        "in_town": bool(getattr(snapshot, "in_town", False)) if snapshot is not None else None,
        **fields,
    })
    rows = state["rows"]
    rows.append(row)
    del rows[:-VISIT_ROWS]
    _journal_write(policy, row)
    return row


def _writer() -> str:
    frame = sys._getframe(1)
    while frame is not None and frame.f_code.co_name in _EXIT_FUNCTIONS | {"_writer"}:
        frame = frame.f_back
    if frame is None:
        return "unknown"
    module = frame.f_globals.get("__name__", "?").rsplit(".", 1)[-1]
    return f"{module}:{frame.f_code.co_name}:{frame.f_lineno}"


def _item(item: Any) -> dict | None:
    if item is None or isinstance(item, str):
        return None
    return {"name": getattr(item, "name", None), "identity": stable_identity(item)}


def note_prepared(policy: Any, snapshot: Any, kind: str, slot: str | None, item: Any,
                  goal: str, key: str) -> None:
    """The single exit composed ``key`` (a wear or a take-off); posted or not is told later."""
    occupant = next((worn for worn in getattr(snapshot, "equipment", ())
                     if getattr(worn, "slot", None) == slot), None)
    journal(policy)["prepared"] = jsonable({
        "key": key, "command": kind, "slot": slot, "goal": goal, "writer": _writer(),
        "item": _item(item if kind == "wield" else occupant),
        "replaces": _item(occupant) if kind == "wield" else None,
        "turn": getattr(snapshot, "turn", None),
        "in_town": bool(getattr(snapshot, "in_town", False)),
    })


def note_posted(policy: Any, key: str) -> None:
    """The executor confirmed ``key`` posted: the prepared wear/take-off is a post row."""
    state = journal(policy)
    prepared = state.get("prepared")
    state["prepared"] = None
    if not isinstance(prepared, dict) or prepared.get("key") != key:
        return
    state["posts"] = state.get("posts", 0) + 1
    _journal_row(policy, None, "post", **prepared)   # the prepared board's turn and town


def _signature_parts(signature) -> dict:
    if not isinstance(signature, tuple):
        return {}
    parts = {name: value for name, value in zip(SIGNATURE_FIELDS, signature)}
    for extra in signature[len(SIGNATURE_FIELDS):]:
        if isinstance(extra, tuple) and extra and isinstance(extra[0], str):
            parts[extra[0]] = extra[1:]
    return parts


def signature_changes(previous, current) -> tuple[list[str], dict]:
    """The signature fields that differ, and the catalogue/worn detail of the change."""
    if previous is None:
        return ["no-previous"], {}
    before, after = _signature_parts(previous), _signature_parts(current)
    changed = [name for name in dict.fromkeys((*before, *after)) if before.get(name) != after.get(name)]
    detail = {}
    if "owned-catalog" in changed:
        old = {entry[0] for entry in before.get("owned-catalog", ()) if entry}
        new = {entry[0] for entry in after.get("owned-catalog", ()) if entry}
        detail["catalog_added"] = sorted(map(str, new - old))[:8]
        detail["catalog_removed"] = sorted(map(str, old - new))[:8]
    if "worn" in changed:
        old, new = set(before.get("worn", ())), set(after.get("worn", ()))
        detail["worn_added"] = sorted(new - old, key=repr)[:8]
        detail["worn_removed"] = sorted(old - new, key=repr)[:8]
    return changed, detail


def note_search(policy: Any, snapshot: Any, previous, current, previous_target, target) -> None:
    """A loadout search ran and its result was stored: why (the signature's changed fields)."""
    state = journal(policy)
    state["searches"] = state.get("searches", 0) + 1
    changed, detail = signature_changes(previous, current)
    _journal_row(policy, snapshot, "search", changed=changed, detail=detail,
            target_added=sorted(map(str, set(target) - set(previous_target)))[:10],
            target_removed=sorted(map(str, set(previous_target) - set(target)))[:10],
            trigger_reason=getattr(policy, "last_reason", None))


def _worn_by_slot(snapshot: Any) -> dict:
    return {item.slot: item for item in getattr(snapshot, "equipment", ())
            if getattr(item, "slot", None) and getattr(item, "tval", None) not in _AMMUNITION}


def observe(policy: Any, snapshot: Any) -> None:
    """Read this board's worn gear into the visit's trails (every public decision, record only).

    The visit is the epoch the previous board's observation minted (the first board of a visit
    is read from the second on); a board off the town and its stores is not read."""
    if (getattr(policy, "_town_visit_epoch", None) is None
            or not (getattr(snapshot, "in_town", False) or getattr(snapshot, "store", None) is not None)):
        return
    state = journal(policy)
    worn = _worn_by_slot(snapshot)
    now = {slot: stable_identity(item) for slot, item in worn.items()}
    before = state.get("worn")
    if before is None:
        state["worn"] = now
        for slot, identity in now.items():
            state["trail"].setdefault(slot, [identity])
        return
    for slot in sorted(set(before) | set(now)):
        old, new = before.get(slot), now.get(slot)
        if _matches(old, new):
            continue
        if old is not None and not any(_matches(old, gone) for gone in state["taken_off"]):
            state["taken_off"].append(old)
        if new is None:
            continue
        if any(_matches(new, gone) for gone in state["taken_off"]):
            _journal_row(policy, snapshot, REWEAR_EVENT, slot=slot, item=_item(worn[slot]))
        trail = state["trail"].setdefault(slot, [])
        if not trail or not _matches(trail[-1], new):
            trail.append(new)
        if len(trail) >= 3 and _matches(trail[-3], new) and not _matches(trail[-2], new):
            name = f"{FLIPFLOP_EVENT}:{slot}"
            _journal_row(policy, snapshot, name, slot=slot, trail=trail[-3:],
                    item=_item(worn[slot]), stops=FLIPFLOP_STOPS)
            if FLIPFLOP_STOPS and state.get("stop") is None:
                state["stop"] = {"reason": STOP_PREFIX + slot, "worn": now}
    state["worn"] = now


def held_stop(policy: Any, snapshot: Any) -> str | None:
    """The round trip's named stop while its worn state stands in the same visit, else None."""
    state = getattr(policy, STATE, None)
    if (not isinstance(state, dict) or state.get("epoch") is None
            or state.get("epoch") != getattr(policy, "_town_visit_epoch", None)):
        return None
    now = {slot: stable_identity(item) for slot, item in _worn_by_slot(snapshot).items()}
    stop = state.get("stop")
    if not stop:
        return None
    held = stop.get("worn") or {}
    if set(held) == set(now) and all(_matches(held[slot], now[slot]) for slot in now):
        return stop["reason"]
    return None


def is_stop(reason: str | None) -> bool:
    return bool(reason) and reason.startswith(STOP_PREFIX)


def stop_message(reason: str) -> str:
    return (f"<{reason}> the slot {reason[len(STOP_PREFIX):]} was worn A, B, A in one town visit "
            "(owner 2026-11-22 「往復が起きたら停止して直す」); the visit's searches and wears "
            "are in equipment-visit.jsonl and the capture's _equipment_visit_journal; "
            "stopping the bot for investigation")
