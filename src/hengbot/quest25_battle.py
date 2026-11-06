"""Quest 25 『幽霊屋敷』 fought phase by phase: ``engagement_plan.revised_plan_draft``.

Owner 2026-11-06 「作り直すまで外す」: n1-b life-323 walked into the hall and took 25 summons.
The redone plan is the draft's owner decisions (strategy/quests/QUEST_25.jsonc, every one
quoted there with its date); this module is their executor.  The phases, in order
(``PHASES``, one row each):

 1. ``ambush`` (phase1): the hound, the skeletal and spectral tyrannosaurs and the vampire
    lord are met in the start region.  「DPSで比較…行動回数で計測」: the actions to kill the
    spectral tyrannosaur by ranged attacks and by melee (attack_expectation, slays and hit
    chance in, the torch out) decide the stand: ranged waits on [13,1] with the door [9,1]
    open, melee waits on [10,1] with it closed and closes in the turn it is opened.
    「どちらにせよ加速を使用する」: hasted while a target is in view.
 2. ``wall-passers`` (phase1_wall_passers): full HP, then [7,1]; what comes is fought; 50
    player actions without a new arrival end it.
 3. ``ipsissimus`` (phase2): full HP, [7,1], haste, [6,1], [5,1], then the strongest attack
    at the pen's [7,17] (the monster's own cell when it is seen).  Others in view: a piercing
    attack (a beam, or a ball or breath aimed at the grid) and a low threat keep the fire on
    the pen; otherwise Teleportation, then a choke before contact (``_rally``).  It ends when
    each of the three is killed or seen out of the pen.
 4. ``stragglers`` (phase1_wall_passers / phase2): on [5,1], the spectres and shadow demons
    that did not come and the Ipsissimus that teleported away are fought as they come; 50
    actions without a new arrival end it.
 5. ``quylthulgs`` (phase3 step 1): with a ball, each quylthulg a ball can catch from a cell
    out of the casters' lines ([5,2], [5,1]; quest25_geometry.ball_centre) is shot until it is
    killed or seen moved.  Without a ball it is skipped.
 6. ``tome`` (phase3 step 2): full HP, haste, then a ball from [5,1]/[5,2] where one reaches
    the tome, else the strongest ranged attack from [5,5], [4,5] or [5,6].
 7. ``corpse-masses`` (phase4): [1,6] by the walk that crosses no corridor trap, the door
    [1,7] opened, the corridor lit when dark (the 11-05 rule), and every mass in view shot.
 8. ``dreadmaster`` (phase5): ranged waits on the edge of its vision ([1,9]), melee on [1,17];
    hasted while it is in view.
 9. ``sweep`` (phase6_sweep): detection when the character has it, else the kill count
    against the roster and, when short, the old room-sweep stands walked as the patrol.
10. ``stairway`` (phase6): full HP, [13,27], haste, the door [13,28], then ranged or a step
    and melee by the actions to kill.  A summons that is not lethal does not stop it.
11. ``druj`` (phase7_druj, after the stairway: the draft orders it last): with a ball and
    Stone to Mud, [13,20], the door [11,19] melted and the ball burst on it; else the door
    opened and the druj shot from a trapless cell in its line.  Teleported away, the walk
    comes back; the Magic-Eater hastes out of the druj's line only.

Between phases (between_phases): a Magic-Eater rests a counted rest until every absorbed
attack power is full, reading the lists turn-free (``b``) to decide (R& does not wait for
them, player-processor.cpp is_fully_healthy).

Traps (phase4, phase5): a corridor cell the map always traps is searched from beside it
until the trap is found, a cell that may hold one (``!``) ten times; a disarming power or
device is aimed first when there is one, the disarm command (``_step_toward``) answers a
found trap.  Walks cross the fewest summon cells while the Ipsissimus live and the fewest
uncleared traps.

Kills are read from the game's kill lines (monster-damage.cpp): the seen ones by the race's
name, an unseen one (何か) as the race the last grid shot was aimed at.

Survival and the summons answer first (dungeon_ladder FLOOR_PLANS): the room sweep's own
survival rungs, then ``_summons`` -- the phase-2 and stairway rules on those phases, the
shared rules (summon_response) elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from hengbot import (
    attack_expectation,
    combat_answer,
    me_capability,
    me_device_attacks,
    me_powers,
    me_powers_refresh,
    once_quest_recall,
    quest25_druj_gear,
    quest25_geometry as geo,
    quest_exposure,
    quest_find_exit,
    quest_room_light,
    quest_room_sweep,
    resist_potion,
    speed_dose,
    summon_response,
)
from hengbot.item_reservation import reserved_item_command
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.me_absorbed_substitutes import CAST_SUFFIX, carry_cast_key
from hengbot.model import (
    Position, SV_ROD_DETECTION, SV_ROD_DISARMING, SV_STAFF_DETECT_EVIL, SV_WAND_DISARMING,
    SV_WAND_TRAP_DOOR_DEST, TVAL_ROD, TVAL_STAFF, TVAL_WAND,
)
from hengbot.policy_constants import DIRECTION_KEYS, REST_MACRO, SEARCH_KEY, WAIT_KEY
from hengbot.quest_find_exit import HOLD_REASON, MELEE_REASON
from hengbot.unseen_strike import message_text

PLAN_KEY = "revised_plan_draft"
REASON = "quest25"
WALK_REASON = f"{REASON}:walk"
OPEN_REASON = f"{REASON}:open-door"
CLOSE_REASON = f"{REASON}:close-door"
SHOT_REASON = f"{REASON}:shot"
SEARCH_REASON = f"{REASON}:trap-search"
DISARM_REASON = f"{REASON}:trap-disarm"
HASTE_REASON = f"{REASON}:haste"
FULL_HP_REASON = f"{REASON}:rest-full"
RECHARGE_REASON = f"{REASON}:rest-recharge"
TELEPORT_REASON = f"{REASON}:teleport"
DETECT_REASON = f"{me_powers.REASON}:quest25-sweep"
MELT_REASON = f"{REASON}:melt-door{CAST_SUFFIX}"
ENGAGE_REASON = f"{REASON}:engage"
RETREAT_REASON = f"{REASON}:druj-out-of-line"
RETREAT_REST_REASON = f"{REASON}:druj-rest-out-of-line"
RETREAT_HEAL_REASON = f"{REASON}:druj-heal-out-of-line"
BLOCKED_REASON = "quest:blocked:quest25-patrol-rounds"
_PLANNED_STEPS = frozenset({WALK_REASON, ENGAGE_REASON, RETREAT_REASON})

# Owner 2026-11-06 「50回来なければ終える」, 「50ターン待っても来なくなったら」(player actions).
QUIET_ACTIONS = 50
# Owner 2026-11-06 wait_limits 「事実上上限無しになる、大きな値を取る。仮に5000にする。」: the ambush
# (phase1) and the dreadmaster's wait (phase5), player actions without an arrival.
LONG_WAIT_ACTIONS = 5000
# Owner 2026-11-06 phase2 「当たらない撃ちで補う」: pen shots in a row with no hit or kill line.
PEN_MISSES_TO_ESCAPED = 10
# The game's lines that a shot found its mark (combat/shoot.cpp exec_shoot).
_HIT_LINES = ("に命中した。", "が敵を捕捉した。", "finds a mark.")
_HIT_LINES_EN = (" hits ",)
# The pain line of a monster a shot or a ball hurt (monster-pain-describer.cpp, every table):
# deal_effect_damage_from_player and exec_shoot print it whenever the monster is within
# MAX_PLAYER_SIGHT (em_ptr->known), seen or not, under monster_desc's name -- 何か / it when unseen.
# [7,17] is 17 from [5,1].  An unseen kill prints 「…を殺した。」 (monster-damage.cpp
# show_kill_message), a _KILL_LINES line.
_PAIN_LINES_JA = frozenset((
    "はうなった。", "はうめいた。", "はうるさく鳴いた。", "はかすかにうめいた。", "はくしゃくしゃになった。",
    "はぐにゃぐにゃと痙攣した。", "はさえずった。", "はしり込みした。", "はのたうち回った。",
    "はほとんど気にとめていない。", "はよろめいた。", "はカタカタと笑った。", "はカタカタ言った。",
    "はガタガタ言った。", "はキーキーと鳴き叫んだ。", "はキーキー鳴いた。", "はギャーギャー鳴いた。",
    "はギャーギャー鳴きわめいた。", "はシーッと鳴いた。", "はピクピクひきつった。", "はピーピー鳴いた。",
    "はヨロヨロ逃げ回った。", "は吠えた。", "は哀れな鳴き声を出した。", "は弱々しくうなった。",
    "は弱々しくうめいた。", "は弱々しく叫んだ。", "は弱々しく吠えた。", "は怒って吠えた。",
    "は怒って頭を上げた。", "は攻撃に肩をすくめた。", "は攻撃を気にとめていない。", "は泣きわめいた。",
    "は猛然と威嚇した。", "は痛みでうなった。", "は痛みでキャンキャン吠えた。", "は痛みでシーッと鳴いた。",
    "は痛みで叫んだ。", "は痛みで弱々しく鳴いた。", "は痛みで絶叫した。", "は痛みで鳴きわめいた。",
    "は痛みに吠えた。", "は痛みに痙攣した。", "は痛みに震えた。", "は縮こまった。", "は苦しげにうめいた。",
    "は苦しげに叫んだ。", "は苦しげに吠えた。", "は苦しんだ。", "は苦痛でもだえ苦しんだ。", "は苦痛で痙攣した。",
    "は苦痛で身もだえした。", "は苦痛にうめいた。", "は苦痛のあまり絶叫した。", "は苦痛のあまり鳴きわめいた。",
    "は躊躇した。", "は身もだえした。", "は雷鳴のように吠えた。",
))
_PAIN_LINES_EN = frozenset((
    " grunts.", " groans.", " moans.", " twitters.", " sighs.", " crumples.", " jerks limply.", " chirps.",
    " flinches.", " flutters about.", " barely notices.", " staggers.", " stumbles.", " rattles.",
    " clatters.", " squeaks.", " chitters.", " squawks.", " chatters.", " hisses.", " twitches.",
    " scuttles about.", " howls.", " roars.", " mewls pitifully.", " snarls feebly.", " moans softly.",
    " cries out feebly.", " yelps feebly.", " growls angrily.", " rears up in anger.",
    " shrugs off the attack.", " ignores the attack.", " wails.", " hisses furiously.", " grunts with pain.",
    " snarls with pain.", " yelps in pain.", " hisses in pain.", " hisses with pain.", " cries out in pain.",
    " squeals in pain.", " mewls in pain.", " screams in pain.", " shrieks in pain.", " howls in pain.",
    " roars with pain.", " jerks in pain.", " quivers in pain.", " squelches.", " gasps.", " rumbles.",
    " jeers.", " writhes in agony.", " jerks in agony.", " hisses in agony.", " screams in agony.",
    " shrieks in agony.", " howls in agony.", " hesitates.", " writhes about.", " roars thunderously.",
))


def _pain_of(text: str, names) -> bool:
    """A pain line of a monster called one of ``names`` (or the unseen 何か / It)."""
    for name in (*names, *_UNSEEN):
        if text.startswith(name):
            rest = text[len(name):]
            if rest in _PAIN_LINES_JA or rest in _PAIN_LINES_EN:
                return True
    return False
# mspell-floor.cpp spell_RF6_TPORT, printed only while the caster is seen.
_TELEPORT_LINE = "がテレポートした。"
_TELEPORT_LINE_EN = " teleports away."
# Owner 2026-11-06 「10回で打ち切る」: searches of a cell that may hold a trap.
MAYBE_TRAP_SEARCHES = 10
# The counted rest between phases (between_phases 「回数を指定して休み、回数を見て続けるかを
# 決める」); the count is the Q34 recharge's (q34_recharge, LUNA-REPORT-me-rest-recharge).
RECHARGE_REST_KEY = "R100\r"
# The rest that ends at full HP/MP (player-processor.cpp).
FULL_HP_REST_KEY = REST_MACRO
# Distances the draft weighs the ranged hit chance at: 「[4,1] で距離9」 for the spectral
# tyrannosaur; the stairway 「[13,27] から階段までは距離2」.  The dreadmaster's fight has
# no distance in the draft: it is weighed at the same 9.
COMPARE_DISTANCE = {geo.SPECTRAL_T: 9, geo.DREADMASTER: 9, geo.STAIRWAY: 2}
# Never-moving casters left to their own phases: no shot, no wait for them elsewhere.
_LATER_IMMOBILE = frozenset({geo.IPSISSIMUS, geo.TOME, geo.QUYL, geo.DRUJ, geo.STAIRWAY, geo.MASS})
_KILL_LINES = ("は死んだ。", "を葬り去った。", "を倒した。", "を殺した。")
_KILL_LINES_EN = ("You have slain ", "You have destroyed ", "You have killed ")
_UNSEEN = ("何か", "it", "It")
_ECHIZEN = "せっかくだから"


# -- memory ----------------------------------------------------------------------------


@dataclass
class Battle:
    """One floor visit of the plan (``QuestFloorNavigator.phase_battle``)."""
    phase: int = 0
    kills: dict = field(default_factory=dict)        # race -> kills read from kill lines
    ready: bool = False            # this phase's preparation is done
    quiet: int = 0                 # actions without a new arrival (the 50-action waits)
    seen: frozenset = frozenset()  # monster indices seen in this phase
    escaped: frozenset = frozenset()   # Ipsissimus indices seen out of the pen
    rallying: bool = False         # phase 2: read Teleportation, hold a choke first
    aimed_race: int | None = None  # the race the last unseen grid shot was aimed at
    searches: dict = field(default_factory=dict)     # trap cell -> searches
    cleared: frozenset = frozenset()   # trap cells answered (disarmed, aimed at, searched out)
    found: frozenset = frozenset()     # trap cells seen with their trap
    quyls_done: frozenset = frozenset()
    style: str | None = None       # "ranged" / "melee" of the phase's choice
    lit: bool = False
    melted: bool = False
    detected: tuple | None = None  # the sweep's detection: cells of what it showed
    detect_turn: int = -1
    patrol_stage: int = 0
    patrol_round: int = 0
    browsed: frozenset = frozenset()   # list kinds read since the last counted rest
    teleports: int = 0             # 「〜がテレポートした。」 lines naming an Ipsissimus
    pen_shot: bool = False         # the last key was a shot at the pen
    pen_misses: int = 0            # pen shots in a row with no hit or kill line
    assumed_escaped: int = 0       # 「当たらない撃ちで補う」: counted escaped after the misses
    aimed_quyl: tuple | None = None    # the quylthulg cell the last shot was aimed at
    displaced: tuple | None = None     # (slot, signature) the druj's anti-teleport piece displaced
    retreating: bool = False       # below the line with the anti-teleport piece on: out of the line
    retreat_rest_hp: int | None = None  # HP when the last rest out of the line was keyed
    observed: tuple | None = None      # the board last read (key and walk_key share one)


def _memory(navigator) -> Battle:
    if navigator.phase_battle is None:
        navigator.phase_battle = Battle()
    return navigator.phase_battle


def _next_phase(battle: Battle) -> None:
    kept = {name: getattr(battle, name) for name in (
        "phase", "kills", "searches", "cleared", "found", "escaped", "quyls_done",
        "melted", "lit", "observed", "teleports", "assumed_escaped", "displaced")}
    kept["phase"] += 1
    fresh = Battle(**kept)
    battle.__dict__.update(fresh.__dict__)


# -- who runs the floor -----------------------------------------------------------------


def _profile(policy, snapshot):
    """The approved Q25 profile with the revised plan, on its own taken floor; else None."""
    if policy._active_fixed_quest_id(snapshot) != geo.QUEST_ID:
        return None
    profile = policy.approved_quest_strategy(geo.QUEST_ID)
    if profile is None or PLAN_KEY not in profile.engagement_plan:
        return None
    return profile


def applies(policy, snapshot) -> bool:
    """This plan runs the floor (quest_room_sweep steps aside for it)."""
    return _profile(policy, snapshot) is not None


def holds(policy, snapshot) -> bool:
    return policy.last_reason == HOLD_REASON and applies(policy, snapshot)


def planned_step(policy, snapshot) -> bool:
    return policy.last_reason in _PLANNED_STEPS and applies(policy, snapshot)


def walks_over_traps(policy, snapshot) -> bool:
    """The plan answers its own traps (trap_warning leaves the step to it)."""
    return applies(policy, snapshot)


@dataclass
class _Ctx:
    policy: object
    snapshot: object
    profile: object
    navigator: object
    battle: Battle

    @property
    def here(self) -> tuple[int, int]:
        return self.snapshot.player.position.y, self.snapshot.player.position.x

    @property
    def terrain(self) -> dict:
        return self.navigator.battlefield.terrain

    def door_closed(self, cell) -> bool:
        return quest_room_sweep._door_is_closed(self.snapshot, tuple(cell))

    def open_terrain(self) -> dict:
        return quest_room_sweep._open_terrain(self.navigator, self.snapshot)

    def hostiles(self) -> list:
        return [monster for monster in (*self.snapshot.visible_monsters,
                                        *self.snapshot.detected_monsters) if monster.hostile]

    def in_view(self) -> list:
        return [monster for monster in self.snapshot.visible_monsters
                if monster.hostile and monster.perception != "detected"]

    def kills(self, race: int) -> int:
        return self.battle.kills.get(race, 0)


def _ctx(policy, snapshot):
    profile = _profile(policy, snapshot)
    if profile is None:
        return None
    navigator = quest_room_sweep._navigator(policy, snapshot, geo.QUEST_ID)
    return _Ctx(policy, snapshot, profile, navigator, _memory(navigator))


# -- what the board says ----------------------------------------------------------------


def _names(policy, race: int) -> tuple[str, ...]:
    knowledge = attack_expectation.race_knowledge(policy, race)
    return tuple(name for name in (knowledge.names if knowledge is not None else ()) if name)


def _killed_name(text: str) -> str | None:
    """The victim's name of a kill line the player's attack prints, else None."""
    text = text.removeprefix(_ECHIZEN)
    for line in _KILL_LINES:
        if text.endswith(line):
            return text[:-len(line)]
    for line in _KILL_LINES_EN:
        if text.startswith(line) and text.endswith("."):
            return text[len(line):-1].removeprefix("the ").removeprefix("The ")
    return None


def _note_kills(ctx: _Ctx) -> None:
    races = {name: race for race in geo.ROSTER for name in _names(ctx.policy, race)}
    kills = dict(ctx.battle.kills)
    for message in ctx.snapshot.messages:
        victim = _killed_name(message_text(message))
        if victim is None:
            continue
        race = races.get(victim)
        if race is None and victim in _UNSEEN:
            race = ctx.battle.aimed_race
        if race is not None:
            kills[race] = kills.get(race, 0) + 1
            if race == geo.QUYL and ctx.battle.aimed_quyl is not None:
                ctx.battle.quyls_done = ctx.battle.quyls_done | {ctx.battle.aimed_quyl}
    ctx.battle.kills = kills
    ipsissimus = _names(ctx.policy, geo.IPSISSIMUS)
    for message in ctx.snapshot.messages:
        text = message_text(message)
        name = (text[:-len(_TELEPORT_LINE)] if text.endswith(_TELEPORT_LINE)
                else text[:-len(_TELEPORT_LINE_EN)].removeprefix("The ") if text.endswith(_TELEPORT_LINE_EN)
                else None)
        if name is not None and name in ipsissimus:
            ctx.battle.teleports += 1   # 「テレポートしたメッセージで判断」


def sees_ipsissimus_unseen(snapshot) -> bool:
    """Telepathy or evil ESP: an Ipsissimus is seen from [5,1] without a line (monster-update.cpp)."""
    return "telepathy" in snapshot.player.abilities or any(
        112 in item.known_flags for item in snapshot.equipment)   # TR_ESP_EVIL


def _note_pen_shot(ctx: _Ctx) -> None:
    """「[7,17] への撃ちで命中や倒したメッセージが10回続けて出なければ、まだ倒していない分は逃げたとみなす」,
    only without telepathy or evil ESP."""
    battle = ctx.battle
    if not battle.pen_shot:
        return
    battle.pen_shot = False
    texts = [message_text(message) for message in ctx.snapshot.messages]
    names = _names(ctx.policy, geo.IPSISSIMUS)
    answered = any(_killed_name(text) is not None or text.endswith(_HIT_LINES)
                   or any(line in text for line in _HIT_LINES_EN) or _pain_of(text, names)
                   for text in texts)
    battle.pen_misses = 0 if answered else battle.pen_misses + 1
    if battle.pen_misses >= PEN_MISSES_TO_ESCAPED and not sees_ipsissimus_unseen(ctx.snapshot):
        battle.assumed_escaped = max(0, geo.ROSTER[geo.IPSISSIMUS] - ctx.kills(geo.IPSISSIMUS)
                                     - _escaped_count(ctx, assumed=False))


def _note_arrivals(ctx: _Ctx) -> None:
    """A new monster in view this phase restarts the 50-action wait; Ipsissimus out of the
    pen is escaped."""
    seen = {monster.index for monster in ctx.hostiles()}
    if seen - ctx.battle.seen:
        ctx.battle.quiet = 0
    ctx.battle.seen = ctx.battle.seen | seen
    out = {monster.index for monster in ctx.hostiles() if monster.race_id == geo.IPSISSIMUS
           and (monster.position.y, monster.position.x) not in geo.IPSISSIMUS_PEN}
    ctx.battle.escaped = ctx.battle.escaped | out


def _race_hp(policy, race: int) -> float:
    knowledge = attack_expectation.race_knowledge(policy, race)
    if knowledge is None:
        return 0.0
    return float(knowledge.max_hp if "FORCE_MAXHP" in knowledge.flags else knowledge.average_hp)


def melee_is_fewer(policy, snapshot, race: int, *, steps: int = 0) -> bool:
    """「必要な行動回数」: melee (plus ``steps`` to reach) kills in fewer actions than ranged."""
    hp = _race_hp(policy, race)
    ranged = attack_expectation.actions_to_kill(hp, attack_expectation.ranged_against(
        policy, snapshot, race, COMPARE_DISTANCE.get(race, 9)))
    melee = attack_expectation.actions_to_kill(
        hp, attack_expectation.melee_against(policy, snapshot, race)) + steps
    return melee < ranged


# -- walking ----------------------------------------------------------------------------


def _escaped_count(ctx: _Ctx, *, assumed: bool = True) -> int:
    """Seen out of the pen, or named teleporting; and, after the misses, the rest."""
    return (max(len(ctx.battle.escaped), ctx.battle.teleports)
            + (ctx.battle.assumed_escaped if assumed else 0))


def _ipsissimus_alive(ctx: _Ctx) -> bool:
    return ctx.kills(geo.IPSISSIMUS) + _escaped_count(ctx) < geo.ROSTER[geo.IPSISSIMUS]


def _avoided(ctx: _Ctx) -> set:
    """The cells a walk crosses as few of as it can."""
    bf = ctx.navigator.battlefield
    cells = {cell for cell in (*bf.trap_cells, *bf.maybe_trap_cells) if cell not in ctx.battle.cleared}
    if _ipsissimus_alive(ctx):
        cells |= geo.summon_cells(ctx.terrain)
    return cells


def _path(ctx: _Ctx, goals) -> list[tuple[int, int]]:
    goals = {tuple(goal) for goal in goals}
    start = ctx.here
    occupied = frozenset((monster.position.y, monster.position.x) for monster in ctx.in_view())
    exposure = geo.exposure_of(_avoided(ctx))
    for water in (False, True):
        terrain = quest_room_sweep._terrain_of(ctx.navigator, ctx.snapshot, water=water)
        terrain[start] = "floor"
        path = quest_exposure.least_exposed_path(terrain, exposure, start, goals, occupied - goals)
        if path:
            return path
    return []


def _step(ctx: _Ctx, cell, reason: str = WALK_REASON) -> str:
    ctx.policy.last_reason = reason
    return ctx.policy._step_toward(ctx.snapshot, Position(*cell))


def _walk(ctx: _Ctx, goals, reason: str = WALK_REASON) -> str | None:
    """The next step toward ``goals`` (the trap rule first); None there or with no way."""
    path = _path(ctx, goals)
    if len(path) < 2:
        return None
    nxt = path[1]
    trap = _trap_key(ctx, nxt)
    if trap is not None:
        return trap
    ctx.policy._declare_reach(Position(*path[-1]))
    return _step(ctx, nxt, reason)


def _direction(origin, cell) -> str:
    return DIRECTION_KEYS[((cell[0] > origin[0]) - (cell[0] < origin[0]),
                           (cell[1] > origin[1]) - (cell[1] < origin[1]))]


# -- traps (phase4, phase5) -------------------------------------------------------------


def _disarm_device_key(ctx: _Ctx, cell) -> str | None:
    """「トラップ解除手段があるなら使う」: an absorbed disarming power, else a carried one."""
    key = me_powers.power_key(ctx.policy, ctx.snapshot, me_powers.TRAP, Position(*cell))
    if key is not None:
        return key
    player = ctx.snapshot.player
    if player.blind or player.confused:
        return None
    for tval, svals, verb in ((TVAL_ROD, (SV_ROD_DISARMING,), "rod"),
                              (TVAL_WAND, (SV_WAND_DISARMING, SV_WAND_TRAP_DOOR_DEST), "wand")):
        item = next((item for item in ctx.snapshot.inventory if item.tval == tval and item.known
                     and item.sval in svals and not item.charging
                     and (tval == TVAL_ROD or item.charges > 0)), None)
        if item is not None:
            key = reserved_item_command(ctx.policy, ctx.snapshot, verb, item,
                                        suffix=_direction(ctx.here, cell))
            if key is not None:
                ctx.policy.last_reason = DISARM_REASON
                return key
    return None


def _trap_key(ctx: _Ctx, cell) -> str | None:
    """Before stepping onto a trap cell of the map: what the owner's rule asks there."""
    bf, battle = ctx.navigator.battlefield, ctx.battle
    always, maybe = cell in bf.trap_cells, cell in bf.maybe_trap_cells
    if not (always or maybe) or cell in battle.cleared:
        return None
    grid = ctx.snapshot.grid_at(Position(*cell))
    if grid is not None and grid.trap:
        battle.found = battle.found | {cell}
        ctx.policy.last_reason = DISARM_REASON
        return ctx.policy._step_toward(ctx.snapshot, Position(*cell))   # the disarm command
    if cell in battle.found:   # seen with its trap, now without: disarmed
        battle.cleared = battle.cleared | {cell}
        return None
    device = _disarm_device_key(ctx, cell)
    if device is not None:
        battle.cleared = battle.cleared | {cell}
        return device
    searched = battle.searches.get(cell, 0)
    if maybe and searched >= MAYBE_TRAP_SEARCHES:
        battle.cleared = battle.cleared | {cell}   # 「罠は無いとみなして通る」
        return None
    battle.searches = {**battle.searches, cell: searched + 1}
    ctx.policy.last_reason = SEARCH_REASON
    return SEARCH_KEY


# -- attacks ----------------------------------------------------------------------------


def _ball_powers(ctx: _Ctx, race: int):
    """(expected damage, radius, shape, key maker) of each ball or breath the character can aim
    at a grid: absorbed powers and carried wands and rods, strongest first."""
    snapshot, policy = ctx.snapshot, ctx.policy
    flags = attack_expectation.race_knowledge(policy, race)
    flags = flags.flags if flags is not None else None
    level = snapshot.player.level
    found = []
    if me_device_attacks.can_use_powers(snapshot):
        for power, success in me_device_attacks.usable_powers(policy):
            if power.shape in me_device_attacks.TARGETABLE_SHAPES and not power.group_only:
                found.append((success * me_device_attacks.expected_damage(power, level, flags),
                              me_device_attacks.AREA_RADIUS[power.shape], power.shape,
                              lambda grid, power=power: me_device_attacks.device_target_key(
                                  policy, power, Position(*grid))))
    if not (snapshot.player.blind or snapshot.player.confused):
        for item in snapshot.inventory:
            kind = {TVAL_WAND: "wand", TVAL_ROD: "rod"}.get(item.tval)
            power = me_device_attacks.POWERS.get((kind, item.sval)) if kind else None
            if (power is None or power.shape not in me_device_attacks.TARGETABLE_SHAPES
                    or not item.known or item.charging or (kind == "wand" and item.charges <= 0)):
                continue
            chance = (attack_expectation.device_use_success if kind == "wand"
                      else attack_expectation.rod_use_success)(snapshot.player.device_skill, power.level)
            found.append((chance * me_device_attacks.expected_damage(power, level, flags),
                          me_device_attacks.AREA_RADIUS[power.shape], power.shape,
                          lambda grid, item=item, kind=kind: _carried_grid_key(ctx, kind, item, grid)))
    return sorted(found, key=lambda row: -row[0])


def _cursor_suffix(ctx: _Ctx, grid) -> str:
    """get_aim_dir's free-cursor walk to ``grid`` (policy_combat ``ranged:fire-offset``)."""
    return "*p" + ctx.policy._cursor_delta_keys(ctx.snapshot.player.position, Position(*grid)) + "t5\x1b"


def _carried_grid_key(ctx: _Ctx, kind: str, item, grid) -> str | None:
    key = reserved_item_command(ctx.policy, ctx.snapshot, kind, item, suffix=_cursor_suffix(ctx, grid))
    if key is not None:
        ctx.policy.last_reason = SHOT_REASON
    return key


def _launcher_grid_key(ctx: _Ctx, grid) -> str | None:
    ammo = ctx.policy._matching_ammo(ctx.snapshot)
    if ammo is None or ctx.snapshot.player.blind or ctx.snapshot.player.confused:
        return None
    key = reserved_item_command(ctx.policy, ctx.snapshot, "fire", ammo, suffix=_cursor_suffix(ctx, grid))
    if key is not None:
        ctx.policy.last_reason = SHOT_REASON
    return key


def _beam_key(ctx: _Ctx, race: int, grid) -> tuple[float, Callable] | None:
    """The best absorbed beam along a ray to ``grid`` (a bolt-or-beam counts at its beam chance)."""
    snapshot = ctx.snapshot
    direction = me_powers.beam_direction(ctx.policy, snapshot, snapshot.player.position, Position(*grid))
    if direction is None or not me_device_attacks.can_use_powers(snapshot):
        return None
    flags = attack_expectation.race_knowledge(ctx.policy, race)
    flags = flags.flags if flags is not None else None
    best = None
    for power, success in me_device_attacks.usable_powers(ctx.policy):
        share = 1.0 if power.shape == "beam" else power.beam_percent / 100
        if share <= 0 or power.group_only:
            continue
        damage = success * share * me_device_attacks.expected_damage(power, snapshot.player.level, flags)
        if best is None or damage > best[0]:
            best = (damage, lambda power=power: me_device_attacks.device_key(ctx.policy, power, direction))
    return best


def _fire_at(ctx: _Ctx, grid, race: int, *, piercing: bool = False, area_only: bool = False) -> str | None:
    """The strongest attack aimed at ``grid`` (「一番ダメージの出る攻撃」); ``piercing``: only one
    that passes the bodies on the way (a beam, a ball or a breath aimed at the grid)."""
    options = [(damage, lambda make=make: make(grid))
               for damage, radius, shape, make in _ball_powers(ctx, race)
               if not area_only or shape == "ball"]
    if not area_only:
        if (beam := _beam_key(ctx, race, grid)) is not None:
            options.append(beam)
        if not piercing:
            distance = quest_exposure.game_distance(ctx.here, tuple(grid))
            launcher = attack_expectation.launcher_against(ctx.policy, ctx.snapshot, race, distance)
            if launcher > 0:
                options.append((launcher, lambda: _launcher_grid_key(ctx, grid)))
    for _damage, make in sorted(options, key=lambda row: -row[0]):
        key = make()
        if key is not None:
            ctx.battle.aimed_race = race
            return key
    return None


def _has_piercing(ctx: _Ctx, race: int, grid) -> bool:
    return bool(_ball_powers(ctx, race)) or _beam_key(ctx, race, grid) is not None


def _balls(ctx: _Ctx, race: int) -> list:
    return [row for row in _ball_powers(ctx, race) if row[2] == "ball"]


def _engage(ctx: _Ctx, targets) -> str | None:
    """Beside the player, the blow; else a shot at the first that can be shot."""
    policy, snapshot = ctx.policy, ctx.snapshot
    beside = [monster for monster in targets if monster.distance <= 1]
    if beside:
        struck = summon_response.named_casters_first(policy, beside)[:1]
        answer = combat_answer.adjacent_attack(policy, snapshot, struck, MELEE_REASON)
        if answer is not None and answer.key is not None:
            return answer.key
    for target in targets:
        if target.distance > 1 and (shot := quest_room_sweep._shot(policy, snapshot, target)) is not None:
            ctx.battle.aimed_race = None
            return shot
    return None


def _fight_targets(ctx: _Ctx) -> list:
    """What this phase fights in view: every mover, not the immobile casters of later phases."""
    return [monster for monster in ctx.in_view() if monster.race_id not in _LATER_IMMOBILE]


def _hold(ctx: _Ctx) -> str:
    ctx.policy.last_reason = HOLD_REASON
    return WAIT_KEY


def _haste(ctx: _Ctx) -> str | None:
    if ctx.policy._player_hasted(ctx.snapshot):
        return None
    return speed_dose.key(ctx.policy, ctx.snapshot, HASTE_REASON)


# -- between phases ---------------------------------------------------------------------


def _attack_kinds(ctx: _Ctx) -> set[str]:
    return {kind for (kind, sval) in me_device_attacks.POWERS
            if me_capability.has(ctx.policy, ctx.snapshot, kind, sval)}


def _full(power, row) -> bool:
    if power.kind == "rod":
        return row.get("charging") == 0
    return isinstance(row.get("current"), int) and row.get("current") == row.get("max")


def _recharge_key(ctx: _Ctx) -> str | None:
    """「攻撃に使うものを全快させる」: browse a stale list, else a counted rest while one is short."""
    if ctx.snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER:
        return None
    lists = getattr(ctx.policy, "_me_device_lists", None) or {}
    for kind in sorted(_attack_kinds(ctx)):
        if kind not in lists or kind not in ctx.battle.browsed:
            ctx.battle.browsed = ctx.battle.browsed | {kind}
            browse = "b" + me_powers_refresh.KIND_LETTER[kind]
            ctx.policy.last_reason = me_powers_refresh.REFRESH_REASON
            ctx.policy._offer_execution(
                browse, producer="bookkeeping", work_id="quest25-recharge-read",
                next_step="magic-eater.browse.send", arguments=(kind,),
                expected_effect="magic-eater-power-list-observed")
            return browse
    short = any(not _full(power, row)
                for kind in _attack_kinds(ctx) for row in lists[kind][1]
                if (power := me_device_attacks._BY_NAME.get((kind, row.get("name")))) is not None)
    if not short:
        return None
    ctx.battle.browsed = frozenset()
    ctx.policy.last_reason = RECHARGE_REASON
    return RECHARGE_REST_KEY


def _full_hp_key(ctx: _Ctx) -> str | None:
    player = ctx.snapshot.player
    if player.hp >= player.max_hp:
        return None
    ctx.policy.last_reason = FULL_HP_REASON
    return FULL_HP_REST_KEY


def _prepare(ctx: _Ctx, phase) -> str | None:
    """On a quiet board, before the phase's first step: the recharge, then full HP."""
    if ctx.battle.ready:
        return None
    if ctx.in_view():
        return None
    key = (_recharge_key(ctx) if ctx.battle.phase else None) or (
        _full_hp_key(ctx) if phase.full_hp else None)
    if key is None:
        ctx.battle.ready = True
    return key


# -- the phases -------------------------------------------------------------------------


def _ambush_done(ctx: _Ctx) -> bool:
    return all(ctx.kills(race) >= geo.ROSTER[race]
               for race in (geo.HOUND, geo.SKELETAL_T, geo.VAMPIRE, geo.SPECTRAL_T))


def _ambush(ctx: _Ctx) -> str | None:
    battle = ctx.battle
    if battle.style is None:
        battle.style = "melee" if melee_is_fewer(ctx.policy, ctx.snapshot, geo.SPECTRAL_T) else "ranged"
    targets = _fight_targets(ctx)
    if targets and (haste := _haste(ctx)) is not None:
        return haste      # 「どちらにせよ加速を使用する」
    door = geo.WEST_DOOR
    if battle.style == "ranged":
        if (key := _engage(ctx, targets)) is not None:
            return key
        if ctx.door_closed(door):
            if quest_exposure.game_distance(ctx.here, door) <= 1:
                ctx.policy.last_reason = OPEN_REASON
                return ctx.policy._step_toward(ctx.snapshot, Position(*door))
            return _walk(ctx, {(door[0] + 1, door[1])})
        return _walk(ctx, {geo.MEET_RANGED}) or _hold(ctx)
    # Melee: the closed door, met the turn it opens (「相手が開けたターンに接敵」).
    beside = [monster for monster in targets if monster.distance <= 1]
    if beside:
        return _engage(ctx, beside)
    if ctx.here != geo.MEET_MELEE:
        return _walk(ctx, {geo.MEET_MELEE}) or _hold(ctx)
    if not ctx.door_closed(door):
        coming = [monster for monster in targets
                  if quest_exposure.game_distance((monster.position.y, monster.position.x), door) <= 1]
        if coming:
            return _step(ctx, door, ENGAGE_REASON)
        if not targets:
            ctx.policy.last_reason = CLOSE_REASON
            return "c"     # easy_open closes the one open door beside, asking no direction
    return _hold(ctx)


def _wall_passers_done(ctx: _Ctx) -> bool:
    return (ctx.kills(geo.SPECTRE) >= geo.ROSTER[geo.SPECTRE]
            and ctx.kills(geo.SHADOW) >= geo.ROSTER[geo.SHADOW])


def _wall_passers(ctx: _Ctx) -> str | None:
    targets = _fight_targets(ctx)
    if (key := _engage(ctx, targets)) is not None:
        return key
    return _walk(ctx, {geo.WALL_PASSER_STAND}) or _hold(ctx)


def _ipsissimus_done(ctx: _Ctx) -> bool:
    return not _ipsissimus_alive(ctx)


def _rally(ctx: _Ctx) -> str | None:
    """After the teleport: 「接敵する前に移動できるなら、なるべく隘路に陣取る」."""
    targets = _fight_targets(ctx)
    if any(monster.distance <= 1 for monster in targets):
        return _engage(ctx, targets)
    summons = geo.summon_cells(ctx.terrain)
    chokes = {cell for cell in ctx.navigator.battlefield.chokepoints if cell not in summons}
    if ctx.here in chokes:
        if targets:
            return _engage(ctx, targets) or _hold(ctx)
        ctx.battle.rallying = False
        return None
    return _walk(ctx, chokes) or _engage(ctx, targets)


def _ipsissimus(ctx: _Ctx) -> str | None:
    battle, policy, snapshot = ctx.battle, ctx.policy, ctx.snapshot
    if battle.rallying and (key := _rally(ctx)) is not None:
        return key
    walk = geo.PHASE2_WALK
    if ctx.here not in walk:
        return _walk(ctx, {walk[0]})
    if ctx.here == walk[0] and (haste := _haste(ctx)) is not None:
        return haste    # 「事前に加速して(6,1)(5,1)と移動」
    if ctx.here != walk[-1]:
        return _step(ctx, walk[walk.index(ctx.here) + 1])
    seen = [monster for monster in ctx.hostiles() if monster.race_id == geo.IPSISSIMUS
            and (monster.position.y, monster.position.x) in geo.IPSISSIMUS_PEN]
    aim = (seen[0].position.y, seen[0].position.x) if seen else geo.IPSISSIMUS_AIM
    others = [monster for monster in ctx.in_view() if monster.race_id != geo.IPSISSIMUS]
    if others:
        # 「貫通可能な攻撃かつ脅威度が高くない場合は先にイプシシマスを倒し増援を断つ」
        threat = policy._is_material_threat(snapshot, policy._physical_hostiles(snapshot))
        if not threat and _has_piercing(ctx, geo.IPSISSIMUS, aim):
            return _pen_shot(ctx, _fire_at(ctx, aim, geo.IPSISSIMUS, piercing=True))
        scroll = policy._find_teleport_scroll(snapshot) if policy._can_read_scrolls(snapshot) else None
        if scroll is not None:
            battle.rallying = True
            policy.last_reason = TELEPORT_REASON
            return policy._read_key(snapshot, scroll)
        return _engage(ctx, others)
    return _pen_shot(ctx, _fire_at(ctx, aim, geo.IPSISSIMUS))


def _pen_shot(ctx: _Ctx, key: str | None) -> str | None:
    ctx.battle.pen_shot = key is not None
    return key


def _stragglers_done(ctx: _Ctx) -> bool:
    left = (ctx.kills(geo.SPECTRE) < geo.ROSTER[geo.SPECTRE]
            or ctx.kills(geo.SHADOW) < geo.ROSTER[geo.SHADOW]
            or ctx.kills(geo.IPSISSIMUS) < geo.ROSTER[geo.IPSISSIMUS])
    return not left


def _stragglers(ctx: _Ctx) -> str | None:
    targets = [monster for monster in ctx.in_view()
               if monster.race_id not in _LATER_IMMOBILE - {geo.IPSISSIMUS}]
    if (key := _engage(ctx, targets)) is not None:
        return key
    return _walk(ctx, {geo.STRAGGLER_STAND}) or _hold(ctx)


def _quyl_plan(ctx: _Ctx):
    """(quyl cell, stand, centre) of the next quylthulg a ball catches from a safe stand; then,
    with balls that catch none from there (owner 2026-11-06 「加速して直接撃つ」), (quyl cell,
    None, None): it is shot directly from a cell with a line to it."""
    radii = sorted({row[1] for row in _balls(ctx, geo.QUYL)}, reverse=True)
    left = [cell for cell, race in ctx.navigator.battlefield.monster_placements
            if race == geo.QUYL and cell not in ctx.battle.quyls_done]
    for cell in left:
        for radius in radii:
            for stand in geo.QUYL_STANDS:
                found = geo.ball_centre(ctx.terrain, stand, cell, radius)
                if found is not None:
                    return cell, stand, found[1]
    if radii and left:
        return left[0], None, None
    return None


def _quyl_line_cells(ctx: _Ctx, cell) -> set:
    """Dry cells with a line of fire to ``cell`` (the projection port), within a shot's reach."""
    return {spot for spot in geo.line_cells(ctx.terrain, cell)
            if ctx.terrain.get(spot) == "floor"
            and quest_exposure.game_distance(spot, cell) <= quest_exposure.MAX_SPELL_RANGE}


def _note_quyls(ctx: _Ctx) -> None:
    """A quylthulg seen off its cell has moved; one killed is done (in placement order)."""
    placed = [cell for cell, race in ctx.navigator.battlefield.monster_placements if race == geo.QUYL]
    seen = {(monster.position.y, monster.position.x) for monster in ctx.hostiles()
            if monster.race_id == geo.QUYL}
    done = set(ctx.battle.quyls_done)
    if seen - set(placed):
        done |= {cell for cell in placed if cell not in seen}
    ctx.battle.quyls_done = frozenset(done)


def _quyls_done(ctx: _Ctx) -> bool:
    _note_quyls(ctx)
    return _quyl_plan(ctx) is None


_FACED = frozenset({geo.IPSISSIMUS, geo.DREADMASTER})


def _quyls(ctx: _Ctx) -> str | None:
    plan = _quyl_plan(ctx)
    if plan is None:
        return None
    # 「テレポート・アウェイを受けるとイプシシマスの残党やドリードマスターと相対する可能性がある。
    # その場合は加速して討伐を試みる。」
    faced = [monster for monster in ctx.in_view() if monster.race_id in _FACED]
    if faced:
        return _haste(ctx) or _engage(ctx, faced) or _hold(ctx)
    cell, stand, centre = plan
    ctx.battle.aimed_quyl = cell
    if stand is None:
        lines = _quyl_line_cells(ctx, cell)
        if ctx.here not in lines:
            return _walk(ctx, lines)   # 「飛ばされたら戻って撃ち直す」
        return _haste(ctx) or _fire_at(ctx, cell, geo.QUYL)
    if ctx.here != stand:
        return _walk(ctx, {stand})
    return _fire_at(ctx, centre, geo.QUYL, area_only=True)


def _tome_done(ctx: _Ctx) -> bool:
    return ctx.kills(geo.TOME) >= geo.ROSTER[geo.TOME]


def _tome(ctx: _Ctx) -> str | None:
    tome = next(cell for cell, race in ctx.navigator.battlefield.monster_placements if race == geo.TOME)
    for _damage, radius, _shape, _make in _balls(ctx, geo.TOME):
        for stand in geo.QUYL_STANDS:   # 「半径3の球を先に使う」: from out of its lines first
            found = geo.ball_centre(ctx.terrain, stand, tome, radius)
            if found is None:
                continue
            if ctx.here != stand:
                return _walk(ctx, {stand})
            return _haste(ctx) or _fire_at(ctx, found[1], geo.TOME, area_only=True)
    stands = [stand for stand in geo.TOME_NEAR_STANDS if _path(ctx, {stand}) or ctx.here == stand]
    if not stands:
        return None
    if ctx.here not in stands:
        return _walk(ctx, {stands[0]})
    return _haste(ctx) or _fire_at(ctx, tome, geo.TOME)


def _masses_seen(ctx: _Ctx) -> list:
    return [monster for monster in ctx.hostiles() if monster.race_id == geo.MASS]


def _masses_done(ctx: _Ctx) -> bool:
    return (ctx.here == geo.MASS_STAND and not ctx.door_closed(geo.MASS_DOOR) and ctx.battle.lit
            and not _masses_seen(ctx))


def _masses(ctx: _Ctx) -> str | None:
    if ctx.here != geo.MASS_STAND:
        return _walk(ctx, {geo.MASS_STAND})
    if ctx.door_closed(geo.MASS_DOOR):
        ctx.policy.last_reason = OPEN_REASON
        return ctx.policy._step_toward(ctx.snapshot, Position(*geo.MASS_DOOR))
    if not ctx.battle.lit:
        ctx.battle.lit = True
        light = quest_room_light.light_room_key(
            ctx.policy, ctx.snapshot, ctx.navigator, ctx.open_terrain(), quest_room_light.LIGHT_REASON)
        if light is not None:
            return light
    for monster in sorted(_masses_seen(ctx), key=lambda each: each.distance):
        key = _fire_at(ctx, (monster.position.y, monster.position.x), geo.MASS)
        if key is not None:
            return key
    return None


def _dreadmaster_done(ctx: _Ctx) -> bool:
    return ctx.kills(geo.DREADMASTER) >= geo.ROSTER[geo.DREADMASTER]


def _dreadmaster(ctx: _Ctx) -> str | None:
    battle = ctx.battle
    if battle.style is None:
        battle.style = "melee" if melee_is_fewer(ctx.policy, ctx.snapshot, geo.DREADMASTER) else "ranged"
    targets = _fight_targets(ctx)
    if any(monster.race_id == geo.DREADMASTER for monster in targets):
        if (haste := _haste(ctx)) is not None:
            return haste     # 「どちらにせよ戦闘時は加速する」
    if (key := _engage(ctx, targets) if (battle.style == "ranged" or any(
            monster.distance <= 1 for monster in targets)) else None) is not None:
        return key
    if battle.style == "melee":
        stand = geo.DREADMASTER_MELEE_STAND
    else:
        dreadmaster = next(cell for cell, race in ctx.navigator.battlefield.monster_placements
                           if race == geo.DREADMASTER)
        edge = geo.vision_cells(ctx.terrain, dreadmaster, geo.DREADMASTER_VISION, edge=True)
        stand = min((cell for cell in edge if cell in geo.NORTH_CORRIDOR), default=None)
    if stand is None:
        return None
    return (_walk(ctx, {stand}) if ctx.here != stand else None) or _hold(ctx)


# -- phase 6: the sweep -----------------------------------------------------------------


_SWEPT_RACES = tuple(race for race in geo.ROSTER if race not in {geo.DRUJ, geo.STAIRWAY, geo.MASS})


def _short(ctx: _Ctx) -> bool:
    return any(ctx.kills(race) < geo.ROSTER[race] for race in _SWEPT_RACES)


def _detector(ctx: _Ctx):
    """「感知が使えるなら」: the absorbed Rod of Detection or Staff of Detect Evil with a charge
    (("power", row)), else a carried one (("item", verb, item)); None without one."""
    policy, snapshot = ctx.policy, ctx.snapshot
    if me_device_attacks.can_use_powers(snapshot):
        for ident in (("rod", SV_ROD_DETECTION), ("staff", SV_STAFF_DETECT_EVIL)):
            if (me_capability.has(policy, snapshot, *ident)
                    and me_capability.charges(policy, snapshot, *ident) > 0):
                return ("power", me_powers.BY_KEY[ident])
    if snapshot.player.blind or snapshot.player.confused:
        return None
    for tval, sval, verb in ((TVAL_ROD, SV_ROD_DETECTION, "rod"),
                             (TVAL_STAFF, SV_STAFF_DETECT_EVIL, "staff")):
        item = next((item for item in snapshot.inventory if item.tval == tval and item.sval == sval
                     and item.known and not item.charging and (tval == TVAL_ROD or item.charges > 0)),
                    None)
        if item is not None:
            return ("item", verb, item)
    return None


def _detect_key(ctx: _Ctx) -> str | None:
    found = _detector(ctx)
    if found is None:
        return None
    if found[0] == "power":
        ctx.policy.last_reason = f"{DETECT_REASON}:{found[1].effect}"
        return found[1].key
    key = reserved_item_command(ctx.policy, ctx.snapshot, found[1], found[2])
    if key is not None:
        ctx.policy.last_reason = DETECT_REASON
    return key


def _sweep_targets(ctx: _Ctx) -> list:
    return [monster for monster in ctx.hostiles()
            if monster.race_id not in {geo.DRUJ, geo.STAIRWAY}]


def _sweep_done(ctx: _Ctx) -> bool:
    battle = ctx.battle
    if _sweep_targets(ctx):
        return False
    if battle.detected is not None:
        return not battle.detected
    if battle.detect_turn < 0 and _detector(ctx) is not None:
        return False
    return not _short(ctx)


def _sweep(ctx: _Ctx) -> str | None:
    battle = ctx.battle
    targets = _sweep_targets(ctx)
    if battle.detect_turn >= 0 and battle.detected is None:
        battle.detected = tuple((monster.position.y, monster.position.x) for monster in targets)
    if targets:
        visible = [monster for monster in targets if monster.perception != "detected"]
        if (key := _engage(ctx, visible)) is not None:
            return key
        nearest = min(targets, key=lambda monster: monster.distance)
        cell = (nearest.position.y, nearest.position.x)
        return _walk(ctx, {(cell[0] + dy, cell[1] + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                           if (dy or dx)}) or _hold(ctx)
    if battle.detected:
        # What the detection showed is gone from sight: walk where it was, then look again.
        cell = battle.detected[0]
        if quest_exposure.game_distance(ctx.here, cell) <= 1:
            battle.detected, battle.detect_turn = None, -1
        else:
            return _walk(ctx, {cell}) or _hold(ctx)
    if battle.detect_turn < 0 and (detect := _detect_key(ctx)) is not None:
        battle.detect_turn = ctx.snapshot.turn
        return detect
    if not _short(ctx):
        return None
    # 「撃破カウントに不足があれば巡回して探す」: the room sweep's stands as the round.
    stands = ctx.profile.engagement_plan["room_sweep"]["stands"]
    if battle.patrol_round >= int(ctx.profile.engagement_plan["room_sweep"]["max_rounds"]):
        ctx.policy.last_reason = BLOCKED_REASON
        return WAIT_KEY
    goal = tuple(stands[battle.patrol_stage]["cell"])
    if ctx.here == goal or not _path(ctx, {goal}):
        battle.patrol_stage += 1
        if battle.patrol_stage >= len(stands):
            battle.patrol_stage, battle.patrol_round = 0, battle.patrol_round + 1
        return _hold(ctx)
    return _walk(ctx, {goal})


# -- phase 6 and 7: the stairway and the druj --------------------------------------------


def _stairway_done(ctx: _Ctx) -> bool:
    return ctx.kills(geo.STAIRWAY) >= geo.ROSTER[geo.STAIRWAY]


def _stairway(ctx: _Ctx) -> str | None:
    battle = ctx.battle
    stairway = next(cell for cell, race in ctx.navigator.battlefield.monster_placements
                    if race == geo.STAIRWAY)
    door, stand = geo.STAIRWAY_DOOR, geo.STAIRWAY_STAND
    if battle.style is None:
        battle.style = ("melee" if melee_is_fewer(ctx.policy, ctx.snapshot, geo.STAIRWAY, steps=1)
                        else "ranged")
    if ctx.here not in {stand, door}:
        return _walk(ctx, {stand})
    if ctx.here == stand and ctx.door_closed(door) and (haste := _haste(ctx)) is not None:
        return haste      # 「全快し、加速して階段の前の扉を開ける」
    if ctx.door_closed(door):
        ctx.policy.last_reason = OPEN_REASON
        return ctx.policy._step_toward(ctx.snapshot, Position(*door))
    seen = [monster for monster in ctx.in_view() if monster.race_id == geo.STAIRWAY]
    if battle.style == "melee":
        if ctx.here != door:
            return _step(ctx, door, ENGAGE_REASON)
        if seen:
            return _engage(ctx, seen)
        return ctx.policy._step_toward(ctx.snapshot, Position(*stairway))
    return _fire_at(ctx, stairway, geo.STAIRWAY)


def _druj_done(ctx: _Ctx) -> bool:
    return ctx.kills(geo.DRUJ) >= geo.ROSTER[geo.DRUJ]


def _melt_key(ctx: _Ctx, grid) -> str | None:
    """Stone to Mud aimed at ``grid``: the absorbed power, else a carried wand."""
    cast = carry_cast_key(ctx.policy, ctx.snapshot, "utility_tools", "wall_breach",
                          direction=f"@{grid[0]},{grid[1]}")
    if cast is not None:
        ctx.policy.last_reason = MELT_REASON
        return cast
    wand = ctx.policy._stone_to_mud_wand(ctx.snapshot)
    return None if wand is None else _carried_grid_key(ctx, "wand", wand, grid)


def _can_melt(ctx: _Ctx) -> bool:
    return (carry_cast_key(ctx.policy, ctx.snapshot, "utility_tools", "wall_breach", direction="@0,0")
            is not None or ctx.policy._stone_to_mud_wand(ctx.snapshot) is not None)


def _druj(ctx: _Ctx) -> str | None:
    battle, druj = ctx.battle, next(cell for cell, race in ctx.navigator.battlefield.monster_placements
                                    if race == geo.DRUJ)
    # 「反テレポート付きで他のデメリットがない装備…この戦闘でのみ使用する」
    worn = quest25_druj_gear.wear_key(ctx.policy, ctx.snapshot, ctx.profile, battle)
    if worn is not None:
        return worn
    door = geo.DRUJ_DOOR
    grid = ctx.snapshot.grid_at(Position(*door))
    if grid is not None and grid.known and not grid.is_door:
        battle.melted = True     # Stone to Mud leaves floor (effect-feature.cpp KILL_WALL)
    lines = geo.line_cells(ctx.open_terrain(), druj)
    # 「魔道具術師は加速する」 out of the druj's line only (「眼の前で欠け直すわけではない」).
    if (ctx.snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER and ctx.here not in lines
            and (haste := _haste(ctx)) is not None):
        return haste
    if (battle.melted or ctx.door_closed(door)) and _balls(ctx, geo.DRUJ) and (battle.melted or _can_melt(ctx)):
        # 「ドアを開けずに13,20に移動して、11,19を岩石溶解して11,19に範囲攻撃を撃つ」
        if ctx.here != geo.DRUJ_AREA_STAND:
            return _walk(ctx, {geo.DRUJ_AREA_STAND})
        if not battle.melted:
            return _melt_key(ctx, door)
        return _fire_at(ctx, door, geo.DRUJ, area_only=True)
    if ctx.door_closed(door):
        if quest_exposure.game_distance(ctx.here, door) <= 1:
            ctx.policy.last_reason = OPEN_REASON
            return ctx.policy._step_toward(ctx.snapshot, Position(*door))
        beside = {(door[0] + dy, door[1] + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)}
        return _walk(ctx, {cell for cell in beside if ctx.terrain.get(cell) == "floor"})
    trapless = sorted(cell for cell in lines if ctx.terrain.get(cell) == "floor"
                      and cell not in ctx.navigator.battlefield.trap_cells)
    if ctx.here not in trapless:
        return _walk(ctx, set(trapless)) or _hold(ctx)
    return _fire_at(ctx, druj, geo.DRUJ)


# -- the table --------------------------------------------------------------------------


@dataclass(frozen=True)
class Phase:
    name: str
    spec_key: str          # the draft's key that says it
    full_hp: bool          # 「全快にして」 before its first step
    done: Callable
    act: Callable          # the phase's own step
    wait_at: tuple | None = None   # where its wait is counted (None: anywhere, once ready)
    wait_limit: int | None = None  # player actions without an arrival that end it


PHASES = (
    Phase("ambush", "phase1", False, _ambush_done, _ambush, None, LONG_WAIT_ACTIONS),
    Phase("wall-passers", "phase1_wall_passers", True, _wall_passers_done, _wall_passers,
          geo.WALL_PASSER_STAND, QUIET_ACTIONS),
    Phase("ipsissimus", "phase2", True, _ipsissimus_done, _ipsissimus),
    Phase("stragglers", "phase1_wall_passers", False, _stragglers_done, _stragglers,
          geo.STRAGGLER_STAND, QUIET_ACTIONS),
    Phase("quylthulgs", "phase3", False, _quyls_done, _quyls),
    Phase("tome", "phase3", True, _tome_done, _tome),
    Phase("corpse-masses", "phase4", False, _masses_done, _masses),
    Phase("dreadmaster", "phase5", False, _dreadmaster_done, _dreadmaster, None, LONG_WAIT_ACTIONS),
    Phase("sweep", "phase6_sweep", False, _sweep_done, _sweep),
    Phase("stairway", "phase6", True, _stairway_done, _stairway),
    Phase("druj", "phase7_druj", False, _druj_done, _druj),
)
PHASE_NAMES = tuple(phase.name for phase in PHASES)


def _finished(ctx: _Ctx, phase: Phase) -> bool:
    """Its own end, or its wait limit (wait_limits, phase1_wall_passers, phase2)."""
    return phase.done(ctx) or (phase.wait_limit is not None and ctx.battle.quiet >= phase.wait_limit)


def current_phase(ctx: _Ctx) -> Phase | None:
    """Advance over every finished phase; the one running, else None (all done)."""
    while ctx.battle.phase < len(PHASES) and _finished(ctx, PHASES[ctx.battle.phase]):
        _next_phase(ctx.battle)
    return PHASES[ctx.battle.phase] if ctx.battle.phase < len(PHASES) else None


def _observe(ctx: _Ctx) -> None:
    """Once per board (``key`` and ``walk_key`` may both read it)."""
    board = (ctx.snapshot.turn, id(ctx.snapshot))
    if ctx.battle.observed == board:
        return
    ctx.battle.observed = board
    _note_kills(ctx)
    _note_pen_shot(ctx)
    _note_arrivals(ctx)
    phase = current_phase(ctx)
    if (phase is not None and phase.wait_limit is not None and ctx.battle.ready
            and phase.wait_at in (None, ctx.here)):
        ctx.battle.quiet += 1


def _phase_key(policy, snapshot) -> str | None:
    """The running phase's own order: its preparation, then its step."""
    ctx = _ctx(policy, snapshot)
    if ctx is None:
        return None
    phase = current_phase(ctx)
    if phase is None:
        # The druj is dead: what the anti-teleport piece displaced goes back on.
        return quest25_druj_gear.restore_key(policy, snapshot, ctx.battle)
    return _prepare(ctx, phase) or phase.act(ctx)


# -- the summons ------------------------------------------------------------------------


def _druj_retreat(policy, snapshot) -> str | None:
    """Owner 2026-11-07 (phase7_druj) 「歩いてドルジの射線から外れる。安全に休憩可能なはずである。
    必要なら歩いて射線から外れた後薬を飲む。」

    With the anti-teleport piece worn on the druj phase, Teleportation cannot be read
    (teleport_player refuses under NO_TELE), so below the plan's line (``abort_conditions.hp_ratio``,
    the line ``_below_line`` reads Teleportation at) the walk leaves the druj's direct line (it never
    moves and every spell of it needs that line), then rests there until HP is full.  A rest that
    did not raise HP (refused or broken off) is followed by a Healing potion -- out of the line only.
    Back at full HP the phase walks back to its stand.
    """
    ctx = _ctx(policy, snapshot)
    if (ctx is None or ctx.battle.phase >= len(PHASES) or PHASES[ctx.battle.phase].name != "druj"
            or quest25_druj_gear.worn_piece(snapshot) is None):
        if ctx is not None:
            ctx.battle.retreating, ctx.battle.retreat_rest_hp = False, None
        return None
    battle, player = ctx.battle, snapshot.player
    if not battle.retreating:
        if player.hp_ratio > float(ctx.profile.abort_conditions["hp_ratio"]):
            return None
        battle.retreating = True
    if player.hp >= player.max_hp:
        battle.retreating, battle.retreat_rest_hp = False, None
        return None
    druj = next(cell for cell, race in ctx.navigator.battlefield.monster_placements if race == geo.DRUJ)
    lines = geo.line_cells(ctx.open_terrain(), druj) | {druj}
    if ctx.here in lines:
        battle.retreat_rest_hp = None
        out = {cell for cell, kind in ctx.terrain.items()
               if kind in {"floor", "door"} and cell not in lines}
        return _walk(ctx, out, RETREAT_REASON)
    if battle.retreat_rest_hp is not None and player.hp <= battle.retreat_rest_hp:
        potion = quest_find_exit._healing_potion(policy, snapshot)
        if potion is not None:
            battle.retreat_rest_hp = None
            policy.last_reason = RETREAT_HEAL_REASON
            return reserved_item_command(policy, snapshot, "quaff", potion)
    battle.retreat_rest_hp = player.hp
    policy.last_reason = RETREAT_REST_REASON
    return REST_MACRO


def _summons(policy, snapshot) -> str | None:
    """Owner 2026-11-06: on phase 2 the reinforcements are answered by the phase's own rule
    (its fire on the pen or the teleport, ``_ipsissimus``); on the stairway 「致死的でなければ
    階段の処理を優先する」.  Elsewhere the shared rules (summon_response)."""
    ctx = _ctx(policy, snapshot)
    if ctx is not None and ctx.battle.phase < len(PHASES):
        name = PHASES[ctx.battle.phase].name
        if name == "ipsissimus":
            return None
        if name == "stairway" and not policy._is_material_threat(
                snapshot, policy._physical_hostiles(snapshot)):
            return None
    return summon_response.key(policy, snapshot)


# -- the rung ---------------------------------------------------------------------------


def key(policy, snapshot) -> str | None:
    """The board on the Q25 floor while the revised plan runs; None leaves it shared."""
    ctx = _ctx(policy, snapshot)
    if (ctx is None or snapshot.player.food_state in quest_find_exit.STARVING
            or once_quest_recall._deliberate_leave(policy, snapshot)):
        return None
    _observe(ctx)
    profile, navigator = ctx.profile, ctx.navigator
    plan = profile.engagement_plan["room_sweep"]
    board = quest_room_sweep._Board(policy, snapshot, profile, navigator, {**plan, "left_alone_races": ()})
    if not board.enemy:
        return (
            _druj_retreat(policy, snapshot)
            or _summons(policy, snapshot)
            or resist_potion.key(policy, snapshot)
            or quest_room_sweep._restore(policy, snapshot)
            or _phase_key(policy, snapshot)
        )
    return (
        quest_find_exit._cure(policy, snapshot)
        or _druj_retreat(policy, snapshot)
        or quest_room_sweep._give_up(policy, snapshot, profile)
        or quest_room_sweep._below_line(policy, snapshot, profile, navigator)
        or quest_find_exit._heal(policy, snapshot, profile)
        or quest_find_exit._speed(policy, snapshot, profile, board)
        or _summons(policy, snapshot)
        or resist_potion.key(policy, snapshot)
        or _phase_key(policy, snapshot)
    )


def walk_key(policy, snapshot) -> str | None:
    """A quiet board reached through the navigator: the phase's step."""
    ctx = _ctx(policy, snapshot)
    if ctx is None:
        return None
    _observe(ctx)
    return _phase_key(policy, snapshot)


def describe(policy, snapshot) -> dict | None:
    """The running phase and the kill ledger (for a test or a decision log)."""
    ctx = _ctx(policy, snapshot)
    if ctx is None:
        return None
    phase = current_phase(ctx)
    return {"phase": None if phase is None else phase.name, "kills": dict(ctx.battle.kills),
            "ready": ctx.battle.ready}
