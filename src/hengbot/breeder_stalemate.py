"""When a breeder fight on a floor turns into flight (owner rule 2026-11-02).

The window is 100 attacking actions (owner 2026-11-09, verbatim: 「加えて判断の窓を長く取る。20回は
短いようだ。」, the answer 「100回」).  It replaces the 20 of the rules quoted below; everything else
about the window (attacks only, the start and end counts of each window compared) is unchanged.

Owner, verbatim: 「攻撃用の物資は制限しない。ただし、20ターンで数が減らせないなら
逃走を選択する。」  Attack supplies are not capped against breeders; once the
bot engages the breeders of a floor, the fight runs in windows of 20 player
actions.  Owner 2026-11-03: 「20回の区切りの初めの数と終わりの数を比べ、減っていれば
次の区切りへ進み、減っていなければ逃げます（Q2 などは放棄）。1体倒しても増えて元に戻る
なら逃げます。」  A completed window with fewer perceived breeders than at its start
opens the next window at the current count; any other completed window is
abandoned: the floor is latched as a breeder breakthrough
(``_breeder_breakthrough_floor``), whose owners leave it by Recall or the up
stairs.  A floor the bot cannot leave (a locked quest floor) keeps fighting
the breeders that attack it (``survival_preemption.strikes_from_adjacent``).

A "turn" is one player action: a decision board whose game turn advanced
since the previous counted board (dungeon-processor.cpp advances
``game_turn`` once per game tick; the player acts when its energy, gained
by ``speed_to_energy`` each tick, reaches the need, so the game turns per
action differ with speed while the boards between actions do not).  Only the
counts at the two ends of a window matter: boards in between neither reset
nor extend it, including boards that show no breeder at all.  A window that
ends with no breeder perceived ends the engagement instead of opening a window
at zero, which could never show a reduction; the next attack on a breeder opens a
new one.  An abandoned window's verdict stands until ``forget``.

This replaces the earlier flight triggers (five kills with more breeders
than at engagement; 3,000 game turns without a reduction).

Floors with a quest plan (owner 2026-11-05 「攻撃を始めてから数える」): the bot
walks those floors in the plan's order past breeders it does not fight yet, and
what comes into view is not growth.  n1-a life-478 was abandoned at full HP on
one gremlin at the window's start and one blue icky thing at its end; life-482
on one Undead mass glimpsed at the start and eleven in view at the end.  There a
window opens on the board that shows the first attack landed on a breeder (a
visible breeder of the last board hurt, or gone with the player's experience
up: the key's own target differs per attack owner, the result does not) and
counts only that race, from its count before the attack.  A shot that misses
opens nothing yet.  The comparison and the abandonment are the same.

Few of them in view on such a floor (owner 2026-11-05 「少ない時は倒した数で判断」,
the option: 「見える数が5体未満なら、窓の中で倒せていれば続けます。5体以上なら今の比較
です。」): 見える数 is the count the window ends with (the count this module always
compared, perceived, of the window's race; the start count does not matter).  Under
FEW_BREEDERS, a window with a kill of that race goes on although it did not reduce;
without one it is abandoned as before.  n1-b life-316 left Q2 at full HP on a window
that went from two blue icky things to three while it killed eleven.  Floors without
a plan keep the rule of 11-03: the question was about Q2's window.

Floors without a quest plan (owner 2026-11-07 「クエストの無い階でも、20回は増える敵に
攻撃を始めてから数える。感知だけで見えて攻撃していない増える敵では帰還しない。」): the
first window opens on the same first attack, so a breeder only perceived (telepathy,
detection, a glimpse) and never attacked opens nothing and cannot end in the
breakthrough's Recall.  There a kill line of a breeder race perceived on the board
before is an attack too: a breeder far below the character's level gives no
experience point, and without the line such a fight would never open a window.  n1-c life-155 recalled from short dives on one distant
telepathy-only 緑イモムシの大群 and a never-moving スライムモルド it never attacked.
What the window counts there is unchanged (every perceived breeder, from the count on
the board before the attack, no race and no kill rule).

A kill is the game's own line for a monster of the window's race, by its name:
「…は死んだ。」 (shots, spells: get_died_message), 「…を葬り去った。」 and 「…を倒した。」
(melee: show_kill_message).  The board's messages are the new ones only.  An unseen
victim is 何か, so its race is not known and it does not count; nor do the deaths
with a line of their own (effect-monster-*: 「…は蒸発した！」 and the like), nor a kill
on a board before the race's name was seen.  A monster killed by another monster
prints the same line and counts.  The kill on the board that opens a first window
is the attack the window counts from; the one on the board that ends a window
belongs to that window, not to the next.

Quest 25's corpse masses (owner 2026-11-08, verbatim: 「Q25の死体の塊では帰らない。」): on the
Q25 floor 死体の塊 (race 202) neither opens, counts in, nor ends a window, so they can never latch
the breakthrough whose Recall fails the PRESET+ONCE quest (quest.cpp leave_quest_check).  The
quest's own plan handles them (phase 4 shoots them from [1,6]; every phase strikes one beside the
player and shoots those in the line of fire, quest25_battle).  n1-c life-164 (2026-11-08 03:29) struck two masses beside it on [1,18], held, and read
Recall 41 decisions later on a window that went from five masses to six.  Any other breeder on
that floor, and every other floor, keeps the rules above.

Only attacks count (owner 2026-11-08 「20回の判定は、実際に攻撃した手だけで数える。」): a window
advances on a player action that attacked, not on a hold, a walk or a rest (n1-c life-164 latched
Q25 on a window of which 38 of 40 actions were holds beside the corpse masses).  An action
attacked when the board after it shows a breeder hurt or killed (the attack reading above), or
when the decision that sent it chose an attack (its reason's ``attack`` in the registry
hengbot.reasons, not a hold, an approach or a repositioning) with a breeder in view: a missed
shot is an attack too.
"""
from __future__ import annotations

from typing import NamedTuple

from hengbot import quest25_geometry, reasons
from hengbot.game_messages import ECHIZEN_PREFIX, KILL_LINE_DESTROYED, KILL_LINE_DIED, KILL_LINE_SLAIN
from hengbot.unseen_strike import message_text


# Owner 2026-11-09 「加えて判断の窓を長く取る。20回は短いようだ。」→「100回」 (was 20, owner 11-02/11-03).
FLEE_AFTER_PLAYER_ACTIONS = 100
# Owner 2026-11-05 「少ない時は倒した数で判断」: 「見える数が5体未満なら…」.
FEW_BREEDERS = 5
# The seen kill lines only: the unseen 「…を殺した。」 (game_messages.KILL_LINE_KILLED) is not read here.
_KILL_LINES = (KILL_LINE_DIED, KILL_LINE_SLAIN, KILL_LINE_DESTROYED)
_KILL_LINE_PREFIX = ECHIZEN_PREFIX     # show_kill_message, is_echizen


class _LastBoard(NamedTuple):
    """What the next board's attack reading compares with."""
    floor: tuple
    exp: int
    sighted: dict       # visible breeder's index -> (race, estimated HP)
    counts: dict        # race -> perceived breeders
    names: dict = {}    # race -> the name kill lines give it, from every board so far


def forget(policy) -> None:
    """A new floor visit: no breeder engagement yet."""
    policy._breeder_engagement_start_count = None
    policy._breeder_engagement_start_turn = None
    policy._breeder_engagement_actions = 0
    policy._breeder_engagement_last_turn = None
    policy._breeder_engagement_race = None
    policy._breeder_engagement_killed = False
    policy._breeder_attack_sent = False


def is_attack_reason(reason: str | None) -> bool:
    """The decision's reason is an attack (owner 2026-11-08): its row's ``attack`` in the
    registry hengbot.reasons (``ranged:fire``, ``melee``, ``quest-strategy:q2-fire``,
    ``quest25:shot``, ``ranged:breeder-area:wand``, ``unseen:strike``, ...)."""
    return reasons.is_attack(reason)


def stalemate_standing(policy) -> bool:
    """A window has run ``FLEE_AFTER_PLAYER_ACTIONS`` attacks without a reduction."""
    return (
        policy._breeder_engagement_start_count is not None
        and policy._breeder_engagement_actions >= FLEE_AFTER_PLAYER_ACTIONS
    )


def _counts_from_first_attack(policy, snapshot) -> bool:
    """This floor is the TAKEN quest's with a plan."""
    quest_id = policy._active_fixed_quest_id(snapshot)
    return quest_id is not None and policy.approved_quest_strategy(quest_id) is not None


def _exempt_races(policy, snapshot) -> frozenset:
    """Breeder races this floor's windows leave out: Q25's corpse masses (owner 2026-11-08)."""
    if policy._active_fixed_quest_id(snapshot) == quest25_geometry.QUEST_ID:
        return frozenset({quest25_geometry.MASS})
    return frozenset()


def _attacked_race(policy, snapshot, breeders: list,
                   kill_lines: bool = False,
                   exempt: frozenset = frozenset()) -> tuple[int, int, int] | None:
    """(race, its count on the last board, every breeder's count on the last board) of a
    breeder the last action hit.

    ``kill_lines`` (floors without a plan) also takes this board's kill line of a breeder
    race perceived on the last board as the attack: a character far above the breeder's
    level gains no experience point from it (n1-c life-120 at Lv21 put down nether worms
    with 「冥界イモムシの大群を葬り去った。」 and its experience unchanged)."""
    last = policy._breeder_last_board
    sighted = {monster.index: monster for monster in snapshot.visible_monsters
               if monster.hostile and monster.can_multiply and monster.race_id not in exempt}
    counts: dict[int, int] = {}
    for monster in breeders:
        counts[monster.race_id] = counts.get(monster.race_id, 0) + 1
    names = {**(last.names if last is not None else {}),
             **{monster.race_id: monster.name for monster in breeders}}
    policy._breeder_last_board = _LastBoard(
        snapshot.floor_key, snapshot.player.exp,
        {index: (monster.race_id, monster.hp) for index, monster in sighted.items()},
        counts, names)
    if last is None or last.floor != snapshot.floor_key:
        return None
    for index, (race, hp) in last.sighted.items():
        now = sighted.get(index)
        hurt = now is not None and now.race_id == race and now.hp < hp
        killed = now is None and snapshot.player.exp > last.exp
        if hurt or killed:
            return race, last.counts.get(race, 1), max(sum(last.counts.values()), 1)
    if kill_lines:
        for race, count in last.counts.items():
            name = last.names.get(race)
            if name and shows_kill(snapshot, name):
                return race, count, max(sum(last.counts.values()), 1)
    return None


def shows_kill(snapshot, name: str) -> bool:
    """This board prints the game's kill line for a monster called ``name``."""
    return any(
        message_text(message).removeprefix(_KILL_LINE_PREFIX) == name + line
        for message in snapshot.messages for line in _KILL_LINES
    )


def _note_kill(policy, snapshot) -> None:
    """Remember a kill line of the window's race on this board."""
    name = policy._breeder_last_board.names.get(policy._breeder_engagement_race)
    if name and shows_kill(snapshot, name):
        policy._breeder_engagement_killed = True


def _window_kept(policy, count: int) -> bool:
    """A completed window that goes on: it reduced, or few remain and it killed.

    A window without a race (a floor without a plan) notes no kill."""
    if count < policy._breeder_engagement_start_count:
        return True
    return count < FEW_BREEDERS and policy._breeder_engagement_killed


def _open_window(policy, snapshot, count: int, race: int | None = None) -> None:
    policy._breeder_engagement_race = race
    policy._breeder_engagement_killed = False
    policy._breeder_engagement_start_count = count
    policy._breeder_engagement_start_turn = snapshot.turn
    policy._breeder_engagement_actions = 0
    policy._breeder_engagement_last_turn = snapshot.turn


def flee_due(policy, snapshot, breeders: list) -> bool:
    """Count this board's action; True once a window ended without a reduction.

    Called after this board's decision: whether it attacked a breeder in view is kept for the
    next board, whose action it is."""
    sent = getattr(policy, "_breeder_attack_sent", False)
    due = _flee_due(policy, snapshot, breeders, sent)
    exempt = _exempt_races(policy, snapshot)
    policy._breeder_attack_sent = is_attack_reason(policy.last_reason) and any(
        monster.hostile and monster.can_multiply and monster.race_id not in exempt
        for monster in snapshot.visible_monsters)
    return due


def _flee_due(policy, snapshot, breeders: list, sent: bool) -> bool:
    planned = _counts_from_first_attack(policy, snapshot)
    exempt = _exempt_races(policy, snapshot)
    if exempt:
        breeders = [monster for monster in breeders if monster.race_id not in exempt]
    attacked = _attacked_race(policy, snapshot, breeders, kill_lines=not planned, exempt=exempt)
    if policy._breeder_engagement_start_count is None:
        if attacked is None:
            return False
        if planned:
            _open_window(policy, snapshot, attacked[1], attacked[0])
            _note_kill(policy, snapshot)
        else:
            _open_window(policy, snapshot, attacked[2])
        return False
    race = policy._breeder_engagement_race
    if race is not None:
        breeders = [monster for monster in breeders if monster.race_id == race]
    count = len(breeders)
    if stalemate_standing(policy):
        return True
    last_turn = policy._breeder_engagement_last_turn
    if last_turn is not None and snapshot.turn > last_turn and (sent or attacked is not None):
        policy._breeder_engagement_actions += 1
    policy._breeder_engagement_last_turn = snapshot.turn
    _note_kill(policy, snapshot)
    if policy._breeder_engagement_actions < FLEE_AFTER_PLAYER_ACTIONS:
        return False
    if not _window_kept(policy, count):
        return True
    if breeders:
        _open_window(policy, snapshot, count, race)
    else:
        forget(policy)
    return False
