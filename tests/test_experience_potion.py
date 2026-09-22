"""Potion of Experience pins (user decisions 2026-09-22, verbatim):

1. 「経験の薬　を所持している。これは経験値の一時喪失を回復した上ですぐ使用するべき物品。」
2. 「買えれば買って回復してから飲む（推奨）」 — with the drain present and no restore
   source carried, buy a Potion of Restore Life Levels (tval 75 / sval 41) if a
   store sells one, drink it, then drink the Potion of Experience (sval 59);
   otherwise keep the Experience potion undrunk (never sold/destroyed) until
   the drain is gone or a restore potion is obtained.

Substrate: the frozen 2026-09-22 16:02:57-16:16:04 protocol-3 bot process
(tests/fixtures/unaffordable-claim-tour-20260922.*, extraction script
tests/extract_unaffordable_claim_tour_fixture.py, sha256-pinned).  It carried
the Potion of Experience from decision 0, drained (exp 204,213 / max 210,580)
until combat filled the drain at list index 2786, never saw a Restore Life
Levels shelf while drained, and deposited the potion at Home as idle dead
weight at list index 3002 (the recorded 16:11 deposit).

Replay: every recorded decision through the public response path on one
policy, WITHOUT the live driver's per-decision telemetry capture
(cli._capture_decision_facts, whose equipment-result cache side effect is
handled separately).  Without it the recorded town visits diverge (a known
harness effect of the capture, present on the pre-change code as well); the
dungeon decisions reproduce the recording.  No pin below reads a divergent
town decision; town pins are value-level or decide on an independent copy.
The Temple check (user 2026-09-22 「町にいれば神殿を確かめに行く（推奨）」) is
pinned on the recorded first-visit departure board (list index 20, drained,
potion carried, Temple unobserved; recorded ('rja', town:recall-to-angband)).
Walls, each declared:
- W1 (recorded periodic save/dump requests, temporary Home/calibration
  files): as in the unaffordable-claim-tour replay.
- W2: the recorded rows are the pre-decision lifetime (the potion stays
  carried, the drained town visits never look at the Temple, the potion is
  deposited).  The replayed policy's drain view is walled to "unknown" (the
  protocol-2 behaviour, pinned unchanged by X7) so the recording remains its
  own trajectory.  The wall is lifted only for the recorded decision 2787
  (X1), for the per-board value probes of X4, and on the independent copies
  every other pin decides on.
- W3 (X5): the capture-less replay never posted the recorded ``~9`` of list
  index 4256, so the recorded ``~9`` response row of 4257 is delivered to the
  copy's Home-knowledge consumer (consume_home_knowledge, which the CLI calls
  for an accepted response).
Hand-built boards (declared at each use): the recorded Temple page (with or
without its Restore Life Levels) shown on the index-20 board; the recorded
index-20 board with the drain filled; the recorded Temple page / outside
boards with the recorded Experience potion inserted into the pack and the
recorded 6,367-point drain applied; the recorded 4257 board with the player on
the Home entrance tile; the following board with the withdrawn potion added.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import pickle
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence, _parse_items
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.model import (
    STORE_HOME,
    STORE_TEMPLE,
    SV_POTION_EXPERIENCE,
    SV_POTION_RESTORE_EXP,
    TVAL_POTION,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy

import absorbing_state_catalog
import test_esp_threat_rest_recorded as esp_recorded
import test_morivant_travel_retired_recorded as morivant
import test_unaffordable_claim_tour_recorded as tour


# List indices into the recorded decisions (decision_sequence + 4).
FIRST_DEPARTURE = 20     # recorded ('rja', 'town:recall-to-angband'), drained
DRAINED_LAST = 2785      # last board whose player row is drained
EXPERIENCE_QUAFF = 2787  # first safe board after the drain was filled
DEPOSIT = 3001           # board of the recorded idle-dead-weight deposit
HOME_PAGE = 3004         # Home page listing the deposited potion
TEMPLE_PAGE = 3061       # Temple page: Restore Life Levels 'k' at 633 gold
AFTER_TEMPLE = 3064      # outside, after the recorded Cure Critical purchase
HOME_SCAN = 4257         # board after the recorded Home ~9 response
DRAIN = 6367             # the recorded drain at decision 0 (210,580 - 204,213)


def _potion(snapshot, sval):
    return next(
        (
            item for item in snapshot.inventory
            if item.tval == TVAL_POTION and item.sval == sval
        ),
        None,
    )


def _with_pack(snapshot, *items, drained=None):
    """Hand-built board: recorded items appended to the pack, drain applied."""
    inventory = list(snapshot.inventory)
    for item in items:
        inventory.append(replace(item, slot=chr(ord(inventory[-1].slot) + 1)))
    player = snapshot.player
    if drained is True:
        player = replace(player, exp=player.max_exp - DRAIN, exp_drained=True)
    elif drained is False:
        player = replace(player, exp=player.max_exp, exp_drained=False)
    return replace(
        snapshot, player=player, inventory=type(snapshot.inventory)(inventory)
    )


def _unwalled_copy(policy):
    clone = tour._independent_copy(policy)
    clone.__dict__.pop("_experience_drain_known", None)
    return clone


def _drain_unknown(_snapshot):
    """W2: the protocol-2 view of the drain."""
    return False


def _decide(policy, snapshot):
    key = policy.choose_key(snapshot)
    key = policy.validate_read_key(snapshot, key)
    decided = (str(key), policy.last_reason)
    policy.confirm_key_posted(key)
    return decided


class ExperiencePotionRecordedTest(unittest.TestCase):
    replay = None

    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(tour.FIXTURE.read_bytes()).hexdigest() == (
            tour.FIXTURE_SHA256
        )
        boundaries_path = tour.FIXTURE.with_suffix(".boundaries.json")
        assert hashlib.sha256(boundaries_path.read_bytes()).hexdigest() == (
            tour.BOUNDARIES_SHA256
        )
        assert hashlib.sha256(tour.CALIBRATION.read_bytes()).hexdigest() == (
            tour.CALIBRATION_SHA256
        )
        cls.boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))
        with gzip.open(tour.FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        cls.starts = [0]
        for count in cls.boundaries["input_rows"]:
            cls.starts.append(cls.starts[-1] + count)
        # The copies below keep writing Home history to this directory.
        directory = TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.directory = Path(directory.name)

    @classmethod
    def _board(cls, index, *, walled=False):
        """A fresh independent copy of the stored policy, and the board."""
        decided, snapshot, pre_decision = cls._replay()["boards"][index]
        return tour._independent_copy(pre_decision if walled else decided), snapshot

    @classmethod
    def _replay(cls):
        if cls.replay is not None:
            return cls.replay
        result = {"decisions": {}, "drained_boards": [], "boards": {}}
        directory = cls.directory
        policy, monrace = tour._live_like_policy(directory)
        for index in range(HOME_SCAN + 1):
            segment = cls.lines[cls.starts[index]:cls.starts[index + 1]]
            _decoded, snapshots = _consume_response_sequence(
                segment, policy, lambda _key: True, monrace,
                knowledge_ledger_path=directory / "knowledge.jsonl",
            )
            snapshot = snapshots[-1]
            if index == 0:
                result["experience_item"] = _potion(
                    snapshot, SV_POTION_EXPERIENCE
                )
            policy.__dict__.pop("_experience_drain_known", None)
            if index <= DRAINED_LAST:
                # Value probes of the unwalled owner on the recorded board.
                potion = _potion(snapshot, SV_POTION_EXPERIENCE)
                result["drained_boards"].append((
                    index,
                    snapshot.in_town,
                    snapshot.player.exp_drained,
                    policy._experience_potion_quaff_key(
                        snapshot, policy._physical_hostiles(snapshot)
                    ),
                    policy._retention_reservation_detail(snapshot, potion)
                    if potion is not None else None,
                    policy._experience_restore_supplier(snapshot)
                    if snapshot.in_town else None,
                ))
            if index != EXPERIENCE_QUAFF:
                policy._experience_drain_known = _drain_unknown
            if index in {
                FIRST_DEPARTURE, DEPOSIT, HOME_PAGE, TEMPLE_PAGE,
                AFTER_TEMPLE, HOME_SCAN,
            }:
                result["boards"][index] = (
                    _unwalled_copy(policy), snapshot, tour._independent_copy(policy)
                )
            if index == HOME_SCAN:
                result["home_scan_segment"] = segment
                break
            reason = cls.boundaries["recorded"][index][1]
            if reason == "periodic:game-save":
                policy.request_game_save()
            elif reason == "periodic:character-dump":
                policy.request_character_dump()
            result["decisions"][index] = (
                _decide(policy, snapshot), snapshot.in_town,
                snapshot.player.exp_drained,
                _potion(snapshot, SV_POTION_EXPERIENCE) is not None,
                bool(policy._physical_hostiles(snapshot)),
            )
        cls.replay = result
        return cls.replay

    def test_x1_carried_undrained_potion_is_drunk_at_the_first_safe_board(self):
        decisions = self._replay()["decisions"]
        recorded = self.boundaries["recorded"]
        decided, in_town, drained, carried, hostiles = decisions[EXPERIENCE_QUAFF]
        # Recorded: the potion ('g', aware, count 1) stayed in the pack.
        self.assertEqual(recorded[EXPERIENCE_QUAFF], ["7", "seek-loot"])
        self.assertEqual((in_town, drained, carried, hostiles), (False, False, True, False))
        self.assertEqual(decided, ("qg", "experience:quaff"))
        # The same board's stat-restore drink keeps its precedence.
        self.assertEqual(decisions[EXPERIENCE_QUAFF - 1][0], ("qg", "restore:quaff-dex"))

    def test_x4_drained_without_supplier_the_potion_is_kept(self):
        replay = self._replay()
        decisions = replay["decisions"]
        recorded = self.boundaries["recorded"]
        boards = replay["drained_boards"]
        # Pin vacuity: every board 0..2785 is drained with the potion carried.
        self.assertEqual([entry[0] for entry in boards], list(range(DRAINED_LAST + 1)))
        self.assertEqual({entry[2] for entry in boards}, {True})
        self.assertGreater(sum(entry[1] for entry in boards), 100)
        # Unwalled owner on every recorded drained board: no drink, kept,
        # and no observed shelf offers Restore Life Levels.
        self.assertEqual(
            {entry[3:] for entry in boards},
            {(None, (1, "experience-potion"), None)},
        )
        # Substrate check: the walled replay reproduces the recorded dungeon
        # decisions of the drained span.
        self.assertEqual(
            [
                index for index in range(DRAINED_LAST + 1)
                if not decisions[index][1]
                and list(decisions[index][0]) != recorded[index]
            ],
            [],
        )

    def test_t1_drained_in_town_routes_to_the_unobserved_temple(self):
        policy, snapshot = self._board(FIRST_DEPARTURE)
        self.assertEqual(
            self.boundaries["recorded"][FIRST_DEPARTURE],
            ["rja", "town:recall-to-angband"],
        )
        self.assertTrue(snapshot.in_town and snapshot.player.exp_drained)
        self.assertIsNotNone(_potion(snapshot, SV_POTION_EXPERIENCE))
        self.assertIsNone(_potion(snapshot, SV_POTION_RESTORE_EXP))
        self.assertIsNone(policy._town_supplier_stock_observations.get(STORE_TEMPLE))
        self.assertEqual(_decide(policy, snapshot), ("\x1b`n$.", "shop:travel"))
        self.assertEqual(policy._shopping_approach_store_type, STORE_TEMPLE)
        self.assertEqual(policy._town_claim_categories, ["experience-restore-check"])

    def _temple_page_board(self, snapshot, *, with_restore):
        """Hand-built: the recorded 3061 Temple page shown on this board."""
        _policy, temple = self._board(TEMPLE_PAGE)
        items = [
            item for item in temple.store.items
            if with_restore
            or (item.tval, item.sval) != (TVAL_POTION, SV_POTION_RESTORE_EXP)
        ]
        return replace(snapshot, store=replace(temple.store, items=items))

    def test_t2_temple_observed_without_restore_departure_proceeds(self):
        policy, snapshot = self._board(FIRST_DEPARTURE)
        page = self._temple_page_board(snapshot, with_restore=False)
        self.assertEqual(_decide(policy, page), ("\x1b", "shop:observe-and-leave"))
        # The next outside board: no further Temple trip, the recorded recall.
        outside = replace(snapshot, turn=snapshot.turn + 1)
        self.assertFalse(policy._experience_restore_check_wanted(outside))
        self.assertIsNone(policy._experience_restore_supplier(outside))
        self.assertEqual(_decide(policy, outside), ("rja", "town:recall-to-angband"))
        self.assertEqual(policy._town_claim_categories, [])
        # The potion is kept, not drunk, while the drain remains.
        self.assertEqual(
            policy._retention_reservation_detail(
                outside, _potion(outside, SV_POTION_EXPERIENCE)
            ),
            (1, "experience-potion"),
        )

    def test_t3_temple_observed_with_restore_buys_it(self):
        policy, snapshot = self._board(FIRST_DEPARTURE)
        page = self._temple_page_board(snapshot, with_restore=True)
        bought = policy._next_purchase(page)
        self.assertEqual(
            (getattr(bought, "letter", None), getattr(bought, "sval", None)),
            ("k", SV_POTION_RESTORE_EXP),
        )
        self.assertEqual(
            _decide(policy, page),
            ("\x1b", "town-progress-invariant:continue-observed-shop"),
        )
        # Outside, the observed shelf now owns the (existing X3) purchase.
        outside = replace(snapshot, turn=snapshot.turn + 1)
        self.assertFalse(policy._experience_restore_check_wanted(outside))
        self.assertEqual(policy._experience_restore_supplier(outside), STORE_TEMPLE)
        self.assertEqual(_decide(policy, outside), ("\x1b`n$.", "shop:travel"))
        self.assertEqual(policy._town_claim_categories, ["experience-restore"])

    def test_t4_not_drained_no_temple_trip(self):
        policy, snapshot = self._board(FIRST_DEPARTURE)
        # Hand-built: the recorded board with the drain filled.
        undrained = _with_pack(snapshot, drained=False)
        self.assertFalse(policy._experience_restore_check_wanted(undrained))
        self.assertEqual(_decide(policy, undrained), ("qg", "experience:quaff"))
        self.assertEqual(policy._town_claim_categories, [])

    def test_x6_disposal_and_deposit_selectors_never_pick_the_potion(self):
        policy, snapshot = self._board(DEPOSIT)
        walled, _board = self._board(DEPOSIT, walled=True)
        potion = _potion(snapshot, SV_POTION_EXPERIENCE)
        self.assertEqual(potion.slot, "h")
        # Recorded 3002 deposited it ('dh...'): the pre-decision view still
        # selects it as idle dead weight on this board.
        self.assertTrue(walled._home_deposit_candidate(potion, snapshot))
        self.assertEqual(
            policy._retention_reservation_detail(snapshot, potion),
            (1, "experience-potion"),
        )
        self.assertEqual(policy._retention_surplus(snapshot, potion), 0)
        self.assertFalse(policy._entire_stack_is_surplus(snapshot, potion))
        self.assertFalse(policy._home_deposit_candidate(potion, snapshot))
        for finder in (
            policy._find_home_deposit,
            policy._find_low_level_sale,
            policy._find_town_organization_surplus,
        ):
            with self.subTest(finder=finder.__name__):
                found = finder(snapshot)
                self.assertFalse(
                    found is not None
                    and (found.tval, found.sval) == (TVAL_POTION, SV_POTION_EXPERIENCE)
                )
        # Home disposal: the recorded Home page listing the deposited potion.
        home, page = self._board(HOME_PAGE)
        walled_home, _page = self._board(HOME_PAGE, walled=True)
        self.assertEqual(page.store.store_type, STORE_HOME)
        self.assertIn(
            (TVAL_POTION, SV_POTION_EXPERIENCE),
            {(item.tval, item.sval) for item in page.store.items},
        )
        seen = {}
        for label, candidate_policy in (("decided", home), ("walled", walled_home)):
            candidate_policy._home_disposal_pass = True
            candidate_policy._home_disposal_home_key(page)
            seen[label] = {
                (candidate.tval, candidate.sval)
                for candidate in candidate_policy._home_disposal_candidates.values()
            }
        self.assertIn((TVAL_POTION, SV_POTION_EXPERIENCE), seen["walled"])
        self.assertNotIn((TVAL_POTION, SV_POTION_EXPERIENCE), seen["decided"])

    def test_x3_drained_without_restore_buys_it_then_drinks_both(self):
        replay = self._replay()
        experience = replay["experience_item"]
        policy, temple = self._board(TEMPLE_PAGE)
        self.assertEqual(temple.store.store_type, STORE_TEMPLE)
        shelf = next(
            item for item in temple.store.items
            if item.tval == TVAL_POTION and item.sval == SV_POTION_RESTORE_EXP
        )
        self.assertEqual((shelf.letter, shelf.price, shelf.count), ("k", 633, 1))
        # Hand-built: the recorded page with the potion carried and drained.
        drained = _with_pack(temple, experience, drained=True)
        # The recorded mandatory Cure Critical ('j') keeps its precedence.
        self.assertEqual(policy._next_purchase(drained).letter, "j")
        # Hand-built: the same page after that recorded purchase ('pj1').
        after_cure = replace(drained, inventory=type(drained.inventory)(
            replace(item, count=item.count + 1)
            if (item.tval, item.sval) == (TVAL_POTION, 36) else item
            for item in drained.inventory
        ))
        bought = policy._next_purchase(after_cure)
        self.assertEqual(
            (getattr(bought, "letter", None), getattr(bought, "sval", None)),
            ("k", SV_POTION_RESTORE_EXP),
        )
        selection = policy._purchase_selection_for_key(after_cure, "pk")
        self.assertEqual(
            (selection.match.rung_id, selection.quantity),
            ("experience:restore-life-levels", 1),
        )
        # Not drained: nothing to restore, the shelf potion is not bought.
        undrained = replace(after_cure, player=temple.player)
        self.assertFalse(
            getattr(policy._next_purchase(undrained), "sval", None)
            == SV_POTION_RESTORE_EXP
        )
        # The departure-supply reserve is respected (632 gold short of it).
        reserve = policy._required_departure_supply_reserve(after_cure)
        poor = replace(after_cure, player=replace(
            after_cure.player, gold=reserve + shelf.price - 1
        ))
        self.assertIsNone(policy._restore_life_levels_purchase(poor))
        self.assertIsNotNone(policy._restore_life_levels_purchase(replace(
            after_cure, player=replace(after_cure.player, gold=reserve + shelf.price)
        )))

        # Outside after the purchase: the observed Temple page routes the need.
        outside_policy, outside = self._board(AFTER_TEMPLE)
        board = _with_pack(outside, experience, drained=True)
        self.assertEqual(outside_policy._experience_restore_supplier(board), STORE_TEMPLE)
        self.assertIn(
            (STORE_TEMPLE, "experience-restore"),
            {
                (need.store_type, need.category)
                for need in outside_policy._enumerate_town_needs(
                    outside_policy.with_known_skill_exp(board)
                )
            },
        )

    def test_x2_restore_life_levels_is_drunk_before_the_experience_potion(self):
        replay = self._replay()
        experience = replay["experience_item"]
        _policy, temple = self._board(TEMPLE_PAGE)
        shelf = next(
            item for item in temple.store.items
            if item.tval == TVAL_POTION and item.sval == SV_POTION_RESTORE_EXP
        )
        restore = replace(experience, sval=SV_POTION_RESTORE_EXP, name=shelf.name)
        policy, outside = self._board(AFTER_TEMPLE)
        # Hand-built: both potions carried ('m' Experience, 'n' Restore), drained.
        both = _with_pack(outside, experience, restore, drained=True)
        self.assertEqual(
            _decide(policy, both), ("qn", "experience:quaff-restore-life-levels")
        )
        # The drain is gone and the restore potion consumed.
        restored = _with_pack(outside, experience, drained=False)
        self.assertEqual(_decide(policy, restored), ("qm", "experience:quaff"))
        # Drained with no restore carried: the Experience potion is not drunk.
        waiting = _with_pack(outside, experience, drained=True)
        self.assertIsNone(policy._experience_potion_quaff_key(waiting, []))
        self.assertEqual(
            policy._retention_reservation_detail(waiting, restore),
            (restore.count, "experience-restore"),
        )

    def test_x5_potion_at_home_is_withdrawn_then_drunk(self):
        replay = self._replay()
        experience = replay["experience_item"]
        policy, snapshot = self._board(HOME_SCAN)
        self.assertIsNone(_potion(snapshot, SV_POTION_EXPERIENCE))
        rows = [json.loads(line) for line in replay["home_scan_segment"]]
        response = next(
            row for row in rows
            if row.get("type") == "knowledge"
            and row["knowledge"].get("category") == "home"
        )
        items = tuple(_parse_items(response["knowledge"]["items"], protocol=3))
        # W3: the recorded ~9 response, delivered to the knowledge consumer.
        policy.consume_home_knowledge(items)
        stored = policy._home_experience_potion(snapshot)
        self.assertEqual((stored.sval, stored.count), (SV_POTION_EXPERIENCE, 1))
        entrance = next(
            position for position, grid in snapshot.grids.items()
            if grid.store_number == STORE_HOME
        )
        # Hand-built: the recorded board with the player on the Home entrance.
        at_home = replace(snapshot, player=replace(snapshot.player, position=entrance))
        self.assertEqual(
            _decide(policy, at_home),
            ("5ph\x1b", "home-errand:atomic-withdraw:experience-potion"),
        )
        self.assertEqual(
            (policy._home_errand.request.signature, policy._home_errand.request.quantity),
            (policy._item_signature(stored), 1),
        )
        # Hand-built: the next outside board with the withdrawn potion carried.
        withdrawn = replace(
            _with_pack(at_home, experience), turn=at_home.turn + 10
        )
        slot = _potion(withdrawn, SV_POTION_EXPERIENCE).slot
        self.assertEqual(_decide(policy, withdrawn), ("q" + slot, "experience:quaff"))
        self.assertEqual(policy._home_errand.state.value, "done")

    def test_x5_route_from_the_recorded_board_claims_the_home_withdrawal(self):
        replay = self._replay()
        policy, snapshot = self._board(HOME_SCAN)
        rows = [json.loads(line) for line in replay["home_scan_segment"]]
        response = next(
            row for row in rows
            if row.get("type") == "knowledge"
            and row["knowledge"].get("category") == "home"
        )
        # W3 as above.
        policy.consume_home_knowledge(
            tuple(_parse_items(response["knowledge"]["items"], protocol=3))
        )
        self.assertEqual(_decide(policy, snapshot), ("1", "shop:approach"))
        self.assertEqual(policy._town_claim_categories[0], "experience-potion-home")
        self.assertEqual(policy._home_errand.request.purpose, "experience-potion")


class ExperiencePotionProtocol2Test(unittest.TestCase):
    def test_x7_protocol2_lifetime_decisions_are_unchanged(self):
        """X7: a recorded protocol-2 lifetime carrying the Experience potion."""
        boundaries_path = morivant.FIXTURE.with_suffix(".boundaries.json")
        self.assertEqual(
            hashlib.sha256(morivant.FIXTURE.read_bytes()).hexdigest(),
            morivant.FIXTURE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(boundaries_path.read_bytes()).hexdigest(),
            morivant.BOUNDARIES_SHA256,
        )
        boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))
        with gzip.open(morivant.FIXTURE, "rt", encoding="utf-8") as stream:
            lines = list(stream)
        monrace = load_monrace_knowledge(esp_recorded.EDIT / "MonraceDefinitions.jsonc")
        decided = []
        carried = 0
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy = esp_recorded._policy(directory, monrace)
            cursor = 0
            for index, count in enumerate(boundaries["input_rows"][:-1]):
                segment = lines[cursor:cursor + count]
                cursor += count
                _decoded, snapshots = _consume_response_sequence(
                    segment, policy, lambda _key: True, monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                snapshot = snapshots[-1]
                self.assertIsNone(snapshot.player.max_exp)
                carried += _potion(snapshot, SV_POTION_EXPERIENCE) is not None
                reason = boundaries["recorded"][index][1]
                if reason == "periodic:game-save":
                    policy.request_game_save()
                elif reason == "periodic:character-dump":
                    policy.request_character_dump()
                decided.append(list(_decide(policy, snapshot)))
        self.assertGreater(carried, 100)
        self.assertEqual(
            [
                index + 1 for index, decision in enumerate(decided)
                if decision != boundaries["recorded"][index]
            ],
            # The existing M0 pin's recorded moves; nothing else changed.
            [153, 155, 158, 618, 620],
        )
        self.assertFalse(any(reason.startswith("experience:") for _key, reason in decided))


class ExperiencePotionRestoredCheckpointTest(unittest.TestCase):
    def test_restored_checkpoint_reads_the_new_paths(self):
        """restore_checkpoint rebuilds __dict__ without __init__."""
        with gzip.open(
            absorbing_state_catalog.HOME_DEFERRAL_CAPTURE, "rt", encoding="utf-8"
        ) as stream:
            capture = json.load(stream)
        policy = restore_checkpoint(
            HengbotPolicy, capture["producer_checkpoint_pickle_b64"]
        )
        snapshot = pickle.loads(base64.b64decode(capture["snapshots_pickle_b64"][0]))
        potion = replace(
            snapshot.inventory[0], tval=TVAL_POTION, sval=SV_POTION_EXPERIENCE,
            aware=True, count=1,
        )
        restore = replace(potion, sval=SV_POTION_RESTORE_EXP)
        board = replace(
            snapshot,
            player=replace(
                snapshot.player,
                max_exp=snapshot.player.exp + DRAIN,
                exp_drained=True,
            ),
            inventory=type(snapshot.inventory)([
                *snapshot.inventory[:-2],
                replace(potion, slot=snapshot.inventory[-2].slot),
                replace(restore, slot=snapshot.inventory[-1].slot),
            ]),
        )
        self.assertIsNone(policy._experience_restore_supplier(board))
        policy._home_experience_potion(board)
        self.assertEqual(
            policy._retention_reservation_detail(board, board.inventory[-2])[1],
            "experience-potion",
        )
        self.assertEqual(
            policy._retention_reservation_detail(board, board.inventory[-1])[1],
            "experience-restore",
        )


if __name__ == "__main__":
    unittest.main()
