import unittest
from pathlib import Path

from tools.inpage.ole import MissingStreamError, read_text_stream

TAJAWUZ = Path("inp/TAJAWUZ.INP")


@unittest.skipUnless(TAJAWUZ.exists(), "inp/ sources not present")
class TestReadTextStream(unittest.TestCase):
    def test_returns_the_inpage_text_stream(self):
        data = read_text_stream(TAJAWUZ)
        # Verified length of the InPage100 stream in this file.
        self.assertEqual(len(data), 701489)

    def test_stream_begins_with_the_known_header(self):
        data = read_text_stream(TAJAWUZ)
        self.assertEqual(data[:4], b"\x00\x00\x02\x00")


class TestMissingStream(unittest.TestCase):
    def test_raises_when_file_is_not_a_compound_file(self):
        path = Path("out/not-ole.bin")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not an ole file at all")
        with self.assertRaises(MissingStreamError):
            read_text_stream(path)


if __name__ == "__main__":
    unittest.main()
