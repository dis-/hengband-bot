"""The 99F/100F finale's own lines where the ordinary ones took over (n1-b life-416, 2026-11-23).

Two places left the finale to the ordinary play, and each broke an owner rule:

**The relay floor.**  Owner 2026-11-21: a lap of 99F/100F that finds nothing regenerates the floor
(the stairs up, then straight down again: policy ``_start_kill_quest_regeneration``, the
regeneration's ``ascend`` then ``descend``), and 「巻物が尽きたら取り込んだテレポートの杖、杖も尽きたら
帰還して補給」.  The floor the ascent reaches (98F for Oberon's 99F, 99F for the Serpent's 100F) is
no 99F/100F floor, so neither the battle (angband_finale_battle ``applies``) nor its recall line
(finale_prep ``recall_closed``) owned it, and the ordinary return check read the supply ledger,
which counts the Teleportation scrolls only: n1-b life-416 (21:09:12, live seq644) arrived on 98F
with no scroll but the absorbed Staff of Teleportation charged and recalled at once under
``teleport-low``.  On the relay floor (``relay_floor``) the return check now asks the finale's line
instead of the supply ledger (``return_due``: no scroll and no staff charge, or the Restore Mana
overspent; policy_town ``_should_start_town_return``).

**The town while Angband is refused for its depth.**  Owner 2026-11-21 (LOCKED)
「帰還の深さが96F以上なら遠征以外で鉄獄へ帰還しない」 and owner 2026-11-19 「鉄獄50F以降は浅い階層への
フォールバックをやめる。行き先を変えるのはダンジョンの主討伐のみとする。」 together leave one way out of
town for a character whose Angband recall depth is 96F or deeper: the finale's expedition.  The
town fell back instead (policy_town ``town:unsafe-recall-fallback``): angband_hold ``held`` was false
while the recall was refused, so the 50F+ rule was skipped and the deepest entered landing, the
Castle 64F, was taken (n1-b life-416 21:10:03, 21:13:51, 21:16:23).  While the refusal holds for a
character preparing the finale (``applies``), the town's departure is this module's
(``town_key``), never a fallback:

* the preparation phase running (finale_prep): wait for it; its steps and their limits are its own,
  and once it lifts the cap the refusal ends and the ordinary departure reads the recall;
* the Teleportation scrolls short (the only supply the town's shops sell,
  store/articles-on-sale.cpp): the other towns' circuit and its night at the inn
  (finale_teleport_tour, owner 2026-11-20 「4つの街を回ってテレポートの巻物を買い足す」
  「一周する毎に宿屋で一泊する」);
* the Restore Mana the only other row short (n1-b's 21:13 board owned 79 of the 84 and every
  other supply), or any supply only the Black Market sells (the Healing, the *Healing*, the
  Resistance: owner 2026-11-24 「闇市を巡回して買い足す — 魔力復活の薬と同じく」, n1-c life-221
  03:01:20 spun on ``finale-not-in-town:healing`` with 2 of the 30; angband_finale
  ``BLACK_MARKET_SUPPLIES``): once the Teleportation is owned, the four towns' Black Markets lap after lap
  with a night at the inn between laps until the carry is owned (finale_bm_tour, owner
  2026-11-23 「4つの町の闇市を巡回して買い足し、目標に届くまで99Fへは行かない。闇市に無ければ
  巡回をくり返す。」); short of gold, Home's cash wares are sold and a fundraising run brings
  it (owner 2026-11-18 「必要なものは買う」); a circuit that closed (an inn, a leg, no town) is
  the driver's final stop ``town:blocked:finale-bm-tour-closed:<why>``;
* anything else short (a supply only the dungeon gives: the absorbed Stone to Mud), or the phase
  stopped (an equipment condition the owned gear does not meet stops it at its check step): a
  named stop (``town:blocked:...``) for the owner, no destination picked; the not-in-town one is a
  final stop of the driver (policy_constants FINALE_NOT_IN_TOWN_STOP_PREFIX), never a wait.

**The Restore Mana whatever the recall depth.**  The Black Markets' circuit is the owner's line
for the Restore Mana short alone, not for the 96F+ refusal: a Scroll of Reset Recall (reset_recall)
sets Angband back to 95F and ``applies`` no longer holds (n1-b life-416 2026-11-24 02:21:00, after
Oberon; five recalls to 95F followed at 75-79 of the 84).  So the departure toward Angband asks
``black_market_due`` first (policy_town ``_town_special_key``, before the recall is read): the
preparation phase idle and only supplies the Black Market sells short, the circuit
(``black_market_key``); any other row short keeps the owner's 2026-11-19 95F exploration.
"""
from __future__ import annotations

from hengbot.model import DUNGEON_ANGBAND
from hengbot.policy_constants import WAIT_KEY

RETURN_TRIGGER = "angband-finale:relay"
# The supply rows the town's shops can fill (angband_finale ``SUPPLY_NAMES``).
TOWN_SUPPLIES = frozenset({"teleport"})
# The rows the Black Markets' circuit fills (finale_bm_tour, owner 2026-11-23 and 2026-11-24):
# angband_finale BLACK_MARKET_SUPPLIES, the supplies no town store sells.
BLACK_MARKET_SUPPLIES = frozenset({"healing", "star_healing", "resistance", "restore_mana"})
WAIT_REASON = "town:finale-hold:phase"
STOPPED = "finale-prep-stopped"
NOT_IN_TOWN = "finale-not-in-town"  # policy_constants FINALE_NOT_IN_TOWN_STOP_PREFIX's
BM_CLOSED = "finale-bm-tour-closed"  # policy_constants FINALE_BM_CLOSED_STOP_PREFIX's
SHORT = "finale-supplies-short"
NOT_ENTERED = "finale-prep-not-entered"


# -- the relay floor ---------------------------------------------------------------------

def relay_floor(policy, snapshot) -> bool:
    """The floor the finale's regeneration climbed to and will go down from: one floor above the
    99F/100F floor whose quest the regeneration runs, on the expedition (the cap lifted)."""
    from hengbot import angband_finale  # import cycle
    if (snapshot.in_town or not angband_finale.magic_eater(snapshot)
            or not angband_finale.lifted(policy)):
        return False
    dungeon_id, level, quest_id = snapshot.floor_key
    if dungeon_id != DUNGEON_ANGBAND or quest_id:
        return False
    if getattr(policy, "_quest_regen_phase", None) != "descend":
        return False
    regen = getattr(policy, "_quest_regen_id", None)
    return any(quest == regen and level == depth - 1
               for depth, (quest, _race) in angband_finale.FINALE.items())


def return_due(policy, snapshot) -> bool:
    """The finale's own reasons to recall from the relay floor (angband_finale_battle
    ``recall_permitted`` without the floor's quest): no Teleportation scroll and no charge of the
    absorbed staff, or the Restore Mana overspent.  Hunger with nothing to eat is the ordinary
    check's own (``food-hungry``), before this one."""
    from hengbot import angband_finale, angband_finale_battle  # import cycle
    return (angband_finale_battle.teleports_out(policy, snapshot)
            or angband_finale.restore_mana_overspent(policy, snapshot))


# -- the town ----------------------------------------------------------------------------

def applies(policy, snapshot) -> bool:
    """In town, preparing the finale, the target Angband and its recall refused for its depth
    outside the expedition (angband_cap ``deep_recall_refused``)."""
    from hengbot import angband_cap, angband_finale  # import cycle
    return (snapshot.in_town and angband_finale.preparing(snapshot)
            and policy._target_dungeon_id == DUNGEON_ANGBAND
            and angband_cap.deep_recall_refused(snapshot, DUNGEON_ANGBAND, policy))


def _wait(policy, reason: str, work_id: str) -> str:
    policy.last_reason = reason
    policy._offer_execution(
        WAIT_KEY, producer="departure", work_id=work_id,
        next_step="finale.prepare", expected_effect="finale-preparation-progress")
    return WAIT_KEY


def _stop(policy, snapshot, reason: str) -> str | None:
    policy._town_blocked_reason = reason
    return policy._town_blocked_key(snapshot)


def short_rows(policy) -> list:
    """The names of the finale's supplies not owned (pack and Home: the readiness angband_finale
    measured on this town board).  The equipment conditions are the phase's check step's (its
    search over the owned gear, Home included; a set short of them stops the phase by name): the
    worn gear of an ordinary visit is no measure of them."""
    from hengbot import angband_finale  # import cycle
    rows = angband_finale.memory(policy).report or {}
    return [name for name, row in (rows.get("owned") or {}).items() if not row["ready"]]


def _black_market_key(policy, snapshot, short: list) -> str | None:
    """The Black Markets' circuit (finale_bm_tour), or the town's named stop when it closed."""
    from hengbot import finale_bm_tour  # import cycle
    circuit = finale_bm_tour.town_key(policy, snapshot)
    if circuit is not None:
        return circuit
    if finale_bm_tour.closed(policy):
        # A final stop of the driver (policy_constants FINALE_BM_CLOSED_STOP_PREFIX).
        return _stop(policy, snapshot, f"{BM_CLOSED}:{finale_bm_tour.why(policy)}")
    return _stop(policy, snapshot,
                 f"{NOT_IN_TOWN}:{','.join(short)}:{finale_bm_tour.why(policy)}")


def black_market_due(policy, snapshot) -> bool:
    """The departure toward Angband while only supplies the Black Market sells are short (the
    Restore Mana, owner 2026-11-23; the Healing and the others, 2026-11-24), whatever Angband's
    recall depth (owner 2026-11-23 「目標に届くまで99Fへは行かない。闇市に無ければ
    巡回をくり返す。」).  ``applies`` covers a recall depth of 96F or deeper only; a Scroll of Reset
    Recall (reset_recall, owner 2026-11-21) sets it back to 95F, and the ordinary departure then
    went to the 95F exploration with the carry short: n1-b life-416 2026-11-24 02:21:00 read it
    after Oberon (99F), and from 02:21:46 to 02:45:18 recalled to 95F five times at 75-79 of the
    84 without a lap of the circuit.  Any other row short, or the preparation phase not idle,
    leaves the departure to the owner's 2026-11-19 rule (the 95F exploration until the
    preparation is complete) and the phase's own steps."""
    from hengbot import angband_finale, finale_prep  # import cycle
    if (not snapshot.in_town or snapshot.player.recalling
            or not angband_finale.preparing(snapshot)
            or policy._target_dungeon_id != DUNGEON_ANGBAND
            or finale_prep.phase(policy).step != finale_prep.IDLE):
        return False
    short = short_rows(policy)
    return bool(short) and frozenset(short) <= BLACK_MARKET_SUPPLIES


def black_market_key(policy, snapshot) -> str | None:
    """The departure's key while ``black_market_due``: the circuit, else a named stop."""
    return _black_market_key(policy, snapshot, short_rows(policy))


def town_key(policy, snapshot) -> str | None:
    """The town's departure while ``applies``: the preparation, the circuit, or a named stop."""
    from hengbot import angband_finale, finale_prep, finale_teleport_tour  # import cycle
    held = finale_prep.phase(policy)
    if held.step == finale_prep.STOPPED:
        return _stop(policy, snapshot, f"{STOPPED}:{held.stopped}")
    if held.step in finale_prep.STEPS:
        # Bounded by the step's own limit (finale_prep.STEP_LIMIT): past it the phase stops by
        # name and the branch above stops the town (reasons.STATIONARY_ROWS).
        return _wait(policy, WAIT_REASON, f"finale-hold:{held.step}")
    short = short_rows(policy)
    outside = [name for name in short if name not in TOWN_SUPPLIES]
    if any(name not in BLACK_MARKET_SUPPLIES for name in outside):
        return _stop(policy, snapshot, f"{NOT_IN_TOWN}:{','.join(outside)}")
    if short and all(name in BLACK_MARKET_SUPPLIES for name in short):
        # Owner 2026-11-23 「闇市を回って買い足す」 and 2026-11-24 「闇市を巡回して買い足す — 魔力復活の
        # 薬と同じく」: the Teleportation owned, the Black Markets.
        return _black_market_key(policy, snapshot, short)
    if not short:
        # Everything owned and the phase idle: it did not enter (a census unknown, a swap or a
        # recall under way) though the town has nothing left to do.
        return _stop(policy, snapshot, NOT_ENTERED)
    night = finale_teleport_tour.night_key(policy, snapshot)
    if night is not None:
        return night
    if finale_teleport_tour.due(policy, snapshot) and finale_teleport_tour.start(policy, snapshot):
        travel = policy._town_producer_entry(
            "_cross_town_shopping_key", lambda: policy._cross_town_shopping_key(snapshot),
            family="cross-town")
        if travel is not None:
            return travel
        return _stop(policy, snapshot, f"{SHORT}:{','.join(short)}:no-leg")
    night = finale_teleport_tour.night_key(policy, snapshot)
    if night is not None:
        return night
    funds = getattr(policy, "_cross_town_shopping_funds", None) or {}
    why = funds.get("why") if angband_finale.memory(policy).teleport_tour_done else "not-due"
    return _stop(policy, snapshot,
                 f"{SHORT}:{','.join(short)}:{why}:{finale_teleport_tour.shortage(policy, snapshot)}")
