import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.save_archive import (
    ArchiveRepository,
    SaveArchiveCoordinator,
    SaveIdentity,
)


class SaveArchiveTest(unittest.TestCase):
    def _repository(self, root: Path, log: list[str]) -> ArchiveRepository:
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True,
                       capture_output=True)
        subprocess.run(["git", "config", "user.name", "Archive Test"], cwd=root,
                       check=True)
        subprocess.run(["git", "config", "user.email", "archive@example.invalid"],
                       cwd=root, check=True)
        return ArchiveRepository(root, log=log.append)

    @staticmethod
    def _metadata() -> dict:
        return {
            "turn": 1234,
            "dungeon_id": 7,
            "dungeon_level": 42,
            "player_level": 31,
            "hp": 287,
            "max_hp": 301,
            "gold": 45678,
            "decision_sequence": 99,
            "bot_git_commit": "abc123",
            "timestamp": "2026-08-11T12:34:56+09:00",
        }

    def test_unchanged_bytes_produce_no_commit(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            logs: list[str] = []
            repository = self._repository(root, logs)
            live = root / "live-save"
            archived = root / "saves" / "BOT_PLAY"
            archived.parent.mkdir()
            live.write_bytes(b"same save")
            archived.write_bytes(b"same save")

            self.assertFalse(repository.archive(live, self._metadata()))
            count = subprocess.run(
                ["git", "rev-list", "--count", "--all"], cwd=root,
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            self.assertEqual(count, "0")
            self.assertIn("bytes unchanged", logs[-1])

    def test_changed_bytes_commit_save_and_matching_metadata(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            logs: list[str] = []
            repository = self._repository(root, logs)
            live = root / "live-save"
            live.write_bytes(b"new save bytes")
            metadata = self._metadata()

            self.assertTrue(repository.archive(live, metadata))
            self.assertEqual((root / "saves" / "BOT_PLAY").read_bytes(), b"new save bytes")
            written = json.loads(
                (root / "saves" / "BOT_PLAY.meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(written, metadata)
            subject = subprocess.run(
                ["git", "log", "-1", "--format=%s"], cwd=root,
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            self.assertEqual(subject, "Archive turn 1234 floor 7:42F CL31 HP287/301")

    def test_missing_git_is_logged_and_does_not_raise(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            logs: list[str] = []
            live = root / "live-save"
            live.write_bytes(b"save")
            repository = ArchiveRepository(
                root / "archive", git="definitely-absent-git", log=logs.append
            )

            self.assertFalse(repository.archive(live, self._metadata()))
            self.assertIn("save archive failed", logs[-1])

    def test_poll_retries_transient_save_absence_and_access_denial(self):
        class TransientPath:
            def __init__(self):
                self.failures = [FileNotFoundError("rename"), PermissionError("scan")]

            def stat(self):
                if self.failures:
                    raise self.failures.pop(0)
                return type("Stat", (), {"st_size": 4, "st_mtime_ns": 2})()

        live = TransientPath()
        coordinator = SaveArchiveCoordinator(live_save=live)
        coordinator._baseline = SaveIdentity(4, 1, "old")
        coordinator._deadline = 10.0
        coordinator._metadata = self._metadata()

        coordinator.poll(1.0)
        coordinator.poll(2.0)

        self.assertEqual(coordinator._baseline, SaveIdentity(4, 1, "old"))
        self.assertEqual(coordinator._deadline, 10.0)
        self.assertEqual(live.failures, [])


if __name__ == "__main__":
    unittest.main()
