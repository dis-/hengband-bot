"""Blind or confused with no curing potion: a carried curing mushroom is eaten.

n1-a life-533 (Warrior Lv22) died 2026-11-22 15:15 on Orc Cave 19F, killed by gibbering mouthers
(race 253): blind and confused for 145 turns with no potion left, it walked the latched return
(return:explore), fled and struck blind (emergency:blind-strike) while a Mushroom of Cure Serious
Wounds (cmd-eat.cpp: cure_serious_wounds, which clears blindness and confusion,
spells-status.cpp:362-376) sat in slot a.  No rule ate a curing mushroom.  Owner 2026-11-07
(design 4.2) 「逃げる手段を取り戻すのが先」: the cure comes before the strike and the wait; the board
after it decides the escape (a scroll is readable again).

The live mushroom was unknown (``aware`` false: a flavour never identified; the death dump names
it because death identifies the pack), so this fix alone would not have eaten it -- the control
below keeps that record.

Recorded: n1-a life-533's town-arrival checkpoint and the capture's 19F boards from turn 443605 to
443865 (tests/fixtures/n1a-533-cure-mushroom-1122), decided through the public ``choose_key``
with the recorded keys posted.

DECLARED CONSTRUCTED: in the second replay the slot-a mushroom is made known (``aware``, sval 16,
the name the death dump gives it); the eat prompt and the following board of the executor pin.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import status_cure
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import TVAL_FOOD, parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load
from tests.support import recorded as executor_pins

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-533-cure-mushroom-1122"
RETURN_WALK = 443624   # blind and confused, the latched return's walk
EMERGENCY = 443865     # blind and confused, the emergency tier's blind strike
CONFUSED_ONLY = 443615  # confused, the cornered attack
EAT_PROMPT = "どれを食べますか? "
SV_FOOD_CURE_SERIOUS = 16


def _post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def _known_mushroom(raw):
    """DECLARED CONSTRUCTED: the slot-a mushroom known as the death dump names it."""
    raw = copy.deepcopy(raw)
    for item in raw["inventory"]:
        if item["tval"] == TVAL_FOOD and not item.get("aware"):
            item.update(aware=True, sval=SV_FOOD_CURE_SERIOUS, name="重傷の治癒のキノコ")
    return raw


def _replay(scratch: Path, *, known: bool):
    policy, _journal, steps = load(FIXTURE, scratch)
    floor = json.loads(lzma.decompress((FIXTURE / "floor.json.xz").read_bytes()).decode(
        "utf-8", "surrogateescape"))
    replayed, boards = {}, {}
    with contextlib.redirect_stdout(io.StringIO()):
        for recorded, supply in steps:
            policy.choose_key(supply())
            _post(policy, recorded["key"])
        for raw, recorded in zip(floor["boards"], floor["decisions"]):
            assert raw["turn"] == recorded["turn"], (raw["turn"], recorded["turn"])
            raw = _known_mushroom(raw) if known else raw
            board = parse_snapshot(raw, policy._monrace_knowledge)
            key = policy.choose_key(board)
            replayed[raw["turn"]] = ((key, policy.last_reason), (recorded["key"], recorded["reason"]))
            boards[raw["turn"]] = (raw, board)
            _post(policy, recorded["key"])
    return policy, replayed, boards


class CureMushroom1122RecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        root = Path(cls.scratch.name)
        cls.record_policy, cls.record, cls.record_boards = _replay(root / "record", known=False)
        cls.policy, cls.known, cls.known_boards = _replay(root / "known", known=True)

    @classmethod
    def tearDownClass(cls):
        for policy in (cls.record_policy, cls.policy):
            policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_record_unknown_mushroom_is_not_eaten(self):
        _raw, board = self.record_boards[EMERGENCY]
        [mushroom] = [item for item in board.inventory if item.tval == TVAL_FOOD]
        self.assertEqual((mushroom.slot, mushroom.aware), ("a", False))
        self.assertTrue(board.player.blind and board.player.confused)
        self.assertIsNone(status_cure.cure_potion(self.record_policy, board))
        for turn, recorded in ((RETURN_WALK, ("6", "return:explore")),
                               (EMERGENCY, ("+6", "emergency:blind-strike")),
                               (CONFUSED_ONLY, ("6", "flee:cornered-attack"))):
            decided, record = self.record[turn]
            self.assertEqual(record, recorded, turn)
            self.assertEqual(decided, record, turn)

    def test_the_known_mushroom_is_eaten_before_the_return_walk(self):
        # Before: ('6', 'return:explore'), blind and confused with no potion.
        self.assertEqual(self.known[RETURN_WALK][0], ("Ea", status_cure.CURE_MUSHROOM_REASON))
        self.assertEqual(self.known[CONFUSED_ONLY][0], ("Ea", status_cure.CURE_MUSHROOM_REASON))

    def test_the_known_mushroom_is_eaten_before_the_emergency_blind_strike(self):
        # Before: ('+6', 'emergency:blind-strike').
        self.assertEqual(self.known[EMERGENCY][0],
                         ("Ea", status_cure.EMERGENCY_CURE_MUSHROOM_REASON))

    def test_the_eat_is_posted_through_the_production_executor(self):
        raw, board = self.known_boards[EMERGENCY]
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        # DECLARED CONSTRUCTED: the eat prompt and the following board.
        after = copy.deepcopy(raw)
        after["turn"] += 10
        game.screens = [executor_pins.prompt_screen(EAT_PROMPT),
                        executor_pins.command_screen(after["turn"])]
        game.states = [copy.deepcopy(raw), after]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", "Ea", None, set(), in_store=False,
            decision={"sequence": self.policy._decision_sequence,
                      "reason": status_cure.EMERGENCY_CURE_MUSHROOM_REASON},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        # Sent whole, as the hunger rungs' eat is: the eat prompt is no staged item source.
        self.assertEqual(game.accepted, ["Ea"])


if __name__ == "__main__":
    unittest.main()
