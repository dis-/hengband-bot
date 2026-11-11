"""Whether the player is covered against a fear or a blindness spell (owner 2026-11-11).

Owner 2026-11-11, the threat tiers' supply plan (「回復と悲観側のずれを全部」): 「恐怖・盲目の呪文を
持つ相手で耐性が無い時は T2 にしない」.  A plan that wins on HP still loses its turns to a fear
(no melee) or a blindness (no reading, no device aiming), which the HP projection cannot see.

Owner 2026-11-11, answer to 「恐怖耐性が無い時のヒーローの薬…は、いつ飲みますか？」:
「恐怖になった時と強敵の前」 -- 「恐怖になって殴れなくなった時に飲む。加えて、恐怖の呪文を持つ
強い相手（T2 以上の戦い）と戦い始める時に先に飲む。持っていれば、さっきの「恐怖の呪文の相手は
T2 にしない」の除外は外す」.  So fear is covered by the resistance, by a running heroism or
berserk, or by a carried Potion of Heroism (drunk by its own rung); blindness only by the
resistance.

Game (C:/hengband/src):
- mspell-status.cpp:248-262 ``spell_RF5_SCARE``: resisted by ``has_resist_fear``, else a saving
  throw; :305-318 ``spell_RF5_BLIND``: by ``has_resist_blind``, else a saving throw.
- player-status-flags.cpp:1513-1526 ``has_resist_fear``: the equipment's TR_RES_FEAR, the
  FEARLESS mutation, ``is_hero`` / ``is_shero`` / ultimate resistance / ``tim_res_fear``;
  :1399-1412 ``has_resist_blind``: TR_RES_BLIND, the munchkin personality, ultimate resistance
  and the magic defence.
- sv-potion-types.h:37 SV_POTION_HEROISM = 32 (quaff-effects.cpp: heroism sets ``hero``).

The snapshot's ``resist_fear`` / ``resist_blind`` abilities are the character sheet's flags; the
temporary ones show on the status bar (bot-json-output.cpp STATUS_BAR_KEYS: ``heroism``,
``berserk``, ``resist_fear``).
"""

from __future__ import annotations

SV_POTION_HEROISM = 32
FEAR_SPELL, BLIND_SPELL = "SCARE", "BLIND"
FEAR_COVERING_BAR = frozenset({"heroism", "berserk", "resist_fear"})

# The reasons a supply plan is withheld (``Assessment.t2_withheld``).
FEAR_WITHHELD, BLIND_WITHHELD = "fear-spell", "blind-spell"


def fear_covered(policy, snapshot) -> bool:
    """The player resists a fear spell now, or carries a Potion of Heroism to drink."""
    player = snapshot.player
    if "resist_fear" in player.abilities:
        return True
    if player.status_bar is not None and FEAR_COVERING_BAR & set(player.status_bar):
        return True
    return policy._exact_potion_count(snapshot, SV_POTION_HEROISM) > 0


def blind_covered(snapshot) -> bool:
    """The player resists a blindness spell (no potion stands in for it)."""
    return "resist_blind" in snapshot.player.abilities


def withheld(policy, snapshot, hostiles) -> tuple:
    """Why a winning supply plan is not graded T2 here: a hostile of the engagement casts fear or
    blindness and the player is not covered against it (empty: nothing withholds it)."""
    abilities = set()
    for monster in hostiles:
        knowledge = policy._monrace_knowledge.get(monster.race_id)
        if knowledge is not None:
            abilities |= set(knowledge.abilities)
    reasons = []
    if FEAR_SPELL in abilities and not fear_covered(policy, snapshot):
        reasons.append(FEAR_WITHHELD)
    if BLIND_SPELL in abilities and not blind_covered(snapshot):
        reasons.append(BLIND_WITHHELD)
    return tuple(reasons)
