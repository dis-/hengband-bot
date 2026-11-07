"""The Magic-Eater's loadout scores INT through the absorbed-power fail rate (owner 2026-11-08).

Owner: 「魔道具術師の装備の評価に、知能（取り込んだ力の失敗率）を入れますか？」 ->
「失敗率を評価に入れる」 (「魔道具術師では、知能の上がり下がりで変わる取り込んだ力の
失敗率を評価に加え、知能を上げる装備を高く見る。」).

n1-b life-339 (Magic-Eater Lv29, INT 16) wore ☆『ラバー・コート』 [6,+12] (+3)
{+賢魅r電冷恐} and had shelved ★『ホルヘンネス』 [5,+10] (+2) {+知賢探赤r暗盲;視}:
the shared warrior evaluator never read INT.  With +2 INT (16 -> 18/00) every
absorbed power's fail floor drops from 8% to 6% and the Dragon's Flame wand
from 46% to 43% (cmd-magiceat.cpp:255-275, 476-490).

Owner, on the 3-AC result: 「ACの評価が高すぎる。知力と盲目耐性の方を重くみる
計算式を考えて。」 -> 「魔法成功率は生存に貢献する別枠で評価。盲目耐性は逃走手段の
確実化ということで別枠で評価。点数の付け方は任せるが、AC3という微差よりは大きく
評価すること。」 (me_loadout_offense.survival_factor).

Recorded: the town-arrival checkpoint and its first 45 journal rows
(tests/extract_me_int_loadout_fixture.py), decided through the public
chooser; rows 9-15 scan the Home and the optimizer runs on the full catalog.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import hengbot.policy  # noqa: F401 -- import order (circular import when run alone)
from hengbot import me_device_attacks
from hengbot.cli import _consume_response_sequence
from hengbot.equipment_optimizer import Loadout, current_loadout
from hengbot.me_loadout_offense import (
    absorbed_power_fail_percent,
    held_attack_powers,
    offense_inputs,
)
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST
from hengbot.warrior_loadout_evaluator import CachedWarriorLoadoutEvaluator
from replay_town_arrival import adopt_calibration, restore


FIXTURES = Path(__file__).with_name("fixtures") / "me-int-loadout-1108"
SCANNED_ROWS = 17
RUBBER_COAT = "☆鋼鉄ヘルメット『ラバー・コート』"
HOLHENNETH = "★鉄ヘルメット『ホルヘンネス』"
MIGHTY = 1  # player-personality-types.h PERSONALITY_MIGHTY: to_m_chance +1


def _journal() -> list[dict]:
    return [json.loads(line) for line in
            lzma.decompress((FIXTURES / "journal.jsonl.xz").read_bytes()).splitlines()]


class MeIntLoadoutRecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.journal = _journal()
        cls.sidecars = json.loads(lzma.decompress((FIXTURES / "sidecars.json.xz").read_bytes()))

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def restore(self):
        visit = self.scratch / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((FIXTURES / "policy.pkl.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(
            json.dumps(self.sidecars["manifest"]), encoding="utf-8")
        (visit / SIDECAR_DIRECTORY).mkdir()
        for role, text in self.sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(text.encode("latin-1"))
        runtime = self.scratch / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        # The live process's calibration and session id (as the arrival read them).
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path", runtime)
        # The arrival's long Home history must not outlive this test.
        self.addCleanup(lambda: policy._home_disposal.history_path.unlink(missing_ok=True))
        return policy

    def decide(self, policy, row):
        entry = self.journal[row]
        inputs = [line + "\n" for line in entry["inputs"]]
        _consume_response_sequence(inputs, policy, lambda _key: True, policy._monrace_knowledge,
                                   parse_snapshots=False,
                                   knowledge_ledger_path=self.scratch / "knowledge.jsonl")
        line = entry["line"] if entry["line"] is not None else entry["inputs"][-1]
        for name, value in entry["cli_latches"].items():
            setattr(policy, name, tuple(value) if isinstance(value, list) else value)
        policy.observe_store_screen(entry["store_screen_verified"])
        board = parse_snapshot(json.loads(line), policy._monrace_knowledge)
        return board, policy.choose_key(board)

    @staticmethod
    def post(policy, key):
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def scanned(self):
        """Replay rows 0-16 through the public chooser (each must match the record)."""
        policy = self.restore()
        board = None
        for row in range(SCANNED_ROWS):
            board, key = self.decide(policy, row)
            self.assertEqual((key, policy.last_reason),
                             (self.journal[row]["key"], self.journal[row]["reason"]), row)
            self.post(policy, key)
        self.assertTrue(policy._equipment_catalog.home_scan_complete)
        return policy, board

    @staticmethod
    def helmets(policy):
        """The optimizer's best loadout (head: the Rubber Coat) and the same with Holhenneth."""
        items = policy._equipment_catalog.items
        best = policy._equipment_optimization_preparation.result.best.loadout
        holhenneth = next(item for item in items if item.item.name.startswith(HOLHENNETH))
        swapped = Loadout(tuple(sorted(
            ((slot, holhenneth if slot == "head" else item) for slot, item in best.slots),
            key=lambda entry: entry[0])), best.hand_mode)
        return best, swapped

    def test_the_fail_formula_reproduces_every_displayed_attack_row(self):
        policy = self.restore()
        rows = 0
        for kind, (_turn, listed) in policy._me_device_lists.items():
            for row in listed:
                power = me_device_attacks._BY_NAME.get((kind, row["name"]))
                if power is None:
                    continue
                rows += 1
                # The worn set has no EASY_SPELL / DEC_MANA / HARD_SPELL; INT 16.
                self.assertEqual(absorbed_power_fail_percent(
                    kind, power.level, 29, 16, personality_id=MIGHTY), row["fail"], row["name"])
        self.assertEqual(rows, 8)
        # Hand-computed from cmd-magiceat.cpp at INT 18/00 (adj_mag_stat 3,
        # adj_mag_fail 6): Dragon's Flame 50*4/5+20 -6 -3*(29-25) +1 = 43.
        self.assertEqual(absorbed_power_fail_percent("wand", 50, 29, 18, personality_id=MIGHTY), 43)
        self.assertEqual(absorbed_power_fail_percent("wand", 2, 29, 18, personality_id=MIGHTY), 6)
        # A rod's level is level*5/6-5 (Lightning Bolts 20 -> 11): 8+20-6-3*(29-5)+1 -> floor 6.
        self.assertEqual(absorbed_power_fail_percent("rod", 20, 29, 18, personality_id=MIGHTY), 6)
        # mod_spell_chance_1/2: EASY_SPELL -3, DEC_MANA -2 then -1, HARD_SPELL +20 then +5.
        self.assertEqual(absorbed_power_fail_percent("wand", 50, 29, 16, personality_id=MIGHTY,
                                                     flags=frozenset({39})), 43)
        self.assertEqual(absorbed_power_fail_percent("wand", 50, 29, 16, personality_id=MIGHTY,
                                                     flags=frozenset({70})), 43)
        self.assertEqual(absorbed_power_fail_percent("wand", 50, 29, 16, personality_id=MIGHTY,
                                                     flags=frozenset({135})), 71)
        self.assertEqual(absorbed_power_fail_percent("wand", 75, 1, 3, flags=frozenset({135})), 100)
        self.assertEqual(held_attack_powers(policy._me_device_lists), (
            ("rod", 15), ("rod", 21), ("wand", 7), ("wand", 14), ("wand", 15), ("wand", 16),
            ("wand", 26)))

    def test_int_raises_the_magic_eater_score_on_the_recorded_visit(self):
        policy, board = self.scanned()
        self.assertEqual(board.player.class_id, 16)
        self.assertEqual(board.player.stat_use[1], 16)
        preparation = policy._equipment_optimization_preparation
        best = preparation.result.best
        # The live optimizer path (policy_equipment -> prepare_warrior_optimization)
        # now carries the held attack powers into the evaluator.
        self.assertGreater(best.metrics.device_dps, 0)
        evaluator = policy._warrior_evaluator_cache.evaluator
        self.assertEqual(evaluator.inputs.magic_eater.powers,
                         held_attack_powers(policy._me_device_lists))
        worn, swapped = self.helmets(policy)
        self.assertTrue(worn.item_at("head").item.name.startswith(RUBBER_COAT))
        self.assertTrue(current_loadout(policy._equipment_catalog.items).item_at("head")
                        .item.name.startswith(RUBBER_COAT))
        rubber = evaluator(worn).metrics
        self.assertEqual(rubber, best.metrics)
        holhenneth = evaluator(swapped).metrics
        self.assertEqual(holhenneth.expected_dps, rubber.expected_dps)
        self.assertAlmostEqual(rubber.device_dps, 62.717, places=2)
        self.assertAlmostEqual(holhenneth.device_dps, 65.721, places=2)
        self.assertGreater(holhenneth.device_dps, rubber.device_dps)
        # Owner 2026-11-08 「魔法成功率は生存に貢献する別枠で評価。盲目耐性は逃走手段の
        # 確実化ということで別枠で評価。…AC3という微差よりは大きく評価すること。」
        # Without the two survival terms the 3 AC of the Rubber Coat won by
        # 1.06% (1.40907 vs 1.39419).  Rubber: power success x1 (INT 16) and
        # 30.3% of the set can blind it (x0.9697); Holhenneth: x1.0294 (INT
        # 18/00) and blind-proof.
        self.assertAlmostEqual(rubber.combat_margin, 1.36640, places=4)
        self.assertAlmostEqual(holhenneth.combat_margin, 1.43520, places=4)
        self.assertGreater(holhenneth.combat_margin / rubber.combat_margin, 1.05)
        # DECLARED: this first search varies one slot from the worn set (the
        # catalog crossed the incremental threshold), so it pairs Holhenneth
        # with the old boots and lamp and picks the Rubber Coat with the speed
        # boots; the next search (row 42) wears Holhenneth: see
        # test_the_next_search_fetches_holhenneth_from_home.
        self.assertTrue(best.loadout.item_at("head").item.name.startswith(RUBBER_COAT))

    def test_each_survival_term_alone_outweighs_three_ac(self):
        policy, _board = self.scanned()
        evaluator = policy._warrior_evaluator_cache.evaluator
        worn, swapped = self.helmets(policy)
        rubber = worn.item_at("head")
        holhenneth = swapped.item_at("head")

        def head(base, **changes):
            flags = changes.pop("flags", base.item.known_flags)
            item = replace(base.item, known_flags=flags, **changes)
            loadout = Loadout(tuple(sorted(
                ((slot, replace(base, id=base.id + "-v", item=item) if slot == "head" else owned)
                 for slot, owned in worn.slots), key=lambda entry: entry[0])), worn.hand_mode)
            return evaluator(loadout).metrics.combat_margin

        base = evaluator(worn).metrics.combat_margin
        three_ac = 1.40907 / 1.39433  # the Rubber Coat's AC 18 -> 15 alone (1.06%)
        # DECLARED CONSTRUCTED variants of the worn Rubber Coat.
        # +2 INT only (its WIS/CHR replaced): the power-success term alone.
        int_only = head(rubber, pval=2, flags=(rubber.flags - {2, 5}) | {1})
        self.assertAlmostEqual(int_only / base, 1.0294, places=3)
        self.assertGreater(int_only / base, three_ac)
        # Resist blindness only: the escape-reliability term alone.
        blind_only = head(rubber, flags=rubber.flags | {56})
        self.assertAlmostEqual(blind_only / base, 1 / (1 - 0.10 * 0.3028), places=3)
        self.assertGreater(blind_only / base, three_ac)
        # No absurd trade: +1 INT (16 -> 17, one fail-floor step) is less than
        # the 3 AC, and Holhenneth stripped of 15 AC loses to the Rubber Coat.
        plus_one = head(rubber, pval=1, flags=(rubber.flags - {2, 5}) | {1})
        self.assertLess(plus_one / base, three_ac)
        self.assertLess(head(holhenneth, ac=0, to_a=0), base)

    def test_the_next_search_fetches_holhenneth_from_home(self):
        """Rows 17-41 replay the recorded boots / lamp transaction; the search
        that follows from the new worn set now wears Holhenneth, so row 44
        walks back to Home (recorded: the old evaluator left for the shops)."""
        policy = self.restore()
        for row in range(42):
            _board, key = self.decide(policy, row)
            self.assertEqual((key, policy.last_reason),
                             (self.journal[row]["key"], self.journal[row]["reason"]), row)
            self.post(policy, key)
        _board, key = self.decide(policy, 42)
        self.assertEqual(key, self.journal[42]["key"])
        best = policy._equipment_optimization_preparation.result.best
        self.assertTrue(best.loadout.item_at("head").item.name.startswith(HOLHENNETH))
        self.post(policy, key)
        _board, key = self.decide(policy, 43)
        self.assertEqual(key, self.journal[43]["key"])
        self.post(policy, key)
        _board, key = self.decide(policy, 44)
        self.assertEqual(self.journal[44]["reason"], "shop:travel")
        self.assertEqual(policy.last_reason, "town:entrance-step-off:equipment-transaction:approach-home")

    def test_device_output_breaks_a_tie_toward_int_and_spares_other_classes(self):
        policy, _board = self.scanned()
        evaluator = policy._warrior_evaluator_cache.evaluator
        worn, swapped = self.helmets(policy)
        # Every other class: no device output, the metrics are as before.
        warrior = CachedWarriorLoadoutEvaluator(
            replace(evaluator.inputs, magic_eater=None), evaluator.encounters)
        self.assertEqual(warrior(worn).metrics.device_dps, 0.0)
        self.assertEqual(warrior(swapped).metrics.device_dps, 0.0)
        # ... and no survival terms: the 3-AC Rubber Coat keeps its margin.
        self.assertAlmostEqual(warrior(worn).metrics.combat_margin, 1.40907, places=4)
        self.assertAlmostEqual(warrior(swapped).metrics.combat_margin, 1.39419, places=4)
        self.assertIsNone(offense_inputs(0, 29, 55, -6, MIGHTY, (("wand", 26),)))
        # DECLARED CONSTRUCTED: the two helmets with equal non-INT metrics --
        # the optimizer's comparison then prefers the INT one.
        from hengbot.equipment_optimizer import EvaluatedLoadout, _stable_operational_best
        rubber = evaluator(worn).metrics
        tied = replace(evaluator(swapped).metrics, survival_turns=rubber.survival_turns,
                       utility_value=rubber.utility_value,
                       combat_margin=rubber.combat_margin, secondary_value=rubber.secondary_value)
        chosen = _stable_operational_best(
            [EvaluatedLoadout(worn, rubber), EvaluatedLoadout(swapped, tied)], worn.item_ids)
        self.assertTrue(chosen.loadout.item_at("head").item.name.startswith(HOLHENNETH))


if __name__ == "__main__":
    unittest.main()
