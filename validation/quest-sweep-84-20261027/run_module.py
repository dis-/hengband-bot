"""File-based runner for derived modules; keep verify_scope's one exclusion."""
import sys
import unittest

import tests  # noqa: F401 -- runtime isolation before test discovery


def filtered(suite):
    result = unittest.TestSuite()
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            result.addTests(filtered(test))
        elif ".DecisionTimingTest." not in test.id():
            result.addTest(test)
    return result


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromName(sys.argv[1])
    outcome = unittest.TextTestRunner(verbosity=2).run(filtered(suite))
    sys.exit(not outcome.wasSuccessful())
