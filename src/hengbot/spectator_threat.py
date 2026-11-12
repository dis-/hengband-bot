"""The threat tiers of the monsters the spectator page lists (viewer only).

Owner 2026-11-08: 「脅威度の判定が入ったなら、観戦UIの見えているモンスター一覧にその判断を追記して。
脅威度順に色分けと、脅威度でのソートも入れて」.

What the page gets, per board (``board_judgement``):

- ``engagement``: the board's engagement as the decision row's telemetry judged it
  (``threat_tiers.facts``, the same assessment, reused when the row already holds it).
- ``monsters``: for each listed hostile, that monster judged alone and from contact, the way the
  tiers judge one target (``threat_tiers.tiered(policy, snapshot, [monster], contact=True)``,
  the memo key ``sensed_t1_leave_key`` uses): a far monster would otherwise read T3 only because
  it has not come yet.  Its tier, its 即死 alone and its flags (``MonsterAssessment``).  Only
  the ``SPECTATE_THREAT_MONSTERS`` nearest are judged; the rest are marked omitted.  A tier past
  the projection's cost cap stays ``skipped: "cost"`` (shown as unknown), never computed further.

Nothing here is read by a decision: the caller runs it as an observer (cli
``_spectator_threat``) and the spectator writer only copies the result into its file.
"""

from __future__ import annotations

from hengbot import threat_tiers

# The nearest 8 hostiles of a board are judged, the others are omitted.  Eight is the number of
# cells beside the player: every monster that can be in melee contact is always judged.  The
# measured cost of one judgement is 0.5-2 ms on ordinary boards and at most about 16 ms on deep
# ones (tests/test_spectator_threat_tiers.py, LUNA-REPORT-spectate-threat-tiers-1108.txt), so 8
# keeps a board's added time near the engagement assessment the decision row already pays.
SPECTATE_THREAT_MONSTERS = 8

# The page's order and colours, most dangerous first (the page keeps the same table).
DEATH, UNKNOWN, OMITTED = "death", "unknown", "omitted"
TIER_RANK = {DEATH: 0, threat_tiers.T1: 1, threat_tiers.T2: 2, threat_tiers.T3: 3,
             UNKNOWN: 4, OMITTED: 5}
NO_JUDGEMENT_RANK = len(TIER_RANK)


# The decision row's ``threat_tiers`` facts of the last captured board, as (board, facts): the
# spectator writes after the row on most boards and reuses the engagement instead of judging it
# again.  Keyed on the board object, so a later board never reads an earlier board's facts.
_noted_engagement: tuple | None = None


def note_engagement(snapshot, facts) -> None:
    """Keep the decision row's engagement facts of ``snapshot`` for the spectator."""
    global _noted_engagement
    _noted_engagement = (snapshot, facts)


def noted_engagement(snapshot):
    """The engagement facts noted for this very board, or None."""
    noted = _noted_engagement
    return noted[1] if noted is not None and noted[0] is snapshot else None


def monster_judgement(assessment, index) -> dict:
    """The viewer row of one monster judged alone (``assessment`` holds it alone)."""
    row = assessment.per_monster.get(index)
    judgement = {
        "tier": assessment.tier,
        "instant_death": assessment.instant_death,
        "instant_death_reasons": list(assessment.instant_death_reasons),
        "skipped": assessment.skipped,
        "t2_withheld": list(assessment.t2_withheld),
    }
    if row is not None:
        judgement.update({
            "irreversible": list(row.irreversible),
            "worsens_with_time": list(row.worsens_with_time),
            "need_not_fight": row.need_not_fight,
            "selected": list(row.selected),
            "reward": list(row.reward),
        })
    return judgement


def engagement_judgement(facts: dict) -> dict:
    """The board's engagement line from the decision row's ``threat_tiers`` facts."""
    return {
        "tier": facts.get("tier"),
        "instant_death": bool(facts.get("instant_death")),
        "skipped": facts.get("skipped"),
        "t2_withheld": list(facts.get("t2_withheld", ())),
        "hostiles": len(facts.get("monsters", ())),
    }


def board_judgement(policy, snapshot, engagement_facts=None) -> dict:
    """``{"engagement": ..., "monsters": {index: judgement}}``; {} outside the design.

    ``engagement_facts``: the decision row's ``threat_tiers`` facts of this board, when the row
    was captured before the spectator wrote; else they are computed here once."""
    if threat_tiers.outside_design(snapshot):
        return {}
    if engagement_facts is None:
        engagement_facts = threat_tiers.facts(policy, snapshot)
    listed = {}
    for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters):
        if monster.hostile:
            listed.setdefault(monster.index, monster)
    nearest = sorted(listed.values(), key=lambda monster: monster.distance)
    monsters = {}
    for rank, monster in enumerate(nearest):
        if rank >= SPECTATE_THREAT_MONSTERS:
            monsters[monster.index] = {"omitted": "bound"}
            continue
        alone = threat_tiers.tiered(policy, snapshot, [monster], contact=True)
        monsters[monster.index] = monster_judgement(alone, monster.index)
    return {"engagement": engagement_judgement(engagement_facts), "monsters": monsters}


def tier_rank(judgement) -> int:
    """The row's place in the page's order: 即死, T1, T2, T3, unknown, omitted, none."""
    if not judgement:
        return NO_JUDGEMENT_RANK
    if judgement.get("omitted"):
        return TIER_RANK[OMITTED]
    if judgement.get("instant_death"):
        return TIER_RANK[DEATH]
    return TIER_RANK.get(judgement.get("tier"), TIER_RANK[UNKNOWN])
