"""What the player does about the summons it receives; the one reader of summon messages.

Owner 2026-11-04 (summon-response-decision-20261104), 「案のとおり3つとも」:
 1. 「召喚した本人が見えて狙えるなら、隣に増援がいても先に撃つ。」 (``caster_shot_key``)

The rungs stand after the survival ladder (policy._choose_key): what threatens the
player's life answers first.

A summon is recognised by the game's own strings (src/mspell/mspell-summon.cpp,
specified-summon.cpp; ``{}`` is ``monster_desc``, so an unseen caster is 何か / It):
the player's own summons have no subject and an item name (the auto-destroyed
魔法書[野性の召喚]) never ends in a cast, so neither is read as one.  The board's
messages are the new ones only (control_client merges a skipped board's into the next).

Pickled checkpoints have no ``MEMORY`` attribute: it is created on first use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import NamedTuple

from hengbot import me_ranged_first
from hengbot.policy_constants import RANGED_MAX_DISTANCE


MEMORY = "_summon_response_memory"
CASTER_SHOT_REASON = "summoner:ranged-kill:named-caster"
# ``monster_desc`` of a monster the player does not see.
UNSEEN_NAMES = frozenset({"何か", "It"})
# The tail of each cast, after the caster's name.
_CAST_TAILS_JA = (
    "がダンジョンの主を召喚した。",
    "が小さなペロロを吐き出した！",
    # S_KIN: MonraceDefinition::get_pronoun_of_summoned_kin
    "が魔法で手下を召喚した。", "が魔法で仲間を召喚した。", "が魔法でウサウサストライカーを召喚した。",
    "がサイバーデーモンを召喚した！",
    "が魔法で仲間を召喚した！",
    "が魔法でモンスターを召喚した！",
    "が魔法でアリを召喚した。",
    "が魔法でクモを召喚した。",
    "が魔法でハウンドを召喚した。",
    "が魔法でヒドラを召喚した。",
    "が魔法で天使を召喚した！",
    "は魔法で混沌の宮廷から悪魔を召喚した！",
    "が魔法でアンデッドの強敵を召喚した！",
    "が魔法でアンデッドを召喚した。",
    "が魔法でドラゴンを召喚した！",
    "が魔法で強力なアンデッドを召喚した！",
    "が魔法で古代ドラゴンを召喚した！",
    "がアンバーの王族を召喚した！",
    "が魔法で特別な強敵を召喚した！",
    "が魔法で特別な強敵を蘇らせた！",
    "が魔法で幽鬼戦隊を召喚した！",
)
_CAST_RE_EN = re.compile(r"^(.+?) (?:magically (?:summons|animates) |vomits minion Peroros!)")
_REPEAT_RE = re.compile(r" <x([1-9]\d*)>$")


class Summon(NamedTuple):
    caster: str  # the name in the message; UNSEEN_NAMES when the player does not see it

    @property
    def seen(self) -> bool:
        return self.caster not in UNSEEN_NAMES


def _parse_cast(text: str) -> Summon | None:
    for tail in _CAST_TAILS_JA:
        if text.endswith(tail) and len(text) > len(tail):
            return Summon(text[:-len(tail)])
    match = _CAST_RE_EN.match(text)
    return None if match is None else Summon(match.group(1))


def summons_of(message: str) -> tuple[Summon, ...]:
    """The casts one message line reports (the game's ``<xN>`` repeats a line)."""
    repeat = _REPEAT_RE.search(message)
    summon = _parse_cast(message if repeat is None else message[:repeat.start()])
    if summon is None:
        return ()
    return (summon,) * (1 if repeat is None else int(repeat.group(1)))


def _plain_name(name: str) -> str:
    """The English message says "The kobold", the board "Kobold"."""
    return re.sub(r"^the ", "", name, flags=re.IGNORECASE).casefold()


@dataclass
class Memory:
    floor: tuple | None = None
    board: tuple | None = None        # the last board read: a redraw is not read twice
    casters: set[str] = field(default_factory=set)  # plain names seen casting on this visit


def _memory(policy) -> Memory:
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        memory = Memory()
        setattr(policy, MEMORY, memory)
    return memory


def forget_floor_visit(policy) -> None:
    """Called on every floor transition beside the other per-visit memories."""
    setattr(policy, MEMORY, Memory())


def observe(policy, snapshot) -> None:
    """Every decision: count this board's summons into this floor visit."""
    memory = _memory(policy)
    if memory.floor != snapshot.floor_key:
        memory = Memory(floor=snapshot.floor_key)
        setattr(policy, MEMORY, memory)
    board = (snapshot.turn, snapshot.messages)
    if board == memory.board:
        return
    memory.board = board
    for message in snapshot.messages:
        for summon in summons_of(message):
            _count(memory, summon)


def _count(memory: Memory, summon: Summon) -> None:
    if summon.seen:
        memory.casters.add(_plain_name(summon.caster))


# -- 1. the caster in view ------------------------------------------------------

def _caster_targets(policy, snapshot) -> list:
    casters = _memory(policy).casters
    here = snapshot.player.position
    return sorted(
        (monster for monster in snapshot.visible_monsters
         if monster.hostile and not monster.asleep
         and _plain_name(monster.name) in casters
         and 2 <= here.distance_to(monster.position) <= RANGED_MAX_DISTANCE),
        key=lambda monster: monster.distance)


def _shot_at(policy, snapshot, target) -> str | None:
    """The ranged order at ``target`` past any nearer body.

    A device needs the ray ``_ranged_target`` proves clear (me_ranged_first aims by
    direction); the bow names the cell and refuses a blocked bolt path
    (``_ranged_attack_key``).  Blindness and confusion refuse both there, fear neither.
    """
    player = snapshot.player
    if (not (player.blind or player.confused)
            and policy._ranged_target(snapshot, [target]) is target):
        device = me_ranged_first.attack_key(policy, snapshot, target)
        if device is not None:
            return device
    return policy._ranged_attack_key(snapshot, [target], [])


def caster_shot_key(policy, snapshot) -> str | None:
    """Shoot the monster named casting a summon on this visit, nearest first; a
    caster beside the player is the melee rungs' (they strike summoners first)."""
    for target in _caster_targets(policy, snapshot):
        key = _shot_at(policy, snapshot, target)
        if key is not None:
            if (policy.last_reason or "").startswith("ranged:fire"):
                policy.last_reason = CASTER_SHOT_REASON
            return key
    return None


def key(policy, snapshot) -> str | None:
    """The owner's answer to the summons on this visit, else None."""
    return caster_shot_key(policy, snapshot)
