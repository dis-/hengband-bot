"""No search command on Angband 99F and 100F: door detection there instead.

Owner 2026-11-23 (verbatim): 「99F 100Fはサーチ禁止。必要なら感知すること。」  n1-b life-416
(Magic-Eater Lv50, Angband 99F, small floor 22x198) sent the search key ``s`` on 1,202 of its last
3,000 decisions: the corridor dead-end rung of ladder_idle searched each cell of an unlit corridor
before stepping on (reason ``search``), every few cells.

The search ('s', src/io/input-key-processor.cpp -> do_cmd_search) spends a player turn to look for
hidden doors beside the player.  On these two floors it is never sent:

- ``banned``: the one predicate (Angband, dungeon level 99 or 100, quest floors included).
- ``detect_key``: where a search for a secret door would have been sent, a door detection instead
  when a wall a door can be in lies within its reach and no door detection of this floor visit has
  covered it yet (quest_target_search ``door_means_key``: the absorbed Detect Doors / Detection
  powers through me_powers ``SECRET_SEARCH``, then a carried Rod of Door/Stair Location or of
  Detection, a Staff of Detect Doors/Stairs, a Scroll of Door/Stair Location).  detect_doors
  discloses every hidden door in its range (src/spell-kind/spells-detection.cpp detect_feat_flag
  -> disclose_grid), so a covered area needs no second look.  None: the caller goes on to its
  next step (explore elsewhere, the stairs, the existing Recall rules), never to the search.
- ``wait_key``: a sender that used the search as one turn spent in place (a hold) sends the wait
  key there instead.

scripts/search_ban_lint.py fails on a function that names the search key (``SEARCH_KEY``,
``CHEST_SEARCH_KEY``, a literal ``"s"`` return) without asking this module, so a new sender
cannot bypass the rule.
"""

from __future__ import annotations

from hengbot.model import DUNGEON_ANGBAND
from hengbot.policy_constants import SEARCH_KEY, WAIT_KEY

# Owner 2026-11-23 「99F 100Fはサーチ禁止」.
BANNED_DEPTHS = frozenset({99, 100})
DETECT_REASON = "search-ban:detect-doors"


def banned(snapshot) -> bool:
    """The search command is not sent here: an Angband floor at 99F or 100F."""
    return (not snapshot.in_town and snapshot.floor_key[0] == DUNGEON_ANGBAND
            and snapshot.dungeon_level in BANNED_DEPTHS)


def wait_key(snapshot) -> str:
    """One turn spent in place: the search key, the wait key where the search is banned."""
    return WAIT_KEY if banned(snapshot) else SEARCH_KEY


def detect_key(policy, snapshot) -> str | None:
    """On a banned floor, the door detection that stands in for a secret door search here, or
    None (nothing within reach is left undetected, or no means is held or usable)."""
    if not banned(snapshot):
        return None
    from hengbot import quest_target_search  # import cycle (ladder_idle -> quest_target_search)

    key = quest_target_search.door_detection_key(policy, snapshot)
    if key is not None and policy.last_reason == quest_target_search.DOOR_MEANS_REASON:
        policy.last_reason = DETECT_REASON
    return key
