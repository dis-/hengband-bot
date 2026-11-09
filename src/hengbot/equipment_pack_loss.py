"""Equipment a transaction carries that the game takes out of the pack.

A transaction that takes worn gear off to store it at Home carries that gear in
the pack through town.  The game can take a pack item away involuntarily on
the way, and only from the pack (never a worn slot):

* a touch to steal items (monster-eating.cpp ``process_eat_item``): one pack
  slot (``INVEN_PACK_SLOTS``) loses one item with
  「{name}({letter})を{一つ}盗まれた！」 / "{Y|One of y}our {name} ({letter}) was
  stolen!" (monster-eating.cpp:145-147), then the thief teleports away
  (monster-attack-player.cpp:526 「泥棒は笑って逃げた！」);
* element damage to the pack (inventory-damage.cpp ``inven_damage``):
  「{name}({letter})が{全部|何個か|一個}壊れてしまった！」 /
  "{Y|All of y|Some of y|One of y}our {name} ({letter}) {was|were} destroyed!"
  (inventory-damage.cpp:70-72).

Both describe the item with ``OD_OMIT_PREFIX``: the name has no count prefix,
as the board's pack names.  The letter is the pack slot the item had on the
board before the message.

n1-a life-505 2026-11-10 01:37: the transaction took the ロング・ソード off to
deposit it; a ブラックマーケットのエージェント stole it on the way home, the
deposit found nothing (``deposit-missing``), the restoration found the owned
sword nowhere and the bot stopped (``restore-blocked-terminal``).

A lost item is neither restored nor deposited: its transaction ownership is
released and a deposit of it is dropped from the plan, so the rest of the
transaction (the other deposits, the new loadout) completes.  The loss is
recorded (``losses``) for the decision log.
"""
from __future__ import annotations

import re
from typing import Any

from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity

# The recorded losses kept for the decision log.
LOSS_RECORD_LIMIT = 8

_LOSS_PATTERNS = (
    ("stolen", re.compile(r"(?P<name>.+)\((?P<letter>[a-z])\)を(?:一つ)?盗まれた！")),
    ("destroyed", re.compile(
        r"(?P<name>.+)\((?P<letter>[a-z])\)が(?:全部|何個か|一個)?壊れてしまった！")),
    ("stolen", re.compile(
        r"(?:Your|One of your) (?P<name>.+) \((?P<letter>[a-z])\) was stolen!")),
    ("destroyed", re.compile(
        r"(?:Your|All of your|Some of your|One of your) (?P<name>.+) "
        r"\((?P<letter>[a-z])\) (?:was|were) destroyed!")),
)


def loss_lines(messages) -> list[tuple[str, str, str]]:
    """(cause, name, pack letter) of each involuntary pack loss message."""
    found = []
    for message in messages or ():
        text = str(message).strip()
        for cause, pattern in _LOSS_PATTERNS:
            match = pattern.fullmatch(text)
            if match is not None:
                found.append((cause, match["name"], match["letter"]))
                break
    return found


def _transaction_debt(policy: Any) -> bool:
    return bool(policy._equipment_transaction_session is not None
                or policy._equipment_transaction_owned_items)


def observe(policy: Any, snapshot: Any) -> None:
    """Record transaction gear the game took out of the pack on this board.

    Runs once per decision board, before the transaction observes it.  The
    pack view is the previous board's carried equipment; it is kept only
    while a transaction is open or owns taken-off gear.
    """
    if not _transaction_debt(policy):
        policy._equipment_pack_view = None
        policy._equipment_transaction_lost = []
        return
    previous = getattr(policy, "_equipment_pack_view", None)
    if previous:
        losses = loss_lines(getattr(snapshot, "messages", ()))
        if losses:
            carried = {
                equipment_move_identity(item)
                for item in (*snapshot.inventory, *snapshot.equipment)
                if item.is_equipment
            }
            for cause, name, letter in losses:
                entry = previous.get(letter)
                if entry is None or entry[0] != name or entry[1] in carried:
                    continue
                _record_loss(policy, snapshot, cause, name, entry[1], entry[2])
    policy._equipment_pack_view = {
        item.slot: (item.name, equipment_move_identity(item), equipment_identity(item))
        for item in snapshot.inventory
        if item.is_equipment
    }


def _record_loss(policy: Any, snapshot: Any, cause: str, name: str,
                 move_identity: str, identity: str) -> None:
    lost = list(getattr(policy, "_equipment_transaction_lost", None) or [])
    lost.append(move_identity)
    policy._equipment_transaction_lost = lost
    owned = policy._equipment_transaction_owned_items
    released = None
    for candidate in (move_identity, identity):
        if any(owned_identity == candidate for owned_identity, _ in owned):
            # One physical member of the duplicate-preserving owned set.
            policy._release_equipment_transaction_owned_item(candidate)
            released = candidate
            break
    record = {
        "turn": snapshot.turn,
        "cause": cause,
        "name": name,
        "move_identity": move_identity,
        "identity": identity,
        "released_ownership": released is not None,
    }
    losses = list(getattr(policy, "_equipment_transaction_losses", None) or [])
    losses.append(record)
    policy._equipment_transaction_losses = losses[-LOSS_RECORD_LIMIT:]


def skip_lost_deposits(policy: Any, session: Any) -> bool:
    """Drop the current deposits of gear the game took out of the pack.

    Only an unposted current deposit is dropped; the item it would store is
    no longer carried, so storing it is moot and the rest of the plan goes on.
    """
    lost = list(getattr(policy, "_equipment_transaction_lost", None) or [])
    skipped = False
    while lost and session.executable and session.pending_action is None:
        action = session.current_action
        if action is None or action.kind != "deposit":
            break
        identity = next((candidate for candidate in (action.move_identity, action.item_identity)
                         if candidate and candidate in lost), None)
        if identity is None:
            break
        if session.prepared_action is not None:
            policy._discard_unposted_equipment_transaction_command()
        session.drop_current_action()
        lost.remove(identity)
        skipped = True
    policy._equipment_transaction_lost = lost
    return skipped


def losses_report(policy: Any) -> list[dict]:
    return [dict(record) for record in getattr(policy, "_equipment_transaction_losses", None) or ()]
