"""Keep away from what disenchants the gear while the player has no resistance.

Owner 2026-11-05 (disenchant-avoid-decision-20261105): 「劣化耐性がないときに劣化属性攻撃
をするモンスターとの戦闘は可能であれば回避する。クエスト中でなければ*破壊*対象とする。」
Correction the same day: 「ランダムクエストの階であってもターゲットでなければ*破壊*してよい」.

Game (C:/hengband/src):
 * The forms: the blow effect UN_BONUS (monster-attack-switcher.cpp calc_blow_disenchant)
   and the breath BR_DISE (effect-player-resist-hurt.cpp effect_player_disenchant).  No
   other monster spell carries AttributeType::DISENCHANT, and no race in
   MonraceDefinitions.jsonc has AURA_DISENCHANT.  75 races, level 5 to 110.
 * Without resistance every landed blow and every breath calls apply_disenchant
   (spell-kind/spells-equipment.cpp), whatever its damage, so a weak monster is no
   smaller a cost: there is no weakness exemption here.  It picks one of eight slots
   (hands, bow, body, cloak, head, arms, feet); an empty slot or one with no plus does
   nothing; an artifact keeps it 71% of the time.  Otherwise to_h, to_d and to_a each
   lose 1 (one more with chance 1/5 above +5) and pval above 1 loses 1 with chance 1/13.
   The armour smith restores only AC.

``exposes_gear`` is the second trigger of destruction_use (awake, in view, in its radius),
the owner's 「*破壊*対象」; the floor and target gates are that module's.
"""

from __future__ import annotations

BLOW_EFFECTS = frozenset({"UN_BONUS"})    # race-info-tokens-table.cpp
ABILITIES = frozenset({"BR_DISE"})        # mspell-breath.cpp
RESIST_ABILITY = "resist_disen"           # bot-json-output.cpp, TR_RES_DISEN


def _race_disenchants(policy, monster) -> bool:
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return knowledge is not None and (
        any(blow.effect in BLOW_EFFECTS for blow in knowledge.blows)
        or bool(ABILITIES & knowledge.abilities))


def exposes_gear(policy, snapshot, monster) -> bool:
    """Its blows or breath disenchant, and the player does not resist."""
    return (_race_disenchants(policy, monster)
            and not snapshot.player.ability_sources.get(RESIST_ABILITY))
