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
        data = _pairs([0x81, 0x20]) + _para_mark(67)
        self.assertEqual(decode(data)[0].geometry, 67)

    def test_splits_on_every_paragraph_mark(self):
        data = (_pairs([0x81, 0x20]) + _para_mark(63)
                + _pairs([0x82, 0x20]) + _para_mark(65))
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
        # 0xE0 is a real but still-unidentified character code, not a control
        # byte: it must survive into `codes` so gate B can round-trip it.
        data = _pairs([0x81, 0xE0]) + _para_mark(63)
        para = decode(data)[0]
        self.assertEqual(para.text, "ا")
        self.assertEqual(para.codes, [0x81, 0xE0])

    def test_trailing_text_without_a_final_mark_still_emits(self):
        self.assertEqual([p.text for p in decode(_pairs([0x81, 0x20]))], ["ا"])

    def test_reverses_a_ltr_digit_run(self):
        # 0xD5 0xD8 0xD9 0xD1 stores 1985 left-to-right, so it must come out
        # reversed: ۱۹۸۵, not the stream order ۵۸۹۱.
        data = _pairs([0xD5, 0xD8, 0xD9, 0xD1]) + _para_mark(10)
        self.assertEqual(decode(data)[0].text, "۱۹۸۵")

    def test_single_digit_is_unaffected_by_reversal(self):
        data = _pairs([0x81, 0xD5, 0x82]) + _para_mark(10)
        self.assertEqual(decode(data)[0].text, "ا۵ب")

    def test_reverses_each_run_independently_and_leaves_letters_in_place(self):
        # Two digit runs either side of a word: only the digit runs flip.
        data = _pairs([0xD8, 0xD2, 0x81, 0x82, 0xD5, 0xD1]) + _para_mark(10)
        self.assertEqual(decode(data)[0].text, "۲۸اب۱۵")

    def test_digit_reversal_keeps_raw_and_codes_in_lockstep(self):
        # Gate B re-encodes `raw` against `codes`; whatever order the digits
        # end up in, codes must carry the matching byte at each position so
        # decode_byte(codes[i]) still reproduces raw[i].
        data = _pairs([0xD5, 0xD8, 0xD9, 0xD1]) + _para_mark(10)
        para = decode(data)[0]
        from tools.inpage.codepage import decode_byte
        self.assertEqual("".join(decode_byte(c) for c in para.codes), para.raw)

    def test_drops_paragraph_with_no_mapped_codes(self):
        # A pure layout record: every code is unmapped, so nothing decodes.
        data = _pairs([0xE0, 0xE8]) + _para_mark(10)
        self.assertEqual(decode(data), [])

    def test_keeps_paragraph_with_one_mapped_code_among_unmapped(self):
        # Real text with rare unmapped punctuation must survive — never drop
        # on a ratio or threshold, only when nothing at all maps.
        data = _pairs([0xE0, 0x81, 0xE8]) + _para_mark(10)
        paras = decode(data)
        self.assertEqual(len(paras), 1)
        self.assertEqual(paras[0].text, "ا")

    def test_drops_an_isolated_pair_as_a_layout_record(self):
        # A lone (0x04, code) pair with no adjacent pair is a 0x04 byte the
        # walker met inside a layout record, not a character. Here the 0x04
        # sits in the middle of a four-byte record, so only the two-pair run
        # that follows is text.
        data = b"\xff\xff\x04\x81\xff\xff" + _pairs([0x82, 0x83]) + _para_mark(10)
        self.assertEqual([p.text for p in decode(data)], ["بپ"])

    def test_keeps_a_run_of_two_pairs(self):
        # Two contiguous pairs are the shortest genuine text run: the corpus
        # spells `ے `, `اب` and the `۱۔` of a table of contents that way.
        data = _pairs([0x81, 0x82]) + _para_mark(10)
        self.assertEqual([p.text for p in decode(data)], ["اب"])

    def test_drops_control_codes_from_codes_entirely(self):
        # Codes below 0x20 are stream control bytes, never characters, so they
        # must not reach `codes` either — gate B compares `raw` against
        # `codes`, and an excluded byte decodes to nothing on both sides.
        data = _pairs([0x81, 0x00, 0x82]) + _para_mark(10)
        para = decode(data)[0]
        self.assertEqual(para.text, "اب")
        self.assertEqual(para.codes, [0x81, 0x82])


@unittest.skipUnless(TAJAWUZ.exists(), "inp/ sources not present")
class TestDecodeRealFile(unittest.TestCase):
    def test_recovers_the_opening_of_the_preface(self):
        paras = decode(read_text_stream(TAJAWUZ))
        joined = "\n".join(p.text for p in paras)
        self.assertIn("غلام حسین ساجد", joined)

    def test_all_codes_reports_every_text_code(self):
        codes = all_codes(read_text_stream(TAJAWUZ))
        self.assertGreater(len(codes), 30_000)


MAZAMEER_1 = Path("inp/MAZAMEER (1).INP")


@unittest.skipUnless(MAZAMEER_1.exists(), "inp/ sources not present")
class TestDecodeRealDates(unittest.TestCase):
    def test_a_real_colophon_year_decodes_forwards(self):
        # Byte-verified in Task 4: the colophon after نومبر stores 1985 as
        # D5 D8 D9 D1, left-to-right, so it must decode to ۱۹۸۵.
        paras = decode(read_text_stream(MAZAMEER_1))
        joined = "\n".join(p.text for p in paras)
        self.assertIn("۱۹۸۵", joined)
        self.assertNotIn("۵۸۹۱", joined)


if __name__ == "__main__":
    unittest.main()
