"""The HP the player's own healing drink restored since the previous board.

n1-c life-216 (Angband 80F, 2026-11-18 13:36): an unseen はぐれメタル shot from the dark while
Recall counted down.  The bot drank a Potion of Healing at HP 555; on the next board HP read 630,
so ``_took_damage`` (HP below the previous board's) was false although the drink's 300 had been
followed by 225 of damage, the unseen-attack evidence (「何かが魔力の矢の呪文を唱えた。」 on that
board) was dropped with it, the unseen-attacker rung of the Recall wait was skipped and the
character waited (``return:wait-recall``) into the next volleys.

``observe`` is the one reader: on every board it compares the carried healing potions
(threat_projection ``HEAL_AMOUNTS``, quaff-effects.cpp:128-133: Healing 300, *Healing* 1200,
Life every HP) with the previous board's and returns the expected HP the spent ones restored,
when the game printed hp_player's message on this board (hp-mp-processor.cpp:455-463,
「…気分が良くなった。」 / "You feel ...": a potion that found the player at full HP prints none
and restores nothing).  The observation adds it to the previous HP before it compares, capped by
the maximum HP, so the damage taken after the drink is still damage.  A potion that left the pack
another way (sold, dropped, destroyed) is no drink: no message, no credit, and nothing in a store.
"""

from __future__ import annotations

MEMORY = "_heal_potions_carried"  # {sval: count} of the healing potions on the previous board
HEAL_MESSAGES = ("気分が良くなった。", "You feel a little better.", "You feel better.",
                 "You feel much better.", "You feel very good.")


def _carried(policy, snapshot) -> dict:
    from hengbot.threat_projection import HEAL_AMOUNTS  # import cycle

    return {sval: policy._exact_potion_count(snapshot, sval) for sval in HEAL_AMOUNTS}


def observe(policy, snapshot) -> int:
    """Every board: the expected HP the healing potions drunk since the previous board restored
    (0 without hp_player's message on this board), and the carried counts remembered."""
    from hengbot.threat_projection import HEAL_AMOUNTS  # import cycle

    carried = _carried(policy, snapshot)
    before = getattr(policy, MEMORY, None)
    setattr(policy, MEMORY, carried)
    if (before is None or snapshot.store is not None
            or not any(message.endswith(HEAL_MESSAGES) for message in snapshot.messages)):
        return 0
    return sum(amount * max(0, before.get(sval, 0) - carried[sval])
               for sval, amount in HEAL_AMOUNTS.items())
