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
capture (cli._capture_decision_facts), because the live process ran it and its
equipment evaluation is part of the state the decisions depend on.  Walls,
each on a collaborator that is not under test:
- the recorded periodic save/dump decisions receive the CLI timer request
  that produced them;
- Home history/disposal files and the calibration file live in a temporary
  directory (the calibration file is the one this process itself rewrote at
  16:11:02; the file it loaded at start was not retained);
- experience-potion (user 2026-09-22) drinks the carried Potion of
  Experience at list index 2787 (recorded seek-loot; the drain was filled at
  2786).  The recorded rows after it are the pre-decision lifetime in which
  the potion stays carried and is deposited, so from 2788 the replay walls the
  policy's drain view to unknown (the unchanged protocol-2 behaviour); the
  potion's own pins are in test_experience_potion.
"""

from __future__ import annotations

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
from hengbot.cli import _capture_decision_facts, _consume_response_sequence
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.home_disposal import HomeDisposalState
from hengbot.model import STORE_ALCHEMIST, STORE_BLACK
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
# List index 2787 (decision 2783): experience-potion (user 2026-09-22) moved
# the recorded ('7', 'seek-loot') to ('qg', 'experience:quaff').
KNOWN_HARNESS_DIVERGENCES = {2701, 2787}
EXPERIENCE_WALL_FROM = 2788
# List indices (decision_sequence + 4 after the four shared probe sequences).
AMMO_BUY = 4260        # decision 4256: 'pj21' 21 crossbow bolts, 7934 -> 7871
HEALING_BUY = 4266     # decision 4262: 'pl' Potion of Healing, 7871 -> 3729
AFTER_PURCHASES = 4267  # decision 4263: recorded travel back to the Alchemist
OWNER_RETIRED = 4271   # decision 4267: recorded town:blocked:owner-retired


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

    @classmethod
    def _replay(cls):
        """Drive the recorded lifetime through the Healing purchase, then decide."""
        if cls.replay is not None:
            return cls.replay
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy, monrace = _live_like_policy(directory)
            decisions = {}
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
                if index == EXPERIENCE_WALL_FROM:
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
                _capture_decision_facts(snapshot, policy)
                policy.confirm_key_posted(key)

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
            _capture_decision_facts(snapshot, policy)
            policy.confirm_key_posted(key)
            # The character dump posts no game time: the following board is
            # the same state, on which the departure reads Word of Recall.
            again = policy.choose_key(snapshot)
            follow_up = (str(again), policy.last_reason)
            cls.replay = (
                decisions, decided, state, follow_up, claim_view, required,
            )
        return cls.replay

    def test_s0_replay_matches_recorded_lifetime_through_the_healing_purchase(self):
        decisions, *_rest = self._replay()
        recorded = self.boundaries["recorded"]
        divergent = {
            index
            for index, decided in decisions.items()
            if list(decided) != recorded[index]
        }
        self.assertEqual(divergent, KNOWN_HARNESS_DIVERGENCES)
        self.assertEqual(len(decisions), AFTER_PURCHASES)

    def test_u2_affordable_optional_purchases_still_happen(self):
        decisions, *_rest = self._replay()
        self.assertEqual(
            decisions[AMMO_BUY], ("pj21\r\r\x1b", "shop:one-shot-buy")
        )
        self.assertEqual(decisions[HEALING_BUY], ("pl\r\x1b", "shop:one-shot-buy"))

    def test_root_cause_claims_on_the_post_purchase_board(self):
        _decisions, _decided, _state, _follow, claim_view, _required = (
            self._replay()
        )
        self.assertEqual(claim_view["gold"], 3729)
        self.assertEqual(claim_view["departure_failed"], [])
        # launcher-enchant is live at the Alchemist; its page this visit wants
        # nothing (no Enchant To-Dam on the shelf).
        self.assertIn((STORE_ALCHEMIST, "launcher-enchant"), claim_view["needs"])
        self.assertTrue(
            claim_view["page_wants_nothing"][(STORE_ALCHEMIST, "launcher-enchant")]
        )
        # The Healing purchase confirmation re-armed the Black Market; its page
        # this visit has nothing affordable at 3,729 gold.
        self.assertIn((STORE_BLACK, "black-market"), claim_view["needs"])
        self.assertTrue(
            claim_view["page_wants_nothing"][(STORE_BLACK, "black-market")]
        )

    def test_u1_after_the_healing_purchase_the_bot_departs(self):
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
        self.assertEqual(decided, ("Cf\ry\x1b\x1b", "town:character-dump"))
        self.assertEqual(state["claims"], [])
        self.assertEqual(state["departure_block"], {})
        self.assertEqual(follow_up, ("rga", "town:recall-to-angband"))

    def test_u3_required_supply_claims_are_not_released(self):
        *_rest, required = self._replay()
        recorded_gold = required[3729]
        self.assertFalse(recorded_gold["helper"])
        self.assertIn("teleport", recorded_gold["claims"])
        self.assertEqual(recorded_gold["decision"], ("\x1b`n%.", "shop:travel"))
        self.assertEqual(recorded_gold["requirements"], ["Teleport scrolls"])
        # The observed Alchemist page offers nothing at 50 gold, yet the
        # required shortage still blocks departure.
        poor = required[50]
        self.assertTrue(poor["helper"])
        self.assertIn("Teleport scrolls", poor["requirements"])
        self.assertIn("teleport_ready", poor["departure_block_failed"])
        self.assertNotEqual(poor["decision"][1], "town:character-dump")
        self.assertFalse(poor["decision"][1].startswith("town:recall-to-"))


if __name__ == "__main__":
    unittest.main()
