"""scripts/search_ban_lint.py: every sender of the search key asks search_ban (owner 2026-11-23
「99F 100Fはサーチ禁止」).  The repository passes; an unguarded sender fails (revert-proof); a
sender behind the ban's ``if`` or its early ``return`` passes."""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import search_ban_lint as lint  # noqa: E402


def _findings(source):
    with TemporaryDirectory() as directory:
        Path(directory, "sender.py").write_text(source, encoding="utf-8")
        return lint.findings(Path(directory), readers={})


class SearchBanLintTest(unittest.TestCase):
    def test_repository_passes(self):
        self.assertEqual(lint.findings(), [])

    def test_unguarded_sender_fails(self):
        found = _findings("def key(policy, snapshot):\n    return SEARCH_KEY\n")
        self.assertEqual(len(found), 1, found)
        found = _findings("def key(policy, snapshot):\n    return 's'\n")
        self.assertEqual(len(found), 1, found)
        # A ban asked elsewhere in the function does not guard this send.
        found = _findings("def key(policy, snapshot):\n    search_ban.banned(snapshot)\n"
                          "    return CHEST_SEARCH_KEY\n")
        self.assertEqual(len(found), 1, found)

    def test_guarded_senders_pass(self):
        self.assertEqual(_findings(
            "def key(policy, snapshot):\n    if search_ban.banned(snapshot):\n        return None\n"
            "    return SEARCH_KEY\n"), [])
        self.assertEqual(_findings(
            "def key(policy, snapshot):\n    if search_ban.banned(snapshot):\n        pass\n"
            "    elif policy.walls:\n        return SEARCH_KEY\n"), [])
        self.assertEqual(_findings(
            "def key(policy, snapshot):\n    if policy.n < 8 and not search_ban.banned(snapshot):\n"
            "        return SEARCH_KEY\n"), [])

    def test_module_level_alias_fails(self):
        found = _findings("WAIT = SEARCH_KEY\n")
        self.assertEqual(len(found), 1, found)


if __name__ == "__main__":
    unittest.main()
