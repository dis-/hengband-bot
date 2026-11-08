"""Importing hengbot.arena first, in a fresh interpreter, succeeds.

hengbot.arena loads me_absorbed_substitutes, which loads me_powers -> hunt_target
-> retreat_enclosure -> sealed_pocket while me_absorbed_substitutes is still
initializing.  sealed_pocket's ``from hengbot.me_absorbed_substitutes import
CAST_SUFFIX, carry_cast_key`` then raised ImportError (partially initialized
module), so test_arena_recorded failed whenever it was the first module of a
process to import hengbot.arena (the landing gate of 2026-11-08), and the
half-loaded me_powers broke later tests in the same process
(test_policy_combat's breeder walkout: no ``me_powers.power_key``).

Importing hengbot.destruction_use first (2026-11-08 landing gate,
test_destruction_use_1104_recorded) went destruction_use -> area_mapping ->
me_powers -> hunt_target -> retreat_enclosure -> sealed_pocket ->
me_absorbed_substitutes, whose import-time ``POWERS`` read ``me_powers.BY_KEY``
on the half-initialized me_powers: AttributeError.  POWERS is now built on first
use, so every module of the cycle imports first.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIRST_IMPORTS = (
    "hengbot.arena", "hengbot.me_absorbed_substitutes", "hengbot.sealed_pocket",
    "hengbot.destruction_use", "hengbot.area_mapping", "hengbot.hunt_target",
    "hengbot.retreat_enclosure", "hengbot.me_powers", "hengbot.me_device_attacks_input",
)


class ImportOrderTest(unittest.TestCase):
    def run_first(self, module):
        code = (f"import {module}\n"
                "from hengbot import me_powers, sealed_pocket\n"
                "assert callable(me_powers.power_key)\n"
                "assert callable(sealed_pocket.key)\n")
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(
            str(ROOT / part) for part in ("src", "tests", "scripts", ".")))
        return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                              capture_output=True, text=True, encoding="utf-8")

    def test_each_module_of_the_cycle_imports_first(self):
        for module in FIRST_IMPORTS:
            result = self.run_first(module)
            self.assertEqual(result.returncode, 0, f"{module}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
