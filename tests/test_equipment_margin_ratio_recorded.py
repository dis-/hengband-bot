"""Recorded pin: the loadout combat margin is survival / kill, not the difference.

User decision 2026-10-02 18:2x (verbatim): 「指輪で優先度が低いのはどう見ても守りの
指輪。ACの評価が高すぎる。」 -> chosen option 「生存÷撃破の比で比べる」.

Live ring set on the 17:01 town board after the equipped C-sheet calibration
(the same recorded input as tests/test_calibration_crlf_dump_recorded.py):
Home 耐混乱の指輪, ダメージの指輪 (+9), worn 大防御の守りの指輪 [+19], with the live
gear.  The 30F band leaves exactly two sets (both wear 耐混乱の指輪):

    prot+rConf  survival 11.10  DPS 138.2  kill 4.50 turns
    dmg+rConf   survival 10.18  DPS 164.1  kill 3.79 turns

As a difference the protection ring won (6.600 vs 6.389, outside the 1% band);
as the ratio the damage ring wins (2.47 vs 2.69).  The pin checks the metric
and the pairwise comparison ``_prefer`` that uses it.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.equipment_optimizer import _prefer
from hengbot.policy import staged_prompt_chain_matches

import test_calibration_crlf_dump_recorded as crlf_pin

PROTECTION = "大防御の守りの指輪 [+19] {.}"
DAMAGE = "ダメージの指輪 (+9)"
RESIST_CONF = "耐混乱の指輪"


def _rings(entry) -> frozenset[str]:
    return frozenset(owned.item.name for slot, owned in entry.loadout.slots
                     if slot in {"main_ring", "sub_ring"})


class EquipmentMarginRatioRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        crlf_pin.CalibrationCrlfDumpRecordedTest.setUpClass()
        crlf = crlf_pin.CalibrationCrlfDumpRecordedTest
        stall = crlf.stall
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            policy = crlf_pin._policy(directory, crlf.monrace)
            policy._character_calibration_path.write_bytes(
                (crlf_pin.FIXTURES
                 / "town-blackmarket-stall-20261002.character-calibration.json")
                .read_bytes())
            policy._crossarea_fundraising_enforced = True  # live argv
            crlf_pin._acquire_calibration(policy, directory, crlf.monrace)
            for index in range(crlf_pin.FIRST_CHANGED + 1):
                _decoded, snapshots = _consume_response_sequence(
                    stall.segments[index], policy, lambda _key: True,
                    crlf.monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                key = policy.choose_key(snapshots[-1])
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain(
                        {"outcome": "released", "posted": str(key)})
            cls.preparation = policy._equipment_optimization_preparation
            # The worn set: every catalog item the candidates draw from the
            # equipment (only the last tie breaker of _prefer reads it).
            cls.worn_ids = frozenset(
                owned.id
                for entry in cls.preparation.result.top_candidates
                for _slot, owned in entry.loadout.slots
                if owned.origin == "equipped"
            )

    def _pair(self):
        by_rings = {}
        for entry in self.preparation.result.top_candidates:
            by_rings.setdefault(_rings(entry), entry)
        protection = by_rings[frozenset({RESIST_CONF, PROTECTION})]
        damage = by_rings[frozenset({DAMAGE, RESIST_CONF})]
        return protection, damage

    def test_live_ring_set_metrics(self):
        self.assertEqual(self.preparation.blockers, ())
        protection, damage = self._pair()
        self.assertAlmostEqual(protection.metrics.survival_turns, 11.100, places=2)
        self.assertAlmostEqual(damage.metrics.survival_turns, 10.178, places=2)
        self.assertAlmostEqual(protection.metrics.expected_dps, 138.2, places=1)
        self.assertAlmostEqual(damage.metrics.expected_dps, 164.1, places=1)

    def test_margin_is_survival_per_kill_ratio(self):
        protection, damage = self._pair()
        self.assertAlmostEqual(protection.metrics.combat_margin, 2.467, places=3)
        self.assertAlmostEqual(damage.metrics.combat_margin, 2.686, places=3)

    def test_damage_ring_set_is_preferred_to_protection_ring_set(self):
        protection, damage = self._pair()
        # Outside the 1% band in the damage ring's favour, so the comparison
        # does not fall through to the tie breakers.
        self.assertGreater(
            damage.metrics.combat_margin - protection.metrics.combat_margin,
            protection.metrics.combat_margin * 0.01,
        )
        self.assertTrue(_prefer(damage, protection, self.worn_ids))
        self.assertFalse(_prefer(protection, damage, self.worn_ids))


if __name__ == "__main__":
    unittest.main()
