from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


LIVE_SAVE_PATH = Path(r"C:\hengband\BOT_PLAY")
ARCHIVE_REPOSITORY_PATH = Path(r"C:\hengband-save-archive")
SAVE_CONFIRMATION_SECONDS = 10.0


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class SaveIdentity:
    size: int
    mtime_ns: int
    sha256: str


def identify_save(path: Path) -> SaveIdentity:
    stat = path.stat()
    return SaveIdentity(stat.st_size, stat.st_mtime_ns, _digest(path))


class ArchiveRepository:
    """Copy one confirmed save and commit it without leaking failures."""

    def __init__(
        self,
        root: Path,
        *,
        git: str = "git",
        log: Callable[[str], None] = print,
    ) -> None:
        self.root = root
        self.git = git
        self.log = log

    def archive(self, live_save: Path, metadata: dict) -> bool:
        try:
            archived = self.root / "saves" / "BOT_PLAY"
            if archived.exists() and _digest(archived) == _digest(live_save):
                self.log("save archive: bytes unchanged; no commit")
                return False
            archived.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(live_save, archived)
            meta_path = self.root / "saves" / "BOT_PLAY.meta.json"
            meta_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            floor = f"{metadata['dungeon_id']}:{metadata['dungeon_level']}F"
            message = (
                f"Archive turn {metadata['turn']} floor {floor} "
                f"CL{metadata['player_level']} "
                f"HP{metadata['hp']}/{metadata['max_hp']}"
            )
            self._git("add", "--", "saves/BOT_PLAY", "saves/BOT_PLAY.meta.json")
            self._git("commit", "-m", message)
            self.log(f"save archive: committed {message}")
            return True
        except Exception as exc:
            self.log(f"save archive failed: {type(exc).__name__}: {exc}")
            return False

    def _git(self, *args: str) -> None:
        subprocess.run(
            [self.git, *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )


class SaveArchiveCoordinator:
    """Observe a posted save without sleeping and archive it off-loop."""

    def __init__(
        self,
        live_save: Path = LIVE_SAVE_PATH,
        repository: ArchiveRepository | None = None,
        *,
        confirmation_seconds: float = SAVE_CONFIRMATION_SECONDS,
        log: Callable[[str], None] = print,
    ) -> None:
        self.live_save = live_save
        self.repository = repository or ArchiveRepository(
            ARCHIVE_REPOSITORY_PATH, log=log
        )
        self.confirmation_seconds = confirmation_seconds
        self.log = log
        self._baseline: SaveIdentity | None = None
        self._deadline: float | None = None
        self._metadata: dict | None = None

    def before_post(self, snapshot, decision_sequence: int) -> None:
        try:
            self._baseline = identify_save(self.live_save)
            self._metadata = {
                "turn": snapshot.turn,
                "dungeon_id": snapshot.floor_key[0],
                "dungeon_level": snapshot.floor_key[1],
                "player_level": snapshot.player.level,
                "hp": snapshot.player.hp,
                "max_hp": snapshot.player.max_hp,
                "gold": snapshot.player.gold,
                "decision_sequence": decision_sequence,
                "bot_git_commit": self._bot_commit(),
                "timestamp": datetime.now().astimezone().isoformat(),
            }
        except Exception as exc:
            self._baseline = None
            self._metadata = None
            self.log(f"game save observation failed to start: {type(exc).__name__}: {exc}")

    def posted(self, now: float) -> None:
        if self._baseline is not None:
            self._deadline = now + self.confirmation_seconds

    def poll(self, now: float) -> None:
        if self._deadline is None:
            return
        try:
            stat = self.live_save.stat()
            if (
                self._baseline is not None
                and stat.st_size == self._baseline.size
                and stat.st_mtime_ns == self._baseline.mtime_ns
            ):
                if now >= self._deadline:
                    self.log("game save did not change within confirmation bound")
                    self._clear()
                return
            current = identify_save(self.live_save)
        except Exception as exc:
            self.log(f"game save observation failed: {type(exc).__name__}: {exc}")
            self._clear()
            return
        if current != self._baseline:
            metadata = self._metadata
            self._clear()
            if metadata is not None:
                threading.Thread(
                    target=self.repository.archive,
                    args=(self.live_save, metadata),
                    daemon=True,
                    name="hengbot-save-archive",
                ).start()
            return

    def _clear(self) -> None:
        self._baseline = None
        self._deadline = None
        self._metadata = None

    @staticmethod
    def _bot_commit() -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"
