"""Angband is explored no deeper than 95F until the 99F/100F tactics exist.

Owner 2026-11-19 (verbatim): 「99F 100Fの戦い方をまだ作っていない。n1-bは次回潜行時に95Fまで登り階段で
戻ること。以降、準備ができるまで鉄獄95Fで探索すること。」  n1-b life-411 (Angband recall depth 99, the
guardian bounce valve's Angband) recalled to 99F and straight back to town, dive after dive.  The rule
is every character's: the tactics are missing for all of them.

- The cap: ``ANGBAND_DEPTH_CAP`` (95).  ``None`` lifts it for every character.
- The lift (owner 2026-11-20, the 99F/100F directive's answer 1): the cap holds until the town
  board finds the character ready (angband_finale ``lifted``: the Restore Mana target, the five
  supplies, the equipment conditions and resist curse); every reader that has the policy passes
  it (``policy=``), so a ready dive goes on below 95F to Oberon's 99F and the Serpent's 100F.
- No stair down past the cap (``capped``): read by ``dive_floor.capped`` (the descent targets, the
  remembered downstairs, explored_floor's dead end) and by the descent-target and the underfoot
  escape stairs' refusals in policy, the no-depth-progress judgement (a dive at the cap is at its
  ceiling).  At the cap the floor is explored as any floor whose descent is refused: explored, it is
  a dead end (explored_floor) and the dive returns by Word of Recall.
- Below the cap (a recall landing deeper, n1-b's 99) the up stairs are the stairs taken
  (``climbing``): the climb of dive_floor (owner 2026-11-17 「49Fに帰還して上り階段を探して適正階層まで
  行く」, ladder_descent's climb rung) under this rule's reasons ``angband-cap-95:*`` (ladder_descent.climb_key, reasons.py).  The
  existing safety rules still come first (the rungs above the climb).
- The recall depth: Word of Recall read in Angband on a floor at or below the cap and shallower than
  the saved depth asks 「ここは最深到達階より浅い階です。この階に戻って来ますか？」
  (src/spell-kind/spells-world.cpp recall_player, ``set_max_level(floor.dun_level)`` on y).  The
  executor answers y there (``reset_recall_depth``), so the next dive lands on the cap's floor
  instead of climbing again; everywhere else it still refuses (the deepest floor is kept).

The speed ceiling (supervisor 2026-11-27, owner 「大きく加速を得るためにはスピードの指輪が一番簡単だが、
これの生成階層は80Fである。私の指定でリスクを取って80Fに行かせていたのはこのためである。」): a character
whose permanent speed does not meet a depth speed row (policy_constants ``SPEED_GATES``: +25 from 81F,
+10 from 70F) has the cap lowered to the floor above that row (``speed_ceiling``, held every board
by ``observe``), for the 81F row's +25 the Ring of Speed's allocation depth 80F
(``RING_OF_SPEED_DEPTH``).  The cap's answers then hold at the ceiling as they hold at 95F: no
stair passes it, a deeper floor is climbed (on the floor one past it the speed gap starts no
return: ``climb_gaps``), and Word of Recall read on the ceiling floor answers the reset-recall question y (the operation's
``angband_cap``).  The recall landing one floor past the ceiling, whose only gap is the speed row,
is admitted (``landing_gaps``): its up staircase is taken at once.  n1-b life-419 (CL50, permanent
speed +17) fled Angband 80F by Teleport Level onto 81F (playrecord-SOAK.txt 「80階(鉄獄):
レベル・テレポートで脱出した」); Angband's saved depth became 81, every Angband recall was refused by
the 81F speed gate, and from 2026-11-26 13:20 to 11-27 12:37 all 221 recalls went to the Mountain
50F or the Castle 64-65F.
"""

from __future__ import annotations

from collections.abc import Mapping

from hengbot.model import DUNGEON_ANGBAND

# Owner 2026-11-19 「準備ができるまで鉄獄95Fで探索」.  None lifts the cap.
ANGBAND_DEPTH_CAP: int | None = 95

# The Ring of Speed's allocation depth: lib/edit/BaseitemDefinitions.jsonc id 136 (ring 「スピード」,
# tval 45 sval 31) "level": 80, "allocations": [{"depth": 80, "rarity": 1}]; its pval is
# randint1(5) + m_bonus(5, level), plus one per one_in_(2) (object-enchant/others/
# apply-magic-ring.cpp SV_RING_SPEED).  The 81F speed row's ceiling (81 - 1) is this floor
# (tests/test_angband_speed_ceiling_1127.py holds the two equal).
RING_OF_SPEED_DEPTH = 80
# The speed ceiling read on the last board (``observe``; None: every speed row met).
CEILING = "_angband_speed_ceiling"


def speed_ceiling(snapshot) -> int | None:
    """The deepest floor the board's permanent speed admits: the floor above the shallowest depth
    speed row it does not meet (policy_constants ``SPEED_GATES``), or None when it meets them all.
    The permanent speed is the fact the depth gates read (speed_valuation; a timed haste is not
    counted, policy_observation ``_missing_required_abilities``)."""
    from hengbot.policy_constants import SPEED_GATES  # import cycle (policy_constants -> angband_finale)
    from hengbot.speed_valuation import permanent_player_speed
    speed = permanent_player_speed(snapshot)
    unmet = [first for first, _label, need in SPEED_GATES if speed < need]
    return min(unmet) - 1 if unmet else None


def observe(policy, snapshot) -> None:
    """Every board: hold the speed ceiling of the board's permanent speed."""
    setattr(policy, CEILING, speed_ceiling(snapshot))


def cap(dungeon_id: int, policy=None) -> int | None:
    """The deepest floor of ``dungeon_id`` the character may stand on, or None (no cap, or the
    cap lifted for ``policy``'s character: angband_finale ``lifted``).  With ``policy`` the speed
    ceiling (``speed_ceiling``) lowers the 95F cap."""
    if dungeon_id != DUNGEON_ANGBAND:
        return None
    if policy is not None:
        from hengbot import angband_finale  # import cycle (restore_mana_target)
        if angband_finale.lifted(policy):
            return None
        ceiling = getattr(policy, CEILING, None)
        if ceiling is not None:
            return ceiling if ANGBAND_DEPTH_CAP is None else min(ceiling, ANGBAND_DEPTH_CAP)
    return ANGBAND_DEPTH_CAP


def _speed_capped(dungeon_id: int, policy) -> int | None:
    """The speed ceiling when it is ``dungeon_id``'s cap for ``policy`` (Angband, the ceiling
    shallower than the 95F cap), else None."""
    ceiling = getattr(policy, CEILING, None) if policy is not None else None
    if ceiling is None or cap(dungeon_id, policy) != ceiling:
        return None
    return ceiling


def _without_speed(gaps) -> frozenset:
    from hengbot.policy_constants import SPEED_GATE_LABELS  # import cycle
    return frozenset(gaps) - SPEED_GATE_LABELS


def landing_gaps(policy, snapshot, dungeon_id: int, depth: int, gaps) -> frozenset:
    """A town gate's ``gaps`` of the recall landing ``depth`` of ``dungeon_id``: the speed rows
    taken out for Angband's landing one floor past the speed ceiling, whose up staircase is taken
    at once (``climbing``).  The risk is bounded to that one floor: a landing deeper still keeps
    its gaps (the recall stays refused), and the floor's danger and escape rules come before the
    climb as on every floor."""
    ceiling = _speed_capped(dungeon_id, policy)
    if (ceiling is None or depth != ceiling + 1
            or not getattr(snapshot, "in_town", False)):
        return frozenset(gaps)
    return _without_speed(gaps)


def climb_gaps(policy, snapshot, gaps) -> frozenset:
    """The ``gaps`` of the floor stood on: on the Angband floor one past the speed ceiling (the
    landing ``landing_gaps`` admits) the speed rows start no town return -- the climb
    (``climbing``) answers them, and a Word of Recall read there would keep the saved depth past
    the ceiling (recall_player asks the reset only on a floor shallower than the saved depth).
    A deeper floor keeps them: several floors climbed short of the speed row is no bounded risk,
    so the ordinary resist-gap return leaves it."""
    floor_key = getattr(snapshot, "floor_key", None)
    if getattr(snapshot, "in_town", True) or not floor_key or floor_key[2]:
        return frozenset(gaps)
    ceiling = _speed_capped(floor_key[0], policy)
    if ceiling is None or floor_key[1] != ceiling + 1:
        return frozenset(gaps)
    return _without_speed(gaps)


def capped_at(dungeon_id: int, destination: int, policy=None) -> bool:
    """A floor ``destination`` of ``dungeon_id`` lies past the cap."""
    deepest = cap(dungeon_id, policy)
    return deepest is not None and destination > deepest


def capped(snapshot, destination: int, policy=None) -> bool:
    """A stair down from this dungeon floor to ``destination`` would pass the cap."""
    return (not snapshot.in_town and snapshot.dungeon_level > 0
            and capped_at(snapshot.floor_key[0], destination, policy))


def climbing_floor(floor_key, policy=None) -> bool:
    """``floor_key`` is a dungeon floor (no quest floor) deeper than the cap."""
    return (floor_key is not None and floor_key[1] > 0 and not floor_key[2]
            and capped_at(floor_key[0], floor_key[1], policy))


def climbing(snapshot, policy=None) -> bool:
    """On a floor deeper than the cap: the up stairs are the way on."""
    return not snapshot.in_town and climbing_floor(snapshot.floor_key, policy)


# Owner 2026-11-21 (verbatim, LOCKED) 「帰還の深さが96F以上なら遠征以外で鉄獄へ帰還しない」 (it replaces
# 「今のまま（99Fに着いたら登って95Fへ）」): n1-b life-411 died on 100F at 17:16 after an ordinary
# departure read Word of Recall toward Angband with its recall depth at 100 and landed beside the
# Serpent of Chaos (it had done so once at 17:15 too).
DEEP_RECALL_REFUSED_FROM = 96


def deep_recall_refused(snapshot, dungeon_id: int, policy=None) -> bool:
    """A recall toward Angband outside the finale's expedition (the cap not lifted for
    ``policy``) while Angband's saved recall depth is DEEP_RECALL_REFUSED_FROM or deeper: the town's
    departure takes another destination (policy ``_recall_destination_safe`` refuses it)."""
    if dungeon_id != DUNGEON_ANGBAND or cap(dungeon_id, policy) is None:
        return False
    depths = getattr(snapshot, "dungeon_recall_depths", None) or {}
    try:
        saved = int(depths.get(DUNGEON_ANGBAND, 0) or 0)
    except (TypeError, ValueError):
        return False
    return saved >= DEEP_RECALL_REFUSED_FROM


def reset_recall_depth(observation, *, lifted: bool = False, deepest: int | None = None) -> bool:
    """The answer to recall_player's reset-recall-depth question on the board ``observation``
    (the raw state the operation was posted on): y in Angband on a floor at or below the cap
    while the saved depth is deeper than the cap; n everywhere else, and always n while the cap
    is lifted for the finale's expedition (``lifted``, the operation's ``cap_lifted``: the saved
    99F is the expedition's way back).  ``deepest`` (the operation's ``angband_cap``: ``cap`` read
    with the policy, the speed ceiling included) lowers the cap when given."""
    if lifted or not isinstance(observation, Mapping):
        return False
    floor = observation.get("floor")
    progress = observation.get("progress")
    if not isinstance(floor, Mapping):
        return False
    try:
        dungeon_id = int(floor.get("dungeon_id", 0))
        level = int(floor.get("level", 0))
    except (TypeError, ValueError):
        return False
    ceiling = cap(dungeon_id)
    if ceiling is not None and deepest is not None:
        ceiling = min(ceiling, deepest)
    if ceiling is None or level < ceiling or int(floor.get("quest_id", 0) or 0):
        return False
    depths = progress.get("dungeon_recall_depths") if isinstance(progress, Mapping) else None
    saved = depths.get(str(dungeon_id), depths.get(dungeon_id)) if isinstance(depths, Mapping) else None
    try:
        return saved is None or int(saved) > ceiling
    except (TypeError, ValueError):
        return False
