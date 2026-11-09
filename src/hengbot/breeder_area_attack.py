"""Against breeders, the attack is chosen by its damage to the whole group (owner 2026-11-01).

Owner, verbatim (2026-11-01, raised in priority 2026-11-03 「増殖モンスターへの
範囲攻撃を優先度上げて実装して」): 「優先度低で良いが、増殖モンスターに対峙して
いるときに範囲攻撃や視界内攻撃を優先するロジックが欲しい。増殖モンスター相手の
ときは敵の群れ全体に与えるダメージ量で攻撃を選択して。」

When the hostiles a combat rung engages include a MULTIPLY monster (the race
knowledge's ``can_multiply``), every usable attack is scored by its expected
total damage over the group: the sum, over each visible hostile monster the
attack would hit, of the damage after that race's known resistance capped by
that monster's estimated HP (damage past death is no damage to the group),
times the attack's success chance.  "The group" (「敵の群れ全体」) is every
visible hostile, breeder or not; a monster only detected (not in view) is not
counted, nor is a pet or a peaceful monster (the town rule below keeps them).

Candidates (``_means``): the Magic-Eater's absorbed attack powers
(me_device_attacks: the displayed rows, success = 100 - fail%) and, for every
class, the known carried attack wands, rods and staffs of that table plus the
Scroll of Dispel Undead (``SCROLLS``).  Their success: zapwand-execution.cpp /
use-execution.cpp (``attack_expectation.device_use_success``) and
zaprod-execution.cpp (``attack_expectation.rod_use_success``); a scroll always
works once it can be read (scroll-read-executor.cpp; blindness, confusion and
an unlit grid refuse it, cmd-read.cpp:37, action-limited.cpp:88-98).  Mana
Storm, Starlight, Wonder, Earthquakes, *Destruction* and the self-damaging
Scrolls of Fire, Ice and Logrus are not candidates.

Shapes, from the source (a direction key aims at the player's position plus
99 steps, spells-launcher.cpp ``get_target_position(..., 99)``; the range is
18, AngbandSystem::get_max_range):

- bolt: PROJECT_STOP, the first monster on the ray (spells-launcher.cpp
  fire_bolt); a beam hits every monster on the ray (fire_beam, PROJECT_BEAM);
  ``fire_bolt_or_beam`` is a beam ``beam_percent`` of the time.
- ball: the ray stops at the first monster or before the first wall
  (effect-processor.cpp: the path breaks before a non-PROJECTION grid when
  rad > 0; an empty path explodes on the player's own grid) and the blast
  covers every grid within ``AREA_RADIUS`` game distance of the impact that is
  projectable from it (range-calc.cpp ball_shape / is_prevent_blast).
- breath: range-calc.cpp breath_shape, ported in ``_breath_cells``; a breath
  with an empty path is a ball (effect-processor.cpp ``breath && !path_n``).
- a targeted burst (owner 2026-11-03 「群れの中心を狙う」): an absorbed ball
  or breath may instead burst on any floor grid within its radius of a
  visible hostile that the projection reaches -- a grid target drops
  PROJECT_STOP (spells-launcher.cpp:33-36, :60-63), so the ray flies over the
  monsters on the way and stops at the grid (projection-path-calculator.cpp
  :79) or before a wall.  The executor walks the target cursor there
  (me_device_attacks_input); carried devices keep the direction aim (their
  item command has no prompt-answering executor step).
- sight: every visible hostile projectable from the player
  (spells-sight.cpp project_all_los); not used while a pet or a peaceful
  monster is in view (me_device_attacks.sight_hits_bystander).

A monster ``r`` grids from the blast centre (a breath: dist_to_line from the
ray) takes ``(dam + r) / (r + 1)`` (effect-monster.cpp
make_description_of_affecred_monster); the falloff is applied to the damage
after resistance (an approximation: the game reduces before resisting).
Walls are the board's impassable grids; an unknown grid blocks.

The decision (``key``): the best area option is used only when its group
score is strictly larger than the best one-target answer the caller could
give -- any of these means on any one visible hostile, melee on an adjacent
one (attack_expectation.melee) or a shot at a distant one
(``_estimated_ranged_damage_per_shot``; its hit chance is left out, so the
baseline is optimistic and a tie keeps today's choice).  Otherwise None keeps
the caller's single-target order unchanged, as does every fight without a
breeder.  Among equal scores, fewer prompts come first (a direction before a
cursor walk; a nearer burst grid), then a rod (it recharges), then the lower
base level.  In town an area option that would catch a friendly the
character could not defeat once angered is dropped (owner 2026-10-31
「敵対させたあと勝てるかで判断。勝てるなら巻き込んで良い。」,
``policy._town_friendly_unbeatable``).  The 100-attack flight rule
(breeder_stalemate) and the survival rungs above every combat rung are
untouched.

Owner 2026-11-08 (「20行動で減らせないのであれば倒すアルゴリズム側に問題がある。特に範囲攻撃の
使い方など。」, the chosen option 「射線にいれば範囲で撃つ」): 「どの段でも、もっと危ない敵が動いて
いなければ、射線にいる増える敵を撃つ。範囲攻撃は一番多く倒せるマスを狙い、2体以上巻き込めるなら
単体攻撃より先に使う。道をふさがれたら待たずに撃って開ける。」

- Kills (``_tally``): a breeder the option reaches dies when the damage after its
  resistance and the falloff ``(dam + r) / (r + 1)`` (effect-monster.cpp:108) reaches its
  HP: the race's dice average (monrace_knowledge ``average_hp``; FORCE_MAXHP the maximum),
  or the health band's upper bound when that is lower (a hurt one).  The expected kills
  are that count times the success chance.  The player's own projection never hurts the
  player (effect-player.cpp:140-141), so no aim is barred for being near the player.
- Two or more (``_mass_key``): when an aim catches at least two visible hostile breeders,
  its group damage beats every one-target answer (owner 2026-11-09 「群れに対して与える合計
  ダメージが単体攻撃より大きければ使う。」) and no more dangerous hostile acts
  (``more_dangerous_acting``), the aim with the most expected kills is used (then the larger
  group damage, then the tie order above).  Otherwise the group-damage comparison above is
  unchanged.
- In the line of fire (``line_of_fire_key``): a visible hostile breeder the projection
  reaches from the player (projectable within ``MAX_RANGE``) is shot when no more
  dangerous hostile acts: the two-or-more aim, else the caller's one-target shot at the
  nearest one.  The quest plans call it where they would otherwise wait or walk (Q25:
  quest25_battle ``_breeders_in_line_key``).
- More dangerous (``more_dangerous_acting``): a visible awake hostile that does not
  breed, whose largest blow or ranged damage (race knowledge) is above every breeder's in
  view or that summons, and that reaches the player now: beside it, a race that moves,
  or one that casts or summons within MONSTER_SPELL_MAX_RANGE.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from hengbot import attack_expectation, me_device_attacks
from hengbot.item_reservation import reserved_item_command
from hengbot.model import TVAL_ROD, TVAL_SCROLL, TVAL_STAFF, TVAL_WAND, Position, game_distance
from hengbot.policy_constants import DIRECTION_KEYS, MONSTER_SPELL_MAX_RANGE
from hengbot.projection_path import projection_path


REASON = "ranged:breeder-area"
MAX_RANGE = 18          # AngbandSystem::get_max_range outside the monster arena
AIM_STEPS = 99          # spells-launcher.cpp: dir.get_target_position(..., 99)
_CARRIED_KIND = {TVAL_WAND: "wand", TVAL_ROD: "rod", TVAL_STAFF: "staff"}
# scroll-read-executor.cpp: SV_SCROLL_DISPEL_UNDEAD = dispel_undead(80), a
# project_all_los of DISP_UNDEAD (spells-sight.cpp:139); level from
# BaseitemDefinitions.jsonc id 211.
SCROLLS = {42: me_device_attacks.Power(
    "scroll", 42, ("アンデッド退散", "Dispel Undead"), 40, "DISP_UNDEAD", "sight", lambda lev: 80)}


@dataclass(frozen=True)
class Means:
    """One usable attack: its power (shape, element, damage), success and key."""
    power: me_device_attacks.Power
    success: float
    send: Callable[[str], str | None]   # direction key ('' when unaimed) -> key
    send_target: Callable[[Position], str | None] | None = None   # burst grid -> key


def _blocker(snapshot):
    def blocks(pos: Position) -> bool:
        grid = snapshot.grids.get(pos)
        return grid is None or not grid.passable
    return blocks


def _projectable(a: Position, b: Position, blocks) -> bool:
    """target/projection-path-calculator.cpp projectable()."""
    path = projection_path(a, b, MAX_RANGE, blocks)
    return not path or path[-1] == b


def _ray(snapshot, offset, blocks, *, stop: bool) -> list[Position]:
    """The grids a direction-aimed projection crosses (PROJECT_STOP when ``stop``)."""
    origin = snapshot.player.position
    aim = Position(origin.y + offset[0] * AIM_STEPS, origin.x + offset[1] * AIM_STEPS)
    occupied = {monster.position for monster in snapshot.visible_monsters}
    cells = []
    for pos in projection_path(origin, aim, MAX_RANGE, blocks):
        if blocks(pos):
            break
        cells.append(pos)
        if stop and pos in occupied:
            break
    return cells


def _grid_ray(snapshot, grid, blocks) -> list[Position] | None:
    """The grids a projection aimed at ``grid`` crosses, else None when it
    cannot reach it (no PROJECT_STOP: it flies over monsters to the grid)."""
    cells = []
    for pos in projection_path(snapshot.player.position, grid, MAX_RANGE, blocks):
        if blocks(pos):
            break
        cells.append(pos)
    return cells if cells and cells[-1] == grid else None


def _ball_cells(centre, radius, blocks, cells):
    """{grid: r} of ``cells`` inside range-calc.cpp ball_shape."""
    return {pos: game_distance(centre, pos) for pos in cells
            if game_distance(centre, pos) <= radius and _projectable(centre, pos, blocks)}


def _dist_to_line(pos, a, b) -> int:
    """range-calc.cpp dist_to_line (C++ integer division)."""
    pd, nd = game_distance(a, pos), game_distance(a, b)
    if pd > nd:
        return game_distance(pos, b)
    normal_y, normal_x = b.x - a.x, a.y - b.y
    numerator = (a.y - pos.y) * normal_y + (a.x - pos.x) * normal_x
    return abs(numerator) // nd if nd > 0 else 0


def _breath_cells(source, path, radius, blocks, cells):
    """{grid: r} of ``cells`` inside range-calc.cpp breath_shape."""
    dist, impact = len(path), path[-1]
    brev = radius * radius // dist
    wanted, hit = set(cells), {}
    centre, path_n = source, 0
    for bdis in range(game_distance(source, impact) + radius + 1):
        brad = 0 if bdis == 0 else radius * (path_n + brev) // (dist + brev)
        if path_n < dist and bdis >= game_distance(path[path_n], source):
            centre = path[path_n]
            path_n += 1
        for pos in wanted - hit.keys():
            if (game_distance(source, pos) == bdis and game_distance(centre, pos) <= brad
                    and _projectable(centre, pos, blocks)):
                hit[pos] = _dist_to_line(pos, source, impact)
    return hit


def _hits(snapshot, power, aim, blocks) -> dict:
    """{grid: r} of the visible monsters' grids one use of ``power`` would reach.

    ``aim`` is a direction offset, or a target grid (a ball or breath)."""
    offset = aim
    cells = [monster.position for monster in snapshot.visible_monsters]
    origin = snapshot.player.position
    if power.shape == "sight":
        return {pos: 0 for pos in cells if _projectable(origin, pos, blocks)}
    if power.shape == "beam":
        ray = set(_ray(snapshot, offset, blocks, stop=False))
        return {pos: 0 for pos in cells if pos in ray}
    if isinstance(aim, Position):
        ray = _grid_ray(snapshot, aim, blocks) or []
    else:
        ray = _ray(snapshot, offset, blocks, stop=True)
    if power.shape == "bolt":
        return {ray[-1]: 0} if ray and ray[-1] in cells else {}
    radius = me_device_attacks.AREA_RADIUS[power.shape]
    if power.shape == "breath" and ray:
        return _breath_cells(origin, ray, radius, blocks, cells)
    return _ball_cells(ray[-1] if ray else origin, radius, blocks, cells)


def _damage(policy, snapshot, power, monster, distance) -> float:
    base = me_device_attacks.expected_damage(
        power, snapshot.player.level, me_device_attacks.race_flags(policy, monster))
    return min((base + distance) / (distance + 1), max(monster.hp, 0))


def _group_score(policy, snapshot, means, aim, blocks) -> float | None:
    """Expected group damage of ``means`` at ``aim`` (``_hits``); None when barred."""
    if means.power.shape == "bolt-or-beam":
        beam = means.power.beam_percent / 100
        parts = ((beam, replace(means.power, shape="beam", beam_percent=100)),
                 (1 - beam, replace(means.power, shape="bolt", beam_percent=0)))
    else:
        parts = ((1.0, means.power),)
    by_cell = {monster.position: monster for monster in snapshot.visible_monsters}
    total = 0.0
    for weight, power in parts:
        for pos, r in _hits(snapshot, power, aim, blocks).items():
            monster = by_cell[pos]
            if not monster.hostile:
                if snapshot.in_town and policy._town_friendly_unbeatable(snapshot, monster):
                    return None
                continue
            total += weight * _damage(policy, snapshot, power, monster, r)
    return means.success * total


def _use(policy, snapshot, kind, item, direction) -> str | None:
    key = reserved_item_command(policy, snapshot, kind, item, suffix=direction)
    if key is not None:
        policy.last_reason = f"{REASON}:{kind}"
    return key


def _carried(policy, snapshot):
    skill = snapshot.player.device_skill
    for item in snapshot.inventory:
        kind = _CARRIED_KIND.get(item.tval)
        if kind is not None:
            power = me_device_attacks.POWERS.get((kind, item.sval))
            charged = not item.charging if kind == "rod" else item.charges > 0
            if power is None or not item.known or not charged:
                continue
            success = (attack_expectation.rod_use_success if kind == "rod"
                       else attack_expectation.device_use_success)(skill, power.level)
        elif item.tval == TVAL_SCROLL and item.aware and item.sval in SCROLLS:
            if not snapshot.can_see_own_grid:
                continue  # cmd-read.cpp: no light, no reading
            kind, power, success = "read", SCROLLS[item.sval], 1.0
        else:
            continue
        yield Means(power, success,
                    lambda direction, kind=kind, item=item: _use(policy, snapshot, kind, item, direction))


def _means(policy, snapshot) -> list[Means]:
    player = snapshot.player
    if player.blind or player.confused or player.hallucinated:
        return []
    means = []
    if me_device_attacks.can_use_powers(snapshot):
        means += [Means(power, success,
                        lambda direction, power=power: me_device_attacks.device_key(policy, power, direction),
                        lambda grid, power=power: me_device_attacks.device_target_key(policy, power, grid))
                  for power, success in me_device_attacks.usable_powers(policy)]
    means += _carried(policy, snapshot)
    if me_device_attacks.sight_hits_bystander(snapshot):
        means = [each for each in means if each.power.shape != "sight"]
    return means


def _one_target_best(policy, snapshot, means, hostiles) -> float:
    """The best damage any one-target answer deals to one visible hostile."""
    shot = policy._estimated_ranged_damage_per_shot(snapshot)
    best = 0.0
    for monster in hostiles:
        cap = max(monster.hp, 0)
        flags = me_device_attacks.race_flags(policy, monster)
        for each in means:
            damage = me_device_attacks.expected_damage(each.power, snapshot.player.level, flags)
            best = max(best, each.success * min(damage, cap))
        if monster.distance <= 1:
            best = max(best, attack_expectation.melee(policy, snapshot, monster))
        else:
            best = max(best, min(shot, cap))
    return best


def _burst_grids(snapshot, radius, blocks):
    """Floor grids a targeted burst reaches with a visible hostile in its radius."""
    origin = snapshot.player.position
    grids = set()
    for monster in snapshot.visible_monsters:
        if not monster.hostile:
            continue
        centre = monster.position
        for y in range(centre.y - radius, centre.y + radius + 1):
            for x in range(centre.x - radius, centre.x + radius + 1):
                grid = Position(y, x)
                if (grid != origin and game_distance(centre, grid) <= radius
                        and not blocks(grid)):
                    grids.add(grid)
    return [grid for grid in sorted(grids) if _grid_ray(snapshot, grid, blocks)]


def _target_prompts(snapshot, grid) -> int:
    """'*', 'p', one cursor step per grid (diagonals included) and 't'."""
    origin = snapshot.player.position
    return 3 + max(abs(grid.y - origin.y), abs(grid.x - origin.x))


def _options(policy, snapshot, means):
    """(group score, prompts, means, key sender, aim) of every usable aim.

    Owner 2026-11-03 「群れの中心を狙う」: a ball or breath with a target
    sender is also scored on every burst grid (``_burst_grids``)."""
    blocks = _blocker(snapshot)
    for each in means:
        aims = ((None, ""),) if not each.power.aimed else DIRECTION_KEYS.items()
        for offset, direction in aims:
            score = _group_score(policy, snapshot, each, offset, blocks)
            if score:
                yield (score, int(each.power.aimed), each, lambda e=each, d=direction: e.send(d),
                       offset)
        if each.send_target is None or each.power.shape not in me_device_attacks.TARGETABLE_SHAPES:
            continue
        radius = me_device_attacks.AREA_RADIUS[each.power.shape]
        for grid in _burst_grids(snapshot, radius, blocks):
            score = _group_score(policy, snapshot, each, grid, blocks)
            if score:
                yield (score, _target_prompts(snapshot, grid), each,
                       lambda e=each, g=grid: e.send_target(g), grid)


def engaged(engaged_hostiles) -> bool:
    """Whether the hostiles a rung engages include a breeder."""
    return any(monster.hostile and monster.can_multiply for monster in engaged_hostiles)


def _hp_estimate(policy, monster) -> int:
    """The race's dice average, or the health band's upper bound when lower."""
    knowledge = attack_expectation.race_knowledge(policy, monster.race_id)
    average = getattr(knowledge, "average_hp", 0) if knowledge is not None else 0
    return max(1, min(monster.hp, average) if average > 0 else monster.hp)


def _visible_breeders(snapshot) -> list:
    return [monster for monster in snapshot.visible_monsters
            if monster.hostile and monster.can_multiply and monster.perception != "detected"]


def _tally(policy, snapshot, means, aim, blocks) -> tuple[float, float]:
    """(expected kills, breeders caught) of ``means`` at ``aim`` (``_hits``)."""
    if means.power.shape == "bolt-or-beam":
        beam = means.power.beam_percent / 100
        parts = ((beam, replace(means.power, shape="beam", beam_percent=100)),
                 (1 - beam, replace(means.power, shape="bolt", beam_percent=0)))
    else:
        parts = ((1.0, means.power),)
    breeders = {monster.position: monster for monster in _visible_breeders(snapshot)}
    kills = caught = 0.0
    for weight, power in parts:
        for pos, r in _hits(snapshot, power, aim, blocks).items():
            monster = breeders.get(pos)
            if monster is None:
                continue
            caught += weight
            base = me_device_attacks.expected_damage(
                power, snapshot.player.level, me_device_attacks.race_flags(policy, monster))
            if (base + r) / (r + 1) >= _hp_estimate(policy, monster):
                kills += weight
    return means.success * kills, caught


def _danger(monster) -> int:
    return max(monster.max_melee_damage, monster.max_ranged_damage)


def more_dangerous_acting(policy, snapshot) -> bool:
    """A visible awake non-breeder more dangerous than the breeders in view reaches the player."""
    breeders = _visible_breeders(snapshot)
    floor = max((_danger(monster) for monster in breeders), default=0)
    for monster in snapshot.visible_monsters:
        if not monster.hostile or monster.can_multiply or monster.asleep:
            continue
        if _danger(monster) <= floor and not monster.can_summon:
            continue
        knowledge = attack_expectation.race_knowledge(policy, monster.race_id)
        moves = knowledge is None or "NEVER_MOVE" not in knowledge.flags
        reaches_from_afar = ((monster.max_ranged_damage > 0 or monster.can_summon)
                             and monster.distance <= MONSTER_SPELL_MAX_RANGE)
        if monster.distance <= 1 or moves or reaches_from_afar:
            return True
    return False


def in_line_of_fire(policy, snapshot) -> list:
    """Visible hostile breeders a projection from the player reaches, nearest first."""
    blocks = _blocker(snapshot)
    origin = snapshot.player.position
    return sorted((monster for monster in _visible_breeders(snapshot)
                   if game_distance(origin, monster.position) <= MAX_RANGE
                   and _projectable(origin, monster.position, blocks)),
                  key=lambda monster: (monster.distance, monster.index))


def _mass_key(policy, snapshot, means) -> str | None:
    """The aim with the most expected kills among those catching two or more breeders whose
    group damage beats every one-target answer (``_one_target_best``).

    Owner 2026-11-09, verbatim: 「範囲攻撃を使うかどうかの判断基準は既に提示している。群れに対して
    与える合計ダメージが単体攻撃より大きければ使う。」 (the 11-01 rule): catching two or more never
    puts an area attack before a one-target answer that deals more.  n1-c life-181 (Q2,
    2026-11-09 12:52) fired its Stinking Cloud about twenty times at blue icky things that are
    IM_POIS (「かなり耐性がある！」) instead of 44-damage bolts, until it had no charge left."""
    blocks = _blocker(snapshot)
    hostiles = [monster for monster in snapshot.visible_monsters if monster.hostile]
    baseline = _one_target_best(policy, snapshot, means, hostiles)
    ranked = []
    for score, prompts, each, send, aim in _options(policy, snapshot, means):
        if score <= baseline:
            continue
        kills, caught = _tally(policy, snapshot, each, aim, blocks)
        if caught >= 2:
            ranked.append((-kills, -score, prompts, each.power.kind != "rod", each.power.level, send))
    for *_order, send in sorted(ranked, key=lambda row: tuple(row[:5])):
        if (sent := send()) is not None:
            return sent
    return None


def line_of_fire_key(policy, snapshot, single: Callable[[object], str | None]) -> str | None:
    """Owner 2026-11-08 「射線にいれば範囲で撃つ」: breeders in the line of fire are shot when no
    more dangerous hostile acts: the two-or-more aim first, else ``single`` at the nearest
    one that it answers.  None leaves the caller's order."""
    player = snapshot.player
    if player.blind or player.confused or player.hallucinated:
        return None
    targets = in_line_of_fire(policy, snapshot)
    if not targets or more_dangerous_acting(policy, snapshot):
        return None
    means = _means(policy, snapshot)
    if means and (mass := _mass_key(policy, snapshot, means)) is not None:
        return mass
    for target in targets:
        if (shot := single(target)) is not None:
            return shot
    return None


def key(policy, snapshot, engaged_hostiles) -> str | None:
    """Two or more breeders caught (``_mass_key``) when no more dangerous hostile acts; else
    the area attack with the largest group damage when it beats every one-target answer
    and a breeder is engaged; else None (the caller's order)."""
    if not engaged(engaged_hostiles):
        return None
    means = _means(policy, snapshot)
    if not means:
        return None
    if (not more_dangerous_acting(policy, snapshot)
            and (mass := _mass_key(policy, snapshot, means)) is not None):
        return mass
    hostiles = [monster for monster in snapshot.visible_monsters if monster.hostile]
    baseline = _one_target_best(policy, snapshot, means, hostiles)
    # Ties: fewer prompts (a direction before a cursor walk), a rod, the lower level.
    ranked = sorted(_options(policy, snapshot, means),
                    key=lambda option: (-option[0], option[1], option[2].power.kind != "rod",
                                        option[2].power.level))
    for score, _prompts, _each, send, _aim in ranked:
        if score <= baseline:
            return None
        if (sent := send()) is not None:
            return sent
    return None
