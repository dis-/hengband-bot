"""While Word of Recall counts down: the self-teleport only on 即死 or with a T1 in the line of fire.

Owner 2026-11-15 (n1-a life-525, a Lv40 warrior on ガラスの城 49F, 21:05): after the Recall was
read the character read ten Teleportation scrolls in about twelve decisions, the last ones at
full HP on T3 boards (the threat-tier memory held the earlier group T1's leave), and the last
one landed beside the sleeping 『スマウグ』, a storm and 『ウリエル』.  The owner's answer,
verbatim: 「即死か射線の通る T1 だけ・残り少なければ即死だけ」.

``withheld``: on a floor where the tiers act (threat_tiers.acts_here: not in town, a store, the
arena, the wilderness or an approved quest plan's floor, whose own order stands) while the
player's Recall counts down (``player.recalling``), the self-teleport -- Teleportation and
Phase Door scrolls, the Staff of Teleportation, the absorbed Teleportation, the set
deep_teleport governs -- is offered only

* on the 即死 board (threat_tiers.instant_death of the engagement, design 3.1), or
* when the engagement's monsters with a line of fire are T1 by
  themselves on this board: ``threat_tiers.assess`` of them, the raw reading, never the decided
  side the tier memory holds (the memory's group T1 is what read the scrolls at full HP);

  the line of fire is the danger reading (policy ``_monster_in_line_of_fire``: an awake monster
  does not see an unknown grid as a wall, as deep_teleport ``fire_p95`` reads it since 11-15),
  owner 2026-11-17 (maintainability review Q5, verbatim 「危険の判定は危険用に揃える」); until
  then the escape count's stricter line_of_fire.in_fire;

and with ``FEW_SCROLLS`` Teleportation scrolls or fewer carried (「残り少なければ」) only on the
即死 board.  Teleport Level, Word of Recall and the stairs are not covered (deep_teleport's
reading of the owner's 「テレポート」, 2026-11-14).

Where it is withheld the finders do not offer the self-teleport (deep_teleport ``no_means``,
the one predicate every finder of the self-teleport asks), so the ladder acts as it does
without one: the flee walk, the fight, the heal, the wait for the Recall.  A read that still
reaches deep_teleport's ``substitute`` (none is known) is refused with a search turn under
``HOLD_REASON``.  The decision record carries ``{"branch": BRANCH}`` (deep_teleport ``report``).
"""

from __future__ import annotations

from hengbot.item_reservation import decision_memo

FEW_SCROLLS = 3  # the owner's 「残り少なければ」 (Teleportation scrolls carried)
BRANCH = "recall-wait-teleport:withheld"
HOLD_REASON = "recall-wait-teleport:hold"
NOTE = "_recall_wait_teleport_withheld"   # the turn the finders held the teleport back on
_BUSY = "_recall_wait_teleport_busy"      # the predicate is being computed (re-entry)


def applies(policy, snapshot) -> bool:
    from hengbot import threat_tiers  # import cycle

    return snapshot.player.recalling and threat_tiers.acts_here(policy, snapshot)


def _t1_in_fire(policy, snapshot, hostiles) -> bool:
    from hengbot import threat_tiers  # import cycle

    in_fire = [monster for monster in hostiles if policy._monster_in_line_of_fire(snapshot, monster)]
    return bool(in_fire) and threat_tiers.assess(policy, snapshot, in_fire).tier == threat_tiers.T1


def withheld(policy, snapshot) -> bool:
    """The self-teleport is not offered on this board (the module docstring).  Pure, memoised
    for the decision; False while it is being computed (a finder asked from inside)."""
    if getattr(policy, _BUSY, False) or not applies(policy, snapshot):
        return False

    def compute():
        from hengbot import threat_tiers  # import cycle

        capture = policy.__dict__.pop("_claim_target_capture", None)
        setattr(policy, _BUSY, True)
        try:
            hostiles = threat_tiers.engagement(policy, snapshot)
            if threat_tiers.instant_death(policy, snapshot, hostiles).holds:
                return False
            if policy._count_teleport_scrolls(snapshot) <= FEW_SCROLLS:
                return True
            return not _t1_in_fire(policy, snapshot, hostiles)
        finally:
            setattr(policy, _BUSY, False)
            if capture is not None:
                policy._claim_target_capture = capture
    held = decision_memo(policy, "recall_wait_teleport.withheld", snapshot, None, compute)
    if held:
        setattr(policy, NOTE, snapshot.turn)
    return held


def observe(policy) -> None:
    """Every decision: the note is the decision's own."""
    setattr(policy, NOTE, None)


def report(policy) -> dict | None:
    """The decision record's field, when the finders held the teleport back."""
    turn = getattr(policy, NOTE, None)
    return None if turn is None else {"branch": BRANCH, "turn": turn}
