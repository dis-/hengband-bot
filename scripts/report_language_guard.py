#!/usr/bin/env python3
"""Claude Code Stop hook: refuse to end a turn whose report is not in Japanese.

User decision 2026-09-24: 「報告は日本語で。」 - repeated more than once, so it is
enforced mechanically here as well as written in the project CLAUDE.md.

Reads the Stop hook JSON on stdin (``transcript_path``, ``stop_hook_active``),
takes the text of the last assistant message of the turn (text blocks only;
tool calls and thinking are ignored), removes what may legitimately be English
(code, paths, URLs, hashes, link targets), and counts letters: Japanese
(hiragana, katakana, CJK ideographs) against Latin.  When there are enough
letters to judge and the Japanese share is too low it exits 2 with a Japanese
message on stderr, which Claude Code feeds back to the assistant.

Exits 0 in every other case: when ``stop_hook_active`` is set (it can never
loop), when the kill switch ``jsonlog/turn-end-guard.disabled`` exists, and -
failing open, with a note on stderr - when the input or transcript cannot be
read.  A broken guard must not trap the session.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Operator-tooling thresholds (not game policy).  Measured 2026-09-24 on the
# 3,838 judgeable final messages of all 22 C--hengband session transcripts,
# after the stripping below:
#   * Japanese reports - dense with file names, hashes and code terms such as
#     "A-round review 進行中。CLEAN → push → B(ARB-2)dispatch へ" - bottomed
#     out at 0.236.  The only Japanese text below 0.20 (0.165) was a message
#     that had an English system notification pasted into it.
#   * English reports sat at 0.00-0.16 (51 messages below 0.20).  Six short
#     English progress lines carrying one long Japanese noun ("12/16 written
#     (＋最大MPへの装備重量ペナルティ)") scored 0.23-0.33 and pass: an accepted
#     miss, since the gap between the two populations closes there.
# MIN_LETTERS: a one-liner such as "push 済み" or "OK" is too short to judge.
MIN_LETTERS = 40
MIN_JAPANESE_SHARE = 0.20

KILL_SWITCH = Path("jsonlog") / "turn-end-guard.disabled"

_FENCED = re.compile(r"(```|~~~).*?(\1|\Z)", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_LINK_TARGET = re.compile(r"\]\([^)\s]*\)")
_URL = re.compile(r"\b(?:https?|ftp|file)://\S+", re.IGNORECASE)
_WINDOWS_PATH = re.compile(r"(?:\b[A-Za-z]:|\\\\)[\\/][^\s`'\"<>|*?]*")
# Any token with a slash or backslash inside is a path or a ref (a/b, src/x.py).
_SLASHED = re.compile(r"[^\s`'\"<>()\[\]、。（）「」]*[\\/][^\s`'\"<>()\[\]、。（）「」]*")
_FILE_NAME = re.compile(r"\b[\w.-]+\.(?:py|ps1|psm1|json|jsonl|jsonc|md|txt|cpp|hpp|h|c|"
                        r"cs|js|ts|toml|yaml|yml|ini|cfg|log|exe|dll|bat|cmd|sh|zip|lock|"
                        r"hold|pid|disabled|tmp)\b", re.IGNORECASE)
_HASH = re.compile(r"\b[0-9a-fA-F]{7,40}\b")
# Code terms and labels: snake_case, tokens with a digit (r3, C4a, ARB-2,
# stall-13), ALL-CAPS labels (CLEAN, BLOCKER, CI) and camelCase/PascalCase.
_IDENTIFIER = re.compile(r"(?<![A-Za-z0-9])(?:"
                         r"[A-Za-z0-9-]*_[A-Za-z0-9_-]*"
                         r"|[A-Za-z-]*[0-9][A-Za-z0-9-]*"
                         r"|[A-Z]{2,}(?:-[A-Z]+)*s?"
                         r"|[A-Za-z]*[a-z][A-Z][A-Za-z]*"
                         r")(?![A-Za-z0-9])")

_JAPANESE = re.compile(r"[぀-ゟ゠-ヿㇰ-ㇿｦ-ﾟ"
                       r"㐀-䶿一-鿿豈-﫿々〆]")
_LATIN = re.compile(r"[A-Za-zＡ-Ｚａ-ｚ]")


def strip_legitimate_english(text: str) -> str:
    """Remove the spans that may be English in a Japanese report."""
    for pattern in (_FENCED, _INLINE_CODE, _LINK_TARGET, _URL, _WINDOWS_PATH,
                    _SLASHED, _FILE_NAME, _HASH, _IDENTIFIER):
        text = pattern.sub(" ", text)
    return text


def measure(text: str) -> tuple[int, int]:
    """(Japanese letters, Latin letters) of the stripped text."""
    stripped = strip_legitimate_english(text)
    return len(_JAPANESE.findall(stripped)), len(_LATIN.findall(stripped))


def verdict(text: str) -> tuple[bool, int, int]:
    """(ok, japanese, latin): ok is False only for a judgeable non-Japanese text."""
    japanese, latin = measure(text)
    total = japanese + latin
    if total < MIN_LETTERS:
        return True, japanese, latin
    return japanese / total >= MIN_JAPANESE_SHARE, japanese, latin


def _text_blocks(entry: dict) -> list[str]:
    message = entry.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    return [block.get("text", "") for block in content
            if isinstance(block, dict) and block.get("type") == "text"
            and isinstance(block.get("text"), str)]


def last_assistant_text(transcript: Path) -> str:
    """The text the assistant ended the turn with.

    Claude Code writes one transcript line per content block, so the final
    message is the run of assistant entries after the last user entry (a
    prompt or a tool result).
    """
    entries = []
    with transcript.open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            # API error lines are written by the client, not the assistant.
            if (isinstance(entry, dict) and not entry.get("isSidechain")
                    and not entry.get("isApiErrorMessage")):
                entries.append(entry)
    parts: list[str] = []
    for entry in reversed(entries):
        kind = entry.get("type")
        if kind == "user":
            break
        if kind == "assistant":
            parts[:0] = _text_blocks(entry)
    return "\n".join(part for part in parts if part)


def _force_utf8_output() -> None:
    """Claude Code reads hook output as UTF-8 whatever the console codec is.

    Left alone, Python writes stderr in the console's code page (cp932 on this
    host, or whatever PYTHONIOENCODING says), and the Japanese blocking message
    would reach the assistant as mojibake.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def main(argv=None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]),
                        help="repository root holding jsonlog/ (for the kill switch)")
    arguments = parser.parse_args(argv)

    if (Path(arguments.root) / KILL_SWITCH).exists():
        return 0
    try:
        raw = sys.stdin.buffer.read().decode("utf-8-sig")
        payload = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError) as error:
        print(f"report-language guard: stdin unreadable, not checking ({error})", file=sys.stderr)
        return 0
    if not isinstance(payload, dict):
        return 0
    if payload.get("stop_hook_active"):
        return 0
    path = payload.get("transcript_path")
    if not path:
        print("report-language guard: no transcript_path, not checking", file=sys.stderr)
        return 0
    try:
        text = last_assistant_text(Path(path))
    except (OSError, UnicodeError) as error:
        print(f"report-language guard: transcript unreadable, not checking ({error})",
              file=sys.stderr)
        return 0

    ok, japanese, latin = verdict(text)
    if ok:
        return 0
    message = (
        "報告が日本語になっていません（コード・パス・ハッシュを除いた文字のうち日本語 "
        f"{japanese} 字、英字 {latin} 字）。ユーザーの決定「報告は日本語で。」に従い、"
        "直前の報告を日本語で書き直してください。コード・パス・コミット名はそのままで構いません。"
        f"（停止スイッチ: {Path(arguments.root) / KILL_SWITCH}）"
    )
    print(message, file=sys.stderr, flush=True)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
