"""What the player does about the summons it receives; the one reader of summon messages.

Owner 2026-11-04 (summon-response-decision-20261104), 「案のとおり3つとも」:
 1. 「召喚した本人が見えて狙えるなら、隣に増援がいても先に撃つ。」 (``caster_shot_key``)
 2. 「姿の見えない敵の召喚が2回続いたら今いる場所から離れる。」 (``leave_key``)
 3. 「同じ階で召喚が3回あったら帰還を読む。一度きりのクエストの階は除く。」 (``recall_key``)

The rungs stand after the survival ladder (policy._choose_key): what threatens the
player's life answers first.

A summon is recognised by the game's own strings (src/mspell/mspell-summon.cpp,
specified-summon.cpp; ``{}`` is ``monster_desc``, so an unseen caster is 何か / It):
the player's own summons have no subject and an item name (the auto-destroyed
魔法書[野性の召喚]) never ends in a cast, so neither is read as one.  The board's
messages are the new ones only (control_client merges a skipped board's into the next).

Blind, a cast prints only 「何かをつぶやいた」, which every spell prints; the line that
follows a summon with a monster in it is read as an unseen cast (``_BLIND_SOUNDS``).

"In a row" (rule 2), from n1-c life-130's decision logs (95 113 decisions, 115 unseen
casts): between consecutive unseen casts on a floor the gap ran 0-21 decisions with the
player within 5 cells (66 pairs), then 24+ decisions with the player 9+ cells away (one
exception, 54 decisions at 0 cells).  So the casts continue while the next comes within
``UNSEEN_CAST_WINDOW_DECISIONS`` and the player has not moved ``LEFT_SPOT_DISTANCE``
cells from the last one.  A seen cast in between does not end the run: the caster the
player cannot see is still there (n1-a life-475: unseen, seen, unseen at one cell).

Leaving is the existing escapes only: *Destruction* where destruction_use's gates pass,
else a Scroll of Teleportation, with an awake hostile in view; a floor whose strategy
forbids the scroll keeps its fight (quest_no_teleport).  The spot left stays out of
routes (the hold point's own veto) and the run ends once the player is away or the
flash has gone off, so a choke hold elsewhere needs two new casts to be left again.

Rule 3 reads through once_quest_recall.read_key, so every exit lock keeps its floor: a
kill quest's lock (a runtime RANDOM quest and Q14 until the 11-01 teleport reserve is
drawn down, random_quest_reserve) still holds such a floor and the read waits for the
lock's own release.  The read latches the return under a survival trigger, so the return
owner then waits and fights as for any emergency return; *Destruction* does not undo it.
Read before a shot and before leaving: its countdown runs whatever happens next.

Pickled checkpoints have no ``MEMORY`` attribute: it is created on first use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import NamedTuple

from hengbot import destruction_use, me_ranged_first, once_quest_recall, return_yield
from hengbot.model import Position
from hengbot.policy_constants import RANGED_MAX_DISTANCE, ExplorationPathOutcome


MEMORY = "_summon_response_memory"
CASTER_SHOT_REASON = "summoner:ranged-kill:named-caster"
LEAVE_REASON = "summons:leave-teleport"
RECALL_REASON = "summons:recall"
# The prefix makes it a survival return (town_hold.is_survival_return_trigger).
RETURN_TRIGGER = "emergency-summons"
# Owner 2026-11-04: 「3回」.
SUMMONS_TO_RECALL = 3
# Owner 2026-11-04: 「2回」.
UNSEEN_CASTS_TO_LEAVE = 2
# From the logs (module docstring): how far apart two unseen casts still run on.
UNSEEN_CAST_WINDOW_DECISIONS = 21
LEFT_SPOT_DISTANCE = 6
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
# What a blind player hears after a summon (mspell-summon.cpp); it names no caster.
_BLIND_SOUNDS = frozenset({
    "多くのものが間近に現れた音がする。", "You hear many things appear nearby.",
    "重厚な足音が近くで聞こえる。", "You hear heavy steps nearby.",
    "何かが間近に現れた音がする。", "You hear something appear nearby.",
    "間近で何か多くのものが這い回る音が聞こえる。", "You hear many creepy things appear nearby.",
    "多くの力強いものが間近に現れた音が聞こえる。", "You hear many powerful things appear nearby.",
    "何者かが次元を超えて現れた気配がした。", "You feel shadow shifting by immortal beings.",
    "多くのものが間近に現れた音が聞こえる。",
    "多くの力強いものが間近に蘇った音が聞こえる。", "You hear many powerful things animate nearby.",
})
_CAST_RE_EN = re.compile(r"^(.+?) (?:magically (?:summons|animates) |vomits minion Peroros!)")
_REPEAT_RE = re.compile(r" <x([1-9]\d*)>$")


class Summon(NamedTuple):
    caster: str  # the name in the message; UNSEEN_NAMES when the player does not see it

    @property
    def seen(self) -> bool:
        return self.caster not in UNSEEN_NAMES


def _parse_cast(text: str) -> Summon | None:
    if text in _BLIND_SOUNDS:
        return Summon(next(iter(UNSEEN_NAMES)))
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
    summons: int = 0                  # every cast of this visit, seen or not
    decisions: int = 0                # decisions of this visit
    unseen_run: int = 0               # unseen casts in a row (module docstring)
    last_unseen: tuple[int, Position] | None = None  # the decision and cell of the last
    leave_turn: int | None = None     # the board of the last leave: a redraw reads no second


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
    memory.decisions += 1
    if _run_ended(memory, snapshot):
        memory.unseen_run = 0
    for message in snapshot.messages:
        for summon in summons_of(message):
            _count(memory, summon, snapshot.player.position)


def _run_ended(memory: Memory, snapshot) -> bool:
    if memory.last_unseen is None:
        return False
    decision, cell = memory.last_unseen
    return (memory.decisions - decision > UNSEEN_CAST_WINDOW_DECISIONS
            or snapshot.player.position.distance_to(cell) >= LEFT_SPOT_DISTANCE
            or any(message in destruction_use.FLASH for message in snapshot.messages))


def _count(memory: Memory, summon: Summon, here: Position) -> None:
    memory.summons += 1
    if summon.seen:
        memory.casters.add(_plain_name(summon.caster))
    else:
        memory.unseen_run += 1
        memory.last_unseen = (memory.decisions, here)


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


# -- 2. the caster out of view --------------------------------------------------

def leave_due(policy, snapshot) -> bool:
    """The unseen casts ran on and the window is still open on this board."""
    memory = _memory(policy)
    return memory.unseen_run >= UNSEEN_CASTS_TO_LEAVE and not _run_ended(memory, snapshot)


def leave_key(policy, snapshot) -> str | None:
    """Leave the spot by the existing escapes (module docstring), else None."""
    memory = _memory(policy)
    if (not leave_due(policy, snapshot) or memory.leave_turn == snapshot.turn
            or not return_yield.awake_hostile_in_view(policy, snapshot)):
        return None
    used = destruction_use.key(policy, snapshot)
    if used is not None:
        memory.leave_turn = snapshot.turn
        return used
    scroll = policy._escape_scroll(snapshot, teleport_only=True)
    if scroll is None:
        return None
    here = snapshot.player.position
    policy._claim_engagement_avoid_cells((here,))
    if here in policy._explore_path:
        policy._clear_explore_path(ExplorationPathOutcome.INVALIDATE)
    memory.leave_turn = snapshot.turn
    policy.last_reason = LEAVE_REASON
    return policy._read_key(snapshot, scroll)


# -- 3. too many on one floor ---------------------------------------------------

def _once_floor(policy, snapshot) -> bool:
    """A fixed quest's floor with the ONCE flag: leaving it fails the quest for good."""
    quest_id = snapshot.floor_key[2]
    if not quest_id or policy._on_random_quest_floor(snapshot):
        return False
    return policy._fixed_quest_is_once(quest_id)


def recall_due(policy, snapshot) -> bool:
    """The floor visit's casts reached the count and a Recall can be read for it."""
    return (_memory(policy).summons >= SUMMONS_TO_RECALL
            and snapshot.dungeon_level >= 1
            and not snapshot.player.recalling
            and not _once_floor(policy, snapshot)
            and not policy._quest_floor_exit_locked(snapshot)
            and policy._find_recall_scroll(snapshot) is not None)


def recall_key(policy, snapshot) -> str | None:
    """Read Word of Recall, the one emergency read, and latch the return."""
    if not recall_due(policy, snapshot):
        return None
    read = once_quest_recall.read_key(policy, snapshot, RECALL_REASON)
    if read is not None:
        policy._note_return_start(RETURN_TRIGGER)
        policy._returning_to_town = True
        policy._last_return_trigger = RETURN_TRIGGER
    return read


def key(policy, snapshot) -> str | None:
    """The owner's answer to the summons on this visit, else None."""
    return (recall_key(policy, snapshot) or leave_key(policy, snapshot)
            or caster_shot_key(policy, snapshot))


def action_due(policy, snapshot) -> bool:
    """A rule outranks the older three-shot summoner rung above the emergency ladder."""
    return recall_due(policy, snapshot) or leave_due(policy, snapshot)
