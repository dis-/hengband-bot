"""A plain unidentified weapon or armour is identified where it lies, not picked up first.

Owner 2026-11-17 (verbatim 「今のまま取りに行き、床の上で鑑定」): the loot walk still goes to the
pile, but standing on it the bot identifies the item on the floor; the auto-destroy of the pick
rules then removes it there, and only what survives is picked up (by the loot owner, as before).
Until then the bot picked it up, identified it in the pack (``identify:dungeon-equipment``) and
the prf destroyed it there: n1-c life-216, 2026-11-17 15:43:34, 49F, ``seek-loot`` to (6,150),
``pickup`` 'g', ``identify:dungeon-equipment`` 'mAfo', then 「戦闘用つるはし (1d8) (-3,-3) (-2)
{呪われている}を自動破壊します。」 (the 50F+ study: 1,401 of 1,530 such pickups were destroyed on
the floor they were found on).

Game (C:/hengband/src):
 * autopick/autopick-matcher.cpp:227-249: the prf's 「無銘の武器／防具」 matches only an identified
   or sensed item, and a floor item is never sensed, so stepping on it destroys nothing.
 * spell-kind/spells-perception.cpp ident_spell: the identify chooser takes USE_EQUIP | USE_INVEN
   | USE_FLOOR with the tester ``object_is_not_identified``; its result applies the auto-destroy
   to a floor item too (``autopick_alter_item`` with a negative index, lines 140/189).  The staff,
   the rod, the scroll and the Magic-Eater's absorbed power all reach it (cmd-usestaff.cpp,
   cmd-zaprod.cpp, scroll-read-executor.cpp, cmd-magiceat.cpp staff_effect).
 * inventory/floor-item-getter.cpp:746-772: ``-`` takes the floor item at once when the tester
   admits exactly one under the player and carry_query_flag is off (lib/pref/pref-opt.prf
   ``X:carry_query_flag``); with more it opens the floor list, which would need a letter.  So the
   cell must hold the one object (``object_count`` 1, as policy ``_floor_item_identifiable_at``
   asks), and that object must be unidentified (else the tester admits none and ``-`` only rings
   the bell): its name shows no to-hit/to-dam ``(+h,+d)`` nor armour bonus ``[ac,+b]``, which
   describe_flavor prints for every identified weapon and armour, and no inscription ``{}``.

Bounded: a cell identified on and still holding the same unidentified-looking pile is not asked
again on this floor visit (``TRIED``); the loot owner then picks it up as before.
"""

from __future__ import annotations

import re

from hengbot.model import (
    TVAL_BOOTS, TVAL_BOW, TVAL_CLOAK, TVAL_CROWN, TVAL_DIGGING, TVAL_DRAG_ARMOR, TVAL_GLOVES,
    TVAL_HAFTED, TVAL_HARD_ARMOR, TVAL_HELM, TVAL_POLEARM, TVAL_SHIELD, TVAL_SOFT_ARMOR,
    TVAL_SWORD, SV_STAFF_IDENTIFY,
)
from hengbot.policy_constants import READ_KEY

# The reason the executor already binds a floor identify to (input_executor, observed_input).
REASON = "loot:identify-floor-item"
FLOOR_CHOICE = "-"
WEAPON_ARMOUR_TVALS = frozenset({
    TVAL_BOW, TVAL_DIGGING, TVAL_HAFTED, TVAL_POLEARM, TVAL_SWORD,
    TVAL_BOOTS, TVAL_GLOVES, TVAL_HELM, TVAL_CROWN, TVAL_SHIELD, TVAL_CLOAK,
    TVAL_SOFT_ARMOR, TVAL_HARD_ARMOR, TVAL_DRAG_ARMOR,
})
# describe_flavor's marks of an identified weapon or armour: (+h,+d), [ac,+b], [+b].
_KNOWN = re.compile(r"\([+-]\d+,\s?[+-]\d+\)|\[\d+,\s?[+-]\d+\]|\[[+-]\d+\]")
# {floor_key: set of (y, x)} -- the cells identified on this floor visit.
TRIED = "_floor_identify_tried"


def plain_unidentified(snapshot, position) -> bool:
    """The cell's one found item is a weapon or armour that reads unidentified and plain."""
    row = next((row for row in snapshot.found_items or ()
                if (row[0], row[1]) == (position.y, position.x)), None)
    if row is None or row[2] != 1 or len(row) < 4 or row[3] not in WEAPON_ARMOUR_TVALS:
        return False
    names = (getattr(snapshot, "found_item_names", None) or {}).get(position) or ()
    name = names[0] if names else None
    if not isinstance(name, str) or "{" in name or _KNOWN.search(name):
        return False
    ids = (getattr(snapshot, "found_item_ids", None) or {}).get(position) or ()
    identity = ids[0] if ids else None
    return not (isinstance(identity, dict) and ("ego_id" in identity or "artifact_id" in identity))


def _tried(policy, snapshot) -> set:
    memory = getattr(policy, TRIED, None)
    if memory is None or snapshot.floor_key not in memory:
        memory = {snapshot.floor_key: set()}
        setattr(policy, TRIED, memory)
    return memory[snapshot.floor_key]


def _source_key(policy, snapshot) -> str | None:
    """The identify use with the floor choice: the absorbed power first (as the dungeon
    identification does), else the carried staff, rod or scroll."""
    from hengbot.me_staff_sequence import identify_power_available, power_key

    if identify_power_available(policy, snapshot):
        key = power_key(policy, snapshot, SV_STAFF_IDENTIFY)
        if key is not None:
            return key + FLOOR_CHOICE
    source = policy._find_identification_source(snapshot, full=False)
    if source is None:
        return None
    command, item = source
    if command == READ_KEY:
        if not policy._can_read_now(snapshot) or policy._is_dark(snapshot):
            return None
        return policy._read_key(snapshot, item, FLOOR_CHOICE)
    from hengbot.item_reservation import reserved_item_command

    return reserved_item_command(policy, snapshot, command, item, suffix=FLOOR_CHOICE)


def key(policy, snapshot) -> str | None:
    """Identify the pile underfoot on the floor when it is one plain unidentified weapon or
    armour, else None (the pickup goes on as before)."""
    player = snapshot.player
    if (snapshot.in_town or snapshot.dungeon_level <= 0 or player.blind or player.confused
            or player.stunned or policy._physical_adjacent_hostiles(snapshot)):
        return None
    here = snapshot.grid_at(player.position)
    if here is None or here.object_count != 1 or not plain_unidentified(snapshot, here.position):
        return None
    tried = _tried(policy, snapshot)
    cell = (here.position.y, here.position.x)
    if cell in tried:
        return None
    answer = _source_key(policy, snapshot)
    if answer is None:
        return None
    tried.add(cell)
    policy._look_floor_items.clear()
    policy._look_floor_object_counts.clear()
    policy.last_reason = REASON
    return answer
