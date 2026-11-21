"""A worn NO_AC piece (宵闇のローブ) in the dungeon: keep it on, read Recall, keep melee away.

Owner 2026-11-21 (verbatim, LOCKED): 「AC0では打撃を受けると即死抽選がある。優先対処。」 and the answer
「着たまま帰還を読み、打撃の届く敵を寄せない」 (not taken off: n1-b life-411's other gear lacks the
robe's acid, sound, nexus, time and water resistance on 95F).  A worn NO_AC piece makes the AC 0
(player-status.cpp calc_base_ac / calc_to_ac, ``yoiyami``).  While one is worn on a dungeon floor:

* the Word of Recall is read at once (``RECALL_REASON``, started through return_start);
* until it fires, a melee-capable hostile (blows in its race, awake) that could stand beside the
  player after its moves of one player turn is answered in the existing order -- *Destruction*,
  Teleport Other at it -- else the player teleports (``TELEPORT_REASON``, the Teleportation scroll:
  deep_teleport lets it through, ``teleport_due``);
* else, the recall counting down, the player waits (``WAIT_REASON``): no exploring, loot or fight.

It is the summoner-shots layer's first rung: below the emergency ladder (the escape from a this-turn
instant death, the emergency drinks), above everything else.  In town the loadout search leaves the
piece out (warrior_optimization, owner 2026-11-21 「99F 100Fでも宵闇のローブは禁止」), so the swap
takes it off.
"""
from __future__ import annotations

from math import ceil

from hengbot.equipment_rules import TR_NO_AC
from hengbot.policy_constants import WAIT_KEY, speed_energy

RECALL_TRIGGER = "no-ac"
RECALL_REASON = "no-ac:recall"
TELEPORT_REASON = "no-ac:teleport"
WAIT_REASON = "return:wait-recall"  # the recall wait every return reads (policy_combat sanctions it)


def worn(snapshot) -> bool:
    return any(TR_NO_AC in item.known_flags for item in snapshot.equipment)


def _closing_melee(policy, snapshot) -> bool:
    """An awake hostile with blows that could reach the player's side within one player turn."""
    return bool(_closers(policy, snapshot))


def _closers(policy, snapshot) -> list:
    """The awake hostiles with blows that could reach the player's side within one player turn."""
    found = []
    player = snapshot.player
    here = player.position
    player_energy = max(1, speed_energy(player.speed))
    knowledge = policy._monrace_knowledge
    for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters):
        race = knowledge.get(monster.race_id)
        if not monster.hostile or monster.asleep or race is None or not race.blows:
            continue
        moves = 0 if "NEVER_MOVE" in race.flags else ceil(
            speed_energy(monster.speed) / player_energy)
        distance = max(abs(monster.position.y - here.y), abs(monster.position.x - here.x))
        if distance <= 1 + moves:
            found.append(monster)
    return found


def teleport_due(policy, snapshot) -> bool:
    """A worn NO_AC piece on a dungeon floor with a melee hostile closing: the self-teleport is
    offered whatever the 50F+ and recall-wait rules would say (deep_teleport asks this)."""
    return (not snapshot.in_town and snapshot.store is None and worn(snapshot)
            and bool(_closers(policy, snapshot)))


def key(policy, snapshot) -> str | None:
    if snapshot.in_town or snapshot.store is not None or not worn(snapshot):
        return None
    if not snapshot.player.recalling:
        recall = policy._find_recall_scroll(snapshot)
        if recall is not None and policy._can_read_scrolls(snapshot):
            from hengbot import return_start
            return_start.start(policy, RECALL_TRIGGER)
            key = policy._read_dungeon_recall_scroll_key(snapshot, recall)
            if key is not None:
                policy.last_reason = RECALL_REASON
                return key
    closers = _closers(policy, snapshot)
    if closers:
        # The existing order first: *Destruction*, then Teleport Other at the worst of them
        # (teleport_follower.away_key, owner 2026-11-09 「*破壊*>テレポートアウェイ>戦闘」, 2026-11-17
        # Q4); else the Teleportation scroll itself, the 50F+ rule's refusal aside (owner
        # 2026-11-21 「打撃の届く敵を寄せない」).
        from hengbot import teleport_follower
        sent = teleport_follower.away_key(policy, snapshot, closers, reason=TELEPORT_REASON)
        if sent is not None:
            return sent
        scroll = policy._escape_scroll(snapshot, teleport_only=True, beside_followers=True)
        if scroll is not None:
            policy.last_reason = TELEPORT_REASON
            return policy._issue_emergency_consumable(snapshot, scroll, TELEPORT_REASON)
    if not snapshot.player.recalling:
        return None
    policy.last_reason = WAIT_REASON
    return WAIT_KEY
