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
  trip).  The row counts the slot's round trips in the visit (``round_trip``); only the
  ``STOP_ROUND_TRIPS``-th settles (owner 2026-11-22 「1往復で決定するなら止める必要はない」).

The settlement.  ``observe`` (every public decision, ``choose_key``) reads the board into the
trails; the ``STOP_ROUND_TRIPS``-th round trip of a slot marks the visit (``state["settle"]``,
named ``ROUND_TRIP_PREFIX + slot``), and ``settle`` (at the head of ``_choose_key``) closes the visit's
equipment transaction once no session is in flight (policy ``_equipment_transaction_visit_closure``,
reason ``SETTLED_CLOSURE``): no plan is made again this visit, the worn kit stays (the last
decider's answer), the departure reads the closed visit as the failed optional change
(``_closed_visit_failure_preparation``), and a ``FLIPFLOP_SETTLED_EVENT`` row and a stderr line
name the slot.  Nothing stops (supervisor 2026-11-28: n1-c life-224, Lv44, stopped in town by the
spear and the axe taking turns; MAINTAINABILITY 2: a stop is for a broken mechanism, and two
deciders disagreeing leave a loadout that each of them accepted).  The round trip is the observed
one: the third wear has been posted and seen.  Out of town the visit's trail is not
kept (the digger swap's weapon -> digger -> weapon is the mining set's own fight rule); the combat
hands alone are read on every board, across the visits, into a record-only trail
(``observe_hands``, ``equipment-hand-roundtrip:<slot>``: a temporary swap's round trip over the
town's edge is written, never stopped on).
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
# Owner Q7 2026-11-22 「外せない時は名指しで止める」 (stage E3): a worn banned piece (equipment_rules,
# the twilight robe) that cannot come off while the loadout search cannot run (policy_equipment
# ``_banned_gear_stuck_stop``).  A policy final stop (policy_constants POLICY_FINAL_STOP_PREFIXES).
BANNED_STUCK_PREFIX = "town:blocked:banned-gear-stuck:"
FLIPFLOP_EVENT = "equipment-slot-flipflop"
# The name of a slot's second round trip (``state["settle"]``, the settlement's stderr line); until
# supervisor 2026-11-28 the stop ``town:blocked:equipment-slot-flipflop:<slot>``.
ROUND_TRIP_PREFIX = FLIPFLOP_EVENT + ":"
REWEAR_EVENT = "equipment-rewear"
# The combat hands' trail across town visits and the dungeon (``observe_hands``, record only:
# a row of state_registry, owner equipment_visit_journal).
HAND_TRAIL_STATE = "_equipment_hand_trail"
HAND_TRAIL_LENGTH = 6
HAND_ROUNDTRIP_EVENT = "equipment-hand-roundtrip"
# Owner 2026-11-22 (verbatim) 「1往復で決定するなら止める必要はない」: one round trip A, B, A
# that settles is recorded (``stops`` false); the slot's second round trip in the visit (A, B,
# A, B or A, B, A, C, A: it keeps going back and forth) settles the visit (``settle``; owner
# 2026-11-22 「往復が起きたら停止して直す」 stopped there until supervisor 2026-11-28).
STOP_ROUND_TRIPS = 2
# The visit closure's reason (policy ``_equipment_transaction_visit_closure``) and the row kind.
SETTLED_CLOSURE = "slot-flipflop"
FLIPFLOP_SETTLED_EVENT = "equipment-slot-flipflop-settled"
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
            "prepared": None, "settle": None, "searches": 0, "posts": 0, "round_trips": {}}


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


def note_search(policy: Any, snapshot: Any, previous, current, previous_target, target,
                events=()) -> None:
    """A loadout search ran and its result was stored: why (the signature's changed fields, and
    the named event that let the visit decide again: equipment_target.REDECIDE_EVENTS, or
    ``visit-start``)."""
    state = journal(policy)
    state["searches"] = state.get("searches", 0) + 1
    changed, detail = signature_changes(previous, current)
    _journal_row(policy, snapshot, "search", changed=changed, detail=detail,
            events=list(events),
            target_added=sorted(map(str, set(target) - set(previous_target)))[:10],
            target_removed=sorted(map(str, set(previous_target) - set(target)))[:10],
            trigger_reason=getattr(policy, "last_reason", None))


def note_held(policy: Any, snapshot: Any, previous, current) -> None:
    """The signature changed but no named event did: the visit's target was read again (stage
    E3), no search ran.  The changed fields say what would have searched before E3."""
    state = journal(policy)
    state["held"] = state.get("held", 0) + 1
    changed, detail = signature_changes(previous, current)
    _journal_row(policy, snapshot, "held", changed=changed, detail=detail,
                 trigger_reason=getattr(policy, "last_reason", None))


def _worn_by_slot(snapshot: Any) -> dict:
    return {item.slot: item for item in getattr(snapshot, "equipment", ())
            if getattr(item, "slot", None) and getattr(item, "tval", None) not in _AMMUNITION}


def _hand_trail(policy: Any) -> dict:
    state = getattr(policy, HAND_TRAIL_STATE, None)
    if not isinstance(state, dict):
        state = {"trail": {}}
        setattr(policy, HAND_TRAIL_STATE, state)
    return state


def observe_hands(policy: Any, snapshot: Any) -> None:
    """Read the combat hands of every board, in town and out (record only, never a stop).

    Owner 2026-11-22 「決まりは足さず、着け直しを記録。往復が起きたら停止して直す。」 named the
    stop for the town visit; the temporary swaps (the mining set's digger, a quest's, Zul's) run
    across the town's edge, where the visit's trail cannot see them: n1-c life-220 (2026-11-22
    06:04) wore ロング・ソード in town and シャベル on Yeek cave 1F by turns, one change per town
    visit.  Each hand's trail here spans the visits (empty boards collapsed as in the visit's
    trail); a trail that ends A, B, A with any of the three seen out of town, or seen in
    different town visits, writes a ``equipment-hand-roundtrip:<slot>`` row with where each was
    seen and whether the mining set held the hands then.  Nothing stops on it: the dungeon's
    contact re-arm and the next floor's digger are the mining set's own fight rule."""
    # Imported here: policy_constants imports this module, and mining_loadout policy_constants.
    from hengbot import mining_loadout
    state = _hand_trail(policy)
    worn = _worn_by_slot(snapshot)
    in_town = bool(getattr(snapshot, "in_town", False) or getattr(snapshot, "store", None) is not None)
    where = ["town" if in_town else "away", getattr(policy, "_town_visit_epoch", None) if in_town else None,
             getattr(snapshot, "turn", None)]
    for slot in mining_loadout.HANDS:
        item = worn.get(slot)
        if item is None:
            continue
        identity = stable_identity(item)
        trail = state["trail"].setdefault(slot, [])
        if trail and _matches(trail[-1][0], identity):
            continue
        trail.append([identity, where])
        del trail[:-HAND_TRAIL_LENGTH]
        if len(trail) < 3:
            continue
        first, middle, last = trail[-3:]
        if not _matches(first[0], identity) or _matches(middle[0], identity):
            continue
        places = [entry[1] for entry in (first, middle, last)]
        if all(place[0] == "town" for place in places) and len({place[1] for place in places}) == 1:
            continue  # one town visit: the visit's own trail (and its stop) reads it
        _journal_row(policy, snapshot, f"{HAND_ROUNDTRIP_EVENT}:{slot}", slot=slot,
                     trail=[entry[0] for entry in (first, middle, last)], where=places,
                     item=_item(item), lent=mining_loadout.hands_lent(policy, snapshot),
                     fundraising_mode=getattr(policy, "_fundraising_mode", None), stops=False)


def observe(policy: Any, snapshot: Any) -> None:
    """Read this board's worn gear into the visit's trails (every public decision, record only).

    The visit is the epoch the previous board's observation minted (the first board of a visit
    is read from the second on); a board off the town and its stores is not read (its hands
    are: ``observe_hands``)."""
    observe_hands(policy, snapshot)
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
            trips = state.setdefault("round_trips", {})
            trips[slot] = trips.get(slot, 0) + 1
            stops = trips[slot] >= STOP_ROUND_TRIPS
            name = f"{FLIPFLOP_EVENT}:{slot}"
            _journal_row(policy, snapshot, name, slot=slot, trail=trail[-3:],
                    item=_item(worn[slot]), stops=stops, round_trip=trips[slot])
            if stops and state.get("settle") is None:
                state["settle"] = {"name": ROUND_TRIP_PREFIX + slot, "slot": slot, "worn": now}
    state["worn"] = now


def settle(policy: Any, snapshot: Any) -> bool:
    """Close this visit's equipment transaction after a slot's second round trip (module
    docstring); True when it closed it now.  A session in flight finishes first (its takeoffs
    and wears are one plan; an abandoned one restores the gear it took off)."""
    state = getattr(policy, STATE, None)
    if (not isinstance(state, dict) or not state.get("settle") or state.get("settled")
            or state.get("epoch") is None
            or state.get("epoch") != getattr(policy, "_town_visit_epoch", None)
            or getattr(policy, "_equipment_transaction_session", None) is not None):
        return False
    name, slot = state["settle"]["name"], state["settle"]["slot"]
    state["settled"] = True
    policy._equipment_transaction_visit_closure = {
        "epoch": state["epoch"], "reason": SETTLED_CLOSURE, "slot": slot,
        "turn": getattr(snapshot, "turn", None),
    }
    _journal_row(policy, snapshot, FLIPFLOP_SETTLED_EVENT, slot=slot,
                 item=_item(_worn_by_slot(snapshot).get(slot)))
    print(f"<{name}> the slot {slot} made its second round trip in one town visit; the "
          "visit's equipment transaction is closed and the worn kit kept (equipment-visit.jsonl "
          f"{FLIPFLOP_SETTLED_EVENT})", file=sys.stderr)
    return True


def is_stop(reason: str | None) -> bool:
    """The equipment's named final stop: the stuck banned piece (the round trip settles)."""
    return bool(reason) and reason.startswith(BANNED_STUCK_PREFIX)


def stop_message(reason: str) -> str:
    return (f"<{reason}> a worn banned piece (equipment_rules, the twilight robe) in the slot "
            f"{reason[len(BANNED_STUCK_PREFIX):]} cannot be taken off (cursed) while the "
            "loadout search cannot run (no calibration; owner 2026-11-22 Q7 「外せない時は"
            "名指しで止める」); stopping the bot for investigation")
