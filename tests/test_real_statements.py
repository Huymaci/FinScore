"""Regression corpus: eight simulated Vietnamese bank statements.

These files carry the structures that broke the alias-based `_auto_mapping`
outright — measured before the profiler was wired in, it resolved **none** of
the eight. They are simulated data (each carries a footer saying so), which is
why they can live in the repository.

What each file contributes:

  BIDV       header on row 0, signed amounts with a " VND" suffix, timestamps
             on the date, running balance, rows ordered newest first
  VPBank     header on row 9 behind an account-details block, *two* date
             columns, running balance, a footer disclaimer row
  MB + 5     the MB template several banks reuse: header on row 18 behind a
  xlsx       bilingual letterhead, headers containing an embedded newline
             ("Ngày giao dịch\\nTransaction date"), separate debit/credit
             columns where the unused side is written "0.00" rather than left
             blank, several statement blocks separated by blank padding, and
             no balance column at all
"""
import os
import unittest

from app.services.imports import _auto_mapping, _parse_row, _table, _xlsx_rows
from app.services.statement_profiler import infer_layout

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "statements")

# filename prefix -> (expected roles, expected header row, balance provable)
EXPECTED = {
    "BIDV": ({"date": 0, "description": 1, "amount": 2, "balance": 3}, 0, True),
    "VPBank": ({"date": 0, "description": 3, "amount": 5, "balance": 6}, 9, True),
    "MB_gia": ({"date": 4, "debit": 9, "credit": 10, "description": 11}, 18, False),
    "Agribank": ({"date": 4, "debit": 9, "credit": 10, "description": 11}, 18, False),
    "MSB": ({"date": 4, "debit": 9, "credit": 10, "description": 11}, 18, False),
    "SHB": ({"date": 4, "debit": 9, "credit": 10, "description": 11}, 18, False),
    "VIB": ({"date": 4, "debit": 9, "credit": 10, "description": 11}, 18, False),
    "VietinBank": ({"date": 4, "debit": 9, "credit": 10, "description": 11}, 18, False),
}


def load(name):
    path = os.path.join(FIXTURES, name)
    content = open(path, "rb").read()
    extension = os.path.splitext(name)[1].lstrip(".")
    return _xlsx_rows(content) if extension == "xlsx" else _table(content, extension)


def corpus():
    for name in sorted(os.listdir(FIXTURES)):
        key = next((k for k in EXPECTED if name.startswith(k)), None)
        if key:
            yield name, key


class LayoutInferenceOnRealFilesTest(unittest.TestCase):
    def test_every_statement_resolves_to_the_right_columns(self):
        for name, key in corpus():
            with self.subTest(file=name):
                roles, header_row, provable = EXPECTED[key]
                result = infer_layout(load(name))
                self.assertEqual(result.header_row, header_row)
                for role, column in roles.items():
                    self.assertEqual(result.mapping.get(role), column, f"{role} in {name}")
                self.assertEqual(result.balance_verified, provable)

    def test_files_without_a_balance_column_ask_for_review(self):
        """No proof available means no claim of certainty, even when correct."""
        for name, key in corpus():
            if EXPECTED[key][2]:
                continue
            with self.subTest(file=name):
                self.assertTrue(infer_layout(load(name)).needs_human_review)


class ParsingOnRealFilesTest(unittest.TestCase):
    def _parsed(self, name):
        rows = load(name)
        mapping = _auto_mapping(rows)
        parsed, failures = [], []
        for number, row in enumerate(rows[mapping["header_rows"]:], start=mapping["header_rows"] + 1):
            if not any(str(cell).strip() for cell in row):
                continue
            try:
                parsed.append(_parse_row(row, mapping))
            except ValueError as error:
                failures.append((number, str(error)))
        return parsed, failures

    def test_blank_padding_is_not_reported_as_errors(self):
        """The sheets pad far past the last transaction and separate blocks with
        blank lines; one file produced 269 bogus "Ngày không hợp lệ" rows."""
        for name, key in corpus():
            with self.subTest(file=name):
                parsed, failures = self._parsed(name)
                self.assertGreater(len(parsed), 30)
                # VPBank ends with a "simulated data" disclaimer line.
                self.assertLessEqual(len(failures), 1, failures[:3])

    def test_incoming_rows_survive_a_zero_debit(self):
        """The MB template writes the unused side as "0.00". Testing the raw
        string made it truthy, so every credit row was charged to the debit
        branch, evaluated to zero and dropped — losing every salary received."""
        parsed, _ = self._parsed("SHB_mau_MB_logo_dung_ngan_hang_50_giao_dich.xlsx")
        incoming = [row for row in parsed if row[2] == "IN"]
        self.assertGreater(len(incoming), 5, "credit rows were dropped")
        self.assertTrue(all(row[1] > 0 for row in incoming))

    def test_totals_match_the_statement_header(self):
        """VPBank declares its own debit and credit totals. They are never used
        during parsing, so agreement is independent evidence the amounts and
        directions are right — not merely that the file parsed."""
        parsed, _ = self._parsed("VPBank_data_gia_thang_09_2025.csv")
        incoming = sum(row[1] for row in parsed if row[2] == "IN")
        outgoing = sum(row[1] for row in parsed if row[2] == "OUT")
        self.assertEqual(incoming, 11_800_000)
        self.assertEqual(outgoing, 7_289_000)
        # Opening 2,000,000 + credits - debits must reach the declared closing.
        self.assertEqual(2_000_000 + incoming - outgoing, 6_511_000)

    def test_currency_suffix_and_timestamps_parse(self):
        """BIDV writes "-139000 VND" and "16/08/2026 19:20:00"."""
        parsed, failures = self._parsed("BIDV_gia_lap_7_thang_2026.csv")
        self.assertEqual(failures, [])
        self.assertEqual(len(parsed), 43)
        self.assertTrue(any(row[2] == "IN" for row in parsed))
        self.assertTrue(any(row[2] == "OUT" for row in parsed))
