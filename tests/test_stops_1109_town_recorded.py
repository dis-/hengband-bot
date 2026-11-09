"""The viewing bots' town stops of 2026-11-08/09 (stops-1109 analysis).

Recorded: the town-arrival checkpoints of the incident captures and their
journals (tests/extract_stops_1109_town_fixtures.py).  Every decision goes
through the public ``choose_key`` on the restored arrival policy; each key is
acknowledged as posted the way the CLI does (``confirm_key_posted`` and the
staged prompt chain), as tests/replay_town_arrival.py replays a visit.

DECLARED for every replay: a row whose recorded decision the replay does not
reproduce is fed with the recorded key posted (the recorded boards follow);
the pins name the rows they assert.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.cli import _consume_response_sequence
from hengbot.home_disposal import HOME_HISTORY_DIR_ENV
from hengbot.model import STORE_HOME, parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.runtime_paths import RUNTIME_DIR_ENV
from hengbot.town_arrival_checkpoint import POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST
from replay_town_arrival import adopt_calibration, restore

FIXTURES = Path(__file__).with_name("fixtures") / "stops-1109-town"


class RecordedVisit(unittest.TestCase):
    """Restore one fixture's arrival policy and replay its journal."""

    fixture = None
    fixtures = FIXTURES
    # Whether the calibration file copied at the capture is read (as
    # tests/replay_town_arrival.py does), or the pickled verdict is kept.
    adopt_calibration = True

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        (self.scratch / "runtime-env").mkdir()
        (self.scratch / "history-env").mkdir()
        env = mock.patch.dict(os.environ, {
            RUNTIME_DIR_ENV: str(self.scratch / "runtime-env"),
            HOME_HISTORY_DIR_ENV: str(self.scratch / "history-env")})
        env.start()
        self.addCleanup(env.stop)
        source = self.fixtures / self.fixture
        self.journal = [json.loads(line) for line in
                        lzma.decompress((source / "journal.jsonl.xz").read_bytes()).splitlines()]
        visit = self.scratch / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((source / "policy.pkl.xz").read_bytes()))
        sidecars = json.loads(lzma.decompress((source / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(json.dumps(sidecars["manifest"]), encoding="utf-8")
        (visit / SIDECAR_DIRECTORY).mkdir()
        self.sidecars = {}
        for role, text in sidecars["files"].items():
            self.sidecars[role] = text.encode("latin-1")
            (visit / SIDECAR_DIRECTORY / role).write_bytes(self.sidecars[role])
        runtime = self.scratch / "runtime"
        runtime.mkdir()
        self.policy = restore(visit, runtime)
        calibration = visit / SIDECAR_DIRECTORY / "_character_calibration_path"
        if self.adopt_calibration and calibration.is_file():
            adopt_calibration(self.policy, calibration, runtime)

    def board(self, row):
        policy, entry = self.policy, self.journal[row]
        _consume_response_sequence([line + "\n" for line in entry["inputs"]], policy,
                                   lambda _key: True, policy._monrace_knowledge,
                                   parse_snapshots=False,
                                   knowledge_ledger_path=self.scratch / "knowledge.jsonl")
        line = entry["line"] if entry["line"] is not None else entry["inputs"][-1]
        for name, value in entry["cli_latches"].items():
            setattr(policy, name, tuple(value) if isinstance(value, list) else value)
        policy.observe_store_screen(entry["store_screen_verified"])
        return parse_snapshot(json.loads(line), policy._monrace_knowledge)

    def post(self, key):
        policy = self.policy
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def decide(self, row, *, post_recorded=False):
        """(board, key, reason) of ``row``; the decided key is posted when it
        is the recorded one, else (DECLARED) the recorded key."""
        board = self.board(row)
        key = self.policy.choose_key(board)
        reason = self.policy.last_reason
        recorded = self.journal[row]
        same = (key, reason) == (recorded["key"], recorded["reason"])
        self.post(recorded["key"] if post_recorded or not same else key)
        return board, key, reason

    def replay_to(self, row):
        """Rows before ``row`` as recorded; returns the rows not reproduced."""
        differing = []
        for index in range(row):
            _board, key, reason = self.decide(index)
            recorded = self.journal[index]
            if (key, reason) != (recorded["key"], recorded["reason"]):
                differing.append(index)
        return differing


class StoredDiggerTakeTest(RecordedVisit):
    """A. n1-c life-174 2026-11-09 02:20 town:blocked:survival:recall_departure_ready.

    Fundraising prepare (5,338 gold, Lv34): nine diggers at Home past its
    first page, none carried.  The three Home passes of the visit deposited the
    overload (row 2), deposited for the equipment transaction (row 8) and left
    an incomplete page (row 11); each was charged to stored-digger and
    fundraising-kit although no pass tried the digger take, and the take's
    owner (``_queue_standing_home_digger``) looked only at the open first
    page.  The claims retired at three attempts and the town end stopped with
    Word of Recall and Teleportation unbought (row 14).

    Fix: a Home pass spends the kit claims only when it tried the kit take
    (home_pass_charge, as identification-withdrawal since e75ff6a750), and
    the take is bound from the whole current Home catalogue.
    """

    fixture = "a174"

    def test_recorded_home_passes_did_other_work(self):
        self.assertEqual([self.journal[row]["reason"] for row in (2, 8, 11)], [
            "home:weight-overload-deposit", "equipment-transaction:deposit",
            "home:scan-incomplete-open-page"])
        self.assertEqual(self.journal[14]["reason"], "town:blocked:survival:recall_departure_ready")
        self.assertEqual(sum(owned.origin == "home" and owned.item.is_digging_tool
                             for owned in self.policy._equipment_catalog.items), 9)

    def test_passes_without_the_digger_take_leave_the_kit_claims_live(self):
        # The three Home passes decide as recorded; row 12 (the recorded end
        # step-off) already walks back to Home.
        differing = self.replay_to(14)
        self.assertTrue({2, 8, 11}.isdisjoint(differing), differing)
        self.assertIn(12, differing)
        self.assertNotIn("stored-digger", self.policy._town_visit_ledger.need_attempts)
        self.assertNotIn("fundraising-kit", self.policy._town_visit_ledger.need_attempts)
        board, key, reason = self.decide(14)
        self.assertEqual(reason, "shop:approach")
        self.assertEqual(self.policy._shopping_approach_store_type, STORE_HOME)
        self.assertEqual(set(self.policy._town_errand_plan.need_categories[STORE_HOME]),
                         {"fundraising-kit", "stored-digger"})
        self.assertNotEqual(key, self.journal[14]["key"])


class HomeIdentificationBesideFullWaitTest(RecordedVisit):
    """H. n1-a life-497 2026-11-09 03:58 town:blocked:unmet:home_candidate_resolved.

    The carried 殺傷の矢 waited for *Identify* (identification need "full")
    with no *Identify* on the Alchemist's shelf; the need's missing source
    kept the Home identification-withdrawal out of the plan although two
    Home items (the armour {average-unreliable} and the dwarven pick) were
    identifiable with the carried Identify staff, and their catalogue take was
    filed.  visit_can_identify stayed true for those Home items, so the wait
    was not released either: the town end stopped (row 37).

    Owner 2026-10-31 「鑑定の手段がある時に、預けた未鑑定の装備を…取り出して鑑定」,
    11-03 「*鑑定* 待ちは鑑定できない訪問なら今の装備で出発」.  Fix: the Home
    candidates a carried source identifies keep the Home withdrawal planned
    beside a need whose source the visit lacks.
    """

    fixture = "h497"

    def test_recorded_rows_replay_to_the_stop(self):
        # Row 16 buys one more of its shelf stack once the unidentified Q34
        # weapons wait for identification (C); every other row as recorded.
        self.assertLessEqual(set(self.replay_to(37)), {16})
        self.assertEqual(self.journal[37]["reason"], "town:blocked:unmet:home_candidate_resolved")
        self.assertEqual(self.policy._identification_need, "full")

    def test_home_candidates_are_taken_beside_the_full_wait(self):
        self.replay_to(37)
        _board, key, reason = self.decide(37)
        self.assertEqual(reason, "shop:approach")
        self.assertNotEqual(key, self.journal[37]["key"])
        plan = self.policy._town_errand_plan
        self.assertIn("identification-withdrawal", plan.need_categories[STORE_HOME])
        self.assertEqual(self.policy._shopping_approach_store_type, STORE_HOME)
        self.assertEqual(self.policy._home_errand.request.purpose, "identification-catalog")


class RefusedLightBuyMakesRoomTest(RecordedVisit):
    """E. n1-c life-172 2026-11-08 20:12 town:blocked:owner-retired-burst.

    Light out in the dark street (light radius 0), 19 of 23 slots used: the
    light restore walked to the General Store, whose page refused the wanted
    torches only for a slot (``_next_purchase`` pack_refusal
    full-pack-nonstacking, rows 19 and 22) and left; the walk re-entered the
    same shop until the owner retirements.  The bought staff could have been
    shelved at Home.  Fix: that refusal starts the town's inventory pass
    (make_room_for_purchase, owner 2026-10-31 「自宅にいるなら先に不要物を仕舞う」),
    and the light restore lets the pass's shelving walk go first.
    """

    fixture = "e172"

    def test_recorded_refusal_and_reentry(self):
        self.assertEqual(self.replay_to(19), [])
        board, key, reason = self.decide(19)
        self.assertEqual((key, reason), ("\x1b", "town-progress-invariant:continue-observed-shop"))
        self.assertEqual(self.policy._shop_selector_diagnostics["wanted_purchase"]["category"], "torch")
        self.assertEqual(board.light_radius, 0)
        self.assertEqual(len(board.inventory), 19)
        self.assertEqual(self.journal[20]["reason"], "shop:approach")

    def test_refused_buy_walks_to_home_to_make_room(self):
        self.replay_to(20)
        board, key, _reason = self.decide(20)
        from hengbot import town_pack_headroom
        self.assertTrue(town_pack_headroom.organizing(self.policy, board))
        self.assertEqual(self.policy._shopping_approach_store_type, STORE_HOME)
        self.assertNotEqual(key, self.journal[20]["key"])


class PowerfulIdentifyCostTest(RecordedVisit):
    """D. n1-b life-351 2026-11-08 21:09 town:blocked:owner-retired-burst.

    The Powerful Activation *Identify* ('UAf' + slot) pays its cost in HP
    (racial_power_reduce_mana).  The next board read the drop as a hit
    (``_took_damage``): the town sought shelter (rows 71, 82, 129, 132, 135,
    141) and ``me_powerful_activation._safe`` turned false, so the carried
    Home take lost its hold (``awaits_identify``) and the deposits shelved
    pieces before their *Identify*; the Home visits ran out
    (town:blocked:equipment-home-unavailable).  The current main departs at
    row 143 instead (forced visit departure), so the stop itself is not
    replayed.  Fix: the board right after a use whose HP drop is within the
    cost is no hit.
    """

    fixture = "d351"

    def test_recorded_use_then_shelter(self):
        self.assertEqual(self.replay_to(70), [])
        self.assertEqual(self.journal[70]["reason"], "me-powerful:identify")
        self.assertEqual(self.journal[71]["reason"], "town:seek-shelter")

    def test_the_activation_cost_is_no_hit(self):
        from hengbot import me_powerful_activation
        self.replay_to(71)
        board, _key, reason = self.decide(71)
        self.assertLess(board.player.hp, board.player.max_hp)
        self.assertFalse(self.policy._took_damage)
        self.assertNotEqual(reason, "town:seek-shelter")
        self.assertTrue(me_powerful_activation.spare_identify_ready(self.policy, board))


class PowerfulIdentifyFloorTest(RecordedVisit):
    """D. The Powerful Activation *Identify* answers to the staff's floor.

    n1-c life-165 (2026-11-08 04:59) failed the Powerful Activation
    *Identify* sixteen times in a row while its Home takes went back and
    forth.  949ca43348 held the absorbed Identify to STAFF_IDENTIFY_MIN_SUCCESS
    for the ordinary cast only; ``spare_identify_ready`` and ``town_key``
    read no rate.  Recorded: n1-b life-353 (tests/fixtures/
    n1b-353-retired-burst-1109), INT drained to 7, whose power list (row 4)
    lists the absorbed Identify at 95% fail; rows 0-19 through choose_key.
    """

    fixtures = Path(__file__).with_name("fixtures")
    fixture = "n1b-353-retired-burst-1109"

    def test_unreliable_power_files_no_powerful_identify(self):
        from hengbot import me_capability, me_powerful_activation
        from hengbot.model import SV_STAFF_IDENTIFY
        self.replay_to(20)
        board = self.board(20)
        row = me_capability.observed_row(self.policy, "staff", SV_STAFF_IDENTIFY)
        self.assertEqual(row["success"], 5)
        self.assertGreaterEqual(board.player.level, me_powerful_activation.MIN_LEVEL)
        self.assertFalse(me_powerful_activation.spare_identify_ready(self.policy, board))
        self.assertIsNone(me_powerful_activation.spare_identify_key(self.policy, board))
        self.assertIsNone(me_powerful_activation.town_key(self.policy, board, ()))


class MeStaffPostedStepTest(RecordedVisit):
    """F. The Magic-Eater staff sequence counts a cell only for its posted step.

    n1-c life-165 (2026-11-08 05:51 and 06:27) stopped under
    quest:blocked:me-staff no-progress:travel: the sequence's position count
    (``_no_progress``) counted every decision whose step it chose, also those
    whose key another owner replaced, and eight periodic character dumps
    ('Cf' + 'y', the CLI timer's request_character_dump) took the travel's
    boards.  No record of those visits was copied; this drives the same
    composition on n1-b life-356 (2026-11-09), whose rows 60-61 are the
    sequence's travel to Morivant.

    DECLARED CONSTRUCTED: row 60's recorded board is decided again after each
    dump with the CLI timer's request latched before every decision (the
    game state does not change under a dump).
    """

    fixture = "g356"
    adopt_calibration = False

    def test_replaced_steps_do_not_stop_the_sequence(self):
        from hengbot.policy_constants import STORE_STUCK_LIMIT
        self.replay_to(60)
        self.assertEqual(self.journal[60]["reason"], "me-staff:travel-morivant")
        board = self.board(60)
        reasons = []
        for _ in range(STORE_STUCK_LIMIT + 1):
            self.policy.request_character_dump()
            key = self.policy.choose_key(board)
            reasons.append(self.policy.last_reason)
            self.post(key)
        self.assertEqual(reasons[0], "periodic:character-dump")
        self.assertFalse(any(reason.startswith("me-staff:") for reason in reasons), reasons)
        key = self.policy.choose_key(board)
        self.assertEqual((key, self.policy.last_reason),
                         (self.journal[60]["key"], self.journal[60]["reason"]))


if __name__ == "__main__":
    unittest.main()
