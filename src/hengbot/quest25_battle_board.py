"""Quest 25's phase battle (quest25_battle): the plan's reasons and numbers, its memory and the board.

The battle's memory (``Battle``: one floor visit, kept over the phases by ``_next_phase`` and over a
restart by quest25_battle_record), the decision's context (``_Ctx``), what each board says (the kill
and teleport lines, the arrivals, the pen's shots), and what is known of the never-moving targets
(the cells that see them, seen there or gone, ``_tome_done`` / ``_druj_done``).

The lowest layer of the battle's modules: it imports none of the others.

Split from quest25_battle.py (maintainability review 2026-11-23 (a)-8, behaviour unchanged).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hengbot import ability_sources
from hengbot import (
    attack_expectation, me_powers, quest25_battle_record, quest25_geometry as geo, quest25_plan,
    quest_exposure, quest_plan_base, quest_room_light, summon_response,
)
from hengbot.game_messages import ECHIZEN_PREFIX, KILL_LINES, KILL_LINES_EN
from hengbot.me_absorbed_substitutes import CAST_SUFFIX
from hengbot.policy_constants import REST_MACRO
from hengbot.quest_plan_base import HOLD_REASON
from hengbot.unseen_strike import message_text


PLAN_KEY = quest25_plan.DRAFT_KEY
REASON = "quest25"
WALK_REASON = f"{REASON}:walk"
OPEN_REASON = f"{REASON}:open-door"
CLOSE_REASON = f"{REASON}:close-door"
SHOT_REASON = f"{REASON}:shot"
SEARCH_REASON = f"{REASON}:trap-search"
DISARM_REASON = f"{REASON}:trap-disarm"
TRAP_DETECT_REASON = f"{REASON}:trap-detect"
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
ENLIGHTEN_REASON = f"{REASON}:ambush-enlightenment"
BLOCKED_REASON = "quest:blocked:quest25-patrol-rounds"
SIGHT_REASON = f"{REASON}:walk-to-sight"
WITHDRAW_REASON = f"{REASON}:withdraw"
OUT_OF_FIRE_REASON = f"{REASON}:step-out-of-fire"
FIRE_REST_REASON = f"{REASON}:rest-out-of-fire"
FIRE_HOLD_REASON = f"{REASON}:hold-out-of-fire"
RECALL_EXIT_WALK_REASON = f"{REASON}:recall-exit-walk"
RECALL_EXIT_REASON = f"{REASON}:recall-exit"
RECALL_OUT_REASON = f"{REASON}:recall-out-of-fire"
RECALL_WAIT_REASON = f"{REASON}:recall-wait"
ABSORBED_HEAL_REASON = f"{REASON}:heal{CAST_SUFFIX}"
MASS_CELL_REASON = f"{REASON}:mass-firing-cell"
CHOKE_BACK_REASON = f"{REASON}:choke-step-back"
RESTOCK_RECALL_REASON = f"{REASON}:restock-recall"

# The plan's numbers -- the waits (wait_limits), the pen misses, the trap searches and the
# distances the hit chance is weighed at -- are items of QUEST_25.jsonc
# ``engagement_plan.revised_plan_values``, each quoting its owner decision there; ``_Ctx.values``
# reads them (quest25_plan).
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
# A monster moved the player (mspell-floor.cpp spell_RF6_TELE_AWAY, spell_RF6_TELE_TO).
_TELEPORTED_LINES = ("にテレポートさせられた。", "があなたを引き戻した。")
_TELEPORTED_LINES_EN = (" teleports you away.", " commands you to return.")
# The counted rest between phases (between_phases 「回数を指定して休み、回数を見て続けるかを
# 決める」); the count is the Q34 recharge's (q34_recharge, LUNA-REPORT-me-rest-recharge).
RECHARGE_REST_KEY = "R100\r"
# Counted recharge rests one phase takes at most.  A long rest is the plan's own (n1-b life-382
# 2026-11-13 04:42: [5,1], INT 15, eleven 'R100' of about 77 game ticks each and still short when
# the loop guard stopped it).  regenmagic (hpmp/hp-mp-regenerator.cpp) refills a wand or staff of
# count c from empty in c * 0x10000 / (regen * (30 + adj_mag_mana[INT]) * (c + 13) / 240) ticks:
# at the slowest the plan meets (count 99, no Regeneration, no INT bonus, resting) about 1,180
# ticks, some 16 such rests.  Thirty is twice that; past it the phase goes on with what is charged.
RECHARGE_REST_LIMIT = 30
# Game turns under which a counted recharge rest was cut short (``_note_rest_cut``).
REST_CUT_GAME_TURNS = 100
# The rest that ends at full HP/MP (player-processor.cpp).
FULL_HP_REST_KEY = REST_MACRO
# Never-moving casters left to their own phases: no shot, no wait for them elsewhere.  The corpse
# masses are not among them (owner 2026-11-08 「射線にいれば範囲で撃つ」): breeders are shot by
# ``_breeders_in_line_key`` wherever a phase would wait or walk, not mixed into its own targets.
_LATER_IMMOBILE = frozenset({geo.IPSISSIMUS, geo.TOME, geo.QUYL, geo.DRUJ, geo.STAIRWAY})
# A phase step that leaves the board to the breeders in the line of fire (a hold, a walk and the
# trap search or disarm on its way).
_IDLE_REASONS = frozenset({HOLD_REASON, WALK_REASON, SEARCH_REASON, DISARM_REASON})
_KILL_LINES = KILL_LINES
_KILL_LINES_EN = KILL_LINES_EN
# The other deaths the game prints after the victim's name (monster-damage.cpp show_kill_message
# prints a non-empty note as name + note): the player's auras (combat/aura-counterattack.cpp),
# the projections' own death notes (effect/effect-monster-*.cpp note_dies), an explosion
# (monrace-definition.cpp get_died_message) and a kill by another monster (melee-postprocess.cpp).
# n1-c life-208 (2026-11-15, turn 3965900): 「幽体ティラノサウルスは灰の山になった。」 -- the fire aura
# killed the spectral tyrannosaurus and no kill was counted (quest25_presence).
_DEATH_NOTES = (
    "は灰の山になった。", "は燃え殻の山になった。", "は凍りついた。", "はズタズタになった。", "は倒れた。",
    "はドロドロに溶けた！", "は蒸発した！", "は観測されなくなった。", "は消えてしまった。", "は消滅してしまった。",
    "は深淵に堕ちてしまった。", "は光を受けてしぼんでしまった！", "の精神は崩壊し、肉体は抜け殻となった。",
    "は爆発して粉々になった。", "は破壊された。", "は殺された。",
)
_DEATH_NOTES_EN = (
    " turns into a pile of ash.", " turns into a pile of cinders.", " was frozen.", " is torn to pieces.",
    " is destroyed.", " dissolves!", " evaporates!", "'s wave function collapses.", " has disappeared.",
    " has vanished.", " has fallen into the abyss.", " shrivels away in the light!",
    " collapses, a mindless husk.", " explodes into tiny shreds.", " is killed.",
)
_UNSEEN = ("何か", "it", "It")
_ECHIZEN = ECHIZEN_PREFIX


# -- memory ----------------------------------------------------------------------------


@dataclass
class Battle:
    """One floor visit of the plan (``QuestFloorNavigator.phase_battle``)."""
    phase: int = 0
    kills: dict = field(default_factory=dict)        # race -> kills read from kill lines
    kill_turns: tuple = ()         # (race, game turn) of each of those kills (quest25_battle_record)
    ready: bool = False            # this phase's preparation is done
    quiet: int = 0                 # actions without a new arrival (the 50-action waits)
    no_way: tuple | None = None    # the cell the last walk held on with no way on (``_walk``)
    seen: frozenset = frozenset()  # monster indices seen in this phase
    summoned: frozenset = frozenset()  # of those, the ones first seen on a board with a summon cast
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
    pen_no_way: int = 0            # phase-2 holds in a row with sight cells left and no way to them
    assumed_escaped: int = 0       # 「当たらない撃ちで補う」: counted escaped after the misses
    aimed_quyl: tuple | None = None    # the quylthulg cell the last shot was aimed at
    retreating: bool = False       # below the line with the anti-teleport piece on: out of the line
    retreat_rest_hp: int | None = None  # HP when the last rest out of the line was keyed
    observed: tuple | None = None      # the board last read (key and walk_key share one)
    enlightened: bool = False      # the ambush's Potion of Enlightenment was drunk this visit
    beam: tuple | None = None      # (turn, origin, step) of the last answer aimed at a trap cell
    detection: tuple | None = None  # (turn, origin) of the last trap detection keyed for a cell
    detect_asked: frozenset = frozenset()  # trap cells a trap detection was keyed for
    recharge_rest_turn: int | None = None  # the turn the last counted recharge rest was keyed
    recharge_rests: int = 0        # this phase's counted recharge rests (``RECHARGE_REST_LIMIT``)
    gone: frozenset = frozenset()  # never-moving races not on their grid (``_immobile_gone``)
    tome_detect: int | None = None  # the turn a detection to confirm the tome was keyed
    tome_shown: bool = False       # a detection showed the tome on its grid this phase
    rest_cut: bool = False         # a sensed moving hostile cut that rest short
    fire_rest: tuple | None = None     # (decision, HP) of the last rest out of the casters' fire
    blind_sights: frozenset = frozenset()  # (target, cell): sight cells reached, the target not seen
    glowing: frozenset = frozenset()   # floor cells seen drawn lit (CAVE_GLOW in view)
    tome_hp: int | None = None     # the tome's HP read from its last seen health (an upper bound)
    # Phase 2 (owner 2026-11-11 「隘路で待って倒す」): the summons Teleportation was read from,
    # (race, last seen cell) each, and the decided boards since one of them was last seen.
    strong: tuple = ()
    strong_quiet: int = 0
    # Phase 2 (owner 2026-11-16 「隘路で迎え撃ち尽きる前に帰還」): the rallies in a row that ended on the
    # choke with no shot at the pen since the last one (the look-out, the summons, the return).
    lookouts: int = 0
    # Owner 2026-11-12 (quest25_sealed_room): the room landed in, (name, actions, step, last
    # counted turn, shots at the clear's target); None off the sealed rooms.
    room: tuple | None = None
    # quest25_presence (owner 2026-11-13 「可能なら感知して存在を確認する」, 2026-11-15): the roster
    # races a board showed are not on the floor (race -> game turn), the plan's detection whose
    # result the next board shows ((turn, origin, effect, presence_quiet and recheck before it)),
    # the quiet count at this phase's last presence check, and a check due at once (a battle
    # restored from an older save, quest25_battle_record ``_before_the_save``).
    absent: dict = field(default_factory=dict)
    cast: tuple | None = None
    presence_quiet: int = 0
    recheck: bool = False
    # The races this phase's presence check showed on the floor (quest25_presence ``presence_key``:
    # shown present, the wait for them is the plan's, and no further check is made this phase).
    presence_shown: frozenset = frozenset()
    # quest25_pocket (owner 2026-11-15 「溶かして撃つ・無ければ帰還」): (target cell, granite wall,
    # stand) of the sealed pocket the sweep opens, whether the last key shot at it, and the shots in
    # a row with no hit, pain or kill line.
    pocket: tuple | None = None
    pocket_shot: bool = False
    pocket_misses: int = 0
    # Owner 2026-11-19 「テレポートで飛ばされてドリードマスターの感知範囲内に行ってしまったら優先して
    # ドリードマスターを倒す」: a monster's teleport left the player in its sensing range
    # (``_note_dread_teleport``), and the style that fight chose (kept apart from the phase's).
    dread_teleported: bool = False
    dread_style: str | None = None


def _memory(navigator, policy=None, snapshot=None) -> Battle:
    if navigator.phase_battle is None:
        # A restart on the same floor visit resumes the previous process's battle
        # (quest25_battle_record); else this visit starts one.
        restored = (None if policy is None or snapshot is None
                    else quest25_battle_record.take(policy, snapshot))
        navigator.phase_battle = restored if restored is not None else Battle()
    return navigator.phase_battle


def _next_phase(battle: Battle) -> None:
    kept = {name: getattr(battle, name) for name in (
        "phase", "kills", "kill_turns", "searches", "cleared", "found", "escaped", "quyls_done",
        "melted", "lit", "observed", "teleports", "assumed_escaped", "enlightened",
        "beam", "detection", "detect_asked", "glowing", "tome_hp", "room", "gone", "absent", "cast", "recheck",
        "dread_teleported", "dread_style")}
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

    @property
    def values(self) -> quest25_plan.PlanValues:
        """The plan's numbers (``engagement_plan.revised_plan_values``)."""
        return quest25_plan.values_of(self.profile)

    def door_closed(self, cell) -> bool:
        return quest_plan_base._door_is_closed(self.snapshot, tuple(cell))

    def open_terrain(self) -> dict:
        return quest_plan_base._open_terrain(self.navigator, self.snapshot)

    def hostiles(self) -> list:
        return [monster for monster in (*self.snapshot.visible_monsters,
                                        *self.snapshot.detected_monsters) if monster.hostile]

    def seen_hostiles(self) -> list:
        """The visible hostiles not known by detection only (review 1117 N9: it was ``in_view``)."""
        return [monster for monster in self.snapshot.visible_monsters
                if monster.hostile and monster.perception != "detected"]

    def kills(self, race: int) -> int:
        """The kills read of ``race``; a race a board showed is not on the floor (``Battle.absent``,
        quest25_presence) counts as its whole roster: none of it is left to wait for or shoot."""
        killed = self.battle.kills.get(race, 0)
        if race in self.battle.absent:
            return max(killed, geo.ROSTER.get(race, killed))
        return killed


def _ctx(policy, snapshot):
    profile = _profile(policy, snapshot)
    if profile is None:
        return None
    navigator = quest_plan_base._navigator(policy, snapshot, geo.QUEST_ID)
    return _Ctx(policy, snapshot, profile, navigator, _memory(navigator, policy, snapshot))


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
    for note in _DEATH_NOTES:
        if text.endswith(note):
            return text[:-len(note)]
    for note in _DEATH_NOTES_EN:
        if text.endswith(note):
            return text[:-len(note)].removeprefix("the ").removeprefix("The ")
    return None


def _note_kills(ctx: _Ctx) -> None:
    races = {name: race for race in geo.ROSTER for name in _names(ctx.policy, race)}
    kills = dict(ctx.battle.kills)
    logged = list(ctx.battle.kill_turns)
    for message in ctx.snapshot.messages:
        victim = _killed_name(message_text(message))
        if victim is None:
            continue
        race = races.get(victim)
        if race is None and victim in _UNSEEN:
            race = ctx.battle.aimed_race
        if race is not None:
            kills[race] = kills.get(race, 0) + 1
            logged.append((race, int(ctx.snapshot.turn)))
            if race == geo.QUYL and ctx.battle.aimed_quyl is not None:
                ctx.battle.quyls_done = ctx.battle.quyls_done | {ctx.battle.aimed_quyl}
    ctx.battle.kills = kills
    ctx.battle.kill_turns = tuple(logged)
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
    return ability_sources.has_ability(snapshot.player, "telepathy") or any(
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
    if battle.pen_misses >= ctx.values.pen_misses_to_escaped and not sees_ipsissimus_unseen(ctx.snapshot):
        battle.assumed_escaped = max(0, geo.ROSTER[geo.IPSISSIMUS] - ctx.kills(geo.IPSISSIMUS)
                                     - _escaped_count(ctx, assumed=False))


def _note_arrivals(ctx: _Ctx) -> None:
    """A new monster in view this phase restarts the 50-action wait; Ipsissimus out of the
    pen is escaped."""
    from hengbot import quest25_presence

    seen = {monster.index for monster in ctx.hostiles()}
    new = seen - ctx.battle.seen
    # What the plan's own detection shows did not come (quest25_presence): no restart of the wait.
    if new and not quest25_presence.cast_board(ctx):
        ctx.battle.quiet = 0
    if new and any(summon_response.summons_of(message) for message in ctx.snapshot.messages):
        ctx.battle.summoned = ctx.battle.summoned | new
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
    """「必要な行動回数」: melee (plus ``steps`` to reach) kills in fewer actions than ranged, the
    hit chance weighed at the plan's ``compare_distance`` for the race."""
    hp = _race_hp(policy, race)
    distance = quest25_plan.values_of(policy.approved_quest_strategy(geo.QUEST_ID)).distance_for(race)
    ranged = attack_expectation.actions_to_kill(hp, attack_expectation.ranged_against(
        policy, snapshot, race, distance))
    melee = attack_expectation.actions_to_kill(
        hp, attack_expectation.melee_against(policy, snapshot, race)) + steps
    return melee < ranged


# -- the Ipsissimus left, and the never-moving targets seen or gone ----------------------


def _escaped_count(ctx: _Ctx, *, assumed: bool = True) -> int:
    """Seen out of the pen, or named teleporting; and, after the misses, the rest."""
    return (max(len(ctx.battle.escaped), ctx.battle.teleports)
            + (ctx.battle.assumed_escaped if assumed else 0))


def _ipsissimus_alive(ctx: _Ctx) -> bool:
    return ctx.kills(geo.IPSISSIMUS) + _escaped_count(ctx) < geo.ROSTER[geo.IPSISSIMUS]


def _tome_done(ctx: _Ctx) -> bool:
    if _tome_absent(ctx):
        ctx.battle.gone = ctx.battle.gone | {geo.TOME}
    return ctx.kills(geo.TOME) >= geo.ROSTER[geo.TOME] or _immobile_gone(ctx, geo.TOME)


def _placed(ctx: _Ctx, race: int):
    """The plan's cell of the never-moving ``race`` (the battlefield's placements), else None."""
    return next((tuple(cell) for cell, placed in ctx.navigator.battlefield.monster_placements
                 if placed == race), None)


def _immobile_gone(ctx: _Ctx, race: int) -> bool:
    """Every cell that sees the grid of the never-moving ``race`` was reached and it was not seen
    there: it is not on that grid any more (``_walk_to_sight``'s 「見えなければ次から選ばない」 run
    out, as the pen's ``_pen_sight`` counts the Ipsissimus escaped).  The races this is asked for
    never move and are not invisible (lib/edit MonraceDefinitions 557 Raal's Tome of Destruction,
    439 Stairway to hell: NEVER_MOVE, no INVISIBLE): unseen on a cell that sees their grid, they
    are not on it -- killed unseen (「何かを殺した。」 names no race, monster-damage.cpp
    show_kill_message), erased, or moved off by the player's own teleport; what is left of the
    floor is the KILL_ALL patrol's after the phases.

    n1-b life-382 (2026-11-13 05:38:34-05:38:46): the walk to the tome's sights reached every one
    of them with no tome seen and walked over [9,8] itself (decision 5907); the plan then shot the
    empty grid from [5,5] 85 times (5944-6028), and with every grid-aimed attack spent had no
    step, which the KILL_ALL patrol took until the loop guard stopped the bot twice.  n1-b
    life-384 (08:42): the stairway [13,29] unseen from both stands, [13,28] beside it included.
    Kept over the phases (``_next_phase``) and the record."""
    battle = ctx.battle
    if race in battle.gone:
        return True
    cell = _placed(ctx, race)
    reached = {sight for aimed, sight in _blind_pairs(ctx) if aimed == cell}
    if cell is None or not reached or _seen_at(ctx, race, {cell}):
        return False
    player = ctx.snapshot.player
    looked = set() if player.blind or player.hallucinated else {ctx.here}   # this board's look
    sights = geo.sight_cells(ctx.open_terrain(), cell, _sight_radius(ctx, cell))
    if sights and sights <= reached | looked:
        battle.gone = battle.gone | {race}
    return race in battle.gone


def _tome_absent(ctx: _Ctx) -> bool:
    """The board after the tome's detection (``_confirm_tome_key``), read as the sweep reads its
    own (``_detection_failed``): a cast that failed is forgotten (cast again); else the tome is
    shown on its grid (the phase goes on) or it is not there (the phase ends, as
    ``_immobile_gone``)."""
    battle = ctx.battle
    cast = battle.tome_detect
    if cast is None or ctx.snapshot.turn <= cast:
        return False
    battle.tome_detect = None
    if _detection_failed(ctx, cast):
        return False
    tome = _placed(ctx, geo.TOME)
    battle.tome_shown = any(monster.race_id == geo.TOME
                            and (monster.position.y, monster.position.x) == tome
                            for monster in ctx.hostiles())
    return not battle.tome_shown


def _note_glow(ctx: _Ctx) -> None:
    """The plain floor cells beyond the player's light that the board draws lit (quest_room_light
    ``drawn_lit``: F_LIT_STANDARD, a glowing cell in view; within his light a cell may be drawn so
    by his own light, view/display-map.cpp decide_visible_terrain_lighting), remembered for the
    visit: a floor cell out of view is not drawn."""
    reach = max(1, int(ctx.snapshot.light_radius or 0))
    lit = {cell for cell in ((position.y, position.x) for position in ctx.snapshot.grids)
           if ctx.terrain.get(cell) == "floor" and quest_exposure.game_distance(ctx.here, cell) > reach
           and quest_room_light.drawn_lit(ctx.snapshot, cell)}
    if lit - ctx.battle.glowing:
        ctx.battle.glowing = ctx.battle.glowing | frozenset(lit)


def _glowing(ctx: _Ctx, target) -> bool:
    """``target``'s grid glows: drawn lit on a board of this visit, or another cell of its room
    was (a Light scroll's lite_room and Enlightenment's wiz_lite light the whole room,
    spells-lite.cpp / spells-floor.cpp; every cell of the quest map is CAVE_ROOM; the room is
    joined through the cells a line passes, so a closed door bounds it)."""
    target = tuple(target)
    if target in ctx.battle.glowing:
        return True
    if not ctx.battle.glowing:
        return False
    return bool(quest_room_light.room_of(ctx.open_terrain(), target) & ctx.battle.glowing)


def _sight_radius(ctx: _Ctx, target=None) -> int:
    """How far a monster on ``target`` is shown (geo.sight_radius, owner 2026-11-09 「照らされた所も
    入れる」): the player's light (a cold-blooded body gives no infravision, monster-update.cpp;
    1 when the board does not say), out to MAX_PLAYER_SIGHT on a glowing grid."""
    return geo.sight_radius(ctx.snapshot.light_radius,
                            target is not None and _glowing(ctx, target))


def _seen_at(ctx: _Ctx, race: int, cells) -> list:
    """The monsters of ``race`` in view (telepathy included: ``ml``) on ``cells``."""
    cells = {tuple(cell) for cell in cells}
    return [monster for monster in ctx.seen_hostiles()
            if monster.race_id == race and (monster.position.y, monster.position.x) in cells]


def _sights(ctx: _Ctx, target, among=None) -> set:
    """The cells that see ``target`` (geo.sight_cells at ``_sight_radius``), less those reached
    where it was not seen; within ``among`` when given (the phase's own stands)."""
    target = tuple(target)
    sights = set(geo.sight_cells(ctx.open_terrain(), target, _sight_radius(ctx, target)))
    sights -= {cell for aimed, cell in _blind_pairs(ctx) if aimed == target}
    return sights if among is None else sights & {tuple(cell) for cell in among}


def _blind_pairs(ctx: _Ctx):
    # A record written before the pairs held bare cells: those name no target.
    return (pair for pair in ctx.battle.blind_sights
            if isinstance(pair, tuple) and len(pair) == 2 and isinstance(pair[0], tuple))


def _detection_failed(ctx: _Ctx, turn: int | None = None) -> bool:
    """The board after a detection keyed on ``turn`` (default the sweep's) says the cast or the use
    failed (and shows nothing)."""
    from hengbot import kill_all_patrol

    if ctx.snapshot.turn == (ctx.battle.detect_turn if turn is None else turn):
        return False
    texts = [message_text(message) for message in ctx.snapshot.messages]
    return (any(line in text for text in texts for line in kill_all_patrol.FAILED_LINES)
            and not any(line in text for text in texts for line in kill_all_patrol.SENSED_LINES))


def _druj_done(ctx: _Ctx) -> bool:
    return ctx.kills(geo.DRUJ) >= geo.ROSTER[geo.DRUJ]
