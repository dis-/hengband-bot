"""n1-a life-526 (2026-11-15 23:52-23:55): a carried chest's drop was never posted in town.

The warrior (Lv33) read Recall on Angband 35F carrying an unopened chest (大きな鉄の箱, slot q)
and arrived in the Outpost at [32,90].  On the arrival board the carried-chest branch of
``_chest_processing_key`` chose ``dq`` (chest:drop) and recorded the drop's origin, but the
bookkeeping rung (periodic:character-dump, decision 33210) replaced the key, so ``dq`` never
reached the game.  Every later board then found the drop "posted" and the chest still carried and
waited with '5' (chest:await-drop) for a drop that could never land: the stall detector restarted
the process twice (the fresh process repeated it under periodic:game-save / character-dump) and
retired the character.  The game lets a chest be dropped in town (cmd-item.cpp do_cmd_drop has no
town test); only the bot's record was wrong.

Fix: the drop record is bound to its decision (``_record_chest_drop``).  A replaced key withdraws it
(``withdraw_unposted_chest_drop``, beside the owner expectations' ``withdraw_unposted``), and game
time passing with the chest still carried ends the wait (any other path that keeps a drop from
the game); after CHEST_DROP_UNCONFIRMED_LIMIT such drops the carried chest is left in the pack on
that floor (a named no-step).

The boards are the capture's first three state rows (stall capture 20261115-235332), decided by
one policy through the public ``choose_key``; the drop is posted through the production executor
port.  DECLARED CONSTRUCTED: the skill-exp knowledge (the capture has no ~f list), the dump timer
request on the first board (the capture shows the dump replacing the arrival decision, 33210), and
the board after the posted drop (the capture never posted it).
"""

from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot.cli import SendResult, _ExecutorInputPort
from hengbot.model import TVAL_CHEST, parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from hengbot.policy_constants import WAIT_KEY
from hengbot.policy_identification import CHEST_DROP_UNCONFIRMED_LIMIT
from tests.support import recorded

ROOT = Path(__file__).parents[1]
RACES = load_monrace_knowledge(
    find_monrace_definitions(ROOT, None) or recorded.EDIT / "MonraceDefinitions.jsonc")

with gzip.open(Path(__file__).with_name("fixtures") / "n1a-526-chest-await-town-1116.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

DROP = "dq"


def board(index: int, *, turn_offset: int = 0) -> dict:
    raw = copy.deepcopy(CASE["boards"][index])
    raw["turn"] += turn_offset
    return raw


def new_policy(test: unittest.TestCase):
    directory = tempfile.TemporaryDirectory()
    test.addCleanup(directory.cleanup)
    return recorded._policy(Path(directory.name), RACES)


def decide(policy, raw, *, post=True):
    for _answered in range(3):
        # DECLARED CONSTRUCTED: the skill-exp cache of this board (no ~f list in the capture).
        policy._skill_exp_cache = (0, 0, raw["player"]["level"], policy._town_visit_epoch)
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        if policy.last_reason != "home:request-knowledge-scan":
            break
        # DECLARED CONSTRUCTED: the ~9 answer (the capture has no Home list; an empty Home).
        policy.confirm_key_posted(key)
        policy.consume_home_knowledge(())
    if post and key is not None:
        policy.confirm_key_posted(key)
    return key, policy.last_reason


class RecordingTest(unittest.TestCase):

    def test_the_capture_waited_in_town_with_the_chest_carried(self):
        self.assertEqual({(row["key"], row["reason"]) for row in CASE["recorded"]},
                         {(WAIT_KEY, "chest:await-drop")})
        self.assertEqual([(row["key"], row["reason"]) for row in CASE["arrival"][1:]],
                         [("~f\x1b", "periodic:skill-exp-knowledge"),
                          ("Cf\ry\x1b\x1b", "periodic:character-dump"),
                          (WAIT_KEY, "chest:await-drop")])
        for raw in CASE["boards"]:
            self.assertTrue(raw["floor"]["in_town"])
            self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (32, 90))
            self.assertEqual([item["slot"] for item in raw["inventory"]
                              if item["tval"] == TVAL_CHEST], ["q"])


class ReplayTest(unittest.TestCase):

    def test_a_replaced_drop_is_withdrawn_and_posted_on_the_next_board(self):
        policy = new_policy(self)
        policy._periodic_dump_requested = True
        self.assertEqual(decide(policy, board(0)), ("Cf\ry\x1b\x1b", "periodic:character-dump"))
        self.assertIsNone(policy._chest_drop_origin)
        self.assertEqual(decide(policy, board(1)), (DROP, "chest:drop"))

    def test_an_unposted_drop_waits_once_then_ends_when_game_time_passes(self):
        policy = new_policy(self)
        # DECLARED CONSTRUCTED: the drop key lost on its way (not confirmed, no replacement).
        self.assertEqual(decide(policy, board(0), post=False), (DROP, "chest:drop"))
        self.assertEqual(decide(policy, board(0)), (WAIT_KEY, "chest:await-drop"))
        # Board 1 is later and the chest is still carried: the drop is posted again.
        self.assertEqual(decide(policy, board(1), post=False), (DROP, "chest:drop"))
        self.assertEqual(policy._chest_drop_unconfirmed, 1)

    def test_the_carried_chest_is_left_after_the_unconfirmed_limit(self):
        policy = new_policy(self)
        reasons = []
        for attempt in range(CHEST_DROP_UNCONFIRMED_LIMIT + 2):
            key, reason = decide(policy, board(0, turn_offset=100 * attempt), post=False)
            reasons.append(reason)
        # The first drop and LIMIT - 1 repeats; the LIMIT-th unconfirmed drop ends the chest.
        self.assertEqual(reasons[:CHEST_DROP_UNCONFIRMED_LIMIT],
                         ["chest:drop"] * CHEST_DROP_UNCONFIRMED_LIMIT)
        self.assertEqual(policy._chest_drop_unconfirmed, CHEST_DROP_UNCONFIRMED_LIMIT)
        for reason in reasons[CHEST_DROP_UNCONFIRMED_LIMIT:]:
            self.assertFalse(reason.startswith("chest:"), reason)

    def test_a_landed_drop_resets_the_count(self):
        policy = new_policy(self)
        self.assertEqual(decide(policy, board(0)), (DROP, "chest:drop"))
        landed = board(1)
        landed["inventory"] = [item for item in landed["inventory"] if item["tval"] != TVAL_CHEST]
        _key, reason = decide(policy, landed)
        self.assertNotEqual(reason, "chest:await-drop")
        self.assertIsNone(policy._chest_drop_origin)
        self.assertEqual(policy._chest_drop_unconfirmed, 0)


class PostedThroughTheExecutorTest(recorded.ProductionHarness):

    def test_the_drop_reaches_the_game_after_the_replaced_board(self):
        policy = new_policy(self)
        policy._periodic_dump_requested = True
        self.assertEqual(decide(policy, board(0))[1], "periodic:character-dump")
        before = board(1)
        self.assertEqual(decide(policy, before, post=False), (DROP, "chest:drop"))
        key = DROP
        # DECLARED CONSTRUCTED: the board after the drop (the chest on the floor).
        after = board(2)
        after["inventory"] = [item for item in after["inventory"] if item["tval"] != TVAL_CHEST]
        game = recorded.FaithfulHookGame()
        game.state = copy.deepcopy(before)
        game.screen = recorded.command_screen(before["turn"])
        game.screens = [recorded.command_screen(after["turn"])]
        game.states = [copy.deepcopy(after)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, [DROP])


if __name__ == "__main__":
    unittest.main()
