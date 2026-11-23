"""The wait of deep_teleport's Recall: the reachable items before *Destruction* when nothing is in view.

Owner 2026-11-23, asked whether the 50F+ Recall read in the teleport's place (deep_teleport
``RECALL_REASON``, ``deep-teleport:recall``) picks the items up while no awake hostile is seen,
verbatim choice: 「帰還を読んでから待つ間に拾う — 先に帰還を読み、発動までの間に、見える起きた敵が
いなければ拾う（11-18 の帰還待ちの拾いと同じ）。」  Asked then whether that pickup goes before the
*Destruction* on (and the approach to) the T1s known only by telepathy or detection: 「見える敵が
いなければ拾いを先に」 (with an awake hostile in view *Destruction* stays first; this overrides
the 2026-11-21 「帰還待ちでは破壊を優先」, recall_wait_teleport ``big_hit_key``, for this wait
only); and whether a sleeping hostile in view stops it: 「眠っていても止める」 (the 2026-11-18 rule
as it is).

n1-b life-416 (Magic-Eater Lv50, Angband 95F, 2026-11-23 14:48-18:09): in 16 such waits the
character cast the absorbed *Destruction* on a sensed T1 on the board after the Recall (most with
no hostile in view: ``emergency:destruction:absorbed-power``, ``sensed-t1:approach-destruction``)
and deleted the items it stood 1-13 cells from (14:52:58 two at 4 and 6, 15:06:36 one at 10,
16:48:20 one at 13), then waited with nothing left in reach.

``key`` (asked at the top of destruction_use ``key`` and ``loot_then_use``, the one entry of every
use of *Destruction* and of the walks that wait on one -- destruction_loot's clean place and
fetch, threat_tiers' approach and remembered approach): while the Recall read under
``RECALL_REASON`` on this floor counts down (``note_read``, ``MEMORY``), with no hostile in view,
awake or asleep, the calm recall wait's pickup (policy ``_recall_wait_collect_key``: the 11-18
gate -- no hostile in view, the HP not low, a zero prediction -- the loot owner's gates, and the
reach of the rest of the countdown, recall_wait_reach) answers in place of the use or the walk:
the unseen big hit's *Destruction* (recall_wait_teleport), the emergency ladder's, the sensed
T1's and its approach.  The rungs that answer before a use (a heal, a cure, a leave by the stairs
or a walk) keep their place: the owner's words order the pickup and *Destruction* only.  The 即死
board (deep_teleport ``fire_p95`` reaching the HP: an unseen attacker's observed loss) is left as
it is.  The read itself is never delayed: this applies from the countdown on.  A Recall read by
any other rule is not this wait.
"""

from __future__ import annotations

# (floor_key, game turn) of the Recall deep_teleport read in the teleport's place, or None.
MEMORY = "_deep_recall_loot_read"
# The pickup is being computed: a use or walk asked from inside it answers as before.
_busy = False


def note_read(policy, snapshot) -> None:
    """deep_teleport read Recall under its ``RECALL_REASON`` on this board."""
    setattr(policy, MEMORY, (tuple(snapshot.floor_key), snapshot.turn))


def applies(policy, snapshot) -> bool:
    """The Recall read under deep_teleport's ``RECALL_REASON`` on this floor counts down."""
    memory = getattr(policy, MEMORY, None)
    return (memory is not None and not snapshot.in_town and snapshot.player.recalling
            and memory[0] == tuple(snapshot.floor_key) and memory[1] <= snapshot.turn)


def key(policy, snapshot) -> str | None:
    """The calm recall wait's pickup in place of a use of *Destruction* or a walk waiting on one in
    this wait, else None."""
    global _busy
    from hengbot import deep_teleport  # import cycle

    if _busy or not applies(policy, snapshot):
        return None
    # 「眠っていても止める」: any hostile in view, awake or asleep.
    if any(monster.hostile for monster in snapshot.visible_monsters):
        return None
    _busy = True
    try:
        if deep_teleport.fire_p95(policy, snapshot) >= snapshot.player.hp:
            return None
        return policy._recall_wait_collect_key(snapshot)
    finally:
        _busy = False
