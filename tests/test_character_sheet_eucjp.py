"""The Linux build writes the character dump in EUC-JP (2026-10-16 soak)."""
import tests  # noqa: F401
import dataclasses
import gzip
from pathlib import Path
import unittest

from hengbot.character_sheet import (SHEET_ENCODINGS, ArenaStanding, CharacterSheetUnavailable,
                                     _decode_sheet, arena_standing, parse_character_sheet)

FIXTURES = Path(__file__).parent / "fixtures"
LINUX_DUMP = FIXTURES / "character-dump-linux-eucjp-20261016.txt"
WINDOWS_DUMP = FIXTURES / "calib-equivalence" / "bot-test-234935.txt"


class LinuxCharacterDumpEncodingTest(unittest.TestCase):
    def test_linux_euc_jp_dump_parses(self):
        # The recorded Linux soak dump (Level 11 warrior): before the fix every
        # parse raised dump-encoding, so calibration never completed on Linux.
        raw = LINUX_DUMP.read_bytes()
        with self.assertRaises(UnicodeError):
            raw.decode("cp932", errors="strict")
        sheet = parse_character_sheet(raw)
        self.assertEqual(len(sheet.rows), 6)

    def test_windows_cp932_dump_still_parses_the_same(self):
        raw = WINDOWS_DUMP.read_bytes()
        self.assertEqual(parse_character_sheet(raw), parse_character_sheet(raw, encoding="cp932"))

    def test_undecodable_bytes_still_report_dump_encoding(self):
        with self.assertRaises(CharacterSheetUnavailable) as caught:
            parse_character_sheet(b"\x85\x40" * 8)  # invalid in both cp932 and EUC-JP
        self.assertEqual(str(caught.exception), "dump-encoding")


class Utf8CharacterDumpEncodingTest(unittest.TestCase):
    """Upstream develop 8c09a69b3 (e60789df3b, c57a5b4ca5) writes the dump in UTF-8 on Unix.

    No UTF-8 dump was recorded before the binary switch, so these inputs are
    constructed: each recorded dump re-encoded to UTF-8, character for character.
    """

    def _same_sheet_as_utf8(self, raw: bytes, encoding: str):
        utf8 = raw.decode(encoding, errors="strict").encode("utf-8")
        self.assertNotEqual(utf8, raw)
        original = parse_character_sheet(raw)
        rewritten = parse_character_sheet(utf8)
        # content_hash is the hash of the file's own bytes, so only it differs.
        self.assertEqual(rewritten.content_hash, parse_character_sheet(utf8, encoding="utf-8").content_hash)
        self.assertEqual(dataclasses.replace(rewritten, content_hash=original.content_hash), original)
        self.assertEqual(len(rewritten.rows), 6)

    def test_utf8_rewrite_of_linux_euc_jp_dump_parses_the_same(self):
        self._same_sheet_as_utf8(LINUX_DUMP.read_bytes(), "euc_jp")

    def test_utf8_rewrite_of_windows_cp932_dump_parses_the_same(self):
        self._same_sheet_as_utf8(WINDOWS_DUMP.read_bytes(), "cp932")

    def test_old_dumps_are_not_valid_utf8_so_they_fall_through(self):
        for path in (LINUX_DUMP, WINDOWS_DUMP):
            with self.assertRaises(UnicodeError):
                path.read_bytes().decode("utf-8", errors="strict")

    def test_arena_line_of_a_utf8_dump(self):
        raw = gzip.decompress((FIXTURES / "calib-recall-20261031.bot-test.txt.gz").read_bytes())
        utf8 = _decode_sheet(raw, ("euc_jp",)).encode("utf-8")
        self.assertEqual(arena_standing(_decode_sheet(utf8, SHEET_ENCODINGS)), ArenaStanding(wins=0))


if __name__ == "__main__":
    unittest.main()
