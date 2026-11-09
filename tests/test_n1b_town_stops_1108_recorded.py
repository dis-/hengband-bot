"""n1-b (Magic-Eater) life-338/339 2026-11-07/08: four town stops.

Recorded: the town-arrival checkpoints of four incident captures and their
journals (tests/extract_n1b_town_stops_1108_fixtures.py), decided through the
public ``choose_key``; A's raise is also posted through the production
executor port.

A, life-338 19:50 stuck-prompt:town:armor-smith:raise: the key
``3a/ka/ba/ka/l\\x1b`` opened どのアイテムを改良しますか？ on the pack page holding
exactly one armour.  view/display-inventory.cpp:86,122-124 lists it at row 1
and clears row 2 (from column 0 for a long name), which wiped the building's
header row the classifier required, so the chooser was unrecognised.

B, life-338 21:52 town:blocked:owner-retired-burst x3: the random-teleport
suppression (policy_town ``_town_random_teleport_suppression_key``) armed a
Home take of (トランプ)ブロード・スピア, a spare the loadout does not wear, to
inscribe it; the take's spare-gear rule (spare_gear.note_taken, owner
2026-11-04 「使わない装備を持ったまま出発しない・自宅に仕舞う」) put it straight
back ('5  ph' then 'dl'), every pass.  Only wielded items teleport
(player/player-status-flags.cpp update_curses walks INVEN_WIELDING_SLOTS), so
an unworn Home item is no suppression target.

C, life-338 17:34 quest:blocked:me-staff no-progress:return: the Magic-Eater
staff sequence (a rung above the global town hunt) travelled toward the inn
past a visible drunk (race 15); out of sight the hunt walked back to where it
was last seen; the sequence's position count stopped it.  Owner 2026-10-31:
town is cleared before errands resume.

D, life-339 02:30 loop-detected: the Alchemist's shelf, observed with nothing
wanted (Word of Recall 9 of 11, none stocked), was left with "shop:leave";
the outside composition released the page without settling the stop, and the
router stepped off and back on its entrance 30+ times.

DECLARED for every replay: rows whose recorded decision the replay does not
reproduce are fed with the recorded key posted (the recorded boards follow).
A row 1 and D rows 1/3/5 (town:seek-shelter picks another equally near store
cell on the restored policy, on the recorded build too) and D's Home rows that
follow from it; C is decided at row 256 directly on the arrival policy with
the earlier rows' responses consumed (its journal replay diverges at row 20 on
the recorded build too).
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.cli import _ExecutorInputPort, _consume_response_sequence, _send_new_decision_key
from hengbot.home_disposal import HOME_HISTORY_DIR_ENV
from hengbot.input_executor import ScreenKind, classify_screen
from hengbot.model import STORE_ALCHEMIST, parse_snapshot
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.runtime_paths import RUNTIME_DIR_ENV
from hengbot.town_arrival_checkpoint import POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST
from replay_town_arrival import restore
from tests.support import recorded as executor_pins

FIXTURES = Path(__file__).with_name("fixtures") / "n1b-town-stops-1108"
SPEAR = "(トランプ)ブロード・スピア (1d9) (+7,+10) (+1探索) {+探r轟因;麻遅活瞬/邪デ}"
RAISE_KEY = "3a/ka/ba/ka/l\x1b"


def recorded_smith_screen():
    """The recorded pack page of the one-item chooser (213x68)."""
    data = json.loads((FIXTURES / "armor-smith-one-item-screen.json").read_text(encoding="utf-8"))
    lines = [" " * data["width"]] * data["height"]
    for row, text in data["rows"].items():
        lines[int(row)] = text
    return {"width": data["width"], "height": data["height"], "cursor": data["cursor"],
            "input_context": data["input_context"], "lines": lines}


def centered(screen, rows):
    """CONSTRUCTED: logical 80x24 rows at the recorded screen's centred offset."""
    value = copy.deepcopy(screen)
    ox, oy = (value["width"] - 80) // 2, (value["height"] - 24) // 2
    value["lines"] = [" " * value["width"]] * value["height"]
    for row, text in rows.items():
        value["lines"][oy + row] = " " * ox + text
    value.pop("input_context", None)
    return value


class SmithOneItemGame(executor_pins.FaithfulHookGame):
    """CONSTRUCTED: market/building-enchanter.cpp's chooser over the building.

    The pack page after each 'a' is the recorded screen verbatim; the
    building menu is its kept rows (41, 45 of the capture) with a header, and
    the equipment page is a several-row list.  A raise charges nothing.
    """

    capacity = 64

    def __init__(self, board):
        super().__init__()
        self.state = copy.deepcopy(board)
        self.state["messages"] = []
        self.phase = "command"
        self.posted = []
        pack = recorded_smith_screen()
        ox, oy = (pack["width"] - 80) // 2, (pack["height"] - 24) // 2
        kept = {y - oy: pack["lines"][y][ox:] for y in (oy + 19, oy + 23)}
        self.pack_page = pack
        self.building = centered(pack, {2: " 防具屋", **kept})
        self.equip_page = centered(pack, {
            0: "(装備品:a-l,'(',')', '/' 持ち物, ESC) どのアイテムを改良しますか？",
            1: "b) 盾", 2: "h) 鎧", 3: "k) 小手", 4: "l) 靴", **kept})

    def _key(self, key):
        if self.phase == "command" and key == "3":
            self.phase = "building"
        elif self.phase == "building":
            if key == "a":
                self.phase = "pack"
            elif key == "\x1b":
                self.phase = "command"
                self.state["turn"] += 1
        elif self.phase == "pack":
            assert key == "/", key
            self.phase = "equip"
        elif self.phase == "equip":
            self.phase = "building"

    def _consume(self, *, pump_frontend=True):
        if pump_frontend:
            self.term_fifo.extend(self.frontend_fifo)
            self.frontend_fifo.clear()
        raw = "".join(self.term_fifo)
        self.term_fifo.clear()
        if not raw:
            return
        for key in raw:
            self.posted.append(key)
            self._key(key)
        if self.phase == "command":
            self.screen = executor_pins.command_screen(self.state["turn"])
            self.jsonl.append(copy.deepcopy(self.state))
        else:
            self.screen = {"pack": self.pack_page, "equip": self.equip_page,
                           "building": self.building}[self.phase]


class N1bTownStops1108RecordedTest(executor_pins.ProductionHarness):

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

    def restore(self, name):
        source = FIXTURES / name
        self.journal = [json.loads(line) for line in
                        lzma.decompress((source / "journal.jsonl.xz").read_bytes()).splitlines()]
        visit = self.scratch / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((source / "policy.pkl.xz").read_bytes()))
        sidecars = json.loads(lzma.decompress((source / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(json.dumps(sidecars["manifest"]), encoding="utf-8")
        (visit / SIDECAR_DIRECTORY).mkdir()
        for role, text in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(text.encode("latin-1"))
        runtime = self.scratch / "runtime"
        runtime.mkdir()
        # DECLARED: the pickled calibration verdict is kept (no re-read of the
        # calibration file): the recorded decisions were made with it.
        return restore(visit, runtime)

    def consume(self, policy, row):
        entry = self.journal[row]
        _consume_response_sequence([line + "\n" for line in entry["inputs"]], policy,
                                   lambda _key: True, policy._monrace_knowledge,
                                   parse_snapshots=False,
                                   knowledge_ledger_path=self.scratch / "knowledge.jsonl")

    def board(self, policy, row):
        entry = self.journal[row]
        line = entry["line"] if entry["line"] is not None else entry["inputs"][-1]
        for name, value in entry["cli_latches"].items():
            setattr(policy, name, tuple(value) if isinstance(value, list) else value)
        policy.observe_store_screen(entry["store_screen_verified"])
        return parse_snapshot(json.loads(line), policy._monrace_knowledge)

    def decide(self, policy, row):
        self.consume(policy, row)
        board = self.board(policy, row)
        return board, policy.choose_key(board)

    @staticmethod
    def post(policy, key):
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def replay(self, policy, rows, *, forced=()):
        """Decide each row; a row in ``forced`` posts the recorded key."""
        for row in rows:
            _board, key = self.decide(policy, row)
            recorded = self.journal[row]
            if row not in forced:
                self.assertEqual((key, policy.last_reason),
                                 (recorded["key"], recorded["reason"]), row)
            self.post(policy, recorded["key"])

    # A ------------------------------------------------------------------

    def test_a_recorded_one_item_chooser_is_the_item_source_prompt(self):
        match = classify_screen(recorded_smith_screen())
        self.assertIs(match.kind, ScreenKind.ITEM_SOURCE, match)
        self.assertTrue(match.feature.endswith("どのアイテムを改良しますか？"))

    def test_a_recorded_raise_is_posted_through_the_one_item_chooser(self):
        policy = self.restore("a")
        self.replay(policy, range(29), forced={1})
        board, key = self.decide(policy, 29)
        self.assertEqual((key, policy.last_reason), (RAISE_KEY, "town:armor-smith:raise"))
        raw = json.loads(self.journal[29]["line"] or self.journal[29]["inputs"][-1])
        game = SmithOneItemGame(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason})
        self.assertTrue(sent, port.last_result)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.posted), RAISE_KEY)
        self.assertEqual(game.phase, "command")

    # B ------------------------------------------------------------------

    def test_b_unworn_home_spear_is_not_taken_out_to_inscribe(self):
        policy = self.restore("b")
        # The arrival policy carries the suppression latch armed on an
        # earlier visit (the recorded 21:06 take and re-deposit).
        self.assertEqual(policy._home_random_teleport_withdrawal[0], SPEAR)
        # DECLARED: the town hunt is held off (the recorded visit never hunted
        # the horse and drunk in view on its way to the inn; with C's repair
        # the staff sequence yields to that hunt, which is not this pin).
        with mock.patch.object(HengbotPolicy, "_town_kill_mob_key", lambda self, snapshot: None):
            self.replay(policy, range(19))
            board, _key = self.decide(policy, 19)
        # Recorded row 19 stepped off toward Home for the take.
        self.assertNotEqual(policy.last_reason, self.journal[19]["reason"])
        self.assertIsNone(policy._home_random_teleport_withdrawal)
        self.assertNotEqual((policy._home_pending_item or ("",))[0], SPEAR)
        self.assertFalse(any(
            owned.origin == "home" and owned.item.name == SPEAR
            for owned in policy._random_teleport_suppression_pending(board)))

    # C ------------------------------------------------------------------

    def test_c_staff_sequence_yields_to_the_town_hunt_beside_a_visible_drunk(self):
        policy = self.restore("c")
        for row in range(256):
            self.consume(policy, row)
        board, key = self.decide(policy, 256)
        drunk = next(m for m in board.visible_monsters if m.race_id == 15)
        self.assertEqual(self.journal[256]["reason"], "me-staff:return-outpost")
        self.assertEqual((key, policy.last_reason), ("9", "town:kill-mob-approach"))
        self.assertEqual(policy._town_hunt_target, drunk.position)

    # D ------------------------------------------------------------------

    def test_d_alchemist_shelf_without_the_wanted_ware_is_not_re_entered(self):
        policy = self.restore("d")
        forced = set(range(75)) - {0, 2, 4, 6, 7} - set(range(23, 36)) - {41, 42, 43, 47}
        self.replay(policy, range(75), forced=forced)
        self.assertEqual(self.journal[74]["reason"], "shop:observe-and-leave")
        # Recorded row 75: '7' shop:approach, stepping off to re-enter it.
        _board, key = self.decide(policy, 75)
        self.assertIn(STORE_ALCHEMIST, policy._town_visit_ledger.nonhome_attempted_without_effect)
        self.assertNotEqual(policy._shopping_approach_store_type, STORE_ALCHEMIST)
        self.assertEqual((key, policy.last_reason), ("\x1b`n$.", "shop:travel"))


if __name__ == "__main__":
    unittest.main()
