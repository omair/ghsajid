import unittest
from pathlib import Path

from tools.inpage import inpage3
from tools.inpage.classify import SEPARATOR_TEXT
from tools.inpage.ole import format_of
from tools.inpage.segment import segment

EAADA = Path("in/EAADA - COMPLETE + sanjh.inp")


def utf16(text: str) -> bytes:
    return text.encode("utf-16-le")


class TestStructure(unittest.TestCase):
    """InPage 3 states its structure; this reads it, and synthesises the
    geometry the rest of the pipeline expects from an InPage 1 book."""

    def test_a_sher_is_two_lines_and_a_blank_ends_it(self):
        paragraphs = inpage3.decode(
            utf16("پہلا مصرع\rدوسرا مصرع\r\rتیسرا مصرع\rچوتھا مصرع\r")
        )
        self.assertEqual(
            [p.geometry for p in paragraphs],
            [
                inpage3.FIRST_MISRA, inpage3.SECOND_MISRA,
                inpage3.FIRST_MISRA, inpage3.SECOND_MISRA,
            ],
        )

    def test_the_blank_itself_is_not_a_paragraph(self):
        # It is a sher boundary, and the boundary now lives in `geometry`.
        paragraphs = inpage3.decode(utf16("ایک\rدو\r\r\r\rتین\rچار\r"))
        self.assertEqual([p.text for p in paragraphs], ["ایک", "دو", "تین", "چار"])

    def test_a_blank_resynchronises_the_pairing(self):
        # An odd number of lines before a blank must not shift every sher
        # after it — the blank says where the next one starts.
        paragraphs = inpage3.decode(utf16("ایک\rدو\rتین\r\rچار\rپانچ\r"))
        self.assertEqual(
            [p.geometry for p in paragraphs],
            [
                inpage3.FIRST_MISRA, inpage3.SECOND_MISRA, inpage3.FIRST_MISRA,
                inpage3.FIRST_MISRA, inpage3.SECOND_MISRA,
            ],
        )

    def test_the_ornament_becomes_the_separator_the_classifier_knows(self):
        paragraphs = inpage3.decode(utf16("ایک\rدو\r\rO\rتین\rچار\r"))
        self.assertEqual(paragraphs[2].text, SEPARATOR_TEXT)
        # and it re-opens the pairing, so the next poem starts on a first misra
        self.assertEqual(paragraphs[3].geometry, inpage3.FIRST_MISRA)


class TestTextRegion(unittest.TestCase):
    """The stream interleaves text with an offset table and formatting
    records, so the text has to be found by what it looks like."""

    def test_finds_text_between_binary_records(self):
        noise = bytes(200)
        body = utf16("پہلا مصرع یہاں ہے اور کافی لمبا ہے\rدوسرا مصرع بھی\r" * 12)
        start, end = inpage3.text_region(noise + body + noise)
        found = (noise + body + noise)[start:end].decode("utf-16-le", "replace")
        self.assertIn("پہلا مصرع", found)
        self.assertIn("دوسرا مصرع", found)

    def test_the_edges_are_not_clipped_mid_line(self):
        # A window is a blunt edge: اِعادہ lost its opening epigraph and the
        # closing lines of its last ghazal before the bounds were walked out
        # one code unit at a time.
        body = utf16("سب سے پہلا مصرع جو ضائع نہیں ہونا چاہیے\r" + "درمیانی مصرع یہاں\r" * 60 + "سب سے آخری مصرع\r")
        start, end = inpage3.text_region(bytes(64) + body + bytes(64))
        found = (bytes(64) + body + bytes(64))[start:end].decode("utf-16-le", "replace")
        self.assertIn("سب سے پہلا مصرع", found)
        self.assertIn("سب سے آخری مصرع", found)

    def test_a_stream_with_no_text_reports_none(self):
        self.assertEqual(inpage3.text_region(bytes(4096)), (0, 0))


@unittest.skipUnless(EAADA.exists(), "in/ sources not present")
class TestEaadaTheBook(unittest.TestCase):
    """اِعادہ, published on its own in 2017, against its own فہرست.

    This book is why the format was worth reading. InPage 1 keeps digits out
    of the text stream, so a کلیات's index arrives with every page number and
    count stripped — جلد ۱'s had to be photographed. An InPage 3 book carries
    its فہرست intact, and اِعادہ's numbers its poems 1 to 100.
    """

    @classmethod
    def setUpClass(cls):
        cls.paragraphs = inpage3.decode(inpage3.read_text(EAADA))
        cls.segments = segment(cls.paragraphs, explicit_pieces=True)

    def test_the_file_is_recognised_as_inpage_3(self):
        self.assertEqual(format_of(EAADA), "inpage3")

    def test_its_fihrist_numbers_a_hundred_poems(self):
        import re

        texts = [p.text for p in self.paragraphs]
        numbered = [t for t in texts if re.fullmatch(r"\d+۔", t)]
        self.assertEqual(len(numbered), 100)
        self.assertEqual(
            [int(t[:-1]) for t in numbered], list(range(1, 101))
        )

    def test_it_segments_into_the_hundred_its_fihrist_declares(self):
        ghazals = [s for s in self.segments if s.kind == "ghazals"]
        self.assertEqual(len(ghazals), 100)

    def test_the_year_and_publisher_survive_the_decode(self):
        # What InPage 1 would have thrown away.
        joined = "\n".join(p.text for p in self.paragraphs[:40])
        self.assertIn("2017", joined)
        self.assertIn("سانجھ", joined)


if __name__ == "__main__":
    unittest.main()
