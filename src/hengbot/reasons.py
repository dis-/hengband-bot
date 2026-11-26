"""The registry of decision reasons whose attributes other modules read.

A decision's reason is a plain string in ``policy.last_reason``.  Two readers act on what a
reason *is*, not on the one reason they were written for:

* the per-dive escape count (policy_observation): an escape counted at the read
  (``EMERGENCY``), or once its effect is observed, a new position or floor
  (``RELOCATING``); the second of a dive returns to town (owner 2026-10-02 「逃走も緊急脱出に
  数える」, 2026-11-09 「全部の逃げを数える」);
* the breeder window (breeder_stalemate): whether the action attacked (``attack``).

Before this table those attributes were literal sets (policy_constants) and a guess from the
words of the reason (breeder_stalemate ``ATTACK_REASON_WORDS``), and nothing tied a new reason
to them: a new teleport left out of the set silently did not count.  Here every reason of the
escape vocabulary (``ESCAPE_WORDS``) is declared with its kind, the module(s) that produce it
and the owner rule or the reason for the kind; scripts/reason_registry_lint.py reads every
reason the source can send and fails on one of that vocabulary the table does not know
(tests/test_reason_registry.py runs it).  Add a row in the same commit as a new reason.

Kinds (the escape count reads only the first two):

``EMERGENCY``      counted at the read (``policy_constants.EMERGENCY_ESCAPE_REASONS``).
``RELOCATING``     counted once its effect is observed (``RELOCATING_ESCAPE_REASONS``).
``EXCLUDED``       a relocation deliberately not counted; ``rule`` says why (owner answer).
``WALK``           a walking retreat, a wait or a step toward an exit: never counted (owner
                   2026-11-09 「歩いての後退は数えない」).
``NOT_ESCAPE``     the vocabulary without an escape from enemies: town and shop travel, the
                   planned returns, a purchase, a gear change.
``OWNER_QUESTION`` a relocation from enemies that no owner answer covers yet.  Not counted until
                   the owner answers; listed for the owner.  None today: the 2026-11-09 registry
                   report's questions were answered 「ダンジョンの分だけ数える」.
``None``           an entry that only carries ``attack``.

``attack`` is the breeder window's 「実際に攻撃した手」 (owner 2026-11-08): the decision chose an
attack.  It reproduces, reason for reason, the word guess it replaces (2c8f8d71f5), including
its oddities, which are marked ``word rule`` below and listed in the registry report: this
table changes no decision.

A row's ``pattern`` is a reason, or an ``fnmatch`` pattern for the reasons the source builds
(``f"esp-threat:leave-{...}"``); ``lookup`` takes an exact row first, else the longest
(the most specific) pattern row that matches.
"""
from __future__ import annotations

from fnmatch import fnmatchcase
from typing import NamedTuple

EMERGENCY = "emergency"
RELOCATING = "relocating"
EXCLUDED = "excluded"
WALK = "walk"
NOT_ESCAPE = "not-escape"
OWNER_QUESTION = "owner-question"
KINDS = (EMERGENCY, RELOCATING, EXCLUDED, WALK, NOT_ESCAPE, OWNER_QUESTION, None)
COUNTED = (EMERGENCY, RELOCATING)

# The escape vocabulary: a reason with one of these words must have a row.  Every counted row
# has one of them (tests/test_reason_registry.py), so the vocabulary covers the registry.
ESCAPE_WORDS = ("teleport", "phase", "recall", "stairs", "ascend", "scroll", "flee", "escape",
                "leave", "disengage")


class Reason(NamedTuple):
    pattern: str
    kind: str | None
    attack: bool
    producers: tuple
    rule: str


ROWS: list[Reason] = []


def _rows(kind, producers, rule, *patterns, attack=False) -> None:
    producers = (producers,) if isinstance(producers, str) else tuple(producers)
    ROWS.extend(Reason(pattern, kind, attack, producers, rule) for pattern in patterns)


# ================================================================ counted at the read
# The emergency ladder (policy_combat._emergency_item, policy._decide's emergency rungs) and the
# blind teleport of threat_escape.blind_teleport_key, which builds ``reason + ":absorbed-power"``
# and ``reason + "-staff"``.
_RULE_EMERGENCY = "the emergency ladder's escapes: counted at the read (EMERGENCY_ESCAPE_REASONS)"
_rows(EMERGENCY, ("policy", "policy_combat", "threat_tiers", "threat_escape"), _RULE_EMERGENCY,
      "emergency:teleport", "emergency:teleport:absorbed-power", "emergency:teleport-staff",
      "emergency:phase", "emergency:stairs")
_rows(EMERGENCY, ("policy", "once_quest_recall"), _RULE_EMERGENCY, "emergency:recall")
_rows(EMERGENCY, "policy_combat", _RULE_EMERGENCY, "emergency:seek-upstairs")
# Owner 2026-11-12 「テレポート追尾が3体以上で致死的なときは破壊の次にテレポートを優先して試す」: the
# teleport from a pack of followers (teleport_follower.pack_teleport_key) is the ladder's escape.
_rows(EMERGENCY, "teleport_follower", _RULE_EMERGENCY,
      "emergency:teleport-follower:pack-teleport",
      "emergency:teleport-follower:pack-teleport:absorbed-power",
      "emergency:teleport-follower:pack-teleport-staff")
# Owner 2026-11-14 「付いてくる敵だけで死なないなら読む」: the same teleport from fewer followers on
# the 即死 board when they alone cannot kill (teleport_follower.survivable_due).
_rows(EMERGENCY, "teleport_follower", _RULE_EMERGENCY,
      "emergency:teleport-follower:survivable-teleport",
      "emergency:teleport-follower:survivable-teleport:absorbed-power",
      "emergency:teleport-follower:survivable-teleport-staff")

# ================================================================ counted once relocated
# User 2026-10-02 13:4x 「逃走も緊急脱出に数える」: the relocating escapes from an unresisted
# confusion/paralysis attacker join the per-dive emergency count once their effect is
# observed (new position or floor); a walking retreat (status-threat:retreat) never counts.
_RULE_STATUS = "user 2026-10-02 「逃走も緊急脱出に数える」 (status-threat relocations)"
_rows(RELOCATING, ("policy", "policy_combat"), _RULE_STATUS, "status-threat:scroll")
_rows(RELOCATING, "policy", _RULE_STATUS, "status-threat:stairs")

# Owner 2026-11-09 (question A of the n1-b deaths life-355/350/346, 「全部の逃げを数える」:
# 「テレポート・フェイズ・階段など、敵から離れるために使った逃げは理由を問わず数え、2回で帰還
# する（歩いての後退は数えない）。」): every relocating escape from enemies joins the count the
# way the status-threat relocations above do.  The list is the deaths-1109-rules report's.
_RULE_ALL = "owner 2026-11-09 A 「全部の逃げを数える」"
# the emergency ladder's variants not counted at the read
_rows(RELOCATING, ("once_quest_recall", "policy"), _RULE_ALL, "emergency:recall-quest-fail")
_rows(RELOCATING, ("policy_combat", "policy_supply"), _RULE_ALL, "emergency:stairs-quest-fail")
_rows(RELOCATING, "policy", _RULE_ALL, "emergency:stairs-down")
# the flee rung (policy._decide_dungeon) and the threat reposition's cornered read
_rows(RELOCATING, "policy", _RULE_ALL, "flee:scroll", "flee:stairs", "flee:stairs-quest-fail",
      "threat:scroll")
# the sensed T1 leave (threat_tiers.sensed_t1_leave_key, SENSED_LEAVE_PREFIX + ...; blind, through
# threat_escape.blind_teleport_key).  Owner 2026-11-13 「射線にT1が入っていない=感知しただけは
# カウントしない」: counted only when a T1 left was in the line of fire (line_of_fire, 2026-11-14 for
# every counted reason).
_rows(RELOCATING, ("threat_tiers", "threat_escape"), _RULE_ALL,
      "sensed-t1:teleport", "sensed-t1:teleport:absorbed-power", "sensed-t1:teleport-staff",
      "sensed-t1:phase", "sensed-t1:stairs", "sensed-t1:recall")
# the exposed summoner's up stairs (policy) and _immobile_summoner_exit_key's up stairs
# (policy_combat): one string.  Owner 2026-11-09 (the registry report's Q6, 「ダンジョンの分だけ
# 数える」): both are escapes in the dungeon and count.  One stair taken counts once: the counter
# reads the reason of the decision whose next board shows the new floor (policy_observation), so a
# '<' sent again by the other producer before the floor changes is not a second escape
# (tests/test_dungeon_escapes_counted_1109.py).
_rows(RELOCATING, ("policy", "policy_combat"), _RULE_ALL + "; owner 2026-11-09 「ダンジョンの分だけ数える」",
      "summoner:stairs")
_rows(RELOCATING, "policy", _RULE_ALL, "summoner:stairs-quest-fail")
# the Anaguma pocket's escape read (anaguma._escape_key): walking out of the pocket is never the
# escape, the read is (owner 2026-11-10 「今の基準のまま」)
_rows(RELOCATING, "anaguma", _RULE_ALL, "anaguma:escape-scroll")
# the summoner hold's teleport (summoner_wait.HOLD_TELEPORT_REASON)
_rows(RELOCATING, "summoner_wait", _RULE_ALL, "summoner:hold-teleport")
# the answer to the summons (summon_response) and the no-chance Resistance leave (resist_potion)
_rows(RELOCATING, "summon_response", _RULE_ALL, "summons:leave-teleport")
# Owner 2026-11-19 「Q33では離脱に取り込んだテレポートの杖の使用を許可する」: the same leave cast from the
# absorbed Teleportation on Quest 33 (quest_summon_answer.absorbed_teleport_key); its "-staff" form is
# teleport_follower.device_teleport_key's carried-staff reason, never sent here.
_rows(RELOCATING, "summon_response", _RULE_ALL, "summons:leave-teleport:absorbed-power",
      "summons:leave-teleport-staff")
_rows(RELOCATING, ("summon_response", "once_quest_recall"), _RULE_ALL, "summons:recall")
_rows(RELOCATING, "resist_potion", _RULE_ALL, "resist-potion:no-chance-teleport")
# the item-destroying breeders' leave (policy_combat._item_destroying_breeder_leave_key)
_rows(RELOCATING, "policy_combat", _RULE_ALL,
      "breeder-item-damage:stairs", "breeder-item-damage:teleport-level",
      "breeder-item-damage:teleport", "breeder-item-damage:recall")
# the fruitless fight's disengage (policy_navigation) and the breeder breakthrough's leave
_rows(RELOCATING, "policy_navigation", _RULE_ALL, "combat:disengage-stairs", "combat:disengage-recall")
# Owner 2026-11-09 (the registry report's Q1 and Q2), verbatim choice 「ダンジョンの分だけ数える」:
# 「ダンジョンの中の逃げだけを数え、荒野での逃げは数えない。」
_RULE_DUNGEON = "owner 2026-11-09 「ダンジョンの分だけ数える」: ダンジョンの中の逃げだけを数え、荒野での逃げは数えない"
# the unprofitable unique's disengage (policy._unprofitable_unique_disengage_key) renames the
# fruitless fight's combat:disengage-stairs / -recall above to these: they count as those do.
_rows(RELOCATING, "policy", _RULE_DUNGEON,
      "combat:avoid-unprofitable-unique-stairs", "combat:avoid-unprofitable-unique-recall")
# the no-wait rung's Teleportation / Phase Door under a material threat (policy_combat,
# 'Rejecting an idle turn'), a read like flee:scroll / threat:scroll above
_rows(RELOCATING, "policy_combat", _RULE_DUNGEON, "no-wait:escape-scroll")
_rows(RELOCATING, "policy_combat", _RULE_ALL, "breeder-breakthrough:ascend", "breeder-breakthrough:recall")
# Owner 2026-11-09 (n1-a life-501) 「浅い階層で見かけたら逃げる」: the paralyser rung's leave at sight
# above the Free Action depth requirement (policy_combat._paralyzer_prevention_key,
# paralyzer_contact.SHALLOW_SIGHT_REASON_PREFIX); counted as the status-threat relocations are.
_rows(RELOCATING, "policy_combat", _RULE_ALL, "shallow-paralyzer:stairs", "shallow-paralyzer:scroll")
# Owner 2026-11-16 (n1-c life-215) 「見かけたと同じに扱い階を離れる」: a paralyser only sensed is
# left by Word of Recall (paralyzer_contact.SHALLOW_SENSED_RECALL_REASON).
_rows(RELOCATING, "policy_combat", _RULE_ALL, "shallow-paralyzer:recall")
# Owner 2026-11-14 「混乱する前に離れるだけ」 (n1-b life-392): the player's own teleport before a
# faster confuser's blow (confuser_contact: the scroll's REASON, the absorbed Teleportation's
# REASON + ":absorbed-power", the staff's STAFF_REASON); counted as the status-threat relocations are.
_rows(RELOCATING, "confuser_contact", _RULE_ALL, "status-threat:confuser-leave*")

# ================================================================ relocations not counted
_rows(EXCLUDED, "destruction_use",
      "owner 2026-11-04 「破壊の回数だけでは帰還しない」: it removes the enemies rather than "
      "leaving them (destruction_use: emergency:destruction[:<sight trigger>][:absorbed-power])",
      "emergency:destruction*")
_rows(EXCLUDED, ("me_powers", "sent_away_t1"),
      "the absorbed Teleport Other moves the enemy, not the player (owner 2026-11-09 E handles it)",
      "me-power:*:teleport-away")
_rows(EXCLUDED, "quest_plan_base",
      "Teleport Away in Q25's Teleportation place moves the enemy, not the player (owner 2026-11-12 "
      "「回復とテレポートアウェイで対処する」)",
      "quest-strategy:teleport-away", "quest-strategy:teleport-away:absorbed-power")
_rows(EXCLUDED, "quest_find_exit",
      "Teleport Away at Q18's worst enemy on the 即死 rung and in the Recall's countdown moves the "
      "enemy, not the player (owner 2026-11-22 「使う」)",
      "quest-strategy:exit-teleport-away", "quest-strategy:exit-teleport-away:absorbed-power")
_rows(EXCLUDED, "teleport_follower",
      "Teleport Other at a monster that follows the player's teleport moves the enemy, not the "
      "player (owner 2026-11-09 「*破壊*>テレポートアウェイ>戦闘」; E handles a T1 sent away)",
      "emergency:teleport-follower:teleport-away",
      "emergency:teleport-follower:teleport-away:absorbed-power")
_rows(EXCLUDED, ("teleport_follower", "ladder_combat"),
      "the status-threat rung's Teleport Other at the threat beside it moves the enemy, not the "
      "player (owner 2026-11-09 「*破壊*>テレポートアウェイ>戦闘」, n1-c life-217; owner 2026-11-18 "
      "「付いてくる敵と同じく」 for a status monster that does not follow)",
      "status-threat:teleport-away", "status-threat:teleport-away:absorbed-power")
_rows(EXCLUDED, ("teleport_follower", "policy_combat"),
      "Teleport Other at a faster blinder beside a blind player moves the enemy, not the player "
      "(design 4.2 「逃げる手段を取り戻すのが先」, status_cure.outpacing_blinders)",
      "emergency:blinder:teleport-away", "emergency:blinder:teleport-away:absorbed-power")
_rows(EXCLUDED, "policy_combat",
      "a town return already; over_extension's answer 6 keeps it uncounted",
      "esp-threat:leave-*")
_RULE_PLAN = "the quest plan's own teleport: answer 11 「作戦が先」"
_rows(EXCLUDED, "policy_quest", _RULE_PLAN,
      "quest-strategy:opening-teleport", "quest-strategy:q22-opening-teleport",
      "quest-strategy:q2-teleport-reset")
_rows(EXCLUDED, "quest_plan_base", _RULE_PLAN, "quest-strategy:sweep-teleport")
# QUEST_33 (owner 2026-11-19 「Q33では離脱に取り込んだテレポートの杖の使用を許可する」): the same escape cast
# from the absorbed Teleportation (quest_summon_answer.absorbed_teleport_key); its "-staff" form is
# teleport_follower.device_teleport_key's carried-staff reason, never sent here.
_rows(EXCLUDED, ("quest_plan_base", "quest_summon_answer"), _RULE_PLAN,
      "quest-strategy:sweep-teleport:absorbed-power", "quest-strategy:sweep-teleport-staff")
# QUEST_33, owner 2026-11-19 「召喚を何度受けても放棄しない。即死はテレポートで離脱。…無理なら離脱。」: the
# plan's own answer to a summon received (quest_summon_answer); the floor is never left for summons.
# Owner 2026-11-19 「Q33では離脱に取り込んだテレポートの杖の使用を許可する」: the absorbed Teleportation first.
_rows(EXCLUDED, "quest_summon_answer", _RULE_PLAN + " (QUEST_33's answer to a summon received)",
      "quest-strategy:summoned-teleport", "quest-strategy:summoned-disengage-teleport",
      "quest-strategy:summoned-teleport:absorbed-power",
      "quest-strategy:summoned-disengage-teleport:absorbed-power",
      # teleport_follower.device_teleport_key's carried-staff reason, never sent here (the
      # means is always the absorbed power).
      "quest-strategy:summoned-teleport-staff", "quest-strategy:summoned-disengage-teleport-staff")
_rows(WALK, "quest_summon_answer", "a walk out of the summoner's lines (owner 2026-11-09 「歩いての後退は数えない」)",
      "quest-strategy:summoned-disengage-walk")
# A room-sweep plan's answer to a hostile out of view that fires at the player and no shot reaches
# (quest_summon_answer.fire_answer_key; owner 2026-11-19 「地形と敵の位置、敵のアルゴリズムを確認して有効な
# 場所で待つ」, n1-c life-220 2026-11-22): the step toward a cell it is shot from, else out of its line,
# else the teleport (the absorbed Teleportation first on Quest 33).
_rows(EXCLUDED, "quest_summon_answer", _RULE_PLAN + " (a room sweep's leave of a line of fire)",
      "quest-strategy:fire-disengage-teleport", "quest-strategy:fire-disengage-teleport:absorbed-power",
      # teleport_follower.device_teleport_key's carried-staff reason, never sent here.
      "quest-strategy:fire-disengage-teleport-staff")
_rows(WALK, "quest_summon_answer", "a walk out of a line of fire (owner 2026-11-09 「歩いての後退は数えない」)",
      "quest-strategy:fire-disengage-walk")
_rows(NOT_ESCAPE, "quest_summon_answer", "a room sweep's step toward a cell it shoots a firing hostile from",
      "quest-strategy:fire-approach")
# Owner 2026-11-19 「安全になったら休息してから召還主や召還されたモンスターを少しずつ釣りだして数を減らす」:
# the walk to the pulling cell of a member of the group, and the rest before it.
_rows(NOT_ESCAPE, "reset_recall", "a town read of the Scroll of Reset Recall that sets Angband's "
      "recall depth to 95F (owner 2026-11-21 「フロア・リセットの巻物があれば使って95Fに戻す」): no "
      "Word of Recall, no leave of a floor", "reset-recall:read", "reset-recall:close-store")
_rows(NOT_ESCAPE, "quest_summon_answer", "QUEST_33's lure after a disengage: a step toward the monsters",
      "quest-strategy:summoned-lure-walk", "quest-strategy:summoned-rest")
# Owner 2026-11-25 「休憩して魔法道具の使用回数を戻せる場合はその限りではない」: the Magic-Eater's counted rest
# out of the lines for the absorbed powers a monster that never comes is killed with.
_rows(NOT_ESCAPE, "quest_summon_answer", "QUEST_33's recharge rest before a monster that never comes",
      "quest-strategy:summoned-rest-recharge")
# Owner 2026-11-19 「予測被害が小さいうちは召還主の撃破を優先する」: the step toward the summoner gone after.
_rows(NOT_ESCAPE, ("finale_teleport_tour", "me_inn_refill"),
      "the inn's night between two loops of the 99F/100F Teleportation circuit, a town walk and a "
      "stay (owner 2026-11-20 「一周する毎に宿屋で一泊する」); \"teleport\" names the scrolls bought",
      "depart:inn-refill:finale-teleport:approach", "depart:inn-refill:finale-teleport:rest")
_rows(NOT_ESCAPE, ("finale_bm_tour", "me_inn_refill"),
      "the inn's night between two laps of the 99F/100F Restore Mana circuit of the Black Markets, "
      "a town walk and a stay (owner 2026-11-23 「闇市に無ければ巡回をくり返す」)",
      "depart:inn-refill:finale-bm:approach", "depart:inn-refill:finale-bm:rest")
_rows(NOT_ESCAPE, "quest_summon_answer", "QUEST_33's chase of a summoner: a step toward it",
      "quest-strategy:summoned-approach")
# Owner 2026-11-23 「加速して向かい、強引に邪悪側を排除する。」: the step toward the EVIL side once mixed.
_rows(NOT_ESCAPE, "quest_mixed_assault", "QUEST_33's assault on the EVIL side once the sides are mixed: a step "
      "toward it", "quest-strategy:mixed-assault-walk")
_rows(EXCLUDED, "quest25_battle", _RULE_PLAN, "quest25:teleport")
_rows(EXCLUDED, "breeder_quest", _RULE_PLAN + " (Q2's breeder breakthrough)", "breeder-breakthrough:teleport")
_RULE_FINALE = ("the 99F/100F battle's own leaves (owner 2026-11-20, verbatim: 「召喚または攻撃を受けてHPが800を"
                "下回ったとき、または対象が距離2より近づいたときテレポートの巻物で離脱する」 and 「帰還による離脱は"
                "成功時と魔力復活の薬を予定の倍以上使ったときのみ」): a plan's step, never a town return by "
                "the escape count (angband_finale_battle)")
_rows(EXCLUDED, "angband_finale_battle", _RULE_FINALE, "angband-finale:teleport",
      "angband-finale:teleport:absorbed-power", "angband-finale:recall")
_RULE_NO_AC = ("a worn NO_AC piece (宵闇のローブ, AC 0): owner 2026-11-21 「AC0では打撃を受けると即死抽選が"
               "ある。優先対処。」「着たまま帰還を読み、打撃の届く敵を寄せない」 -- the leave of that rule, "
               "never the escape count's (no_ac_recall)")
_rows(EXCLUDED, "no_ac_recall", _RULE_NO_AC, "no-ac:teleport", "no-ac:teleport:absorbed-power",
      "no-ac:recall")
_rows(EXCLUDED, "destruction_use", "a town return: owner 2026-11-22 「群れの数に関わらず破壊対象とする。1度で"
      "消しきれないなら帰還を読む。」 -- the Recall read where the ranged breeders one *Destruction* did not "
      "clear came back (breeder_comeback_recall_key), never the escape count's",
      "breeder-comeback:recall")
_rows(NOT_ESCAPE, "policy_quest",
      "the Q2 plan's phases (q2-phase-<race>: a step of the sweep; q2-light-phase-<race>: the Light "
      "scroll read): \"phase\" is the plan's stage, not Phase Door",
      "quest-strategy:q2-phase-*", "quest-strategy:q2-light-phase-*")
_RULE_SUMMONER_EXIT = ("_immobile_summoner_exit_key leaves a floor explored around an immobile "
                       "summoner by the ordinary floor rules (owner 2026-11-02 「通常の階の決まりで離れる」)")
_rows(EXCLUDED, "policy_combat", _RULE_SUMMONER_EXIT,
      "summoner:stairs-down", "summoner:teleport-level", "summoner:recall")
_rows(WALK, "policy_combat", _RULE_SUMMONER_EXIT,
      "summoner:seek-downstairs", "summoner:seek-upstairs", "summoner:wait-recall")
_RULE_CASTLE_CLIMB = ("the unsafe-recall fallback's Castle below its band takes the up stairs in the "
                      "down stairs' place: no enemy prompted it (owner 2026-11-17 「49Fに帰還して上り"
                      "階段を探して適正階層まで行く」, dive_floor.climbing)")
_rows(EXCLUDED, ("ladder_descent", "deep_climb"), _RULE_CASTLE_CLIMB, "castle-climb:ascend")
_rows(WALK, ("ladder_descent", "deep_climb"), _RULE_CASTLE_CLIMB, "castle-climb:seek-upstairs")
_RULE_DEEP_CLIMB = ("the Castle's 50F landing and every climb floor below the band are climbed from at "
                    "once: the up stairs, the walk to them, the search for them; no enemy prompted it "
                    "(owner 2026-11-22 「城の50Fに帰還してすぐ38〜42Fへ登る」, deep_climb)")
_rows(EXCLUDED, "deep_climb", _RULE_DEEP_CLIMB, "castle-climb-landing-50:ascend")
_rows(WALK, "deep_climb", _RULE_DEEP_CLIMB, "castle-climb-landing-50:seek-upstairs",
      "castle-climb-landing-50:search-upstairs", "castle-climb:search-upstairs")
_rows(NOT_ESCAPE, "deep_climb",
      "the pile on the cell the climb stands on, one action, no walk to the loot (owner 2026-11-23 "
      "「足元の品だけ1手で拾う」, deep_climb.underfoot_key): no escape",
      "castle-climb-landing-50:pickup", "castle-climb:pickup",
      "castle-climb-landing-50:trigger-autodestroy", "castle-climb:trigger-autodestroy")
_RULE_DEEP_FALL = ("a floor whose trap door would newly reach 50F, without a trap detection, is left by "
                   "the up stairs or Recall: no enemy prompted it (owner 2026-11-22 「そもそも50Fに降りない"
                   "方をしっかり作ること」, deep_fall_guard)")
_rows(EXCLUDED, "deep_fall_guard", _RULE_DEEP_FALL, "deep-fall-guard:ascend", "deep-fall-guard:recall")
_rows(WALK, "deep_fall_guard", _RULE_DEEP_FALL, "deep-fall-guard:wait-recall")
_RULE_ANGBAND_CAP = ("an Angband floor deeper than the cap takes the up stairs in the down stairs' "
                     "place: no enemy prompted it (owner 2026-11-19 「n1-bは次回潜行時に95Fまで登り"
                     "階段で戻ること」, angband_cap.climbing)")
_rows(EXCLUDED, "ladder_descent", _RULE_ANGBAND_CAP, "angband-cap-95:ascend")
_rows(WALK, "ladder_descent", _RULE_ANGBAND_CAP, "angband-cap-95:seek-upstairs")
_RULE_FINALE_DESCENT = ("the finale expedition's way down to its floor, the down stairs found and walked to at "
                        "once: no enemy prompted it (owner 2026-11-24 「決戦装備にしたら速やかに最下層まで"
                        "降りること。寄り道は不要。」, finale_descent)")
_rows(WALK, "finale_descent", _RULE_FINALE_DESCENT, "finale-descent:seek-downstairs",
      "finale-descent:search-downstairs")
_RULE_STUCK = "stuck / livelock relocations: no enemy prompted them"
_rows(EXCLUDED, ("policy", "retreat_enclosure", "policy_navigation", "sealed_pocket"), _RULE_STUCK,
      "stuck:destroyed-circle-teleport", "stuck:destroyed-circle-recall",
      "stuck:ascend", "stuck:enclosed-teleport", "stuck:recall-escape", "stuck:teleport-escape",
      "stuck:walled-off-recall", "livelock:ascend", "livelock:recall-escape", "livelock:teleport-explore")
_rows(WALK, ("policy", "policy_navigation"), _RULE_STUCK,
      "stuck:seek-stairs", "livelock:seek-upstairs", "breakout:dig-to-stairs")
_rows(EXCLUDED, "deep_teleport", _RULE_STUCK + " (owner 2026-11-15 「岩石溶解で掘る・だめなら帰還」: the "
      "50F+ stuck escape's Recall in place of the teleport)", "stuck:deep-recall")
_rows(EXCLUDED, "deep_teleport", "a town return already: Recall in place of a 50F+ self-teleport off "
      "the instant-death board (owner 2026-11-14 「敵への対処以前に手段が尽きた時点で帰還させる」)",
      "deep-teleport:recall")
_rows(WALK, "deep_teleport", "a search turn in place of a 50F+ self-teleport off the instant-death "
      "board with no Recall to read that reached the substitute past the finders: nothing is read",
      "deep-teleport:hold")
_rows(NOT_ESCAPE, "deep_teleport", "the decision record's branch name, not a decision's reason: 50F+ off the "
      "instant-death board with no Recall and no *Destruction* answer, no self-teleport is offered and the "
      "ladder acts as without one (owner 2026-11-14)", "deep-teleport:no-means-fight")
_rows(WALK, "recall_wait_teleport", "a search turn in place of a self-teleport withheld while Recall counts "
      "down (neither the instant-death board nor a T1 with a line of fire) that reached the substitute past "
      "the finders: nothing is read (owner 2026-11-15)", "recall-wait-teleport:hold")
_rows(NOT_ESCAPE, "recall_wait_teleport", "the decision record's branch name, not a decision's reason: while "
      "Recall counts down off the instant-death board with no T1 in the line of fire (or with three "
      "Teleportation scrolls or fewer), no self-teleport is offered and the ladder acts as without one "
      "(owner 2026-11-15)", "recall-wait-teleport:withheld")
_rows(EXCLUDED, "policy_combat", "a reposition to fight the guardian from cover, not a leave",
      "guardian:teleport-to-cover")
_rows(EXCLUDED, "policy_supply", "the starving leave of a locked quest floor: no enemy prompted it",
      "survival:ascend", "survival:stairs-quest-fail")
_rows(EXCLUDED, ("policy", "policy_quest"), "the quest regeneration's floor change (a plan, no enemy)",
      "quest:regen:ascend")
_rows(EXCLUDED, "quest25_pocket",
      "Q25's sealed pocket with no Stone to Mud (owner 2026-11-15 「溶かして撃つ・無ければ帰還」): the "
      "plan gives the floor up and reads Recall; a plan's leave, no enemy prompted it",
      "quest25:sealed-pocket-recall")
_rows(EXCLUDED, "quest25_battle",
      "Q25 phase 2's restock (owner 2026-11-16 「隘路で迎え撃ち尽きる前に帰還」): three fruitless look-outs "
      "in a row or two Healing potions left, the plan reads Recall to restock and the quest fails; a "
      "plan's leave by its own counts, not an escape from an enemy",
      "quest25:restock-recall")

# ================================================================ walks and waits
_RULE_WALK = "owner 2026-11-09 「歩いての後退は数えない」: a walk, a wait or a step toward an exit"
_rows(WALK, "policy", _RULE_WALK, "flee", "flee:wait", "status-threat:retreat", "threat:reposition",
      "no-wait:flee")
_rows(WALK, "threat_tiers", _RULE_WALK, "sensed-t1:walk")
_rows(WALK, "ladder_combat", _RULE_WALK + " (n1-c life-209: a declared walk-out's step to its up-stair)",
      "flee:seek-upstairs")
_rows(WALK, "threat_tiers", "owner 2026-11-10 P2 「積極的に*破壊*で消しにいく」: a step toward a T1 known only "
      "by detection, to bring it into the *Destruction* radius; no escape", "sensed-t1:approach-destruction")
_rows(WALK, ("policy_combat", "summoner_wait"), _RULE_WALK, "summoner:retreat")
_rows(WALK, ("policy", "policy_combat", "policy_navigation", "attack_answer", "blind_strike"), _RULE_WALK,
      "combat:disengage", "combat:disengage-", "combat:disengage-armed", "combat:disengage-clear-path",
      "combat:disengage-cut-through", "combat:disengage-explore", "combat:disengage-hold",
      "combat:disengage-search-upstairs", "combat:disengage-seek-upstairs", "combat:disengage-step",
      "combat:disengage-wait", "combat:disengage-wait-recall", "combat:disengage-*")
_rows(WALK, ("policy", "policy_combat"), _RULE_WALK,
      "emergency:clear-escape-path", "breeder-breakthrough:clear-escape-path",
      "breeder-breakthrough:seek-upstairs", "breeder-breakthrough:wait-recall",
      "breeder-item-damage:seek-stairs")
_rows(WALK, "policy_navigation", _RULE_WALK + " (exploration toward the down stairs)", "seek-downstairs")
# combat:disengage-melee strikes; the word rule reads its "disengage" as no attack.
_rows(WALK, ("attack_answer", "blind_strike"), _RULE_WALK + "; it strikes (word rule: no attack)",
      "combat:disengage-melee")

# ================================================================ the vocabulary without an escape
_RULE_TOWN = "town, shop, home and wilderness travel: no dive escape"
_rows(NOT_ESCAPE, ("policy_town", "policy_shop", "policy_home", "policy", "town_hold", "town_arbiter",
                   "cli", "policy_equipment", "policy_instore", "dungeon_shop", "purchase_rungs",
                   "input_executor"), _RULE_TOWN,
      "town:*", "shop:*", "home:*", "home-disposal:*", "store:*", "bounty:*", "claim:*",
      "outpost-fare:*", "mandatory:*", "tail:*", "supply-ledger:*", "equipment:*",
      "equipment-transaction:*", "suppress-random-teleport:*",
      "random-teleport-suppression-unactionable-current-loadout", "escape:take-off-anti-teleport",
      "posting-contract:*", "failed:recall-destination-unchosen", "recall-destination-unchosen",
      "survival:leave-wrong-store", "survival:mana-leave-wrong-store", "no-wait:leave-store",
      "fixedquest:q2-teleport", "fixedquest:q2-teleport-step-off", "quest25:quest25-druj-anti-teleport",
      "quest-carry:*", "random-teleport", "no-recall")
_rows(NOT_ESCAPE, ("policy", "policy_town", "policy_combat", "dark_recall", "once_quest_recall", "town_hold"),
      "the planned town return (return:*), not an escape from enemies",
      "return:*")
_rows(NOT_ESCAPE, ("policy", "policy_fundraising", "policy_combat", "town_hold"),
      "the fundraising (mining / scavenging) return: no dive", "fundraise:*", "fundraising:recall-stockout")
_rows(NOT_ESCAPE, ("policy", "policy_combat", "blind_strike"),
      "blind with a Recall already read: strike, heal, move or stay until it fires",
      "unseen-recall:blind-stay", "unseen-recall:heal", "unseen-recall:move")
_rows(NOT_ESCAPE, "me_powers", "the absorbed detection when the stairs are needed and unknown",
      "me-power:stairs-needed-and-unknown:*")
_rows(NOT_ESCAPE, "me_powers", "the absorbed area mapping when seen loot has no known way to it "
      "(owner 2026-11-13 「経路が見つからない時に周辺感知を使う」)", "me-power:loot-unreachable:*")
_rows(NOT_ESCAPE, "destruction_loot",
      "the steps and pickups before a non-urgent *Destruction* (owner 2026-11-17 「価値の高い品は先に拾って"
      "から撃つ」; a begun fetch is walked to its end, owner 2026-11-18 Q3 「命の危険が無ければ取り終える」): "
      "a walk to loot, no escape",
      "destruction-loot:place", "destruction-loot:fetch", "destruction-loot:fetch-frontier",
      "destruction-loot:pickup",
      "destruction-loot:trigger-autodestroy")
_rows(NOT_ESCAPE, "item_use_route",
      "a retention label naming why a kind is kept (item_use_route.RETENTION_KINDS, the item-use-route "
      "report and lint); never sent as a decision reason, no read and no escape",
      "retention:*")

# ================================================================ answered by the owner 2026-11-09
# The registry report's questions (「ダンジョンの分だけ数える」): Q1 and Q2 count (above); these do not.
_rows(WALK, "policy", _RULE_WALK + " (the unprofitable unique's disengage, renamed)",
      "combat:avoid-unprofitable-unique-seek-upstairs", "combat:avoid-unprofitable-unique-search-upstairs",
      "combat:avoid-unprofitable-unique-wait-recall")
_rows(EXCLUDED, "quest25_battle",
      "Q25 after its Recall is read (owner 2026-11-09 「段をやめ射線外で待つ」): the start stair, "
      "taken while the Recall is active; the Recall read is the escape counted (Q3, coordinator "
      "2026-11-09). Its floor change leads to town, where the per-dive counter does not run",
      "quest25:recall-exit")
_rows(WALK, ("quest25_battle", "quest_room_sweep"), _RULE_WALK + " (Q25 waiting for its Recall)",
      "quest25:recall-exit-walk", "quest25:recall-wait")
# "fire" of the casters' line of fire: the word rule read an attack.  Kept (registry report).
_rows(WALK, "quest25_battle", _RULE_WALK + " (Q25 out of the casters' fire; word rule: attack, kept)",
      "quest25:recall-out-of-fire", attack=True)
_rows(None, "quest25_battle", "word rule: a step / rest out of the casters' fire read an attack (kept)",
      "quest25:step-out-of-fire", "quest25:rest-out-of-fire", attack=True)
_rows(EXCLUDED, ("town_arbiter", "town_hold"), _RULE_DUNGEON + " (Q4: the wilderness's escapes)",
      "wilderness:escape-scroll", "wilderness:recall")
_rows(WALK, ("town_arbiter", "town_hold"), _RULE_DUNGEON + " (Q4: the wilderness's walk and wait)",
      "wilderness:flee", "wilderness:wait-recall")

# ================================================================ attacks (breeder window)
_RULE_ATTACK = "owner 2026-11-08 「20回の判定は、実際に攻撃した手だけで数える」: an attack"
_rows(None, ("policy", "policy_combat", "combat_answer", "blind_strike", "arena", "unseen_strike",
             "speed_dose", "policy_quest", "status_cure"), _RULE_ATTACK,
      "melee", "melee:choke", "melee:esp-threat-hunt", "no-wait:attack", "no-wait:melee",
      "arena:blind-strike", "arena:melee", "arena:unseen-strike", "arena:unseen-strike:absorbed-power",
      "emergency:blind-strike", "emergency:cornered-attack", "emergency:cornered-attack:absorbed-power",
      "emergency:unseen-strike", "emergency:unseen-strike:absorbed-power",
      "unseen:strike", "unseen:strike:absorbed-power", "unseen:strike-dark",
      "unseen:strike-dark:absorbed-power", "unseen:strike-return", "unseen:strike-return:absorbed-power",
      "stuck:walled-off-strike", "town:kill-mob", "town:kill-mob-friendly",
      attack=True)
# Owner 2026-11-10 (G1 of n1-a life-504): the short light/darkness blindness is not cured; the
# adjacent hostile or the unseen attacker is struck (status_cure.short_blind_key).
_rows(None, "status_cure", _RULE_ATTACK + " (a short light/darkness blindness, not cured)",
      "blind:short-melee", "blind:short-strike", "blind:short-strike:absorbed-power", attack=True)
# Owner 2026-11-07 「分からない隣のマスにも攻撃する」: the dungeon's blind board hit by an unseen
# blow (status_cure.dungeon_unseen_blow_key).
_rows(None, "status_cure", _RULE_ATTACK + " (blind, an unseen blow on the board)",
      "blind:unseen-strike", "blind:unseen-strike:absorbed-power", attack=True)
_rows(None, ("policy_combat", "policy", "magic_eater", "me_device_attacks", "me_q1_torch", "breeder_area_attack",
             "policy_quest", "quest25_battle", "summon_response", "policy_supply"), _RULE_ATTACK,
      "ranged:fire", "ranged:fire-offset", "ranged:fire-target", "ranged:aim-wand", "ranged:throw-oil",
      "ranged:throw-torch", "ranged:magic-eater-device", "ranged:magic-eater-powerful",
      "ranged:breeder-area", "ranged:breeder-area:*",
      "quest-strategy:melee", "quest-strategy:q2-fire", "quest-strategy:q2-melee-corpse-attack",
      "quest-strategy:ranged-fire", "quest-strategy:ranged-fire:magic-eater",
      "quest-strategy:ranged-light-area", "quest-strategy:ranged-light-area:absorbed-power",
      "quest-strategy:throw-never-move-blocker", "quest-strategy:throw-torch", "quest25:shot",
      "summoner:ranged-kill", "summoner:ranged-kill:can-summon", "summoner:ranged-kill:named-caster",
      "supply-fight:aim-wand", "supply-fight:fire-good-ammo", "supply-fight:read-attack-scroll",
      attack=True)
# QUEST_33 (owner 2026-11-19 「次の一行動で召喚主を倒す見込みがあるなら戦闘」): the blow at the summoner.
_rows(None, "quest_summon_answer", _RULE_ATTACK, "quest-strategy:summoned-strike", attack=True)
# The Anaguma pocket's blows and its area attack into the mouth (anaguma, owner 2026-11-10).
_rows(None, "anaguma", _RULE_ATTACK, "melee:anaguma", "melee:anaguma-close", "ranged:anaguma-close-area",
      attack=True)
# Escape-vocabulary attacks: their kind is no escape, their action strikes.
_rows(WALK, ("combat_answer", "blind_strike", "policy_quest", "speed_dose"), _RULE_ATTACK + " (cornered)",
      "flee:cornered-attack", "flee:cornered-attack:absorbed-power", attack=True)
# Owner 2026-11-09 「*破壊*>テレポートアウェイ>戦闘」: the status-threat rung's fight beside a follower.
_rows(None, ("combat_answer", "ladder_combat"), _RULE_ATTACK + " (cornered beside a status threat)",
      "status-threat:cornered-attack", attack=True)
_rows(NOT_ESCAPE, ("blind_strike", "policy_combat", "policy_quest", "speed_dose"),
      _RULE_ATTACK + " (blind, a Recall read)",
      "unseen-recall:blind-strike", "unseen-recall:strike", "unseen-recall:strike:absorbed-power",
      attack=True)
# Owner 2026-11-11 「恐怖になった時と強敵の前」: the Potion of Heroism, drunk in place of the blow
# fear refuses and before an attack on a T2-or-worse fear caster.  A drink: no escape, no attack.
_rows(NOT_ESCAPE, ("heroism_potion", "combat_answer"),
      "owner 2026-11-11 「恐怖になった時と強敵の前」 (a drink, neither an escape nor an attack)",
      "heroism:afraid", "heroism:fear-caster")
# The word rule's oddities, kept so that no decision changes (registry report): no attack is
# sent, but a word of the old list is in the reason ("shot" in oneshot, "melee", "kill", "fire").
_RULE_WORDS = "word rule: no attack is sent, the old word guess read one (kept; registry report)"
_rows(None, "oneshot_breath", _RULE_WORDS, "oneshot-breath:quaff", attack=True)
# combat:disengage-melee strikes and reads no attack ("disengage"); renamed by the unprofitable
# unique's disengage it loses that word and reads one ("melee").  Kept as the word rule read them.
_rows(None, "policy", "word rule: the renamed combat:disengage-melee (kept; registry report)",
      "combat:avoid-unprofitable-unique-melee", attack=True)
_rows(None, ("policy_combat", "policy_fundraising", "mining_loadout"), _RULE_WORDS,
      "melee:restore-weapon", "melee:restore-weapon:*", "melee:rearm-empty-hand", attack=True)
_rows(None, "policy_shop", _RULE_WORDS + " (a carry shortage's category)", "quest-carry:throwing_items*",
      attack=True)
_rows(None, ("policy_quest", "town_terminal"), _RULE_WORDS, "toughest-kill-time", "kill-descent",
      "quest:readiness:toughest-kill-time", "quest:readiness:kill-descent", attack=True)
# The depth gate's refusal names the missing abilities; resist_fire has "fire".
_rows(None, "policy", _RULE_WORDS, "depth-gate:destination-*:missing-*resist_fire*", attack=True)
_rows(None, "policy_town", _RULE_WORDS,
      "fundraising:no-safe-destination:depth-gate:destination-*:missing-*resist_fire*", attack=True)


# ---------------------------------------------------------------- lookups
_EXACT: dict[str, Reason] = {}
_PATTERNS: list[Reason] = []
for _row in ROWS:
    if any(mark in _row.pattern for mark in "*?["):
        _PATTERNS.append(_row)
    else:
        _EXACT.setdefault(_row.pattern, _row)
_PATTERNS.sort(key=lambda row: -len(row.pattern))   # stable: equal lengths keep the table's order


def lookup(reason: str | None) -> Reason | None:
    """The row of ``reason``: its exact row, else the longest pattern row that matches."""
    if not reason:
        return None
    row = _EXACT.get(reason)
    if row is not None:
        return row
    return next((row for row in _PATTERNS if fnmatchcase(reason, row.pattern)), None)


ESCAPE_KINDS = (EMERGENCY, RELOCATING, EXCLUDED)


def escapes(reason: str | None) -> bool:
    """The decision under ``reason`` is an escape: it relocates the player (counted or not) or
    removes or sends away the enemy (*Destruction*, Teleport Other) -- every row of
    ``ESCAPE_KINDS``.  Owner 2026-11-22 「逃げの手は全部床より先にする」: damaging_ground's step
    off never replaces one (a walk, a wait or any other stop is no escape here)."""
    row = lookup(reason)
    return row is not None and row.kind in ESCAPE_KINDS


def escape_shaped(reason: str) -> bool:
    """``reason`` has a word of the escape vocabulary, so it needs a row."""
    return any(word in reason for word in ESCAPE_WORDS)


def is_attack(reason: str | None) -> bool:
    """The decision under ``reason`` attacked (the breeder window's ``attack``)."""
    row = lookup(reason)
    return row is not None and row.attack


def strikes(reason: str | None) -> bool:
    """The decision under ``reason`` sends an attack: an ``attack`` row that is not one of the
    word rule's oddities (``_RULE_WORDS`` and its kin, whose action strikes nothing)."""
    row = lookup(reason)
    return row is not None and row.attack and not row.rule.startswith("word rule")


def survival(reason: str | None) -> bool:
    """``reason`` is a survival rung's: an escape the count reads (``COUNTED``) or a walking
    retreat (the rows of owner 2026-11-09 「歩いての後退は数えない」).  The ping-pong guard never
    refuses one (pingpong_guard)."""
    row = lookup(reason)
    return row is not None and (row.kind in COUNTED or row.rule == _RULE_WALK)


def reasons_of(kind: str) -> frozenset:
    """The exact reasons of ``kind`` (the counted kinds have no pattern rows)."""
    return frozenset(row.pattern for row in ROWS if row.kind == kind)


# ---------------------------------------------------------------- survival (design rev 9 item 3)
# Which decisions are "survival": the town hold's claim (town_hold, ``Claim.survival``; the
# decision's claim may pre-empt its holder) and cli's town-blocked fuse (TOWN_FUSE_COMBAT_REASON_
# PREFIXES: fighting and the survival ladder answer a monster, not the blocked visit) read these
# families, and no other list (scripts/reason_registry_lint.py fails on a second one).  A family
# is a reason prefix: every reason that starts with it is survival, registered row or not.
# Not ``survival`` above: that one is the ping-pong guard's survival rung (the counted escapes and
# the walking retreats of the rows).
class SurvivalFamily(NamedTuple):
    prefix: str
    rule: str


SURVIVAL_FAMILIES: tuple[SurvivalFamily, ...] = (
    SurvivalFamily("emergency:", "the emergency ladder's output (enters EscapeState as ``emergency``)"),
    SurvivalFamily("summons:", "the answer to the summons (summon_response; the third summon of a "
                   "floor visit reads Recall)"),
    SurvivalFamily("unseen-recall:", "the unseen attacker's Recall family"),
    SurvivalFamily("guardian:teleport-to-cover", "the guardian's teleport to cover"),
    SurvivalFamily("combat:disengage", "the disengage family"),
    SurvivalFamily("unseen:", "the unseen-attacker family"),
    SurvivalFamily("esp-threat:leave-", "the ESP-threat floor exit"),
    SurvivalFamily("town:seek-shelter", "town: a shelter from a monster"),
    SurvivalFamily("town:recover", "town: recovery from a monster's damage"),
)
SURVIVAL_PREFIXES = tuple(family.prefix for family in SURVIVAL_FAMILIES)
# A ``return:`` decision is survival only while the trigger that started the return is a danger
# trigger (policy_combat.py ``_last_return_trigger``).
SURVIVAL_RETURN_PREFIX = "return:"
# Rev 9.3: ``guardian-reposition`` is not in it -- a guardian reposition never starts a return
# (policy_combat.py sets ``_returning_to_town`` only when not repositioning), so it can never be
# the trigger a return began with.
SURVIVAL_RETURN_TRIGGERS = frozenset({"esp-threat", "unseen-attacker"})
SURVIVAL_RETURN_TRIGGER_PREFIX = "emergency-"


def is_survival_return_trigger(trigger: str | None) -> bool:
    return bool(trigger) and (
        trigger in SURVIVAL_RETURN_TRIGGERS
        or trigger.startswith(SURVIVAL_RETURN_TRIGGER_PREFIX)
    )


def is_survival(reason: str | None, return_trigger: str | None = None) -> bool:
    """Whether a decision is survival in the sense of design rev 9 item 3."""
    reason = reason or ""
    if reason.startswith(SURVIVAL_PREFIXES):
        return True
    return reason.startswith(SURVIVAL_RETURN_PREFIX) and is_survival_return_trigger(
        return_trigger
    )


# ---------------------------------------------------------------- stationary (cli's loop guard)
# The reasons that hold the player on one cell by design, so the position loop guard
# (cli._cell_loop_guard_applies) does not count their boards: each one is bounded by its own
# leash, named in its rule.  Before this table they were hand lists in cli.py (STATIONARY_REASONS,
# STATIONARY_EXEMPT_REASONS, QUEST_COMBAT_REASON_PREFIXES and three literal prefixes), and a
# reason left out of them stopped the bot as loop-detected (11-06 Q18's rest, 11-11 Q25's trap
# search, 11-13 Q25's recharge rest).  cli reads this table (``stationary_set`` /
# ``stationary_prefixes``) and scripts/reason_registry_lint.py fails on a hand list in cli.py.
# Add a row in the same commit as a new stationary reason.
#
# How a row matches a reason:
#
# ``HOLD``          the reason itself or any ``reason + ":..."`` (cli.STATIONARY_REASONS).
# ``EXEMPT``        the reason exactly (cli.STATIONARY_EXEMPT_REASONS).
# ``QUEST_COMBAT``  every reason that starts with it: fixed-quest attacks from one post
#                   (cli.QUEST_COMBAT_REASON_PREFIXES).
# ``ACTION``        every reason that starts with it: item use, ranged attacks and chests
#                   (cli.STATIONARY_ACTION_PREFIXES).
#
# The guard skips a board only when the player did not move.  tests/test_stationary_reasons.py
# pins the answer for every reason the code knows, and that the producers' own constants
# (policy_constants.RETURN_STATIONARY_REASONS, anaguma.STATIONARY, policy.ESCAPE_BUDGETED_WAIT_LIMITS,
# quest25_battle, quest_target_search, ...) are rows of this table.
HOLD = "hold"
EXEMPT = "exempt"
QUEST_COMBAT = "quest-combat"
ACTION = "action"
STATIONARY_MATCHES = (HOLD, EXEMPT, QUEST_COMBAT, ACTION)


class Stationary(NamedTuple):
    reason: str
    match: str
    rule: str


STATIONARY_ROWS: list[Stationary] = []


def _stationary(match, rule, *names) -> None:
    STATIONARY_ROWS.extend(Stationary(name, match, rule) for name in names)


# ======================================== HOLD: the reason or reason + ":..."
_stationary(HOLD, "searching a dead end in place", "search")
_stationary(HOLD, "meleeing in place", "melee")
# Walking returns may need SEARCH_LIMIT stationary searches at each candidate wall before moving
# to the next one; the policy bounds that work with _wall_search_counts (feeding these holds to
# the 40-cell watchdog produces a false loop at five walls, 5 * 8).  The Recall countdown (15-35
# turns) and the walk-out dig (walkout_dig; one cell tunnelled over several decisions, ended by
# the navigation ledger) are the other holds (policy_constants.RETURN_STATIONARY_REASONS).
_RULE_RETURN_HOLD = ("the walking return's bounded holds: the wall search (_wall_search_counts), the "
                     "Recall countdown, the walk-out dig (policy_constants.RETURN_STATIONARY_REASONS)")
_stationary(HOLD, _RULE_RETURN_HOLD,
            "return:search-upstairs", "return:wait-recall", "return:dig-to-upstairs",
            "return:dig-to-frontier")
# The ESP-threat leave relabels the same return machinery (_esp_threat_leave_key: return:X ->
# esp-threat:leave-X), so the same bounded holds arrive under these names.  The recall wait is
# emitted only while player.recalling and ends when the recall fires (n1-b life-357 2026-11-09
# 14:06 stopped as loop-detected after 32 esp-threat:leave-wait-recall waits on 48F).
_stationary(HOLD, _RULE_RETURN_HOLD + ", relabelled by the ESP-threat leave",
            "esp-threat:leave-search-upstairs", "esp-threat:leave-wait-recall",
            "esp-threat:leave-dig-to-upstairs", "esp-threat:leave-dig-to-frontier")
_RULE_WAIT_RECALL = "waiting in place for Word of Recall to fire: the countdown (15-35 turns) ends the hold"
_stationary(HOLD, _RULE_WAIT_RECALL, "fundraise:wait-recall")
# The mining run aborted on a ruled-out unique waits for its Recall under the abort's name
# (_mining_abort_exit_key, policy_constants.MINING_ABORT_REASON_PREFIX + ":wait-recall"), emitted
# only while player.recalling (n1-a life-530 2026-11-18 06:40 stopped as loop-detected after 33
# waits on Yeek cave 1F with the recall running).
_stationary(HOLD, _RULE_WAIT_RECALL + " (the mining abort's)",
            "fundraise:abort-unbeatable-unique:wait-recall")
# Clearing a physically occupied escape route attacks without changing cells; accuracy-aware
# combat projection bounds whether this is chosen.
_stationary(HOLD, "clearing an occupied escape route attacks without moving",
            "fundraise:clear-escape-path")
_stationary(HOLD, _RULE_WAIT_RECALL, "town:wait-recall", "wilderness:wait-recall")
# deep_fall_guard waits for its own Recall in place on a floor whose trap door would land on 50F+
# (owner 2026-11-22 「そもそも50Fに降りない方をしっかり作ること」), emitted only while player.recalling.
_stationary(HOLD, _RULE_WAIT_RECALL + " (deep_fall_guard)", "deep-fall-guard:wait-recall")
# Waiting for Recall after a breeder disengage is bounded (FRUITLESS_DISENGAGE_LIMIT backstops it);
# like the other *:wait-recall reasons it must not feed the guard, or the very escape armed by the
# breeder-containment disengage re-trips it.
_stationary(HOLD, _RULE_WAIT_RECALL + " (FRUITLESS_DISENGAGE_LIMIT)",
            "combat:disengage-wait-recall", "breeder-breakthrough:wait-recall", "summoner:wait-recall")
# _fruitless_disengage_key re-labels return:* reasons before the CLI sees them; this is the same
# bounded _wall_search_counts search as return:search-upstairs.
_stationary(HOLD, _RULE_RETURN_HOLD + ", relabelled by the fruitless disengage",
            "combat:disengage-search-upstairs")
# The income run's floor exit searches the same walls with the same bound
# (policy_fundraising ``_secret_wall_exit``; n1-a life-537 2026-11-24).
_stationary(HOLD, _RULE_RETURN_HOLD + ", the income run's floor exit (_secret_wall_exit)",
            "fundraise:search")
# Riding out confusion with no physical hostile: the game's confusion timer counts down every
# player turn (magic-effects-timeout-reducer.cpp mod_confusion(-1)), so the hold ends by itself
# (n1-b life-297 2026-11-02 22:49 stopped as loop-detected after 170 waits).
_stationary(HOLD, "riding out confusion: the game's timer ends it", "confused:wait")

# ======================================== EXEMPT: the reason exactly
# Productive actions that deliberately hold the player on one tile, which looks like a confined
# oscillation to the position-based guard.  Walking and failed-position reasons remain guardable.
_stationary(EXEMPT, "digging toward the stairs", "breakout:dig-to-stairs")
# Mining-rework digs, bounded by the sweep's MINING_SWEEP_HARD_LIMIT and MINING_STALL_LIMIT.
_stationary(EXEMPT, "mining: MINING_STALL_LIMIT / MINING_SWEEP_HARD_LIMIT",
            "fundraise:dig-to-treasure", "fundraise:dig-mark-bump", "fundraise:mine-treasure",
            "fundraise:tunnel-out")
# Picking the closed door that leads back to a known up staircase; bounded per door by
# FUNDRAISING_UPSTAIRS_DOOR_ATTEMPT_LIMIT (D19).
_stationary(EXEMPT, "FUNDRAISING_UPSTAIRS_DOOR_ATTEMPT_LIMIT per door (D19)",
            "fundraise:open-upstairs-door")
# Picking a locked door on the mining closure's route to a detected vein; bounded per target by
# MINING_STALL_LIMIT and per floor by MINING_SWEEP_HARD_LIMIT (D31).
_stationary(EXEMPT, "MINING_STALL_LIMIT per target, MINING_SWEEP_HARD_LIMIT per floor (D31)",
            "fundraise:seek-treasure:open-door")
_stationary(EXEMPT, "waiting at a choke for an unseen attacker", "unseen:choke-wait")
# Waiting out a short light/darkness blindness at high HP with nothing adjacent to strike (owner
# 2026-11-10 G1 「隣の敵は殴り、いなければ治るまで待つ」, status_cure.short_blind_key).  Each onset ends
# within status_cure.SHORT_BLIND_MAX_GAME_TURNS (3-7 ticks, effect-player-resist-hurt.cpp), and sight,
# a heavy HP loss, a confusion, a cut or a longer blindness ends the hold (short_blind_holds).
# n1-a life-535 (2026-11-23 05:15, 城42階): light hounds' flash breaths re-blinded it four times in
# 186 game turns; 28 waits on two cells filled the 40-decision window and stopped it.
_stationary(EXEMPT, "status_cure.SHORT_BLIND_MAX_GAME_TURNS per onset (owner 2026-11-10 G1)",
            "blind:short-wait")
# Repeated opens against the reviewed Q34 doors are productive game actions: each lock-pick
# attempt advances the game while the player stays at the approved approach cell.  The final
# (glass) door is bounded by Q34_FINAL_DOOR_ATTEMPT_LIMIT, the doors after it by
# Q34_SEQUENCE_DOOR_ATTEMPT_LIMIT per door.
_stationary(EXEMPT, "Q34's lock picks (Q34_FINAL_DOOR_ATTEMPT_LIMIT, Q34_SEQUENCE_DOOR_ATTEMPT_LIMIT)",
            "quest-strategy:open-opening-door", "quest-strategy:open-final-door",
            "quest-strategy:open-sequence-door")
# Bounded by DETECTED_THREAT_HOLD_MAX_GAME_TURNS (50 player / 500 game turns).
_stationary(EXEMPT, "DETECTED_THREAT_HOLD_MAX_GAME_TURNS",
            "summoner:hold-choke", "detected:hold-choke")
# The Anaguma pocket (owner 2026-11-10): the uses of Stone to Mud from one cell (also through the
# absorbed power), the hold on the pocket (bounded by anaguma.WAIT_GAME_TURNS without contact,
# then a detection and the plan's end), the detection and the absorbed Speed of the close-in
# (anaguma.STATIONARY).
_stationary(EXEMPT, "the Anaguma pocket's own bounds (anaguma.WAIT_GAME_TURNS, the plan's end)",
            "anaguma:dig", "anaguma:dig:absorbed-power", "anaguma:hold", "anaguma:detect",
            "anaguma:close-haste")
# A quest hold ends when a wave appears or completion routing takes ownership; one kept for the
# enemies the hold was retaken for ends when they are gone (quest_sweep_target.hold_kept: the
# retreat veto's lifetime, UNSEEN_GAME_TURNS after they were last shown).
_stationary(EXEMPT, "a quest hold ends with a wave or the completion routing",
            "quest-strategy:hold")
# Resting on a quest search's cast stop until the detection spacing comes
# (quest_target_search._redetect_wait): bounded by HUNT_REDETECT_GAME_TURNS from the latest cast,
# then the rows cast and the stop is covered.
_stationary(EXEMPT, "HUNT_REDETECT_GAME_TURNS from the latest cast",
            "quest-search:wait-redetect")
# Resting in place on 50F+ while the Rod of Detection recharges before a step out of the
# trap-detected area (deep_detection_rod, owner 2026-11-26 「50F以降は全感知のロッドを持つ」):
# bounded by the rod's recharge, then the rod is zapped.
_stationary(EXEMPT, "stationary_bounds.DETECTION_ROD_RECHARGE_MAX_GAME_TURNS (the rod's recharge, pval 99)",
            "deep-detection-rod:wait-recharge")
_stationary(EXEMPT, "the plan's dig_attempt_limit", "quest-strategy:exit-dig")
# Bounded per warned cell by SEARCH_LIMIT (trap_warning): a corridor of traps walked one search at
# a time is no confined loop.
_stationary(EXEMPT, "SEARCH_LIMIT per warned cell", "warning:trap-search")
# Q25's own trap rule (quest25_battle_walk._trap_key, owner 2026-11-09 「罠探知があるなら使用することで確定。
# そうでなければ10回で打ち切る。」): bounded per cell by the plan's revised_plan_values.trap_searches
# (n1-a life-508 2026-11-11: row 1 from [1,14] to [1,9], stopped by the 40-decision window).
_stationary(EXEMPT, "the plan's trap_searches per cell (owner 2026-11-09)",
            "quest25:trap-search")
# Q25's between-phases rest (quest25_battle_attack._recharge_key, owner 2026-11-06 「各段階の間に、魔道具術師の
# 使用回数のうち、攻撃に使うものを全快させる」): each 'R100' advances the game and a phase takes at most
# RECHARGE_REST_LIMIT of them (n1-b life-382 2026-11-13 04:42:57: eleven rests on [5,1]).
_stationary(EXEMPT, "RECHARGE_REST_LIMIT per phase (owner 2026-11-06)",
            "quest25:rest-recharge")
# The summon answer's recharge rest (quest_summon_answer._recharge_key, owner 2026-11-25 「休憩して魔法道具
# の使用回数を戻せる場合はその限りではない」): each 'R100' advances the game; the list reads between the
# rests continue its episode.
_stationary(EXEMPT, "stationary_bounds.SUMMONED_RECHARGE_REST_MAX_DECISIONS (owner 2026-11-25)",
            "quest-strategy:summoned-rest-recharge")
_stationary(EXEMPT, "the once-quest floor's rest (policy_constants.ONCE_QUEST_TICK_REST_REASON)",
            "once-quest:recover")
# Exact policy-registered escape WAIT terminals (policy.ESCAPE_BUDGETED_WAIT_LIMITS).  Each owns
# the bound recorded there and ends visibly as livelock:exhausted; no other escape reason bypasses
# the outer guard.
_stationary(EXEMPT, "policy.ESCAPE_BUDGETED_WAIT_LIMITS",
            "status-threat:wait", "flee:wait", "return:wait", "combat:disengage-wait", "emergency:wait",
            "town:blocked:repetition")
# The waits the loop guard did not know, given a bound and taken out of it (whole-bot review
# 2026-11-23 K3, owner (b)-1 「上限を付けて見張りから外す」): each hold episode on one cell that
# outlasts its bound stops as ``stationary:exhausted:<reason>`` (stationary_bounds, which says
# where each value comes from).
_stationary(EXEMPT, "stationary_bounds.BLIND_MAX_GAME_TURNS (the longest blindness onset)",
            "blind:wait-sight", "fundraise:wait-sight", "return:wait-sight")
_stationary(EXEMPT, "stationary_bounds.RECALL_MAX_GAME_TURNS (emitted only while the recall counts down)",
            "combat:disengage-hold", "combat:avoid-unprofitable-unique-hold")
_stationary(EXEMPT, "stationary_bounds.UNPROFITABLE_UNIQUE_WAIT_MAX_DECISIONS (FRUITLESS_DISENGAGE_LIMIT)",
            "combat:avoid-unprofitable-unique-wait")
_stationary(EXEMPT, "stationary_bounds.FINALE_HOLD_MAX_DECISIONS (STAND_ROUTE_TRIES x OPEN_STAND_WAIT)",
            "angband-finale:hold")
# The town's wait for the 99F/100F preparation phase while Angband's 96F+ recall is refused
# (finale_hold.town_key): each step stops the phase by name past finale_prep.STEP_LIMIT, and the
# town then stops as town:blocked:finale-prep-stopped:<reason>.
_stationary(EXEMPT, "finale_prep.STEP_LIMIT per step (the phase stops by name, then the town)",
            "town:finale-hold:phase")
# The Black Markets' Restore Mana circuit short of gold (finale_bm_tour._funds_key, owner
# 2026-11-18 「必要なものは買う」): Home's cash sale acts between the waits, at most
# FUNDS_SALE_WAITS at one gold; the fundraising run handed over leaves town on its own.
_stationary(EXEMPT, "finale_bm_tour.FUNDS_SALE_WAITS at one gold, then the fundraising run",
            "town:finale-hold:bm-funds-sale")
_stationary(HOLD, "one wait: the fundraising run handed over takes the town (morivant_tower)",
            "town:finale-hold:bm-funds-fundraise")
# Owner 2026-11-25, the 96F+ case: the deepest other dungeon picked for the finale's gold
# (policy_town._finale_funds_dive_key); the next board reads the recall to it.
_stationary(HOLD, "one wait: the next board's departure reads the recall to the picked dungeon",
            "town:finale-funds-dive")
_stationary(EXEMPT, "stationary_bounds.AMBERITE_HOLD_MAX_GAME_TURNS (no natural end)", "amberite:hold")
_stationary(EXEMPT, "stationary_bounds.THREAT_WAIT_MAX_GAME_TURNS (no natural end)", "threat:wait")
_stationary(EXEMPT, "stationary_bounds.QUEST25_FIRE_HOLD_MAX_GAME_TURNS (no natural end)",
            "quest25:hold-out-of-fire")
_stationary(EXEMPT, "stationary_bounds.QUEST_HOLD_UNREACHABLE_MAX_GAME_TURNS (no natural end)",
            "quest-strategy:hold-unreachable")
_stationary(EXEMPT, "stationary_bounds.QUEST_BLOCKED_HOLD_MAX_GAME_TURNS (after the plan's hold_budget)",
            "quest:blocked:hold")
_stationary(EXEMPT, "stationary_bounds.IDLE_WAIT_MAX_GAME_TURNS (no natural end)", "wait")
_stationary(EXEMPT, "stationary_bounds.NONE_WAIT_MAX_GAME_TURNS (no natural end)", "policy:none-wait")

# ======================================== QUEST_COMBAT: every reason starting with it
# Fixed-quest combat is productive even when a strategy deliberately fights from one post for an
# entire wave.  Route/avoid failures remain guardable; only commands which actually attack are exempt.
_RULE_QUEST_COMBAT = "a fixed-quest attack from one post: the wave or the quest ends it"
_stationary(QUEST_COMBAT, _RULE_QUEST_COMBAT,
            "quest-strategy:melee", "quest-strategy:ranged-fire",
            # The same ranged core labels its Q2 shots separately.
            "quest-strategy:q2-fire",
            # Quest 33's summon answer's blow (quest_summon_answer._strike: the summoner, then the
            # summoned nearest first; its shots are ranged: rows).  n1-b life-419 (2026-11-26 08:54)
            # killed the Queen Ant beside (26,42), then about one of her fire ants a blow (63 -> 41 in
            # view), and the window stopped it as confined.
            "quest-strategy:summoned-strike")

# ======================================== ACTION: every reason starting with it
_stationary(ACTION, "using an item in place", "item:")
_stationary(ACTION, "a ranged attack from one cell", "ranged:")
_stationary(ACTION, "opening or disarming a chest in place", "chest:")


# ---------------------------------------------------------------- bounded waits (lint only)
# A wait or rest whose reason is no row above still holds the player on one cell, and the loop
# guard counts it: it is fine only when the producer bounds it well inside LOOP_WINDOW (40
# decisions).  scripts/stationary_reason_lint.py fails on a wait or rest under a reason that is
# neither a stationary row nor a row here (beyond its 2026-11-23 baseline).  A row names the
# module constant that bounds the hold (``module.NAME``, checked to exist) and the rule; nothing
# at run time reads this table, so a row changes no decision.
class BoundedWait(NamedTuple):
    reason: str
    bound: str      # "module.CONSTANT" of src/hengbot
    rule: str


BOUNDED_WAITS: list[BoundedWait] = []


def stationary_set(match: str) -> frozenset:
    """The reasons of the ``HOLD`` or ``EXEMPT`` rows."""
    return frozenset(row.reason for row in STATIONARY_ROWS if row.match == match)


def stationary_prefixes(match: str) -> tuple:
    """The prefixes of the ``QUEST_COMBAT`` or ``ACTION`` rows, in the table's order."""
    return tuple(row.reason for row in STATIONARY_ROWS if row.match == match)


def stationary_matches(reason: str, holds, exempt, prefixes) -> bool:
    """``reason`` holds the player on one cell by design, read from the given sets (cli passes
    its module names, which a test may patch)."""
    return (
        any(reason == hold or reason.startswith(f"{hold}:") for hold in holds)
        or reason in exempt
        or reason.startswith(tuple(prefixes))
    )


def stationary(reason: str | None) -> bool:
    """``reason`` holds the player on one cell by design (the table above)."""
    return bool(reason) and stationary_matches(
        reason, stationary_set(HOLD), stationary_set(EXEMPT),
        stationary_prefixes(QUEST_COMBAT) + stationary_prefixes(ACTION))
