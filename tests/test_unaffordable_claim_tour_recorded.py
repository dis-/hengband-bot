"""Recorded pins: optional claims touring suppliers observed with nothing wanted.

2026-09-22 16:02:57-16:16:04 (one bot process, 4272 decisions, protocol 3).
Back in town after the 44F dive, with every required supply satisfied, the
town-errand owner bought 21 crossbow bolts (Weapon Smiths) and one Potion of
Healing (Black Market, 4,142 gold).  Two optional claims then outlived their
suppliers' answers: ``launcher-enchant`` (Alchemist; the crossbow is (+10,+9)
so only *Enchant To-Dam* is wanted, and this visit's Alchemist page does not
stock it) and ``black-market`` (re-armed by the Healing purchase confirmation;
the page observed this visit offers nothing affordable at 3,729 gold).  Each
store's rebuild re-armed the other; the owner toured Alchemist -> Black Market
and retired (town:blocked:owner-retired) without trying to depart.

Substrate: every recorded decision of the process lifetime, replayed through
the public response path on one policy (tests/extract_unaffordable_claim_tour_
fixture.py).  The replay also runs the live driver's per-decision telemetry
capture, because the live process ran it and its equipment evaluation is part
of the state the decisions depend on.  The recorded process ran the capture
BEFORE it was made a pure observer (2026-09-23, pure-decision-telemetry), so
the replay reproduces that driver with the unscoped evaluation the process
actually performed (_recorded_process_capture below; the recording is
otherwise not reproducible from list index 2643, where the capture's cached
equipment result changed the live key).  Walls, each on a collaborator that
is not under test:
- the recorded periodic save/dump decisions receive the CLI timer request
  that produced them;
- Home history/disposal files and the calibration file live in a temporary
  directory (the calibration file is the one this process itself rewrote at
  16:11:02; the file it loaded at start was not retained);
- experience-potion (user 2026-09-22): the recorded process carried a
  Potion of Experience while its experience was drained.  The new owner
  drinks it at list index 2787 (recorded seek-loot) and, in the drained town
  visits, first looks at the unobserved Temple shelf.  The recorded rows are
  the pre-decision lifetime, so the replay walls the policy's drain view to
  unknown throughout (the unchanged protocol-2 behaviour); the potion's own
  pins are in test_experience_potion.

The current speed-adjusted optimizer first changes the action at list index 2.
The live-key fidelity check stops there. Ownership, supply, and claim-row tests
continue on the recorded later boards as counterfactual new-code measurements;
they pin the resulting equipment-transaction path and its S3 violations.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
from hengbot.policy import staged_prompt_chain_matches
import copy
import gzip
import hashlib
import json
import shutil
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.cli import (
    _capture_decision_facts_unchecked,
    _consume_response_sequence,
)
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.home_disposal import HomeDisposalState
from hengbot.model import STORE_ALCHEMIST
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import TownNeed
from hengbot.quest_knowledge import find_quest_definitions, load_quest_knowledge
from hengbot.quest_strategies import load_quest_strategies
from hengbot.terrain_knowledge import load_damaging_terrain_ids
from hengbot.town_maps import find_town_map, parse_town_map
from hengbot.wilderness_map import find_wilderness_definition, load_wilderness_map


GAME_ROOT = Path("C:/hengband")
EDIT = GAME_ROOT / "lib" / "edit"
FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "unaffordable-claim-tour-20260922.jsonl.gz"
CALIBRATION = FIXTURES / "unaffordable-claim-tour-20260922.character-calibration.json"
FIXTURE_SHA256 = "ee4c27fa348569fe8274767cbfc9c1ce76a4f54cf8a102768216cb42995c024d"
BOUNDARIES_SHA256 = "59d574ab2830846cd7d324907ed397ff2ef97ca5660b7d8334298d08960d1b47"
CALIBRATION_SHA256 = "94e45131a9f886e13ad4f4fcf01ba127384ccea9e8dfbc0b8fea32fff023cfd8"
# List index 2701 (decision 2697): a travel interruption the live executor
# reported ('store:entry-interrupted-replan'); the replay re-converges at 2702.
KNOWN_HARNESS_DIVERGENCES = {2701}
# The 2026-09-23 loot/choke alternation fix.  The recorded run abandoned every
# anticipatory choke the decision before it had just prepared, bouncing with
# explore/search one cell away (list indices 1848-2014 at the (15, 16) choke of
# floor (1, 42, 0), where the recording escaped only by a livelock recall, and
# 3324-3325 at a later one).  A started retreat now keeps the decision to the
# covered cell it chose and, on reaching it, holds under the unchanged 50-turn
# detected-threat bound.
CHOKE_ALTERNATION_FIXED = {
    1848: ("5", "summoner:hold-choke"),
    1997: ("5", "summoner:hold-choke"),
    1999: ("5", "summoner:hold-choke"),
    2001: ("5", "summoner:hold-choke"),
    2003: ("5", "summoner:hold-choke"),
    2011: ("s", "search"),
    2013: ("5", "summoner:hold-choke"),
    2014: ("s", "search"),
    3324: ("4", "detected:prepare-choke"),
    3325: ("5", "summoner:hold-choke"),
}
# The 2026-09-26 stale equipment-mutation gate fix (departure-unsatisfiable-
# weight).  The recorded run's executor stayed POSTED after the board of list
# index 2651 showed the re-equip of 2650 ('wq)') worn, because it observed
# only when the next wield/takeoff was requested.  On that board the
# space-deposit gate read the stale POSTED, so the decision entry preempted
# the transaction with a Home knowledge scan; the decision entry now
# observes the executor first, the space-deposit gate is open and the
# transaction continues ('te') one decision earlier.  2652 awaits the
# takeoff's confirmation, and from 2653 the replay decides as live.
STALE_MUTATION_GATE_FIXED = {
    2651: ("te", "equipment-transaction:takeoff"),
    2652: ("5", "equipment-transaction:await-confirmation"),
}
# List indices (decision_sequence + 4 after the four shared probe sequences).
AMMO_BUY = 4260        # decision 4256: 'pj21' 21 crossbow bolts, 7934 -> 7871
HEALING_BUY = 4266     # decision 4262: 'pl' Potion of Healing, 7871 -> 3729
AFTER_PURCHASES = 4267  # decision 4263: recorded travel back to the Alchemist
OWNER_RETIRED = 4271   # decision 4267: recorded town:blocked:owner-retired
# S2a.1 closure pins (list indices 0-4266): the Observe completions by the
# confirmation site that recorded them, and how selected owners' Reach /
# Observe claims ended (ownership_metrics.gate_numbers, item (c)).
S2A1_OBSERVE_COMPLETE_LABELS = {
    # R3 speed-survival: the index-2 shield takeoff is never confirmed by the
    # recorded travel board. Repeated equipment ownership preempts the later
    # recorded purchases and most of the old Observe completions.
    "home-knowledge-current": 1,
    "floor-changed": 6,
    "staged-tail-posted": 19,
    "home-deposit-observed": 3,
    "equipment-transaction-complete": 2,
    "entered-store": 1,
}
# The unconfirmed equipment work changes 33 next-row Reach completions from
# the prior 1,347-row counterfactual. Far-target reasons remain checked below.
S2A1_NEXT_ROW_COMPLETE = 1314
S2A1_FAR_TARGET_REASONS = frozenset({
    "return:seek-upstairs", "livelock:seek-upstairs",
    "combat:disengage-seek-upstairs", "fundraise:seek-upstairs",
    "mana-food:seek-device", "survival:seek-exit", "town:seek-shelter",
    "stuck:seek-stairs", "fixedquest:seek-exit", "fixedquest:reward-approach",
    "quest-strategy:approach-final-target", "town:rumor",
    "esp-threat:hunt-strong", "emergency:seek-upstairs", "chest:approach",
    "paralyzer-guard:approach-range", "seek-secret-wall",
    "return:seek-secret-wall", "bounty:approach",
    "town:morivant-full-identify:library", "fundraise:sweep-explore",
})
# Measured endings for the named owner/goal classes on the new-code replay.
# Old purchase confirmations and equipment completions are absent after the
# index-2 transaction diverges from the recorded key.
S2A1_ENDINGS = {
    "shop-buy/Observe": {"complete": 0, "open-at-end": 0},
    "home-visit/Observe": {"complete": 0, "release": 0,
                           "expired": 0, "abandoned": 0},
    "equipment-txn/Observe": {"complete": 0, "abandoned": 53},
    # One-step walks stay separate. The counterfactual reaches 67 ordinary
    # floor-loot goals and two one-step goals.
    "floor-loot/Reach": {"complete": 67, "abandoned": 0},
    "floor-loot/Reach:one-step": {"complete": 2},
    "positioning/Reach": {"complete": 10, "release": 1},
    "positioning/Reach:one-step": {"complete": 5},
    "departure/Reach": {"complete": 2},
    "departure/Reach:one-step": {"complete": 0},
}

# Exact new-code S3 measurement on the old captured boards. The first shield
# takeoff at index 2 is not confirmed by the following travel board, so an
# equipment transaction repeatedly owns and releases the counterfactual path.
# Grouping by owner pair keeps every sequence pinned without hiding 60 rows in
# a digest. Every S3 violation is an owner-change; the test asserts that too.
S3_OWNER_CHANGE_SEQUENCES = {
    ("equipment-txn", "combat"): [2700],
    ("equipment-txn", "departure"): [21, 2056, 2713, 3078],
    ("equipment-txn", "idle"): [5, 2654, 2681, 3033, 3038],
    ("equipment-txn", "shop-buy"): [
        3, 9, 14, 17, 19, 2043, 2048, 2054, 2670, 2672, 2674,
        2684, 2687, 2691, 2694, 2706, 2711, 3054, 3058, 3062,
        3064, 3066, 3068, 3072, 3075, 4229, 4233, 4239, 4241,
        4254, 4256, 4258, 4260, 4262,
    ],
    ("equipment-txn", "store-router"): [2645, 2647, 3043, 3045, 3047, 4252],
    ("equipment-txn", "town-plan"): [2696, 3056, 4250],
    ("home-scan", "calibration"): [2998, 3020],
    ("shop-sell", "equipment-txn"): [4248],
    ("store-router", "equipment-txn"): [2646, 3044, 3046, 4253],
}


def _live_like_policy(directory: Path) -> tuple[HengbotPolicy, dict]:
    monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
    town_maps = {}
    for town_index in range(1, 6):
        path = find_town_map(town_index, GAME_ROOT)
        if path is not None:
            town_maps[town_index - 1] = parse_town_map(path)
    policy = HengbotPolicy(
        town_map=town_maps.get(0),
        town_maps=town_maps,
        wilderness_map=load_wilderness_map(find_wilderness_definition(GAME_ROOT)),
        dungeon_knowledge=load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc"),
        monrace_knowledge=monrace,
        damaging_terrain_ids=load_damaging_terrain_ids(EDIT / "TerrainDefinitions.jsonc"),
        quest_knowledge=load_quest_knowledge(
            find_quest_definitions(GAME_ROOT / "bot-client" / "state.jsonl")
        ),
        quest_strategies=load_quest_strategies(
            Path(__file__).resolve().parents[1] / "strategy" / "quests"
        ),
        home_disposal_state=HomeDisposalState(
            directory / "home-withdraw-history.jsonc",
            directory / "home-disposal-decisions.jsonc",
            directory / "home-disposal-queue.json",
            directory / "events.jsonl",
        ),
        baseitem_costs=load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc"),
    )
    calibration = directory / "character-calibration.json"
    shutil.copyfile(CALIBRATION, calibration)
    policy._character_calibration_path = calibration
    return policy, monrace


def _drain_unknown(_snapshot) -> bool:
    """The protocol-2 view of the experience drain (see the module wall)."""
    return False


def _recorded_process_capture(policy: HengbotPolicy, snapshot) -> None:
    """The per-decision telemetry capture as the recorded process ran it.

    WALL: the live driver evaluated the decision-row facts directly on its
    policy, so its evaluators' memoization (the equipment optimization
    preparation above all) entered the next decisions.  cli now scopes the
    capture as a pure observer; this replay is of the earlier driver.
    """
    _capture_decision_facts_unchecked(policy.with_known_skill_exp(snapshot), policy)


def _claim_row(policy: HengbotPolicy, snapshot, key, index: int) -> dict:
    """The claim ledger row of one replayed decision (S2a.1 closure pins)."""
    claim = dict(policy.decision_claim or {})
    claim.update(
        kind="claim",
        session="tour",
        reason=policy.last_reason,
        key=None if key is None else str(key),
        position={"y": snapshot.player.position.y, "x": snapshot.player.position.x},
        index=index,
    )
    return claim


def _independent_copy(policy: HengbotPolicy) -> HengbotPolicy:
    """Deep copy whose cached NeedSpec closures are rebuilt on the copy.

    The registry lambdas close over the instance that built them; a copy that
    kept them would evaluate (and mutate) the original policy.
    """
    clone = copy.deepcopy(policy)
    clone._town_need_specs = None
    return clone


class UnaffordableClaimTourRecordedTest(unittest.TestCase):
    replay = None
    claim_rows = None

    def test_s3_new_code_replay_names_remaining_violations(self):
        self._replay()
        self.assertEqual(
            [(row["decision_sequence"], row["owner"])
             for row in self.claim_rows
             if 2998 <= row["decision_sequence"] <= 3003],
            [(sequence, "calibration") for sequence in range(2998, 3004)],
        )
        actual: dict[tuple[str, str], list[int]] = {}
        for row in self.claim_rows:
            violation = row.get("violation")
            if not isinstance(violation, dict) or violation.get("scope") != "S3":
                continue
            self.assertEqual(violation["kind"], "owner-change")
            actual.setdefault((violation["from"], violation["to"]), []).append(
                row["decision_sequence"]
            )
        self.assertEqual(actual, S3_OWNER_CHANGE_SEQUENCES)

    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        boundaries_path = FIXTURE.with_suffix(".boundaries.json")
        assert hashlib.sha256(boundaries_path.read_bytes()).hexdigest() == (
            BOUNDARIES_SHA256
        )
        assert hashlib.sha256(CALIBRATION.read_bytes()).hexdigest() == (
            CALIBRATION_SHA256
        )
        cls.boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        assert len(cls.lines) == sum(cls.boundaries["input_rows"])

    def test_s0_replay_stops_at_first_changed_equipment_choice(self):
        """Recorded boards are authoritative only until the first changed key."""
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy, monrace = _live_like_policy(directory)
            cursor = 0
            for index, count in enumerate(self.boundaries["input_rows"]):
                segment = self.lines[cursor:cursor + count]
                cursor += count
                _decoded, snapshots = _consume_response_sequence(
                    segment, policy, lambda _key: True, monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                snapshot = snapshots[-1]
                policy._experience_drain_known = _drain_unknown
                recorded_reason = self.boundaries["recorded"][index][1]
                if recorded_reason == "periodic:game-save":
                    policy.request_game_save()
                elif recorded_reason == "periodic:character-dump":
                    policy.request_character_dump()
                if index == 2:
                    # The new loadout metric permits the existing 5% survival
                    # trade for Theoden's two-hand damage. This changes the
                    # live key; later recorded boards follow the old travel.
                    key = policy.choose_key(snapshot)
                    self.assertEqual((str(key), policy.last_reason), (
                        "tb", "equipment-transaction:takeoff",
                    ))
                    return
                key = policy.choose_key(snapshot)
                key = policy.validate_read_key(snapshot, key)
                decided = (str(key), policy.last_reason)
                recorded = tuple(self.boundaries["recorded"][index])
                self.assertEqual(decided, recorded)
                register = policy._claim_register
                policy._claim_register = copy.copy(register)
                _recorded_process_capture(policy, snapshot)
                policy._claim_register = register
                policy.confirm_key_posted(key)
        self.fail("equipment-choice divergence was not reached")

    @classmethod
    def _replay(cls):
        """Drive the recorded lifetime through the Healing purchase, then decide."""
        if cls.replay is not None:
            return cls.replay
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy, monrace = _live_like_policy(directory)
            decisions = {}
            claim_rows = []
            cls.claim_rows = claim_rows
            cursor = 0
            snapshot = None
            for index in range(AFTER_PURCHASES + 1):
                count = cls.boundaries["input_rows"][index]
                segment = cls.lines[cursor : cursor + count]
                cursor += count
                _decoded, snapshots = _consume_response_sequence(
                    segment, policy, lambda _key: True, monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                snapshot = snapshots[-1]
                policy._experience_drain_known = _drain_unknown
                if index == AFTER_PURCHASES:
                    break
                recorded_reason = cls.boundaries["recorded"][index][1]
                if recorded_reason == "periodic:game-save":
                    policy.request_game_save()
                elif recorded_reason == "periodic:character-dump":
                    policy.request_character_dump()
                key = policy.choose_key(snapshot)
                key = policy.validate_read_key(snapshot, key)
                decisions[index] = (str(key), policy.last_reason)
                claim_rows.append(_claim_row(policy, snapshot, key, index))
                # S2a.1: the claim register is kept out of the unscoped
                # capture, as the live driver's observer scope now does; no
                # decision reads the register, so the recorded decisions
                # cannot move (test_s0 below still pins them).
                register = policy._claim_register
                policy._claim_register = copy.copy(register)
                _recorded_process_capture(policy, snapshot)
                policy._claim_register = register
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    # The live sender commits the prompt tail after posting;
                    # leaving it staged makes later ownership rows fictitious.
                    policy.commit_staged_prompt_chain({
                        "outcome": "released", "posted": str(key),
                    })

            # Value-level view of the two optional claims on the recorded
            # post-purchase board, evaluated on an independent copy after it
            # decided that board (the decision's outside observation confirms
            # the Healing purchase, which re-arms the Black Market).
            probe = _independent_copy(policy)
            probe.choose_key(snapshot)
            board = probe.with_known_skill_exp(snapshot)
            needs = probe._enumerate_town_needs(board)
            claim_view = {
                "gold": snapshot.player.gold,
                "needs": sorted(
                    (need.store_type, need.category) for need in needs
                ),
                "page_wants_nothing": {
                    (need.store_type, need.category):
                        probe._observed_supplier_page_wants_nothing(board, need)
                    for need in needs
                },
                "departure_failed": sorted(
                    name
                    for name, ready in probe._town_departure_conjuncts(board).items()
                    if not ready
                ),
            }

            # U3 boards: the same recorded input with one Teleport scroll
            # fewer (a required departure shortage), at the recorded gold and
            # at a gold that makes the observed Alchemist page offer nothing.
            def short_board(gold):
                return replace(
                    snapshot,
                    player=replace(snapshot.player, gold=gold),
                    inventory=type(snapshot.inventory)(
                        replace(item, count=item.count - 1)
                        if item.is_teleport_scroll else item
                        for item in snapshot.inventory
                    ),
                )

            required = {}
            for gold in (snapshot.player.gold, 50):
                shortage_policy = _independent_copy(policy)
                shortage = short_board(gold)
                known = shortage_policy.with_known_skill_exp(shortage)
                helper = shortage_policy._observed_supplier_page_wants_nothing(
                    known, TownNeed(STORE_ALCHEMIST, "teleport", "normal")
                )
                shortage_key = shortage_policy.choose_key(shortage)
                required[gold] = {
                    "helper": helper,
                    "decision": (str(shortage_key), shortage_policy.last_reason),
                    "claims": list(shortage_policy._town_claim_categories),
                    "requirements": [
                        row["item"]
                        for row in shortage_policy.procurement_requirements(shortage)
                    ],
                    "departure_block_failed": (
                        shortage_policy._departure_block or {}
                    ).get("failed"),
                }

            key = policy.choose_key(snapshot)
            key = policy.validate_read_key(snapshot, key)
            decided = (str(key), policy.last_reason)
            state = {
                "claims": list(policy._town_claim_categories),
                "departure_block": policy._departure_block,
            }
            _recorded_process_capture(policy, snapshot)
            policy.confirm_key_posted(key)
            # Probe the same captured board twice; equipment ownership remains
            # active without a new confirmation row.
            again = policy.choose_key(snapshot)
            follow_up = (str(again), policy.last_reason)
            cls.replay = (
                decisions, decided, state, follow_up, claim_view, required,
            )
        return cls.replay

    def test_u2_recorded_purchase_boards_are_only_observed(self):
        decisions, *_rest = self._replay()
        # These old boards no longer produce purchases: the index-2 equipment
        # takeoff was never confirmed, and the shop pages are only observed.
        self.assertEqual(
            decisions[AMMO_BUY], ("\x1b", "shop:observe-and-leave")
        )
        self.assertEqual(decisions[HEALING_BUY],
                         ("\x1b", "shop:observe-and-leave"))

    def test_root_cause_claims_on_the_post_purchase_board(self):
        _decisions, _decided, _state, _follow, claim_view, _required = (
            self._replay()
        )
        self.assertEqual(claim_view["gold"], 3729)
        self.assertEqual(claim_view["needs"], [])
        self.assertEqual(claim_view["page_wants_nothing"], {})
        self.assertEqual(claim_view["departure_failed"], [
            "calibration_loadout_restored", "calibration_phase_complete",
            "calibration_restore_complete", "equipment_departure_ready",
        ])

    def test_u1_recorded_post_purchase_board_remains_equipment_owned(self):
        _decisions, decided, state, follow_up, _view, _required = self._replay()
        recorded = self.boundaries["recorded"]
        # Recorded: ('\x1b`n%.', 'shop:travel') back to the Alchemist, then the
        # 4/6 tour and town:blocked:owner-retired at OWNER_RETIRED.
        self.assertEqual(
            recorded[AFTER_PURCHASES], ["\x1b`n%.", "shop:travel"]
        )
        self.assertEqual(
            recorded[OWNER_RETIRED], ["2", "town:blocked:owner-retired"]
        )
        self.assertEqual(decided, ("3", "equipment-transaction:approach-home"))
        self.assertEqual(state["claims"],
                         ["equipment-work", "equipment-transaction"])
        self.assertEqual(state["departure_block"], {})
        self.assertEqual(follow_up, decided)

    def test_u3_teleport_requirement_remains_visible_under_equipment_owner(self):
        *_rest, required = self._replay()
        recorded_gold = required[3729]
        self.assertFalse(recorded_gold["helper"])
        self.assertEqual(recorded_gold["claims"],
                         ["equipment-work", "equipment-transaction"])
        self.assertEqual(recorded_gold["decision"],
                         ("3", "equipment-transaction:approach-home"))
        self.assertEqual(recorded_gold["requirements"], ["Teleport scrolls"])
        # The Alchemist page offers nothing at 50 gold. The Teleport shortage
        # remains visible, while the equipment owner still takes the decision.
        poor = required[50]
        self.assertTrue(poor["helper"])
        self.assertEqual(poor["requirements"], ["Teleport scrolls"])
        self.assertEqual(poor["claims"],
                         ["equipment-work", "equipment-transaction"])
        self.assertEqual(poor["decision"], recorded_gold["decision"])
        self.assertIsNone(poor["departure_block_failed"])

    def test_s2a1_observe_goals_complete_on_their_confirmed_effect(self):
        """S2a.1 (design rev 9.1 item 3, acceptance ii) on this lifetime.

        The counterfactual replay keeps the recorded boards after the index-2
        equipment divergence. It measures which Observe claims still complete
        and which Reach claims arrive on the next row. Other closure pins are
        in tests/test_ownership_s2a1_closure.py.
        """
        from hengbot.ownership_metrics import gate_numbers

        self._replay()
        rows = self.claim_rows
        self.assertEqual(len(rows), AFTER_PURCHASES)
        labels: dict[str, int] = {}
        for row in rows:
            closed = row.get("closed_claim") or {}
            if (
                closed.get("goal_kind") == "Observe"
                and closed.get("closed") == "complete"
            ):
                label = closed["closed_reason"]
                labels[label] = labels.get(label, 0) + 1
        self.assertEqual(labels, S2A1_OBSERVE_COMPLETE_LABELS)
        # S3.0/S3.1: adding a newly stripped item changes the per-key post,
        # but the session's plan and claim identity remain fixed.
        self.assertEqual(
            [row["violation"] for row in rows
             if isinstance(row.get("violation"), dict)
             and row["violation"].get("kind") == "retarget"
             and row["violation"].get("from") == "equipment-txn"],
            [],
        )
        # R3: batch inscription is a precursor, not a store operation; its
        # three false shop-sell retargets disappear as well.
        self.assertEqual(
            {
                owner: sum(
                    isinstance(row.get("violation"), dict)
                    and row["violation"].get("kind") == "retarget"
                    and row["violation"].get("from") == owner
                    for row in rows
                )
                for owner in ("shop-buy", "shop-sell")
            },
            {"shop-buy": 0, "shop-sell": 0},
        )
        # Rev 9.3 (R2): Reach claims that completed on the very next row.
        # Explore's own goal test, loot one cell away and native travel
        # (many cells per key) genuinely arrive next row; the walks rev 9.3
        # names now declare their far target, so of them only a chest one
        # step away completes next row, and the shelter walk no longer does.
        next_row: dict[str, int] = {}
        index = 0
        while index < len(rows):
            end = index
            while (
                end + 1 < len(rows)
                and rows[end + 1]["claim_id"] == rows[index]["claim_id"]
            ):
                end += 1
            following = rows[end + 1] if end + 1 < len(rows) else {}
            closed = following.get("closed_claim") or {}
            if (
                rows[index]["goal"]["kind"] == "Reach"
                and end == index
                and closed.get("claim_id") == rows[index]["claim_id"]
                and closed.get("closed") == "complete"
            ):
                reason = rows[index]["reason"]
                next_row[reason] = next_row.get(reason, 0) + 1
            index = end + 1
        self.assertEqual(sum(next_row.values()), S2A1_NEXT_ROW_COMPLETE)
        self.assertEqual(
            {
                reason: count for reason, count in next_row.items()
                if reason in S2A1_FAR_TARGET_REASONS
            },
            {"chest:approach": 1},
        )
        endings = gate_numbers(rows)["endings"]
        self.assertEqual(
            {
                name: {
                    ending: endings.get(name, {}).get(ending, 0)
                    for ending in counts
                }
                for name, counts in S2A1_ENDINGS.items()
            },
            S2A1_ENDINGS,
        )


if __name__ == "__main__":
    unittest.main()
