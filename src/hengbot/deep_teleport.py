"""50F+: the player's own teleport only on 即死 by the monsters with a line of fire.

Owner 2026-11-14 (verbatim): 「50F以降のテレポートの条件を厳しくする。深い階層のテレポートには
即死抽選があるためである。射線の通っている敵の合計予測被害95%が現在HPを上回るとき=即死のとき
のみ。当てはまらない時は破壊または近寄って破壊を試みる。」

``allows``: on a dungeon floor of depth ``DEPTH`` or deeper where the tiers act
(threat_tiers.acts_here: not on an approved quest plan's floor, whose own order stands, nor in
town, a store, the arena or the wilderness), the self-teleport -- Teleportation and Phase Door
scrolls, the Staff of Teleportation, the absorbed Teleportation; anything that moves the player
to a random cell (spells-teleport.cpp teleport_player) -- is allowed only when the summed
one-turn p95 of the monsters that have a line of fire to the player (line_of_fire, the game's
projectable at range 18) reaches the current HP.  It is the 即死 test's sum (instant_death: the
next action's operational p95 of the engagement, each monster at its adjusted speed, ``>=``
the HP as there) with every monster without a line of fire left out.  Not covered (owner's
reading of 2026-11-14): Teleport Away (it moves the monster), Teleport Level, Word of Recall,
stairs.

``substitute``: where a rung would read or cast that teleport and ``allows`` refuses it, the
answer is *Destruction* -- destruction_use's ``key`` with the concerned monsters as the hostiles
it leaves (its sure radius 13, cmd-usestaff.cpp:282 and scroll-read-executor.cpp:342 13 +
randint0(5); its gates: a clear head, a reliable means with a charge, a floor the game destroys,
no guardian or hurt quest target in its worst radius) -- else the walk toward the nearest
concerned monster until it is within the sure radius (threat_tiers.approach_key for monsters
known by detection alone; the same walk for one in view).  The concerned monsters are the awake
hostiles of the engagement that hurt from contact (``threat_prediction(contact=True)``, as the
tiers judge a far monster), but the floor's guardian and the active quest's target, which
*Destruction* spares.  Every rung that reads a relocation scroll passes ``_read_key`` or
``_issue_emergency_consumable`` (or composes the read beside ``_anti_teleport_takeoff_key``), and
the staff and absorbed casts pass ``threat_escape.blind_teleport_key`` or
``teleport_follower.device_teleport_key``: the substitute is asked there.

``KEEPS_TELEPORT``: with no concerned monster, or none *Destruction* can be used on now and no
walk toward one (confused, the means spent or unreliable, the guardian in the circle, a failed
use's fallback, no known way), the teleport is read as before.  Owner 2026-11-14 「50F以降で
破壊手段なしの探索は許可しない。」: without the means the floor is already being left
(destruction_use.gap_here), so this branch is the means held but not usable on this board.
"""

from __future__ import annotations

from hengbot import line_of_fire
from hengbot.item_reservation import decision_memo
from hengbot.model import SV_SCROLL_PHASE_DOOR, SV_SCROLL_TELEPORT, TVAL_SCROLL, game_distance

DEPTH = 50  # the owner's 「50F以降」
SCROLL_SVALS = frozenset({SV_SCROLL_TELEPORT, SV_SCROLL_PHASE_DOOR})
DESTRUCTION_SUFFIX = ":deep-teleport"


def applies(policy, snapshot) -> bool:
    from hengbot import destruction_use, threat_tiers  # noqa: F401 -- import cycle

    return snapshot.dungeon_level >= DEPTH and threat_tiers.acts_here(policy, snapshot)


def fire_p95(policy, snapshot) -> int:
    """The next action's p95 of the engagement's monsters with a line of fire."""
    from hengbot import destruction_use, threat_tiers  # noqa: F401 -- import cycle

    from hengbot.threat_projection import _with_adjusted_speed

    def compute():
        hostiles = [_with_adjusted_speed(monster)
                    for monster in threat_tiers.engagement(policy, snapshot)]
        if not hostiles:
            return 0
        rows = policy.threat_prediction(snapshot, hostiles, 1).get("monsters", ())
        return sum(row.get("operational_contribution", 0)
                   for monster, row in zip(hostiles, rows)
                   if line_of_fire.in_fire(policy, snapshot, monster))
    return decision_memo(policy, "deep_teleport.fire_p95", snapshot, None, compute)


def allows(policy, snapshot) -> bool:
    """The self-teleport may be read or cast on this board."""
    if not applies(policy, snapshot):
        return True
    return fire_p95(policy, snapshot) >= snapshot.player.hp


def concerned(policy, snapshot) -> list:
    """The awake engagement hostiles that hurt from contact, but those *Destruction* spares."""
    from hengbot import destruction_use, threat_tiers  # noqa: F401 -- import cycle

    spared = {destruction_use._guardian_race(policy, snapshot),
              destruction_use._target_race(policy, snapshot)}
    awake = [monster for monster in threat_tiers.engagement(policy, snapshot)
             if not monster.asleep and monster.race_id not in spared]
    if not awake:
        return []
    rows = policy.threat_prediction(snapshot, awake, 1, contact=True).get("monsters", ())
    return [monster for monster, row in zip(awake, rows)
            if row.get("operational_contribution", 0) > 0]


def is_self_teleport_scroll(item) -> bool:
    return item is not None and item.tval == TVAL_SCROLL and item.sval in SCROLL_SVALS


def _walk_key(policy, snapshot, targets) -> str | None:
    """A step toward the nearest grid within the sure radius of a target, under the approach's
    gates (threat_tiers._approach_targets but its in-view refusal)."""
    from hengbot import destruction_use, threat_tiers  # noqa: F401 -- import cycle

    if (not destruction_use.holds_means(policy, snapshot)
            or not destruction_use._clear_headed(snapshot.player)
            or not destruction_use._floor_destroyed(policy, snapshot)):
        return None
    here = snapshot.player.position
    radius = destruction_use.GUARANTEED_RADIUS
    if any(game_distance(here, monster.position) <= radius for monster in targets):
        return None  # in reach: only the use answers, and the gates refused it
    step = policy._nearest_goal_step(snapshot, lambda grid: any(
        game_distance(grid.position, monster.position) <= radius for monster in targets))
    if step is None:
        return None
    policy.last_reason = threat_tiers.APPROACH_REASON
    return policy._step_toward(snapshot, step)


def KEEPS_TELEPORT(policy, snapshot) -> None:  # noqa: N802 -- the named branch of the docstring
    """No *Destruction* and no walk toward it on this board: the teleport is read as before."""
    return None


def substitute(policy, snapshot) -> str | None:
    """The key in place of a self-teleport ``allows`` refuses here, else None (read it)."""
    from hengbot import destruction_use, threat_tiers  # noqa: F401 -- import cycle

    if allows(policy, snapshot):
        return None
    targets = concerned(policy, snapshot)
    if not targets:
        return KEEPS_TELEPORT(policy, snapshot)
    if destruction_use.usable(policy, snapshot, leaving=targets):
        used = destruction_use.key(policy, snapshot, leaving=targets, suffix=DESTRUCTION_SUFFIX)
        if used is not None:
            return used
    approach = threat_tiers.approach_key(policy, snapshot, targets)
    if approach is not None:
        return approach
    walk = _walk_key(policy, snapshot, targets)
    if walk is not None:
        return walk
    return KEEPS_TELEPORT(policy, snapshot)


def scroll_substitute(policy, snapshot, item) -> str | None:
    """``substitute`` for a read of ``item`` (only Teleportation and Phase Door)."""
    return substitute(policy, snapshot) if is_self_teleport_scroll(item) else None
