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
    「どちらにせよ加速を使用する」: hasted while a target is in view.  With no hostile in view, a carried
    Potion of Enlightenment is drunk first, once (owner 2026-11-07, ``_ambush_enlightenment``).
 2. ``wall-passers`` (phase1_wall_passers): full HP, then [7,1]; what comes is fought; 100
    player actions without a new arrival end it (owner 2026-11-09 「待つターンを倍にしてみる」).
 3. ``ipsissimus`` (phase2): full HP, [7,1], haste, [6,1], [5,1], then the strongest attack
    at the pen's [7,17] (the monster's own cell when it is seen).  Summons in view: a piercing
    attack (a beam, or a ball or breath aimed at the grid) and a low threat keep the fire on
    the pen; otherwise Teleportation, then a choke before contact (``_rally``), weighed before the
    walk to the stand.  What it teleported from is remembered and waited for on the choke until
    killed or unseen for the stragglers' 50 actions, then full HP and the walk again (owner
    2026-11-11 「隘路で待って倒す」); the walk never goes toward it.  The wall-passers
    the phase before left alive are no summons (``_summons_in_view``): they are ignored and the
    fire stays on the pen, never teleported from (owner 2026-11-09, n1-b life-359).  It ends when each of the three is
    killed or seen out of the pen.
 4. ``stragglers`` (phase1_wall_passers / phase2): on [5,1], the spectres and shadow demons
    that did not come and the Ipsissimus that teleported away are fought as they come; 50
    actions without a new arrival end it.
 5. ``quylthulgs`` (phase3 step 1): with a ball, each quylthulg a ball can catch from a cell
    out of the casters' lines ([5,2], [5,1]; quest25_geometry.ball_centre) is shot until it is
    killed or seen moved.  Without a ball it is skipped.
 6. ``tome`` (phase3 step 2): full HP, haste, then a ball from [5,1]/[5,2] where one reaches
    the tome, else the strongest ranged attack from [5,5], [4,5] or [5,6].
 7. ``corpse-masses`` (phase4): [1,6] by the walk that crosses no corridor trap, the door
    [1,7] opened, the corridor lit when dark (the 11-05 rule), and every mass in view shot --
    from the cell that reaches the most of them (owner 2026-11-09 「一番多く届く位置へ」,
    ``_walk_to_widest``), back to [1,6] when none is left to shoot.
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

In every phase (owner 2026-11-07 「隣に来たら倒す」, widened the same day 「全部の段に広げる」), a corpse
mass beside the player is struck (else shot) before the phase's own step (``_adjacent_mass_key``).
Owner 2026-11-08 「射線にいれば範囲で撃つ」 (it replaces 「離れた塊は今のまま相手にしない」): 「どの段でも、
もっと危ない敵が動いていなければ、射線にいる増える敵を撃つ。範囲攻撃は一番多く倒せるマスを狙い、2体
以上巻き込めるなら単体攻撃より先に使う。道をふさがれたら待たずに撃って開ける。」  Where the phase's own
step would wait or walk (or has none), the masses in the line of fire are shot instead
(``_breeders_in_line_key``, breeder_area_attack ``line_of_fire_key``): the aim with the most kills
when it catches two or more, else the phase's strongest shot at the nearest.  A more dangerous
hostile that acts keeps the phase's step; the phase's own fights and every survival rung come first.

Owner 2026-11-09 「見えない時は矢を撃たない。マスを狙う範囲の攻撃で削り、無ければ相手が見えるマスへ移って
撃つ。」 (the tome first), widened 「Q25 の全部の段に広げる」: the pen, the quylthulgs, the tome, the
stairway and the druj are shot with the launcher only when seen (``_unseen_fire``); a seen cell is
the player's light, or out to MAX_PLAYER_SIGHT on a glowing grid (「照らされた所も入れる」, ``_sight_radius``).

Between phases (between_phases): a Magic-Eater rests a counted rest until every absorbed
attack power is full, reading the lists turn-free (``b``) to decide (R& does not wait for
them, player-processor.cpp is_fully_healthy).  While a sensed moving hostile cuts that rest
short, the phase walks to its post instead and the rest goes on once none is sensed (owner
2026-11-09, ``_prepare``).

Traps (phase4, phase5): a corridor cell the map always traps is settled by a trap detection
when the character has one, else searched from beside it ten times (owner 2026-11-09), a cell
that may hold one (``!``) ten times; a disarming power or
device is aimed first when there is one, the disarm command (``_step_toward``) answers a
found trap.  A disarming beam that went off (the game's flash) answers every trap cell of its
line, and a cell that holds an item holds no trap (``_settle_beam``, ``_trap_key``).  Walks cross
the fewest summon cells while the Ipsissimus live and the fewest uncleared traps.

Kills are read from the game's kill lines (monster-damage.cpp): the seen ones by the race's
name, an unseen one (何か) as the race the last grid shot was aimed at.

Survival and the summons answer first (dungeon_ladder FLOOR_PLANS): the room sweep's own
survival rungs, then ``_summons`` -- the phase-2 and stairway rules on those phases, the
shared rules (summon_response) elsewhere.  The Resistance potion's drink stands there too, but
its no-chance leave (Teleportation or *Destruction*) comes after the phase's own step (owner
2026-11-07 「Q25内部でのテレポートの優先度を下げる」: n1-c life-159 read six Scrolls of Teleportation
in phase 1, the first beside the spectral tyrannosaurus on [10,1]).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from hengbot import (
    attack_expectation,
    breeder_area_attack,
    combat_answer,
    me_capability,
    me_device_attacks,
    me_powers,
    me_powers_refresh,
    once_quest_recall,
    quest25_druj_gear,
    quest25_battle_record,
    quest25_geometry as geo,
    quest25_plan,
    quest_exposure,
    quest_firing_cells,
    quest_plan_base,
    quest_room_light,
    quest_room_sweep,
    resist_potion,
    speed_dose,
    summon_response,
    threat_tiers,
)
from hengbot.game_messages import ECHIZEN_PREFIX, KILL_LINES, KILL_LINES_EN
from hengbot.item_reservation import reserved_item_command
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.me_absorbed_substitutes import CAST_SUFFIX, carry_cast_key, item_cast_key
from hengbot.model import (
    Position, SV_POTION_HEALING, SV_ROD_DETECTION, SV_ROD_DISARMING, SV_SCROLL_DETECT_TRAP, SV_STAFF_DETECT_EVIL,
    SV_STAFF_DETECT_TRAP, SV_WAND_DISARMING, SV_WAND_TRAP_DOOR_DEST, TVAL_ROD, TVAL_SCROLL,
    TVAL_POTION, TVAL_STAFF, TVAL_WAND,
)
from hengbot.policy_constants import (
    DIRECTION_KEYS, FIXED_QUEST_TOUGHEST_KILL_TURNS, RANGED_MAX_DISTANCE, REST_MACRO, SEARCH_KEY,
    UP_STAIRS_KEY, WAIT_KEY,
)
from hengbot.quest_plan_base import HOLD_REASON, MELEE_REASON
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
_PLANNED_STEPS = frozenset({WALK_REASON, ENGAGE_REASON, RETREAT_REASON, SIGHT_REASON, WITHDRAW_REASON,
                            OUT_OF_FIRE_REASON, quest_room_sweep.EXIT_WALK_REASON,
                            RECALL_EXIT_WALK_REASON, RECALL_OUT_REASON, MASS_CELL_REASON})
# The plan's own '<' on the start stair: Recall active (_recall_wait) or Healing used up (_leave_by_exit).
_START_STAIR_LEAVES = frozenset({RECALL_EXIT_REASON, quest_room_sweep.EXIT_REASON})

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
# The counted rest between phases (between_phases 「回数を指定して休み、回数を見て続けるかを
# 決める」); the count is the Q34 recharge's (q34_recharge, LUNA-REPORT-me-rest-recharge).
RECHARGE_REST_KEY = "R100\r"
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
_UNSEEN = ("何か", "it", "It")
_ECHIZEN = ECHIZEN_PREFIX


# -- memory ----------------------------------------------------------------------------


@dataclass
class Battle:
    """One floor visit of the plan (``QuestFloorNavigator.phase_battle``)."""
    phase: int = 0
    kills: dict = field(default_factory=dict)        # race -> kills read from kill lines
    ready: bool = False            # this phase's preparation is done
    quiet: int = 0                 # actions without a new arrival (the 50-action waits)
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
    assumed_escaped: int = 0       # 「当たらない撃ちで補う」: counted escaped after the misses
    aimed_quyl: tuple | None = None    # the quylthulg cell the last shot was aimed at
    displaced: tuple | None = None     # (slot, signature) the druj's anti-teleport piece displaced
    retreating: bool = False       # below the line with the anti-teleport piece on: out of the line
    retreat_rest_hp: int | None = None  # HP when the last rest out of the line was keyed
    observed: tuple | None = None      # the board last read (key and walk_key share one)
    enlightened: bool = False      # the ambush's Potion of Enlightenment was drunk this visit
    beam: tuple | None = None      # (turn, origin, step) of the last answer aimed at a trap cell
    detection: tuple | None = None  # (turn, origin) of the last trap detection keyed for a cell
    detect_asked: frozenset = frozenset()  # trap cells a trap detection was keyed for
    recharge_rest_turn: int | None = None  # the turn the last counted recharge rest was keyed
    rest_cut: bool = False         # a sensed moving hostile cut that rest short
    fire_rest: tuple | None = None     # (decision, HP) of the last rest out of the casters' fire
    blind_sights: frozenset = frozenset()  # (target, cell): sight cells reached, the target not seen
    glowing: frozenset = frozenset()   # floor cells seen drawn lit (CAVE_GLOW in view)
    tome_hp: int | None = None     # the tome's HP read from its last seen health (an upper bound)
    # Phase 2 (owner 2026-11-11 「隘路で待って倒す」): the summons Teleportation was read from,
    # (race, last seen cell) each, and the decided boards since one of them was last seen.
    strong: tuple = ()
    strong_quiet: int = 0
    # Owner 2026-11-12 (quest25_sealed_room): the room landed in, (name, actions, step, last
    # counted turn, shots at the clear's target); None off the sealed rooms.
    room: tuple | None = None


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
        "phase", "kills", "searches", "cleared", "found", "escaped", "quyls_done",
        "melted", "lit", "observed", "teleports", "assumed_escaped", "displaced", "enlightened",
        "beam", "detection", "detect_asked", "glowing", "tome_hp", "room")}
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


def owns_leave_confirmation(policy, snapshot) -> bool:
    """The plan's start-stair step owns 「本当にこの階を去りますか？」 (the quest is left unfinished).

    Owner 2026-11-04 「体力回復を使い切り HP 20% 以下で開始の階段まで5歩以内なら踏む」 and 2026-11-09
    「段をやめ射線外で待つ」 (「開始の階段へ行ければ踏み」) decided the leave; the '<' they post must
    answer the question cmd-move.cpp confirm_leave_level asks on the taken ONCE quest floor.  n1-c
    life-181 (2026-11-09 19:18) posted quest25:recall-exit's '<' on [13,1] three times into the
    unowned confirm and retired on the stuck prompts."""
    return policy.last_reason in _START_STAIR_LEAVES and applies(policy, snapshot)


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

    def in_view(self) -> list:
        return [monster for monster in self.snapshot.visible_monsters
                if monster.hostile and monster.perception != "detected"]

    def kills(self, race: int) -> int:
        return self.battle.kills.get(race, 0)


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
    if battle.pen_misses >= ctx.values.pen_misses_to_escaped and not sees_ipsissimus_unseen(ctx.snapshot):
        battle.assumed_escaped = max(0, geo.ROSTER[geo.IPSISSIMUS] - ctx.kills(geo.IPSISSIMUS)
                                     - _escaped_count(ctx, assumed=False))


def _note_arrivals(ctx: _Ctx) -> None:
    """A new monster in view this phase restarts the 50-action wait; Ipsissimus out of the
    pen is escaped."""
    seen = {monster.index for monster in ctx.hostiles()}
    new = seen - ctx.battle.seen
    if new:
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


def _refused(ctx: _Ctx) -> frozenset:
    """The cells a weapon warning was refused on (``_warning_refused_cells``): never walked onto.

    n1-c life-200 (2026-11-12 12:03): after the refusal of (6,29)->(5,29) the walk aimed at
    (5,29) again on every decision; the gate turned the step into a wait and the wait into a
    flee, so the plan went back and forth.  The plan's walks go round them like an occupied cell,
    and a walk with no way round holds (``_step``)."""
    return frozenset((cell.y, cell.x) for cell in getattr(ctx.policy, "_warning_refused_cells", ()))


def _path(ctx: _Ctx, goals, taken=frozenset()) -> list[tuple[int, int]]:
    refused = _refused(ctx)
    goals = {tuple(goal) for goal in goals} - refused
    if not goals:
        return []
    start = ctx.here
    occupied = (frozenset((monster.position.y, monster.position.x) for monster in ctx.in_view())
                | taken | refused)
    exposure = geo.exposure_of(_avoided(ctx))
    return quest_plan_base._least_exposed_walk(
        ctx.navigator, ctx.snapshot, exposure, start, goals, occupied - goals)


def _step(ctx: _Ctx, cell, reason: str = WALK_REASON, *, guard: bool = True) -> str:
    if tuple(cell) in _refused(ctx):
        return _hold(ctx)   # the refused cell is not stepped onto: the plan holds where it is
    if guard and (held := _fire_guard(ctx, cell)) is not None:
        return held
    ctx.policy.last_reason = reason
    return ctx.policy._step_toward(ctx.snapshot, Position(*cell))


# Owner 2026-11-12: a race this many strong among the awake movers is a pack the walk shuns.
PACK_SIZE = 3


def _shunned(ctx: _Ctx) -> list:
    """The awake movers no walk goes toward (owner 2026-11-11 「召喚された強敵や T1 の敵の方へは歩かない」,
    widened 2026-11-12 to every phase, 第0段・第1段 included): one that alone is T1, a summons the
    phase-2 teleport was read from (``battle.strong``), a pack (``PACK_SIZE`` of a race)."""
    movers = [monster for monster in ctx.hostiles()
              if not monster.asleep and not monster.can_multiply
              and not quest_plan_base._never_moves(ctx.policy, monster)]
    if not movers:
        return []
    counts = {}
    for monster in movers:
        counts[monster.race_id] = counts.get(monster.race_id, 0) + 1
    strong = {race for race, _cell in ctx.battle.strong}
    shunned = []
    for monster in movers:
        if (counts[monster.race_id] >= PACK_SIZE or monster.race_id in strong
                or threat_tiers.tiered(ctx.policy, ctx.snapshot, [monster]).tier == "T1"):
            shunned.append(monster)
    return shunned


def _toward_cells(ctx: _Ctx, shunned) -> frozenset:
    """The cells beside each shunned mover and, of those in view, every cell nearer to it than the
    player stands (``_rally``'s rule)."""
    cells = [(monster.position.y, monster.position.x) for monster in shunned]
    seen = {monster.index for monster in ctx.in_view()}
    near = {(y + dy, x + dx) for (y, x) in cells for dy in (-1, 0, 1) for dx in (-1, 0, 1)}
    looked = [(monster.position.y, monster.position.x) for monster in shunned if monster.index in seen]
    near |= {cell for cell in ctx.terrain
             if any(quest_exposure.game_distance(cell, each) < quest_exposure.game_distance(ctx.here, each)
                    for each in looked)}
    return frozenset(near - {ctx.here})


def _shunned_hold(ctx: _Ctx, toward) -> str:
    """No way that does not go toward them: 「道が無ければ今いる召喚を受けないマスで迎え撃つ」 (owner
    2026-11-12, the 11-11 choke hold).  Off a summon-safe cell, a walk to the nearest one first."""
    targets = _fight_targets(ctx)
    summons = geo.summon_cells(ctx.terrain)
    if ctx.here in summons:
        safe = {cell for cell, kind in ctx.terrain.items()
                if kind in {"floor", "door"} and cell not in summons}
        path = _path(ctx, safe, toward)
        if len(path) >= 2:
            ctx.policy._declare_reach(Position(*path[-1]))
            return _step(ctx, path[1], WALK_REASON, guard=False)
    return _engage(ctx, targets) or _hold(ctx)


def _walk(ctx: _Ctx, goals, reason: str = WALK_REASON, *, taken=frozenset()) -> str | None:
    """The next step toward ``goals`` (the trap rule first); None there or with no way.
    ``taken``: cells the walk does not cross besides the monsters in view.  Never toward a shunned
    mover (``_shunned``): with no other way, the hold where the player stands."""
    goals = {tuple(goal) for goal in goals}
    if ctx.here in goals:
        return None
    shunned = _shunned(ctx)
    toward = _toward_cells(ctx, shunned) if shunned else frozenset()
    path = _path(ctx, goals, frozenset(taken) | toward)
    if len(path) < 2 and toward and len(_path(ctx, goals, taken)) >= 2:
        return _shunned_hold(ctx, toward)
    if len(path) < 2:
        return None
    nxt = path[1]
    trap = _trap_key(ctx, nxt)
    if trap is not None:
        return trap
    if (held := _fire_guard(ctx, nxt)) is not None:
        return held
    ctx.policy._declare_reach(Position(*path[-1]))
    return _step(ctx, nxt, reason, guard=False)


# -- the casters' fire (owner 2026-11-09) ------------------------------------------------
#
# Owner 2026-11-09 (n1-c life-178): 「第二に一歩で安全圏に移動して休息できるのに愚かにも戦闘を継続した
# こと。」, the formation's 「傷ついて敵がいなければ射線の外まで歩いて休む」 and 「クイル・破壊集大成・
# ドルジの射線のマスでは待たず、休まない」.  The fire is where a never-moving caster's spell reaches
# (phase3_spell_ranges): the tome's and the druj's own lines and the cells beside them their balls
# and breaths are aimed at, the quylthulgs' lines (their teleports need one).  Damaged is below the
# plan's rest line (room_sweep ``rest_below_ratio``).  With no enemy in view, a damaged player
# steps out of the fire when one step does it, and does not walk back into it: it rests first.


def _fire(ctx: _Ctx) -> frozenset:
    terrain = ctx.open_terrain()
    quyls_left = ctx.kills(geo.QUYL) < geo.ROSTER[geo.QUYL]
    cells = set()
    for cell, race in ctx.navigator.battlefield.monster_placements:
        if (race == geo.TOME and not _tome_done(ctx)) or (race == geo.DRUJ and not _druj_done(ctx)):
            cells |= geo.fire_cells(terrain, (cell,))
        elif race == geo.QUYL and quyls_left and cell not in ctx.battle.quyls_done:
            cells |= geo.line_cells(terrain, cell)
    return frozenset(cells)


def _damaged(ctx: _Ctx) -> bool:
    plan = ctx.profile.engagement_plan["room_sweep"]
    return ctx.snapshot.player.hp_ratio < float(plan["rest_below_ratio"])


def _rest_out_of_fire(ctx: _Ctx) -> str:
    """Rest on a cell out of the fire; a rest keyed on the decision before that did not raise HP
    is followed by one turn held (the game time passes either way)."""
    battle, player = ctx.battle, ctx.snapshot.player
    decision = int(getattr(ctx.policy, "_decision_sequence", 0))
    last = battle.fire_rest
    if ((last is not None and last[0] == decision - 1 and player.hp <= last[1]) or player.confused
            or player.food_state not in {"normal", "full", "gorged", "hungry"}):
        battle.fire_rest = None
        ctx.policy.last_reason = FIRE_HOLD_REASON
        return WAIT_KEY
    battle.fire_rest = (decision, player.hp)
    ctx.policy.last_reason = FIRE_REST_REASON
    return REST_MACRO


def _fire_guard(ctx: _Ctx, cell) -> str | None:
    """A damaged player with no enemy in view does not step from out of the fire into it."""
    if not _damaged(ctx) or ctx.in_view():
        return None
    fire = _fire(ctx)
    if tuple(cell) not in fire or ctx.here in fire:
        return None
    return _rest_out_of_fire(ctx)


def _safe_cells(ctx: _Ctx, fire) -> set:
    cells = {cell for cell, kind in ctx.terrain.items() if kind in {"floor", "door"} and cell not in fire}
    if _ipsissimus_alive(ctx):
        cells -= geo.summon_cells(ctx.terrain)
    return cells


def _withdraw(ctx: _Ctx, reason: str = WITHDRAW_REASON) -> str | None:
    """Out of the fire by the least exposed walk, then the rest there."""
    fire = _fire(ctx)
    if ctx.here not in fire:
        return _rest_out_of_fire(ctx)
    refused = _refused(ctx)
    safe = _safe_cells(ctx, fire) - refused
    occupied = frozenset((monster.position.y, monster.position.x) for monster in ctx.in_view())
    terrain = quest_plan_base._terrain_of(ctx.navigator, ctx.snapshot, water=False)
    terrain[ctx.here] = "floor"
    path = quest_exposure.least_exposed_path(terrain, geo.exposure_of(fire | _avoided(ctx)),
                                             ctx.here, safe, (occupied - safe) | refused)
    if len(path) < 2:
        return None
    trap = _trap_key(ctx, path[1])
    if trap is not None:
        return trap
    return _step(ctx, path[1], reason, guard=False)


def _out_of_fire_key(policy, snapshot) -> str | None:
    """「一歩で安全圏に移動して休息できる」: damaged in the fire with no enemy in view, one step out."""
    ctx = _ctx(policy, snapshot)
    if ctx is None or not _damaged(ctx) or ctx.in_view():
        return None
    fire = _fire(ctx)
    if ctx.here not in fire:
        return None
    occupied = {(monster.position.y, monster.position.x) for monster in ctx.hostiles()}
    traps = {cell for cell in (*ctx.navigator.battlefield.trap_cells,
                               *ctx.navigator.battlefield.maybe_trap_cells)
             if cell not in ctx.battle.cleared}
    beside = sorted(cell for cell in _safe_cells(ctx, fire) - occupied - traps - _refused(ctx)
                    if quest_exposure.game_distance(cell, ctx.here) == 1)
    if not beside:
        return None
    return _step(ctx, beside[0], OUT_OF_FIRE_REASON, guard=False)


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
        _note_beam(ctx, cell)
        ctx.policy.last_reason = DISARM_REASON
        return ctx.policy._step_toward(ctx.snapshot, Position(*cell))   # the disarm command
    if cell in battle.found:   # seen with its trap, now without: disarmed
        battle.cleared = battle.cleared | {cell}
        return None
    if grid is not None and grid.object_count:
        # An item lies there, so no trap does: a trap terrain has no DROP (TerrainDefinitions),
        # an item is dropped only where Grid::can_drop_item, and a trap is placed only on a
        # clean grid (FloorType::place_trap_at, Grid::is_clean).  Searching would never find one.
        battle.cleared = battle.cleared | {cell}
        return None
    if _settled_on_board(ctx, grid):
        battle.cleared = battle.cleared | {cell}
        return None
    device = _disarm_device_key(ctx, cell)
    if device is not None:
        battle.cleared = battle.cleared | {cell}
        _note_beam(ctx, cell)
        return device
    if cell not in battle.detect_asked:
        detect = _trap_detect_key(ctx)
        if detect is not None:
            battle.detect_asked = battle.detect_asked | {cell}
            battle.detection = (int(ctx.snapshot.turn), ctx.here)
            return detect
    searched = battle.searches.get(cell, 0)
    limit = ctx.values.maybe_trap_searches if maybe and not always else ctx.values.trap_searches
    if searched >= limit:
        battle.cleared = battle.cleared | {cell}   # 「罠は無いとみなして通る」
        return None
    battle.searches = {**battle.searches, cell: searched + 1}
    ctx.policy.last_reason = SEARCH_REASON
    return SEARCH_KEY


def _settled_on_board(ctx: _Ctx, grid) -> bool:
    """The board's own record that the grid holds no hidden trap: known, no trap shown, and no
    longer CAVE_UNSAFE (grid_map.unsafe_rows).  Every grid of a dungeon floor starts unsafe
    (floor-generator.cpp wipe_generate_random_floor_flags); a trap detection clears it within its
    range after disclosing every trap there (spells-detection.cpp detect_feat_flag), KILL_TRAP and
    KILL_DOOR clear it on the grids of their path in sight after destroying the trap
    (effect-feature.cpp), and a step clears it only in light or where no trap is (player-move.cpp
    move_player_effect).  The flag is the game's, so it outlives a restart of the bot."""
    return (grid is not None and grid.known and not grid.trap
            and ctx.snapshot.unsafe_rows is not None and not ctx.snapshot.unsafe_rows_malformed
            and not ctx.snapshot.unsafe_rows[grid.position.y][grid.position.x])


def _trap_detect_key(ctx: _Ctx) -> str | None:
    """Owner 2026-11-09 「罠探知があるなら使用することで確定」: the absorbed Detect Traps power,
    else a carried Staff or Scroll of Detect Traps (detect_traps, DETECT_RAD_DEFAULT)."""
    key = me_powers.power_key(ctx.policy, ctx.snapshot, me_powers.TRAP_CELL)
    if key is not None:
        return key
    player = ctx.snapshot.player
    if player.blind or player.confused or player.hallucinated:
        return None
    for tval, sval, verb in ((TVAL_STAFF, SV_STAFF_DETECT_TRAP, "staff"),
                             (TVAL_SCROLL, SV_SCROLL_DETECT_TRAP, "read")):
        item = next((item for item in ctx.snapshot.inventory if item.tval == tval and item.known
                     and item.sval == sval and (tval != TVAL_STAFF or item.charges > 0)), None)
        if item is not None:
            key = reserved_item_command(ctx.policy, ctx.snapshot, verb, item)
            if key is not None:
                ctx.policy.last_reason = TRAP_DETECT_REASON
                return key
    return None


# The lines of a use that went off without its effect (cmd-magiceat.cpp, use-execution.cpp).
_USE_FAILED_LINES = ("呪文をうまく唱えられなかった！", "You failed to get the magic off!",
                     "杖をうまく使えなかった。", "You failed to use the staff properly.")


def _settle_detection(ctx: _Ctx) -> None:
    """The board after a trap detection keyed for a cell: unless the use failed, every trap
    within the detected area is shown (detect_feat_flag discloses each), so each map trap cell
    within ``DETECT_RAD - 1`` of where it was used is answered: found when its trap is shown,
    else cleared (no trap)."""
    battle = ctx.battle
    if battle.detection is None or ctx.snapshot.turn <= battle.detection[0]:
        return
    _turn, origin = battle.detection
    battle.detection = None
    if any(message_text(message) in _USE_FAILED_LINES for message in ctx.snapshot.messages):
        return
    bf = ctx.navigator.battlefield
    for cell in {*bf.trap_cells, *bf.maybe_trap_cells}:
        if quest_exposure.game_distance(origin, cell) > me_powers.DETECT_RAD - 1:
            continue
        grid = ctx.snapshot.grid_at(Position(*cell))
        if grid is None:
            continue
        if grid.trap:
            battle.found = battle.found | {cell}
        else:
            battle.cleared = battle.cleared | {cell}


# The line KILL_TRAP prints for each trap it destroys on a known grid (effect-feature.cpp).
_FLASH_LINES = ("まばゆい閃光が走った！", "There is a bright flash of light!")


def _note_beam(ctx: _Ctx, cell) -> None:
    """An answer aimed from beside at the trap cell ``cell``: a disarming power or device goes
    on along the line past it (spells-beam.cpp disarm_trap, PROJECT_BEAM)."""
    here = ctx.here
    step = ((cell[0] > here[0]) - (cell[0] < here[0]), (cell[1] > here[1]) - (cell[1] < here[1]))
    ctx.battle.beam = (int(ctx.snapshot.turn), here, step)


def _settle_beam(ctx: _Ctx) -> None:
    """The board after the aimed answer: when the game printed KILL_TRAP's flash, the beam went
    off, and every trap on its line is gone (cave_alter_feat DISARM on each grid of the path, the
    hidden ones too: has_trap_at reads the terrain, not the mimic).  n1-c life-174 (2026-11-09):
    one beam from [1,18] destroyed the ten traps of [1,8]-[1,17] (「まばゆい閃光が走った！ <x10>」),
    the plan counted only [1,17] answered, and searched [1,10] for a trap that was gone until the
    loop guard stopped it."""
    battle = ctx.battle
    if battle.beam is None or ctx.snapshot.turn <= battle.beam[0]:
        return
    _turn, origin, step = battle.beam
    battle.beam = None
    if not any(message_text(message) in _FLASH_LINES for message in ctx.snapshot.messages):
        return
    terrain = ctx.open_terrain()
    bf = ctx.navigator.battlefield
    traps = {*bf.trap_cells, *bf.maybe_trap_cells}
    line = set()
    cell = tuple(origin)
    for _ in range(geo.MAX_SPELL_RANGE):
        cell = (cell[0] + step[0], cell[1] + step[1])
        if terrain.get(cell) not in geo.PROJECTING_KINDS:
            break
        line.add(cell)
    battle.cleared = battle.cleared | (line & traps)


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


def _fire_options(ctx: _Ctx, grid, race: int, *, piercing: bool = False, area_only: bool = False,
                  missiles: bool = True) -> list:
    """(expected damage, key maker) of every attack aimed at ``grid``; ``piercing``: only one that
    passes the bodies on the way (a beam, a ball or a breath aimed at the grid); ``missiles``:
    the launcher too."""
    options = [(damage, lambda make=make: make(grid))
               for damage, radius, shape, make in _ball_powers(ctx, race)
               if not area_only or shape == "ball"]
    if not area_only:
        if (beam := _beam_key(ctx, race, grid)) is not None:
            options.append(beam)
        if not piercing and missiles:
            distance = quest_exposure.game_distance(ctx.here, tuple(grid))
            launcher = attack_expectation.launcher_against(ctx.policy, ctx.snapshot, race, distance)
            if launcher > 0:
                options.append((launcher, lambda: _launcher_grid_key(ctx, grid)))
    return options


def _fire_at(ctx: _Ctx, grid, race: int, *, piercing: bool = False, area_only: bool = False,
             missiles: bool = True) -> str | None:
    """The strongest attack aimed at ``grid`` (「一番ダメージの出る攻撃」), of ``_fire_options``."""
    options = _fire_options(ctx, grid, race, piercing=piercing, area_only=area_only, missiles=missiles)
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
        if target.distance > 1 and (shot := quest_plan_base._shot(policy, snapshot, target)) is not None:
            ctx.battle.aimed_race = None
            return shot
    return None


def _fight_targets(ctx: _Ctx) -> list:
    """What this phase fights in view: every mover, not the immobile casters of later phases
    nor the breeders (``_breeders_in_line_key``)."""
    return [monster for monster in ctx.in_view()
            if monster.race_id not in _LATER_IMMOBILE and not monster.can_multiply]


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
    ctx.battle.recharge_rest_turn = int(ctx.snapshot.turn)
    ctx.policy.last_reason = RECHARGE_REASON
    return RECHARGE_REST_KEY


def _sensed_movers(ctx: _Ctx) -> list:
    """Awake hostiles known only by sensing (ESP, detection) whose race can move."""
    seen = {monster.index for monster in ctx.in_view()}
    found = []
    for monster in ctx.hostiles():
        if monster.index in seen or monster.asleep:
            continue
        knowledge = attack_expectation.race_knowledge(ctx.policy, monster.race_id)
        if knowledge is None or "NEVER_MOVE" not in knowledge.flags:
            found.append(monster)
    return found


def _note_rest_cut(ctx: _Ctx) -> None:
    """The board after a counted recharge rest: cut short while a sensed hostile moves.

    A sensed (ml) hostile that moves disturbs the player when it is of the player's level or
    above, or of a race never killed (monster-move.cpp, disturb_high and disturb_unknown on by
    default in option-types-table.cpp), and a disturbance ends the rest.  ``R100`` is 100 player
    turns, at least 200 game turns even at the fastest speed (speed_to_energy caps at 49 of the
    100 a turn needs), so a rest that ended in fewer than ``REST_CUT_GAME_TURNS`` was cut.
    n1-c life-174 (2026-11-09 03:16:46): on [2,24] every rest ended after 3-13 game turns while
    the Dreadmaster, sensed undead, came through the walls, and the read-and-rest cycle repeated
    until the loop guard stopped the bot."""
    battle = ctx.battle
    if battle.recharge_rest_turn is None or ctx.snapshot.turn <= battle.recharge_rest_turn:
        return
    elapsed = int(ctx.snapshot.turn) - battle.recharge_rest_turn
    battle.recharge_rest_turn = None
    if elapsed < REST_CUT_GAME_TURNS and _sensed_movers(ctx):
        battle.rest_cut = True


def _full_hp_key(ctx: _Ctx) -> str | None:
    player = ctx.snapshot.player
    if player.hp >= player.max_hp:
        return None
    ctx.policy.last_reason = FULL_HP_REASON
    return FULL_HP_REST_KEY


def _prepare(ctx: _Ctx, phase) -> str | None:
    """On a quiet board, before the phase's first step: the recharge, then full HP.

    Owner 2026-11-09 「持ち場へ歩き静まれば休む」: 「感知した動く敵が休みを切る間は、見えている敵が
    いる時と同じに扱い、その段の持ち場へ歩いて備える。静かになったら充填の休みを続ける。」  After a
    recharge rest a sensed moving hostile cut short (``_note_rest_cut``), the board is not quiet
    while such a hostile is sensed: the phase's step runs, as with a hostile in view; once none
    is sensed the preparation goes on."""
    if ctx.battle.ready:
        return None
    if ctx.in_view() or ctx.battle.rallying or ctx.battle.strong:
        return None   # phase 2's rally owns the board (``_rally``); it rests again when it ends
    if ctx.battle.rest_cut:
        if _sensed_movers(ctx):
            return None
        ctx.battle.rest_cut = False
    key = (_recharge_key(ctx) if ctx.battle.phase else None) or (
        _full_hp_key(ctx) if phase.full_hp else None)
    if key is None:
        ctx.battle.ready = True
    return key


# -- the phases -------------------------------------------------------------------------


def _ambush_done(ctx: _Ctx) -> bool:
    return all(ctx.kills(race) >= geo.ROSTER[race]
               for race in (geo.HOUND, geo.SKELETAL_T, geo.VAMPIRE, geo.SPECTRAL_T))


def _ambush_enlightenment(ctx: _Ctx) -> str | None:
    """Owner 2026-11-07 「Q25の段階1、待ち伏せ中に安全で啓蒙の薬を持っているなら飲むを追加」, 安全 being
    「攻撃が届く範囲に=視界内に敵がいない」: no hostile in view (a detected one out of sight does not
    count), the carried Potion of Enlightenment is drunk, once per floor visit.  The game:
    quaff-effects.cpp wiz_lite maps and lights the whole level and shows no monster."""
    if ctx.battle.enlightened or ctx.in_view():
        return None
    potion = quest_room_light.carried_potion(ctx.policy, ctx.snapshot, quest_room_light.ROOM_LIGHT_POTION)
    if potion is None:
        return None
    key = reserved_item_command(ctx.policy, ctx.snapshot, "quaff", potion)
    if key is not None:
        ctx.battle.enlightened = True
        ctx.policy.last_reason = ENLIGHTEN_REASON
    return key


def _ambush(ctx: _Ctx) -> str | None:
    battle = ctx.battle
    if (potion := _ambush_enlightenment(ctx)) is not None:
        return potion
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


def _match_strong(ctx: _Ctx, entries) -> list:
    """Each remembered (race, cell) with the hostile of its race now in view or sensed nearest to
    the cell (None when none is left): the game's monster index is no name, compact_monsters
    reorders it (monster-compaction.cpp, every turn the floor holds 32 dead slots)."""
    left = list(ctx.hostiles())
    matched = []
    for race, cell in entries:
        same = [monster for monster in left if monster.race_id == race]
        if not same:
            matched.append(None)
            continue
        monster = min(same, key=lambda each: quest_exposure.game_distance(
            (each.position.y, each.position.x), cell))
        left.remove(monster)
        matched.append(monster)
    return matched


def _note_strong(ctx: _Ctx) -> None:
    """Owner 2026-11-11 「隘路で待って倒す」: the summons Teleportation was read from are remembered
    (owner 2026-11-09 「起きた敵も最後の位置を覚える」) until killed or not seen for the plan's wait.

    Each decided board: the cell of one in view or sensed is renewed and the wait starts over; a
    kill line naming its race forgets one of that race; with none of them seen the board counts,
    and ``wait_limits.quiet_actions`` such boards (the phase-2 wait owner 2026-11-06 「50ターン待っ
    ても来なくなったら」 bounds) forget them all: it went elsewhere."""
    battle = ctx.battle
    if not battle.strong:
        battle.strong_quiet = 0
        return
    strong = list(battle.strong)
    for message in ctx.snapshot.messages:
        victim = _killed_name(message_text(message))
        if victim is None:
            continue
        killed = next((entry for entry in strong if victim in _names(ctx.policy, entry[0])), None)
        if killed is not None:
            strong.remove(killed)
    matched = _match_strong(ctx, strong)
    strong = [(race, cell if monster is None else (monster.position.y, monster.position.x))
              for (race, cell), monster in zip(strong, matched)]
    seen = any(monster is not None for monster in matched)
    battle.strong_quiet = 0 if seen else battle.strong_quiet + 1
    if battle.strong_quiet >= ctx.values.quiet_actions:
        strong, battle.strong_quiet = [], 0
    battle.strong = tuple(strong)


def _remember_strong(ctx: _Ctx, summons) -> None:
    """The summons in view join the remembered ones; one of a race already remembered is it."""
    kept = list(ctx.battle.strong)
    for monster in summons:
        same = [entry for entry in kept if entry[0] == monster.race_id]
        if same:
            kept.remove(same[0])
    ctx.battle.strong = tuple(kept) + tuple(
        (monster.race_id, (monster.position.y, monster.position.x)) for monster in summons)
    ctx.battle.strong_quiet = 0


def _rally(ctx: _Ctx) -> str | None:
    """After the teleport: 「接敵する前に移動できるなら、なるべく隘路に陣取る」.

    Owner 2026-11-11 「隘路で待って倒す」 (n1-c life-195): 「仕切り直しの隘路（召喚を受けないマス）で、最後に
    見えた強敵が来るのを待って迎え撃つ。倒してから立ち位置へ戻る。HP の線を切ったら今の決まりで立て直す。」
    While a summons Teleportation was read from is remembered (``_note_strong``), the choke holds
    and does not end when no enemy is in view; the walk to it never goes toward one: no choke
    within two cells of where one is (or was last seen), no cell beside one crossed, and with one
    in view no step onto a cell nearer to it than the player stands.  The rally ends on the choke
    with none remembered and none in view; the phase then rests to full HP again before its walk
    to [7,1] (phase2 「全快して(7,1)に移動」).  The HP line and the instant death answer above the
    plan, as before."""
    battle = ctx.battle
    targets = _fight_targets(ctx)
    if any(monster.distance <= 1 for monster in targets):
        return _engage(ctx, targets)
    summons = geo.summon_cells(ctx.terrain)
    chokes = {cell for cell in ctx.navigator.battlefield.chokepoints if cell not in summons}
    if ctx.here in chokes:
        if targets:
            return _engage(ctx, targets) or _hold(ctx)
        if battle.strong:
            return _hold(ctx)
        battle.rallying = False
        battle.ready = False
        return None
    cells = [cell for _, cell in battle.strong]
    seen = [cell for (_, cell), monster in zip(battle.strong, _match_strong(ctx, battle.strong))
            if monster is not None]
    near = {(y + dy, x + dx) for (y, x) in cells for dy in (-1, 0, 1) for dx in (-1, 0, 1)}
    near |= {cell for cell in ctx.terrain
             if any(quest_exposure.game_distance(cell, each) < quest_exposure.game_distance(ctx.here, each)
                    for each in seen)}
    # Never toward it (owner 2026-11-11, n1-c life-195 walked west into the dracolich's breaths).
    goals = {cell for cell in chokes
             if all(quest_exposure.game_distance(cell, each) > 2 for each in cells)
             and all(quest_exposure.game_distance(cell, each) >= quest_exposure.game_distance(ctx.here, each)
                     for each in seen)}
    return (_walk(ctx, goals, taken=frozenset(near - {ctx.here})) or _engage(ctx, targets)
            or (_hold(ctx) if battle.strong else None))


def _ipsissimus(ctx: _Ctx) -> str | None:
    battle, policy, snapshot = ctx.battle, ctx.policy, ctx.snapshot
    if (battle.rallying or battle.strong) and (key := _rally(ctx)) is not None:
        return key
    seen = [monster for monster in ctx.hostiles() if monster.race_id == geo.IPSISSIMUS
            and (monster.position.y, monster.position.x) in geo.IPSISSIMUS_PEN]
    aim = (seen[0].position.y, seen[0].position.x) if seen else geo.IPSISSIMUS_AIM
    # Owner 2026-11-09 「Q25 の全部の段に広げる」 (``_unseen_fire``): no arrow at the pen it does not
    # see.  With no attack aimed at the grid, the walk goes to a cell that sees the pen instead of
    # [5,1]; seen there, the fire is from there.  Every such cell reached with none seen: they are
    # out of the pen (the pen's 「当たらない撃ちで補う」 reads the same: counted escaped).
    in_sight = bool(_seen_at(ctx, geo.IPSISSIMUS, geo.IPSISSIMUS_PEN))
    from_stand = in_sight or bool(_fire_options(ctx, aim, geo.IPSISSIMUS, missiles=False))
    walk = geo.PHASE2_WALK
    walking = from_stand and ((ctx.here not in walk and not in_sight)
                              or (ctx.here in walk and ctx.here != walk[-1]))
    others = [monster for monster in ctx.in_view() if monster.race_id != geo.IPSISSIMUS]
    summons = _summons_in_view(ctx, others)
    # Owner 2026-11-11 (n1-c life-195): the summons are weighed before the walk to the stand, not
    # after it -- a walk never goes on toward a summons the threat would teleport from.  A low
    # threat on the walk lets it go on (the summons are answered on [5,1] as before).
    threat = bool(summons) and policy._is_material_threat(snapshot, policy._physical_hostiles(snapshot))
    if summons and (threat or not walking):
        piercing = _has_piercing(ctx, geo.IPSISSIMUS, aim)
        # 「貫通可能な攻撃かつ脅威度が高くない場合は先にイプシシマスを倒し増援を断つ」, the threat read as the
        # 11-05 summon rule reads it (summon_response ``counter_shot_key``): 「見えている敵の3ターンの
        # 想定被害が今の HP の半分以上なら高い」.
        if not threat and piercing:
            return _pen_shot(ctx, _fire_at(ctx, aim, geo.IPSISSIMUS, piercing=True))
        # 「それ以外の場合はテレポートで仕切り直す。接敵する前に移動できるならなるべく隘路に陣取る」; what it is
        # read from is remembered and waited for on the choke (``_rally``, owner 2026-11-11).
        _remember_strong(ctx, summons)
        battle.rallying = True
        scroll = policy._find_teleport_scroll(snapshot) if policy._can_read_scrolls(snapshot) else None
        if scroll is not None:
            policy.last_reason = TELEPORT_REASON
            return policy._read_key(snapshot, scroll)
        return _engage(ctx, summons) or _rally(ctx)
    if from_stand:
        if ctx.here not in walk and not in_sight:
            return _walk(ctx, {walk[0]})
        if ctx.here == walk[0] and (haste := _haste(ctx)) is not None:
            return haste    # 「事前に加速して(6,1)(5,1)と移動」
        if ctx.here in walk and ctx.here != walk[-1]:
            return _step(ctx, walk[walk.index(ctx.here) + 1])
    if summons:
        # A low threat in the way of the walk: fought where the player stands, not teleported from.
        return _engage(ctx, summons) or _hold(ctx)
    piercing = bool(others) and _has_piercing(ctx, geo.IPSISSIMUS, aim)
    # The wall-passers' stragglers (the spectres and shadow demons the quiet wait of the
    # wall-passers' phase left alive) are no reinforcements and no reason to teleport: owner
    # 2026-11-09 「ここでテレポートすると以降の段取りが全て崩れるので逃走回数は最小にしたい。」  They are
    # ignored, beside the player or not (owner 2026-11-09 「無視して囲いを撃つ」, phase2 「イプシシマスとの
    # 戦闘中に出会った残党は無視する。イプシシマスを全て倒すかテレポートさせたあとで対処。」): the fire stays on
    # the pen, through them when it can; the stragglers' phase fights them on [5,1] afterwards.  The
    # survival rungs above the plan (the 1-turn 即死, the HP line) still answer first.
    if not from_stand:
        return _pen_sight(ctx, aim)
    return _pen_shot(ctx, _fire_at(ctx, aim, geo.IPSISSIMUS, piercing=piercing, missiles=in_sight))


def _pen_sight(ctx: _Ctx, aim) -> str | None:
    """Unseen, no attack aimed at the grid: to a cell that sees the pen's ``aim``; none left (each
    reached with no Ipsissimus seen), the ones not killed nor seen out are counted escaped."""
    if (key := _walk_to_sight(ctx, aim, _sights(ctx, aim))) is not None:
        return key
    battle = ctx.battle
    battle.assumed_escaped = max(0, geo.ROSTER[geo.IPSISSIMUS] - ctx.kills(geo.IPSISSIMUS)
                                 - _escaped_count(ctx, assumed=False))
    return None


def _summons_in_view(ctx: _Ctx, others) -> list:
    """Of the non-Ipsissimus in view on phase 2, the summoned ones; the rest are stragglers.

    A straggler (owner 2026-11-06 phase1_wall_passers / phase2) is a spectre or shadow demon of
    the roster that the wall-passers' phase left alive: it was on the floor before the phase, so
    it is not first seen on a board carrying a summon cast (summon_response's reading of the
    game's cast lines; ``Battle.summoned``), and there are no more of a race than the roster less
    the kills read.  Anything else -- another race, one first seen with a cast, one over that
    count -- is a summons.  The nearest are counted as stragglers first."""
    left = {race: max(0, geo.ROSTER[race] - ctx.kills(race)) for race in (geo.SPECTRE, geo.SHADOW)}
    summons = []
    for monster in sorted(others, key=lambda monster: monster.distance):
        if left.get(monster.race_id, 0) > 0 and monster.index not in ctx.battle.summoned:
            left[monster.race_id] -= 1
        else:
            summons.append(monster)
    return summons


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
               if monster.race_id not in _LATER_IMMOBILE - {geo.IPSISSIMUS} and not monster.can_multiply]
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


def _quyls(ctx: _Ctx, plan=None) -> str | None:
    plan = _quyl_plan(ctx) if plan is None else plan
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
        # Owner 2026-11-09 「Q25 の全部の段に広げる」 (``_unseen_fire``): unseen, no arrow; the ball at
        # its grid, else a cell of its line that sees it.
        seen = bool(_seen_at(ctx, geo.QUYL, {cell}))
        if not seen and not _fire_options(ctx, cell, geo.QUYL, missiles=False):
            return _walk_to_sight(ctx, cell, _sights(ctx, cell, lines))
        if ctx.here not in lines:
            return _walk(ctx, lines)   # 「飛ばされたら戻って撃ち直す」
        return _haste(ctx) or _unseen_fire(ctx, cell, geo.QUYL, seen=seen)
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
    # Owner 2026-11-09 Q1 「見えない時は矢を撃たない。マスを狙う範囲の攻撃（取り込んだボール・ブレス
    # など）で削り、無ければ相手が見えるマスへ移って撃つ。」 and 「1に加え、倒しきれなければ下がる。
    # 生存を優先させたはず」 (「数行動で倒しきる見込みが無ければ、射線の外へ下がって休み、やり直す。」).
    # From [5,5] the tome is not in view (n1-c life-178: arrows at half the hit chance, ``geo.los``);
    # an attack aimed at its grid does not need the sight, the launcher does.  The plan with the
    # larger expected damage is taken: the near stands with the grid-aimed attacks, or a cell
    # that sees it with the launcher too.  Damaged, a plan that needs more actions than the
    # quest's kill horizon (FIXED_QUEST_TOUGHEST_KILL_TURNS) withdraws out of the fire and rests.
    seen = any(monster.race_id == geo.TOME for monster in ctx.in_view())
    hp = _tome_hp(ctx)
    stands = [stand for stand in geo.TOME_NEAR_STANDS if _path(ctx, {stand}) or ctx.here == stand]
    near = max((damage for damage, _make in _fire_options(ctx, tome, geo.TOME, missiles=False)),
               default=0.0)
    sights = _sights(ctx, tome)
    far = 0.0
    if sights:
        distance = min(quest_exposure.game_distance(cell, tome) for cell in sights)
        far = max(near, attack_expectation.launcher_against(ctx.policy, ctx.snapshot, geo.TOME, distance))
    if stands and near > 0 and near >= far:
        if _hopeless(ctx, hp, near):
            return _withdraw(ctx)
        if ctx.here not in stands:
            return _walk(ctx, {stands[0]})
        return _haste(ctx) or _fire_at(ctx, tome, geo.TOME, missiles=seen)
    if far <= 0:
        return None
    if _hopeless(ctx, hp, far):
        return _withdraw(ctx)
    if seen:
        return _haste(ctx) or _fire_at(ctx, tome, geo.TOME)
    return _walk_to_sight(ctx, tome, sights)


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


# -- unseen immobile targets (owner 2026-11-09) ------------------------------------------
#
# Owner 2026-11-09 Q1 「見えない時は矢を撃たない。マスを狙う範囲の攻撃（取り込んだボール・ブレスなど）で
# 削り、無ければ相手が見えるマスへ移って撃つ。」 (the tome first), widened the same day 「Q25 の全部の段に
# 広げる」: every phase that shoots a never-moving target it may not see -- the Ipsissimus pen [7,17],
# the quylthulgs, the stairway to hell, the druj.  An unseen monster is hit at half the chance
# (shoot.cpp test_hit_fire with ``monster.ml`` false); an attack aimed at the grid (a ball or a
# breath, spells-launcher.cpp fire_ball drops PROJECT_STOP) or a beam along its ray needs no sight.


def _seen_at(ctx: _Ctx, race: int, cells) -> list:
    """The monsters of ``race`` in view (telepathy included: ``ml``) on ``cells``."""
    cells = {tuple(cell) for cell in cells}
    return [monster for monster in ctx.in_view()
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


def _walk_to_sight(ctx: _Ctx, target, sights) -> str | None:
    """To the nearest cell of ``sights``; this cell is one of them and the target was not seen
    here: the line was there, the target was not (not this cell again)."""
    target = tuple(target)
    if ctx.here in sights:
        ctx.battle.blind_sights = ctx.battle.blind_sights | {(target, ctx.here)}
        sights = sights - {ctx.here}
    return _walk(ctx, sights, SIGHT_REASON)


def _unseen_fire(ctx: _Ctx, grid, race: int, *, seen: bool, piercing: bool = False,
                 among=None) -> str | None:
    """The strongest attack at ``grid``: the launcher too when the target is seen; unseen, an
    attack aimed at the grid or along a ray, else the walk to a cell that sees it (of ``among``,
    the phase's stands, when one does; else any)."""
    if seen:
        return _fire_at(ctx, grid, race, piercing=piercing)
    key = _fire_at(ctx, grid, race, piercing=piercing, missiles=False)
    if key is not None:
        return key
    return _walk_to_sight(ctx, grid, _sights(ctx, grid, among) or _sights(ctx, grid))


# The health bar's length (system/monster-entity.cpp get_hp_bar_data: clamp(percent / 10 + 1, 1, 10))
# bounds the percent from above: 10 * length - 1 below the full bar.
def _bar_percent(length: int) -> int:
    return 100 if length >= 10 else max(1, 10 * int(length) - 1)


def _note_tome_health(ctx: _Ctx) -> None:
    """Owner 2026-11-09 「見えた傷の具合で見込む」: the tome's HP from its health when seen -- the
    board's band (bot-json-output.cpp monster_health_band: unhurt ... almost dead, MonsterState
    ``hp`` its upper bound on the race's maximum) and, when the health bar tracks it, the bar's
    length -- the lower of the two; kept while it is not seen."""
    for monster in ctx.in_view():
        if monster.race_id != geo.TOME:
            continue
        hp = monster.hp
        bar = ctx.snapshot.health_bar
        if bar is not None and bar[0] and bar[1] == monster.index and bar[2] is not None:
            hp = min(hp, max(1, (monster.max_hp * _bar_percent(bar[2]) + 99) // 100))
        ctx.battle.tome_hp = int(hp)
        return


def _tome_hp(ctx: _Ctx) -> float:
    """The tome's HP for the kill estimate: its last seen health (``_note_tome_health``), else
    (never seen) the race's maximum (owner 2026-11-09 「見えていなければ最後に見えた状態、一度も見えて
    いなければ最大の500」: 50d10)."""
    if ctx.battle.tome_hp is not None:
        return float(ctx.battle.tome_hp)
    knowledge = attack_expectation.race_knowledge(ctx.policy, geo.TOME)
    return float(knowledge.max_hp) if knowledge is not None else 0.0


def _hopeless(ctx: _Ctx, hit_points: float, per_action: float) -> bool:
    return _damaged(ctx) and attack_expectation.actions_to_kill(
        hit_points, per_action) > FIXED_QUEST_TOUGHEST_KILL_TURNS


def _masses_seen(ctx: _Ctx) -> list:
    return [monster for monster in ctx.hostiles() if monster.race_id == geo.MASS]


def _masses_done(ctx: _Ctx) -> bool:
    return (ctx.here == geo.MASS_STAND and not ctx.door_closed(geo.MASS_DOOR) and ctx.battle.lit
            and not _masses_seen(ctx))


def _masses(ctx: _Ctx) -> str | None:
    opening = ctx.door_closed(geo.MASS_DOOR) or not ctx.battle.lit
    if opening and ctx.here != geo.MASS_STAND:
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
    if (key := _walk_to_widest(ctx)) is not None:
        return key
    if (key := _breeders_in_line_key(ctx)) is not None:
        return key   # owner 2026-11-08: the aim with the most kills when it catches two or more
    for monster in sorted(_masses_seen(ctx), key=lambda each: each.distance):
        key = _fire_at(ctx, (monster.position.y, monster.position.x), geo.MASS)
        if key is not None:
            return key
    if ctx.here != geo.MASS_STAND:
        return _walk(ctx, {geo.MASS_STAND})   # none to shoot from here: the plan's cell looks again
    return None


def _mass_firing_cells(ctx: _Ctx) -> dict:
    """reach -> the cells a shot at the masses in view reaches that many from (owner 2026-11-09
    「一番多く届く位置へ」, quest_firing_cells ``reach``, the Q2 fix's measure), of the cells the plan
    may stand on: floor through the doors as the board shows them, no trap not answered, out of
    the casters' fire (``_fire``: the tome, the quylthulgs, the druj), out of the summons while the
    Ipsissimus live, out of the dreadmaster's vision while it lives (phase4 「[1,6] には罠が無く、
    ドリードマスターの感知範囲の外で、召喚も受けない」), not beside a mass (they drain by touch) nor on a
    monster.  The plan's [1,6] is one of them."""
    masses = _masses_seen(ctx)
    if not masses:
        return {}
    bf = ctx.navigator.battlefield
    avoid = set(_fire(ctx)) | {cell for cell in (*bf.trap_cells, *bf.maybe_trap_cells)
                               if cell not in ctx.battle.cleared}
    if _ipsissimus_alive(ctx):
        avoid |= geo.summon_cells(ctx.terrain)
    if not _dreadmaster_done(ctx):
        dreadmaster = next((cell for cell, race in bf.monster_placements if race == geo.DREADMASTER), None)
        if dreadmaster is not None:
            avoid |= geo.vision_cells(ctx.terrain, dreadmaster, geo.DREADMASTER_VISION)
    occupied = {(monster.position.y, monster.position.x) for monster in ctx.hostiles()}
    near = {cell for cell, kind in ctx.open_terrain().items() if kind == "floor"
            and any(quest_exposure.game_distance(cell, (monster.position.y, monster.position.x))
                    <= RANGED_MAX_DISTANCE for monster in masses)}
    cells = {Position(*cell) for cell in near - avoid - occupied}
    cells -= quest_firing_cells.touching_cells(ctx.policy, ctx.snapshot, cells)
    by_reach: dict = {}
    for cell in cells:
        count = quest_firing_cells.reach(ctx.snapshot, cell, masses)
        if count:
            by_reach.setdefault(count, set()).add((cell.y, cell.x))
    return by_reach


def _walk_to_widest(ctx: _Ctx) -> str | None:
    """To the cells that reach the most masses (``_mass_firing_cells``), the most first among the
    reachable; None when no cell reaches more than this one (a cell the plan may not stand on
    reaches none) or none that does can be walked to."""
    by_reach = _mass_firing_cells(ctx)
    here = next((count for count, cells in by_reach.items() if ctx.here in cells), 0)
    for count in sorted(by_reach, reverse=True):
        if count <= here:
            return None
        if (key := _walk(ctx, by_reach[count], MASS_CELL_REASON)) is not None:
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


def _sweep(ctx: _Ctx, *, patrol: bool = False) -> str | None:
    """``patrol``: the round is walked whatever the kill count says (``_after_the_phases``)."""
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
    if not _short(ctx) and not patrol:
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
    # Owner 2026-11-09 「Q25 の全部の段に広げる」 (``_unseen_fire``): unseen from [13,27], no arrow; the
    # door [13,28] beside it when nothing is aimed at the grid.
    return _unseen_fire(ctx, stairway, geo.STAIRWAY, seen=bool(seen), among={stand, door})


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
    # Owner 2026-11-09 「Q25 の全部の段に広げる」 (``_unseen_fire``): unseen, no arrow; a trapless cell
    # of its line that sees it when nothing is aimed at the grid.
    return _unseen_fire(ctx, druj, geo.DRUJ, seen=bool(_seen_at(ctx, geo.DRUJ, {druj})), among=trapless)


# -- the table --------------------------------------------------------------------------


@dataclass(frozen=True)
class Phase:
    name: str
    spec_key: str          # the draft's key that says it
    full_hp: bool          # 「全快にして」 before its first step
    done: Callable
    act: Callable          # the phase's own step
    wait_at: tuple | None = None   # where its wait is counted (None: anywhere, once ready)
    wait_limit: str | int | None = None  # the wait_limits item (or a number): actions without an arrival that end it


PHASES = (
    Phase("ambush", "phase1", False, _ambush_done, _ambush, None, "long_wait_actions"),
    Phase("wall-passers", "phase1_wall_passers", True, _wall_passers_done, _wall_passers,
          geo.WALL_PASSER_STAND, "wall_passer_quiet_actions"),
    Phase("ipsissimus", "phase2", True, _ipsissimus_done, _ipsissimus),
    Phase("stragglers", "phase1_wall_passers", False, _stragglers_done, _stragglers,
          geo.STRAGGLER_STAND, "quiet_actions"),
    Phase("quylthulgs", "phase3", False, _quyls_done, _quyls),
    Phase("tome", "phase3", True, _tome_done, _tome),
    Phase("corpse-masses", "phase4", False, _masses_done, _masses),
    Phase("dreadmaster", "phase5", False, _dreadmaster_done, _dreadmaster, None, "long_wait_actions"),
    Phase("sweep", "phase6_sweep", False, _sweep_done, _sweep),
    Phase("stairway", "phase6", True, _stairway_done, _stairway),
    Phase("druj", "phase7_druj", False, _druj_done, _druj),
)
PHASE_NAMES = tuple(phase.name for phase in PHASES)


def _adjacent_mass_key(ctx: _Ctx) -> str | None:
    """Owner 2026-11-07 「全部の段に広げる」: 「第1段から最後の段まで、隣のマスの死体の塊は殴るか撃って
    倒す。離れた塊は今のまま相手にしない。」: the blow (``_engage``'s adjacent attack), else the
    strongest shot at it.

    The masses breed (MULTIPLY) along the north corridor and drain CON by touch (n1-c life-159
    2026-11-07: max HP 766 -> 446 while the ambush held on [1,18] beside them)."""
    beside = sorted((monster for monster in ctx.in_view()
                     if monster.race_id == geo.MASS and monster.distance <= 1),
                    key=lambda monster: monster.index)
    if not beside:
        return None
    if (key := _engage(ctx, beside)) is not None:
        return key
    for monster in beside:
        if (key := _fire_at(ctx, (monster.position.y, monster.position.x), geo.MASS)) is not None:
            return key
    return None


def _breeders_in_line_key(ctx: _Ctx) -> str | None:
    """Owner 2026-11-08 「射線にいれば範囲で撃つ」: the breeders in the line of fire, when no more
    dangerous hostile acts (breeder_area_attack ``line_of_fire_key``); the one-target answer is
    the phase's strongest shot at the nearest (``_fire_at``)."""
    def single(target):
        return _fire_at(ctx, (target.position.y, target.position.x), target.race_id)
    key = breeder_area_attack.line_of_fire_key(ctx.policy, ctx.snapshot, single)
    if key is not None:
        ctx.battle.aimed_race = geo.MASS
    return key


def _act(ctx: _Ctx, phase: Phase) -> str | None:
    """The phase's own step; where it waits or walks (or has none), the breeders in line first.

    A step that names no reason of its own keeps the previous one, so the reason is read only
    when the step set it."""
    entry = ctx.policy.last_reason
    ctx.policy.last_reason = ""
    key = phase.act(ctx)
    own = ctx.policy.last_reason
    if not own:
        ctx.policy.last_reason = entry
    if key is None or own in _IDLE_REASONS:
        if (shot := _breeders_in_line_key(ctx)) is not None:
            return shot
        if not own:
            ctx.policy.last_reason = entry
        elif key is not None:
            ctx.policy.last_reason = own
    return key


def _finished(ctx: _Ctx, phase: Phase) -> bool:
    """Its own end, or its wait limit (wait_limits, phase1_wall_passers, phase2)."""
    return phase.done(ctx) or (phase.wait_limit is not None
                               and ctx.battle.quiet >= _wait_limit(ctx, phase))


def _wait_limit(ctx: _Ctx, phase: Phase) -> int:
    """The phase's wait in player actions: its ``wait_limits`` item, or a number a row carries
    itself (a recorded process's own wait, as tests/test_n1c_174_q25_loops_1109_recorded
    replays the 50 actions that process ran)."""
    limit = phase.wait_limit
    return limit if isinstance(limit, int) else ctx.values.wait_limit(limit)


def current_phase(ctx: _Ctx) -> Phase | None:
    """Advance over every finished phase; the one running, else None (all done)."""
    while ctx.battle.phase < len(PHASES) and _finished(ctx, PHASES[ctx.battle.phase]):
        _next_phase(ctx.battle)
    return PHASES[ctx.battle.phase] if ctx.battle.phase < len(PHASES) else None


def _note_room_kill(ctx: _Ctx) -> None:
    from hengbot import quest25_sealed_room

    quest25_sealed_room.note_kill(ctx)


def _observe(ctx: _Ctx) -> None:
    """Once per board (``key`` and ``walk_key`` may both read it)."""
    board = (ctx.snapshot.turn, id(ctx.snapshot))
    if ctx.battle.observed == board:
        return
    ctx.battle.observed = board
    _settle_beam(ctx)
    _settle_detection(ctx)
    _note_rest_cut(ctx)
    _note_kills(ctx)
    _note_room_kill(ctx)
    _note_pen_shot(ctx)
    _note_arrivals(ctx)
    _note_strong(ctx)
    _note_glow(ctx)
    _note_tome_health(ctx)
    phase = current_phase(ctx)
    if (phase is not None and phase.wait_limit is not None and ctx.battle.ready
            and phase.wait_at in (None, ctx.here)):
        ctx.battle.quiet += 1


def observe_board(policy, snapshot) -> None:
    """Read a board the plan does not decide (a turn-free list read takes it): its kill lines
    and arrivals count as on a decided board."""
    ctx = _ctx(policy, snapshot)
    if ctx is not None:
        _observe(ctx)


def _phase_key(policy, snapshot) -> str | None:
    """The running phase's own order: its preparation, then its step.  On a room whose only way
    out is a great-hall door while the hall is dangerous, the room's plan first (owner 2026-11-12,
    quest25_sealed_room)."""
    ctx = _ctx(policy, snapshot)
    if ctx is None:
        return None
    phase = current_phase(ctx)
    if phase is None:
        # The druj is dead: what the anti-teleport piece displaced goes back on.
        return (quest25_druj_gear.restore_key(policy, snapshot, ctx.battle)
                or _after_the_phases(ctx))
    from hengbot import quest25_sealed_room

    return (_adjacent_mass_key(ctx) or quest25_sealed_room.key(ctx)
            or _prepare(ctx, phase) or _act(ctx, phase))


def _after_the_phases(ctx: _Ctx) -> str | None:
    """Every phase ended and the quest (KILL_ALL) is not complete: what is left is found and killed.

    n1-b life-378 (2026-11-13 01:46, build bot-68c820fd6): the quylthulgs' phase found no ball then
    (owner 2026-11-06 phase3 「範囲攻撃が無ければ 1) をとばして」), the sweep's Detect Evil showed
    nothing (a quylthulg is not evil), the stairway and the druj fell, and with the quest still
    taken the plan had no step: ``quest:blocked:execute`` waits on [12,24] until the loop guard
    stopped the bot, three times.  The draft's order puts the quylthulgs before the druj (owner
    2026-11-05 「最後ドルジの前に処理する」) and the quest is won only with every monster dead, so
    the plan goes on: each quylthulg still on its cell is shot directly from a cell of its line
    (phase3 「加速して直接撃つ」, ``_quyls``), then the sweep's round is walked for what is left
    (phase6_sweep 「巡回して探す」), bounded by ``room_sweep.max_rounds`` as there."""
    left = [cell for cell, race in ctx.navigator.battlefield.monster_placements
            if race == geo.QUYL and cell not in ctx.battle.quyls_done]
    if left and ctx.kills(geo.QUYL) < geo.ROSTER[geo.QUYL]:
        _note_quyls(ctx)
        left = [cell for cell in left if cell not in ctx.battle.quyls_done]
    if left and ctx.kills(geo.QUYL) < geo.ROSTER[geo.QUYL]:
        key = _quyls(ctx, (left[0], None, None))
        if key is not None:
            return key
    return _sweep(ctx, patrol=True)


def phase_index(name: str) -> int:
    """The index of the phase named ``name`` in ``PHASES``."""
    return next(index for index, phase in enumerate(PHASES) if phase.name == name)


# -- the summons ------------------------------------------------------------------------


def _druj_retreat(policy, snapshot, *, line=True) -> str | None:
    """Owner 2026-11-07 (phase7_druj) 「歩いてドルジの射線から外れる。安全に休憩可能なはずである。
    必要なら歩いて射線から外れた後薬を飲む。」

    With the anti-teleport piece worn on the druj phase, Teleportation cannot be read
    (teleport_player refuses under NO_TELE), so below the plan's line (``abort_conditions.hp_ratio``,
    the line ``_below_line`` reads Teleportation at) the walk leaves the druj's direct line (it never
    moves and every spell of it needs that line), then rests there until HP is full.  A rest that
    did not raise HP (refused or broken off) is followed by a Healing potion -- out of the line only.
    Back at full HP the phase walks back to its stand.  ``line=False``: the plan's escape asked by
    its 即死 rung, whatever the HP (threat_tiers.instant_death_key).
    """
    ctx = _ctx(policy, snapshot)
    if (ctx is None or ctx.battle.phase >= len(PHASES) or PHASES[ctx.battle.phase].name != "druj"
            or quest25_druj_gear.worn_piece(snapshot) is None):
        if ctx is not None:
            ctx.battle.retreating, ctx.battle.retreat_rest_hp = False, None
        return None
    battle, player = ctx.battle, snapshot.player
    if not battle.retreating:
        if line and player.hp_ratio > float(ctx.profile.abort_conditions["hp_ratio"]):
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
        potion = quest_plan_base._healing_potion(policy, snapshot)
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
    if (ctx is None or quest_plan_base.steps_aside_for_food(policy, snapshot)
            or once_quest_recall._deliberate_leave(policy, snapshot)):
        return None
    _observe(ctx)
    profile, navigator = ctx.profile, ctx.navigator
    plan = profile.engagement_plan["room_sweep"]
    board = quest_room_sweep._Board(policy, snapshot, profile, navigator, {**plan, "left_alone_races": ()})
    if not board.enemy:
        return (
            _druj_retreat(policy, snapshot)
            or _leave_by_exit(policy, snapshot, board)
            or _summons(policy, snapshot)
            or resist_potion.drink_key(policy, snapshot)
            or _restore(policy, snapshot)
            or _out_of_fire_key(policy, snapshot)
            or _recall_wait(policy, snapshot)
            or _phase_key(policy, snapshot)
            or resist_potion.leave_key(policy, snapshot)
        )
    return (
        # Owner 2026-11-07 「作戦が先・即死だけ例外」: only the 1-turn 即死 pre-empts the plan.
        # The plan's escape: with the druj's anti-teleport piece worn the walk out of its line
        # (owner 2026-11-07 phase7_druj), else the below-line Teleportation.
        threat_tiers.instant_death_key(policy, snapshot, lambda: (
            _druj_retreat(policy, snapshot, line=False)
            or quest_plan_base._below_line(policy, snapshot, profile, navigator, line=False)))
        or quest_plan_base._cure(policy, snapshot)
        or _druj_retreat(policy, snapshot)
        or _leave_by_exit(policy, snapshot, board)
        or quest_plan_base._give_up(policy, snapshot, profile)
        or quest_plan_base._below_line(policy, snapshot, profile, navigator)
        or _absorbed_heal(policy, snapshot, profile)
        or quest_plan_base._heal(policy, snapshot, profile)
        or quest_plan_base._speed(policy, snapshot, profile, board)
        or _summons(policy, snapshot)
        or resist_potion.drink_key(policy, snapshot)
        or _out_of_fire_key(policy, snapshot)
        or _recall_wait(policy, snapshot)
        or _phase_key(policy, snapshot)
        or resist_potion.leave_key(policy, snapshot)
    )


def _restore(policy, snapshot) -> str | None:
    """The plan's 「敵がいない時に下がっていれば飲む」 (QUEST_25 consumable_plan): not while a summons
    Teleportation was read from is remembered (``_note_strong``, owner 2026-11-09 「起きた敵も最後の
    位置を覚える」).  n1-c life-195 (2026-11-11 game 05:37): on [2,2] the dracolich seen on the board
    before stood out of the light, the board showed no enemy, and the Restore Life Levels was
    drunk; it was beside the player on the next board."""
    ctx = _ctx(policy, snapshot)
    if ctx is not None and ctx.battle.strong:
        return None
    return quest_plan_base._restore(policy, snapshot)


def _absorbed_heal(policy, snapshot, profile) -> str | None:
    """Owner 2026-11-09 Q3 「成功率が80%以上なら体力回復は使っても良い。テレポートは許可しない」, and the
    same day 「即死の危険がないときは薬より優先する」 / 「ロッドも同じ」: at the plan's heal line (where a
    Healing potion is drunk), the absorbed Healing -- the staff's, else the rod's -- whose displayed
    success rate is at least 80% (me_capability ``reliable``, the owner's one number for absorbed
    powers in place of an item) comes before the potion, unless the instant death holds
    (threat_tiers ``instant_death``: the next action's p95 reaches the HP); then a carried potion,
    which does not fail, goes first.  Without a potion it is cast either way.  n1-c life-178 had
    4 charges at 32%: none."""
    threshold = profile.consumable_plan.get("heal_threshold_ratio")
    if threshold is None or snapshot.player.hp_ratio >= float(threshold):
        return None
    if (quest_plan_base._healing_potion(policy, snapshot) is not None
            and threat_tiers.instant_death(policy, snapshot).holds):
        return None
    key = item_cast_key(policy, snapshot, (TVAL_POTION, SV_POTION_HEALING))
    if key is not None:
        policy.last_reason = ABSORBED_HEAL_REASON
    return key


def _recall_wait(policy, snapshot) -> str | None:
    """Owner 2026-11-09 Q2 「段をやめ射線外で待つ」: 「段の動きをやめる。開始の階段へ行ければ踏み、
    行けなければ動かない敵の射線の外へ下がって発動を待つ。」

    Once Recall is active (read when the supplies ran out, once_quest_recall), no phase step: the
    start stair when a walk reaches it without entering the casters' fire, taken there; else out
    of the fire and the wait (a rest while damaged).  n1-c life-178: after the Recall of decision
    5205 the phase walked back toward the tome twice at HP 14-18% and died before it took effect."""
    ctx = _ctx(policy, snapshot)
    if ctx is None or not snapshot.player.recalling:
        return None
    fire = _fire(ctx)
    goal = tuple(ctx.navigator.battlefield.exit)
    if ctx.here == goal:
        policy.last_reason = RECALL_EXIT_REASON
        return UP_STAIRS_KEY
    occupied = frozenset((monster.position.y, monster.position.x) for monster in ctx.in_view())
    terrain = quest_plan_base._terrain_of(ctx.navigator, snapshot, water=False)
    terrain[ctx.here] = "floor"
    path = quest_exposure.least_exposed_path(terrain, geo.exposure_of(fire | _avoided(ctx)),
                                             ctx.here, {goal}, (occupied - {goal}) | _refused(ctx))
    if len(path) >= 2 and not set(path[1:]) & fire:
        return _trap_key(ctx, path[1]) or _step(ctx, path[1], RECALL_EXIT_WALK_REASON, guard=False)
    if ctx.here in fire:
        return _withdraw(ctx, RECALL_OUT_REASON)
    if _damaged(ctx):
        return _rest_out_of_fire(ctx)
    policy.last_reason = RECALL_WAIT_REASON
    return WAIT_KEY


def _leave_by_exit(policy, snapshot, board) -> str | None:
    """Owner 2026-11-04 (QUEST_25 room_sweep ``exit_when_out_of_healing``, 「薬を使い切っていたら
    踏んで良い」): the Healing used up, HP at the panic line (PANIC_HP_RATIO) and the start stair
    within a few steps: walk there and take it (quest_room_sweep ``_leave_by_exit``).  The room
    sweep's own order holds it; the phase battle that replaced the sweep on this floor dropped it
    (n1-c life-178 decision 5216: HP 81 of 503 on [11,1], no Healing, the stair [13,1] two steps
    off, and the phase walked back to the tome).  On the quiet board too: the tome that hits
    from out of sight leaves no enemy on the board between its breaths."""
    ctx = _ctx(policy, snapshot)
    plan = {**ctx.profile.engagement_plan["room_sweep"], "left_alone_races": ()}
    return quest_room_sweep._leave_by_exit(policy, snapshot, ctx.navigator, plan, board)


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
