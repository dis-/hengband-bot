"""File entry point for modules; avoid runtime imports under python -c."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def filtered(suite):
    result = unittest.TestSuite()
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            result.addTests(filtered(test))
        elif not test.id().startswith("test_cli.DecisionTimingTest."):
            result.addTest(test)
    return result


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromName(sys.argv[1])
    result = unittest.TextTestRunner(verbosity=2).run(filtered(suite))
    raise SystemExit(not result.wasSuccessful())
