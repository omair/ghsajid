import struct
import unittest
from pathlib import Path

from tools.inpage.decode import all_codes, decode
from tools.inpage.ole import read_text_stream

TAJAWUZ = Path("inp/TAJAWUZ.INP")


def _pairs(text_codes: list[int]) -> bytes:
    return b"".join(bytes([0x04, code]) for code in text_codes)


def _para_mark(geometry: int) -> bytes:
    return b"\x0d" + struct.pack("<I", geometry)


class TestDecode(unittest.TestCase):
    def test_decodes_a_pair_run_into_text(self):
        data = _pairs([0x81, 0x20, 0x82]) + _para_mark(65)
        paras = decode(data)
        self.assertEqual(len(paras), 1)
        self.assertEqual(paras[0].text, "ا ب")

    def test_carries_the_geometry_of_the_paragraph_mark(self):
        data = _pairs([0x81]) + _para_mark(67)
        self.assertEqual(decode(data)[0].geometry, 67)

    def test_splits_on_every_paragraph_mark(self):
        data = _pairs([0x81]) + _para_mark(63) + _pairs([0x82]) + _para_mark(65)
        self.assertEqual([p.text for p in decode(data)], ["ا", "ب"])

    def test_keeps_raw_codes_for_the_round_trip_gate(self):
        data = _pairs([0x81, 0x82]) + _para_mark(63)
        self.assertEqual(decode(data)[0].codes, [0x81, 0x82])

    def test_raw_keeps_surrounding_spaces_that_text_strips(self):
        data = _pairs([0x20, 0x81, 0x20]) + _para_mark(63)
        para = decode(data)[0]
        self.assertEqual(para.text, "ا")
        self.assertEqual(para.raw, " ا ")

    def test_unmapped_code_becomes_empty_text_but_is_kept_in_codes(self):
        data = _pairs([0x81, 0x02]) + _para_mark(63)
        para = decode(data)[0]
        self.assertEqual(para.text, "ا")
        self.assertEqual(para.codes, [0x81, 0x02])

    def test_trailing_text_without_a_final_mark_still_emits(self):
        self.assertEqual([p.text for p in decode(_pairs([0x81]))], ["ا"])


@unittest.skipUnless(TAJAWUZ.exists(), "inp/ sources not present")
class TestDecodeRealFile(unittest.TestCase):
    def test_recovers_the_opening_of_the_preface(self):
        paras = decode(read_text_stream(TAJAWUZ))
        joined = "\n".join(p.text for p in paras)
        self.assertIn("غلام حسین ساجد", joined)

    def test_all_codes_reports_every_text_code(self):
        codes = all_codes(read_text_stream(TAJAWUZ))
        self.assertGreater(len(codes), 30_000)


if __name__ == "__main__":
    unittest.main()
