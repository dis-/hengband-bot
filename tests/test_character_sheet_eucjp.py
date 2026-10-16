"""The Linux build writes the character dump in EUC-JP (2026-10-16 soak)."""
import tests  # noqa: F401
from pathlib import Path
import unittest

from hengbot.character_sheet import CharacterSheetUnavailable, parse_character_sheet

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


if __name__ == "__main__":
    unittest.main()
