"""The Amberites' blood curse: erase them with *Destruction*, or kill them only when ready.

Owner 2026-11-17 (verbatim): 「魔法防御上昇の装備がないときは破壊で消す。倒すときは視界とその回りに
起きた敵が他にいなくてHPが十分のとき、加速して耐性の薬を使用して倒す。」

n1-b life-410 (Magic-Eater Lv50, Angband 80F, 2026-11-17 02:17): decisions #17762-17763 fired two
Rockets (``ranged:magic-eater-device``) at アンバーの狂気の夢想家『ブランド』 with the absorbed
*Destruction* usable on the same board; the second one killed it, the blood curse made the player
a statue and summoned 理想の戦士『ベネディクト』, and the player died paralysed.

Game (C:/hengband/src):
 * monster/monster-damage.cpp ``death_amberites``: an AMBERITE kind (MonsterKindType::AMBERITE,
   the race's ``flags`` in MonraceDefinitions.jsonc) killed by the player curses one time in two:
   ``curse_equipment(100, 50)`` and 2-4 ``activate_ty_curse``.
 * spell-kind/spells-random.cpp ``activate_ty_curse`` (cases 13-15, 19-20): paralysis (13 turns
   at most, 3 with free action) unless free action and ``randint1(125) < skill_sav``; the other
   cases summon, drain, damage, lose stats.  TR_RES_CURSE (「魔法防御上昇」) adds 30 to the saving
   throw (player-status.cpp calc_saving_throw); the board reports it as the ``resist_curse``
   ability (bot-json-output.cpp).
 * spell-kind/spells-floor.cpp ``destroy_area``: a monster in the circle is deleted
   (``delete_monster``), no death processing, so no blood curse; a QUESTOR is healed and moved
   instead (destruction_use).

The rule, as it is enforced:
 1. No ``resist_curse``: owner 2026-11-17 (verbatim) 「呪力耐性がないときは王族をT1扱いにする。行動は
    T1の処理に準じる。」  The tiers read every engagement with an Amberite T1 (``t1_amberites``,
    asked by threat_projection ``_tier``, the one place a tier is assigned), so the T1 rules
    answer it: the sensed-T1 *Destruction* and approach, the leave and the escapes, no reward
    selection, the random quest's T1 target given up.  (Until then it was a sight trigger of
    destruction_use.)
 2. Every decided key passes ``after_ladder`` (dungeon_ladder.AFTER_DECIDE), the one gate of
    "can this action kill an Amberite now" (``struck``): a step into a cell an Amberite holds
    (melee), or a ranged attack (attack_answer's shot reasons, reasons.strikes) while an Amberite
    is in view or has a line of fire with the player (a ball, a beam, a sight power or the game's
    target cursor may hit it, not only the aimed monster).  Any strike that reaches it counts as
    one that can kill: the bot's damage expectation is no bound (me_device_attacks gives the Rocket
    400 at Lv50, the live one took 750 of Brand's 1200 HP, and the expectation would have let the
    killing Rocket at 450 HP through).
 3. A strike passes only with ``resist_curse``, no other awake hostile in view or around (the
    engagement of the threat tiers, threat_projection.engagement: the strategic hostiles in view
    and the awake detected ones; an unseen attacker's evidence counts as one), and the HP at or
    above the low-HP line (policy ``_low_hp_walk_threshold``, the line worsens_kill's 被害無く
    kill keeps).  Before the strike the player is hasted (speed_dose: the absorbed Speed, else a
    Potion of Speed; haste_read says whether it is on) and covered by a Potion of Resistance
    (resist_potion.covered: the five elements on the status bar); each missing one is taken in
    the strike's place, and a missing means refuses the strike.
 4. A refused strike (``_kept_alive_key``), where a rung still decides one (the T1 rules above
    it declined): without ``resist_curse`` *Destruction* on it (destruction_use.key leaving it);
    then the existing engagement retreat (policy ``_avoid_engagement_key``), else a wait
    (``HOLD_REASON``).  The walk toward *Destruction* is the T1 rules' (threat_tiers
    ``approach_key``, deep_teleport's walk), not this gate's.  Nothing teleports here.

Record only: ``report`` (the decision log's ``amberite``) names the Amberites the decided key
could hit, the verdict and the key it replaced.
"""

from __future__ import annotations

from hengbot import attack_answer, haste_read, line_of_fire, reasons
from hengbot.policy_constants import WAIT_KEY

KIND_FLAG = "AMBERITE"                 # MonraceDefinitions.jsonc flags, MonsterKindType::AMBERITE
RESIST_ABILITY = "resist_curse"        # bot-json-output.cpp, TR_RES_CURSE
SIGHT_SUFFIX = ":amberite"             # the reason suffix of the gate's *Destruction*
HASTE_REASON = "amberite:haste"
RESIST_REASON = "amberite:quaff-resistance"
HOLD_REASON = "amberite:hold"
NOTE = "_amberite_curse_note"          # (decision sequence, record); record only

# Verdicts (the record's ``verdict``).
PERMITTED = "permitted"
NO_RESIST_CURSE = "no-resist-curse"
OTHER_AWAKE = "other-awake"
HP_LOW = "hp-low"
NO_HASTE = "no-haste-means"
NO_RESISTANCE = "no-resistance-potion"
HASTE = "haste-first"
RESISTANCE = "resistance-first"


def is_amberite(policy, monster) -> bool:
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return knowledge is not None and KIND_FLAG in knowledge.flags


def resists_curse(snapshot) -> bool:
    return bool(snapshot.player.ability_sources.get(RESIST_ABILITY))


def t1_amberites(policy, snapshot, hostiles) -> tuple:
    """Owner 2026-11-17 「呪力耐性がないときは王族をT1扱いにする」: the indices of the Amberites of
    ``hostiles`` the tiers read T1 (threat_projection ``_tier``, the one place a tier is assigned),
    awake or asleep, seen or sensed; () with resist curse."""
    if resists_curse(snapshot):
        return ()
    return tuple(monster.index for monster in hostiles if is_amberite(policy, monster))


# -- the gate -------------------------------------------------------------------

def _known_amberites(policy, snapshot) -> list:
    seen = {}
    for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters):
        if monster.hostile and monster.index not in seen and is_amberite(policy, monster):
            seen[monster.index] = monster
    return list(seen.values())


def struck(policy, snapshot, key) -> list:
    """The Amberites ``key`` (under ``policy.last_reason``) may hit, so may kill: the one reader."""
    if key is None or snapshot.in_town:
        return []
    amberites = _known_amberites(policy, snapshot)
    if not amberites:
        return []
    cell = attack_answer.step_cell(snapshot, key)
    if cell is not None:
        # Walking into a monster's cell strikes it, whatever the rung meant (a hunt step too).
        return [monster for monster in amberites if monster.position == cell]
    reason = policy.last_reason or ""
    if not (reason.startswith(attack_answer.SHOT_REASON_PREFIXES) or reasons.strikes(reason)):
        return []
    shown = {monster.index for monster in snapshot.visible_monsters}
    return [monster for monster in amberites
            if monster.index in shown or line_of_fire.in_fire(policy, snapshot, monster)]


def _others_awake(policy, snapshot, amberites) -> bool:
    from hengbot import threat_tiers  # import cycle

    if getattr(policy, "_unseen_attack_evidence", None) is not None:
        return True
    struck_indices = {monster.index for monster in amberites}
    return any(not monster.asleep and monster.index not in struck_indices
               for monster in threat_tiers.engagement(policy, snapshot))


def refusal(policy, snapshot, amberites) -> str | None:
    """Why a strike that can kill ``amberites`` may not be sent now, else None (rule 3)."""
    if not resists_curse(snapshot):
        return NO_RESIST_CURSE
    if len(amberites) > 1 or _others_awake(policy, snapshot, amberites):
        return OTHER_AWAKE
    player = snapshot.player
    if player.hp < policy._low_hp_walk_threshold(player.max_hp):
        return HP_LOW
    return None


def after_ladder(policy, snapshot, key):
    """The decided ``key``, or what goes in its place when it can kill an Amberite."""
    amberites = struck(policy, snapshot, key)
    if not amberites:
        return key
    from hengbot import resist_potion, speed_dose  # import cycle (destruction_use's sight trigger)

    original = (key, policy.last_reason)
    verdict = refusal(policy, snapshot, amberites)
    if verdict is None:
        if not haste_read.hasted(policy, snapshot):
            dose = speed_dose.key(policy, snapshot, HASTE_REASON)
            if dose is not None:
                _note(policy, amberites, HASTE, original)
                return dose
            verdict = NO_HASTE
        elif not resist_potion.covered(snapshot.player):
            drink = resist_potion.quaff_key(policy, snapshot, RESIST_REASON)
            if drink is not None:
                _note(policy, amberites, RESISTANCE, original)
                return drink
            verdict = NO_RESISTANCE
        else:
            _note(policy, amberites, PERMITTED, original)
            return key
    answer = _kept_alive_key(policy, snapshot, amberites, verdict)
    _note(policy, amberites, verdict, original)
    return answer


def _kept_alive_key(policy, snapshot, amberites, verdict):
    """Rule 4: the answer that leaves the Amberite alive (never a strike at it)."""
    from hengbot import destruction_use  # import cycle

    if verdict == NO_RESIST_CURSE:
        used = destruction_use.key(policy, snapshot, leaving=amberites, suffix=SIGHT_SUFFIX)
        if used is not None:
            return used
    retreat = policy._avoid_engagement_key(snapshot, policy._physical_hostiles(snapshot))
    if retreat is not None and not struck(policy, snapshot, retreat):
        return retreat
    policy.last_reason = HOLD_REASON
    return WAIT_KEY


# -- the record -----------------------------------------------------------------

def _note(policy, amberites, verdict, original) -> None:
    setattr(policy, NOTE, (policy._decision_sequence, {
        "amberites": [[monster.index, monster.race_id, monster.name, monster.hp, monster.max_hp]
                      for monster in amberites],
        "verdict": verdict,
        "decided": list(original),
        "answer_reason": policy.last_reason,
    }))


def report(policy) -> dict | None:
    """The decision log's ``amberite`` field of this decision, else None."""
    note = getattr(policy, NOTE, None)
    if note is None or note[0] != getattr(policy, "_decision_sequence", None):
        return None
    return note[1]
