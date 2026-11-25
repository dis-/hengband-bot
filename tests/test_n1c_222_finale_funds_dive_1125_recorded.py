"""The finale's Black Market gold from a dive, not from 1F mining (n1-c life-222, 2026-11-25).

Owner 2026-11-25, verbatim: 「決戦用の資金調達は分かったが、1F採掘は明らかに効率が悪いので適当な
ダンジョンに潜って稼いでくれ」 (finale_bm_tour ``_funds_key``).

What happened: n1-c life-222 (Magic-Eater Lv49, Angband recall depth 95, preparing the finale) owned
8 of the 30 Healing and 8 of the 15 *Healing*, the supplies only the Black Market sells.  The
Black Markets' circuit sold Home's rings (to 42,504 gold) and at 20:10:50 (turn 8354703) handed a
mining run over for the next leg's 49,993 (``town:entrance-step-off:town:finale-hold:
bm-funds-fundraise:49993``): the Yeek cave 1F, the run's ascent back to town, the circuit and its
Black Market again, the next run -- town and 1F about every 10 s.  Now the circuit yields its
departure to the ordinary one, which reads the recall to its own destination (Angband 95F).

Recorded: tests/fixtures/n1c-222-finale-funds-dive-1125.json.gz (the 20:10:50 board,
tests/extract_n1c_222_finale_funds_dive_1125_fixture.py) and the absorbed power lists of the same
life (tests/fixtures/n1c-222-me-lists-1125.json, 13:20 that day).  A fresh policy primes on the
board and decides it once through the public ``choose_key``.

DECLARED CONSTRUCTED: the circuit's record as the decision log shows it on that board
(``cross_town_shopping.finale_bm_tour``: lap 2, the Outpost and Morivant seen, the prices seen);
the visit's departure conjuncts ready (the recorded decision was the departure's own:
``rung: town-errand:departure``; a fresh policy has no Home catalogue); the absorbed *Destruction*
already refilled at the inn (``me_inn_refill.destruction_key`` none); in
``test_a_refused_recall_keeps_the_fundraising_run`` Angband's recall depth set to 96.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import gzip
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import angband_finale, finale_bm_tour, finale_hold, home_cash_sale, me_inn_refill
from hengbot.me_device_attacks import observe_lists
from hengbot.model import DUNGEON_ANGBAND, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import WAIT_KEY
from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).with_name("fixtures")
with gzip.open(FIXTURES / "n1c-222-finale-funds-dive-1125.json.gz", "rt", encoding="utf-8") as _stream:
    BOARD = json.load(_stream)
LISTS = json.loads((FIXTURES / "n1c-222-me-lists-1125.json").read_text(encoding="utf-8"))["lists"]
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
GOLD = 42504
# The decision log's circuit on the board (cross_town_shopping.finale_bm_tour).
PRICES = {angband_finale.RESISTANCE: 5886, angband_finale.HEALING: 7063,
          angband_finale.RESTORE_MANA: 23546, angband_finale.STAR_HEALING: 35319}


class FinaleFundsDive1125RecordedTest(unittest.TestCase):
    def arrange(self, raw=None):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        raw = copy.deepcopy(raw or BOARD)
        policy = _policy(Path(scratch.name), MONRACE)
        board = parse_snapshot(copy.deepcopy(raw), MONRACE)
        policy.prime(board)
        for kind in ("staff", "wand", "rod"):
            listed = dict(copy.deepcopy(raw), turn=raw["turn"] - 1,
                          _magic_eater_power_list={"kind": kind, "rows": LISTS[kind]})
            observe_lists(policy, parse_snapshot(listed, MONRACE))
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        with contextlib.redirect_stdout(io.StringIO()):
            policy.choose_key(board)
        # DECLARED CONSTRUCTED (module docstring): the circuit as recorded.
        tour = finale_bm_tour._start(policy, board)
        tour.lap, tour.seen = 2, [2, 0]
        tour.laps = [{"lap": 1, "seen": [0, 1, 2, 3], "bought": 4}]
        tour.prices = dict(PRICES)
        conjuncts = policy._recall_town_departure_conjuncts
        policy._recall_town_departure_conjuncts = (
            lambda snapshot, **kw: {name: True for name in conjuncts(snapshot, **kw)})
        return policy, board, tour

    def departure(self, policy, board):
        policy.last_reason = None
        with mock.patch.object(me_inn_refill, "destruction_key", return_value=None), \
                contextlib.redirect_stdout(io.StringIO()):
            key = policy._town_special_key(board)
        return key, policy.last_reason

    def test_short_of_gold_the_departure_recalls_to_its_destination(self):
        policy, board, tour = self.arrange()
        self.assertEqual(board.player.gold, GOLD)
        self.assertEqual(board.dungeon_recall_depths.get(DUNGEON_ANGBAND), 95)
        self.assertFalse(finale_hold.applies(policy, board))
        self.assertTrue(finale_hold.black_market_due(policy, board))
        self.assertFalse(home_cash_sale.pending(policy, board))

        key, reason = self.departure(policy, board)

        # Recorded: (WAIT, 'town:finale-hold:bm-funds-fundraise:49993') and the mining run handed
        # over (fundraising mode 'prepare', then 'mine' on the Yeek cave 1F).
        self.assertIsNone(policy._fundraising_mode)
        self.assertIsNone(tour.fundraise_target)
        self.assertFalse(str(reason).startswith(finale_bm_tour.FUNDRAISE_REASON))
        self.assertGreater(tour.funds_needed, GOLD)
        self.assertEqual(tour.dive_target, tour.funds_needed)
        self.assertTrue(finale_bm_tour.diving(policy, board))
        # The ordinary departure's own destination: the recall to Angband (95F).
        self.assertEqual(policy._town_recall_destination(board), ("angband", DUNGEON_ANGBAND))
        self.assertEqual(reason, "town:recall-to-angband")
        self.assertNotEqual(key, WAIT_KEY)
        self.assertEqual(policy._town_recall_issue_watch[0], DUNGEON_ANGBAND)

    def test_the_gold_reached_resumes_the_circuit(self):
        policy, board, tour = self.arrange()
        self.departure(policy, board)
        target = tour.dive_target
        raw = copy.deepcopy(BOARD)
        raw["player"]["gold"] = target
        richer = parse_snapshot(raw, MONRACE)
        self.assertFalse(finale_bm_tour.diving(policy, richer))

        with contextlib.redirect_stdout(io.StringIO()):
            finale_bm_tour.town_key(policy, richer)

        # The next leg's travel (the circuit's own), the dive over.
        self.assertIsNone(tour.dive_target)
        self.assertIsNone(tour.closed)
        self.assertIsNone(policy._fundraising_mode)

    def test_a_refused_recall_keeps_the_fundraising_run(self):
        raw = copy.deepcopy(BOARD)
        # DECLARED CONSTRUCTED (module docstring): Angband's recall refused for its depth.
        raw["progress"]["dungeon_recall_depths"][str(DUNGEON_ANGBAND)] = 96
        policy, board, tour = self.arrange(raw)
        self.assertTrue(finale_hold.applies(policy, board))

        finale_bm_tour._funds_key(policy, board, tour, GOLD + 1)

        self.assertIsNone(tour.dive_target)
        self.assertFalse(finale_bm_tour.diving(policy, board))
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertEqual(policy.last_reason, f"{finale_bm_tour.FUNDRAISE_REASON}:{GOLD + 1}")


if __name__ == "__main__":
    unittest.main()
