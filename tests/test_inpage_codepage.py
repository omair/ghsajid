import unittest

from tools.inpage import codepage


class TestTable(unittest.TestCase):
    def test_alphabet_runs_from_alif(self):
        self.assertEqual(codepage.decode_byte(0x81), "ا")
        self.assertEqual(codepage.decode_byte(0x82), "ب")
        self.assertEqual(codepage.decode_byte(0xA0), "ن")

    def test_tail_letters_are_not_in_plain_alphabet_order(self):
        # InPage inserts noon-ghunna after noon and orders the ye/he forms
        # differently from the recited alphabet.
        self.assertEqual(codepage.decode_byte(0xA1), "ں")
        self.assertEqual(codepage.decode_byte(0xA2), "و")
        self.assertEqual(codepage.decode_byte(0xA4), "ی")
        self.assertEqual(codepage.decode_byte(0xA6), "ہ")
        self.assertEqual(codepage.decode_byte(0xA7), "ھ")

    def test_space_is_literal_ascii(self):
        self.assertEqual(codepage.decode_byte(0x20), " ")

    def test_every_entry_records_its_evidence(self):
        for code, (text, evidence) in codepage.CODEPAGE.items():
            self.assertTrue(evidence.strip(), f"{code:#04x} has no evidence note")

    def test_table_is_injective(self):
        # Gate B (round-trip) is only meaningful if no two codes share a
        # character. Genuine duplicates must be declared in ALIASES.
        seen: dict[str, int] = {}
        for code, (text, _) in codepage.CODEPAGE.items():
            if code in codepage.ALIASES:
                continue
            self.assertNotIn(
                text, seen, f"{code:#04x} collides with {seen.get(text, 0):#04x}"
            )
            seen[text] = code

    def test_encode_reverses_decode(self):
        for code in codepage.CODEPAGE:
            if code in codepage.ALIASES:
                continue
            self.assertEqual(codepage.encode_char(codepage.decode_byte(code)), code)

    def test_unmapped_reports_unknown_codes(self):
        self.assertEqual(codepage.unmapped([0x81, 0x02]), {0x02})


if __name__ == "__main__":
    unittest.main()
