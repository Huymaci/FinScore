"""Layout inference across incompatible bank statement formats.

The fixtures are deliberately hostile: unknown header wording, preamble rows,
no header at all, Excel-native cell types, and amounts that collide with the
Excel date-serial range. Each one is a format the alias-matching approach in
`_auto_mapping` cannot handle.
"""
import unittest
from datetime import date, timedelta

from app.services.statement_profiler import (
    column_uses_date_serials,
    detect_date_order,
    detect_number_convention,
    fingerprint,
    infer_layout,
    parse_number,
    to_import_mapping,
)


def walk(seed, rows=25, start=50_000_000):
    """Movements plus the running balance a real statement would print."""
    out, balance, day, rnd = [], start, date(2026, 3, 2), seed
    for index in range(rows):
        rnd = (rnd * 1103515245 + 12345) % 2147483648
        amount = ((rnd >> 7) % 4_000_000) + 20_000
        inflow = (rnd >> 3) % 5 == 0
        signed = amount if inflow else -amount
        balance += signed
        out.append((day + timedelta(days=index), signed, balance,
                    f"GD {index:03d} {'LUONG' if inflow else 'THANH TOAN'}", f"FT{rnd % 10**8:08d}"))
    return out


class LayoutInferenceTest(unittest.TestCase):
    def assert_mapping(self, grid, expected, proved=None):
        result = infer_layout(grid)
        for role, column in expected.items():
            self.assertEqual(result.mapping.get(role), column,
                             f"role {role!r}: got {result.mapping.get(role)}, want {column}")
        if proved is not None:
            self.assertEqual(result.balance_verified, proved)
        return result

    def test_signed_amount_without_balance(self):
        grid = [["Ngày", "Nội dung", "Số tiền", "Số tham chiếu"]]
        for day, signed, _balance, description, reference in walk(7):
            grid.append([day.strftime("%d/%m/%Y"), description,
                         f"{signed:,}".replace(",", "."), reference])
        self.assert_mapping(grid, {"date": 0, "description": 1, "amount": 2})

    def test_preamble_rows_and_debit_credit_columns(self):
        grid = [["NGÂN HÀNG TMCP KỸ THƯƠNG VIỆT NAM"], ["Chủ tài khoản: NGUYEN VAN A"],
                ["Từ 02/03/2026 đến 26/03/2026"], [],
                ["Ngày GD", "Số CT", "Diễn giải", "Ghi nợ", "Ghi có", "Số dư"]]
        for day, signed, balance, description, reference in walk(11):
            grid.append([day.strftime("%d/%m/%Y"), reference, description,
                         f"{abs(signed):,}" if signed < 0 else "",
                         f"{signed:,}" if signed > 0 else "", f"{balance:,}"])
        result = self.assert_mapping(grid, {"date": 0, "debit": 3, "credit": 4, "balance": 5}, proved=True)
        self.assertEqual(result.header_row, 4, "must skip the bank letterhead")

    def test_unknown_headers_are_resolved_by_arithmetic(self):
        """No header here appears in any alias list, and the dates are mm/dd."""
        grid = [["TXN_DT", "SEQ", "BAL_AFT", "MEMO", "MVMT", "FX_RT"]]
        for day, signed, balance, description, reference in walk(23):
            grid.append([day.strftime("%m/%d/%Y"), reference, f"{balance:.2f}",
                         description, f"{signed:.2f}", "1.00"])
        self.assert_mapping(grid, {"date": 0, "amount": 4, "balance": 2}, proved=True)

    def test_excel_native_types_with_serial_dates(self):
        epoch = date(1899, 12, 30)
        grid = [["Date", "Description", "Debit", "Credit", "Balance"]]
        for day, signed, balance, description, _reference in walk(31):
            grid.append([(day - epoch).days, description,
                         abs(signed) if signed < 0 else None,
                         signed if signed > 0 else None, balance])
        self.assert_mapping(grid, {"date": 0, "debit": 2, "credit": 3, "balance": 4}, proved=True)

    def test_no_header_row_at_all(self):
        grid = [[day.strftime("%d/%m/%Y"), description, signed, balance, reference]
                for day, signed, balance, description, reference in walk(41)]
        self.assert_mapping(grid, {"date": 0, "amount": 2, "balance": 3}, proved=True)

    def test_sparse_credit_column_is_still_a_candidate(self):
        """A salary account may show a single inflow in the whole period."""
        grid = [["Ngay", "Dien giai", "Ghi no", "Ghi co", "So du"]]
        balance = 20_000_000
        for index in range(20):
            inflow = index == 7
            signed = 15_000_000 if inflow else -300_000
            balance += signed
            grid.append([f"{index+1:02d}/05/2026", f"GD {index}",
                         "" if inflow else 300_000, 15_000_000 if inflow else "", balance])
        self.assert_mapping(grid, {"date": 0, "debit": 2, "credit": 3, "balance": 4}, proved=True)


class RefusalTest(unittest.TestCase):
    """Knowing when to say "I am not sure" matters as much as being right."""

    def test_decoy_column_loses_to_the_invariant(self):
        grid = [["Ngay", "Dien giai", "So tien", "Phi", "So du"]]
        balance = 10_000_000
        for index in range(20):
            amount = -100_000 - index * 1000
            balance += amount
            grid.append([f"{index+1:02d}/04/2026", f"GD {index}", amount, amount - 500, balance])
        result = infer_layout(grid)
        self.assertEqual(result.mapping["amount"], 2)
        self.assertTrue(result.balance_verified)

    def test_ambiguous_file_is_flagged_for_review(self):
        grid = [["Ngay", "Dien giai", "Cot A", "Cot B"]]
        for index in range(20):
            grid.append([f"{index+1:02d}/04/2026", f"GD {index}",
                         -100_000 - index * 1000, -55_000 - index * 700])
        result = infer_layout(grid)
        self.assertFalse(result.balance_verified)
        self.assertTrue(result.needs_human_review)
        self.assertLess(result.confidence, 0.75)

    def test_tampered_balance_is_not_claimed_as_proved(self):
        grid = [["Ngay", "Dien giai", "So tien", "So du"]]
        balance = 10_000_000
        for index in range(20):
            balance -= 100_000
            if index == 10:
                balance -= 777_777  # a movement that no row accounts for
            grid.append([f"{index+1:02d}/04/2026", f"GD {index}", -100_000, balance])
        self.assertFalse(infer_layout(grid).balance_verified)

    def test_empty_and_tiny_sheets_raise(self):
        with self.assertRaises(ValueError):
            infer_layout([])
        with self.assertRaises(ValueError):
            infer_layout([["Ngay", "So tien"]])


class ColumnLevelDecisionTest(unittest.TestCase):
    """Ambiguity that is unresolvable per cell but decidable per column."""

    def test_number_convention_is_decided_once_per_column(self):
        self.assertEqual(detect_number_convention(["1.234.567", "2.000.000"]), "vn")
        self.assertEqual(detect_number_convention(["1,234,567", "2,000,000"]), "en")
        self.assertEqual(parse_number("1.234.567", "vn"), 1234567.0)
        self.assertEqual(parse_number("1,234,567", "en"), 1234567.0)

    def test_date_order_resolved_by_any_unambiguous_cell(self):
        self.assertEqual(detect_date_order(["01/02/2026", "13/02/2026"]), "dmy")
        self.assertEqual(detect_date_order(["01/02/2026", "02/13/2026"]), "mdy")

    def test_amounts_in_the_serial_range_are_not_dates(self):
        """46,083 VND is a valid Excel date serial; a column decides which."""
        amounts = [46083, 51200, 39400, 68000, 44100]
        self.assertFalse(column_uses_date_serials(amounts),
                         "an amount column must not be read as dates")
        span = [46083, 46084, 46085, 46086, 46087]
        self.assertTrue(column_uses_date_serials(span),
                        "a tight run of serials is a real date column")

    def test_reference_codes_are_not_numbers(self):
        self.assertIsNone(parse_number("FT01261800"))
        self.assertIsNone(parse_number("GD 001 THANH TOAN"))
        self.assertEqual(parse_number("1500000 VND"), 1500000.0)


class TemplateReuseTest(unittest.TestCase):
    def setUp(self):
        self.grid = [["Ngay", "Dien giai", "So tien", "So du"]]
        balance = 5_000_000
        for index in range(15):
            balance -= 50_000
            self.grid.append([f"{index+1:02d}/06/2026", f"GD {index}", -50_000, balance])

    def test_fingerprint_is_stable_and_layout_specific(self):
        other = [["Date", "Memo", "Amount", "Balance"]] + self.grid[1:]
        self.assertEqual(fingerprint(self.grid, 0), fingerprint(self.grid, 0))
        self.assertNotEqual(fingerprint(self.grid, 0), fingerprint(other, 0))

    def test_export_shape_matches_what_imports_expects(self):
        mapping = to_import_mapping(infer_layout(self.grid))
        self.assertEqual(mapping["header_rows"], 1)
        self.assertEqual(mapping["date"], 0)
        self.assertEqual(mapping["amount"], 2)
        self.assertIn("%d/%m/%Y", mapping["date_formats"])
        self.assertIn("number_convention", mapping)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class BalanceConventionTest(unittest.TestCase):
    """Banks disagree on where the balance sits and which way rows are sorted.

    These are conventions, not formats: the arithmetic is intact in each case,
    only the pair of rows to compare moves. The invariant picks the convention
    itself, so none of these needs a per-bank template either.
    """

    @staticmethod
    def _rows(seed=15):
        return walk(seed)

    def test_balance_printed_before_the_transaction(self):
        grid = [["Ngay", "Noi dung", "So tien", "So du truoc GD"]]
        balance = 50_000_000
        for day, signed, _after, description, _reference in self._rows():
            grid.append([day.strftime("%d/%m/%Y"), description, f"{signed:,}", f"{balance:,}"])
            balance += signed
        result = infer_layout(grid)
        self.assertTrue(result.balance_verified)
        self.assertEqual(result.mapping["amount"], 2)
        self.assertEqual(result.mapping["balance"], 3)

    def test_statement_sorted_newest_first(self):
        grid = [["Ngay", "Noi dung", "So tien", "So du"]]
        for day, signed, balance, description, _reference in reversed(self._rows(21)):
            grid.append([day.strftime("%d/%m/%Y"), description, f"{signed:,}", f"{balance:,}"])
        result = infer_layout(grid)
        self.assertTrue(result.balance_verified)
        self.assertEqual(result.mapping["balance"], 3)


class NoProofAvailableTest(unittest.TestCase):
    """Without a usable balance column the mapping may still be right, but the
    system must say so rather than claim certainty. Every case here is expected
    to resolve correctly *and* ask for confirmation.
    """

    def _assert_correct_but_unproved(self, grid, expected):
        result = infer_layout(grid)
        for role, column in expected.items():
            self.assertEqual(result.mapping.get(role), column)
        self.assertFalse(result.balance_verified)
        self.assertTrue(result.needs_human_review)

    def test_no_header_and_no_balance(self):
        grid = [[day.strftime("%d/%m/%Y"), description, f"{signed:,}", reference]
                for day, signed, _b, description, reference in walk(5)]
        self._assert_correct_but_unproved(grid, {"date": 0, "amount": 2})

    def test_positive_amounts_with_a_separate_indicator_column(self):
        grid = [["Ngay", "Noi dung", "So tien", "Loai"]]
        for day, signed, _b, description, _r in walk(9):
            grid.append([day.strftime("%d/%m/%Y"), description, f"{abs(signed):,}",
                         "D" if signed < 0 else "C"])
        self._assert_correct_but_unproved(grid, {"date": 0, "amount": 2})

    def test_too_few_rows_to_prove_anything(self):
        grid = [["Ngay", "Noi dung", "So tien", "So du"]]
        for day, signed, balance, description, _r in walk(33, rows=3):
            grid.append([day.strftime("%d/%m/%Y"), description, f"{signed:,}", f"{balance:,}"])
        self._assert_correct_but_unproved(grid, {"date": 0, "amount": 2})


class HeaderIndependenceTest(unittest.TestCase):
    """The defence question: is ROLE_HINTS a per-bank template in disguise?

    If it were, deleting it would degrade the result. It does not: on any file
    carrying a balance column the header text contributes nothing, because the
    arithmetic decides. This test fails if someone later makes the header hints
    load-bearing.
    """

    @staticmethod
    def _statement(headers):
        grid = [list(headers)]
        for day, signed, balance, description, _reference in walk(23):
            grid.append([day.strftime("%d/%m/%Y"), description, f"{signed:,}", f"{balance:,}"])
        return grid

    def test_result_is_identical_without_any_header_hints(self):
        import app.services.statement_profiler as profiler

        grid = self._statement(["Ngay", "Noi dung", "So tien", "So du"])
        with_hints = infer_layout(grid)
        original = profiler.ROLE_HINTS
        try:
            profiler.ROLE_HINTS = {role: () for role in original}
            without_hints = infer_layout(grid)
        finally:
            profiler.ROLE_HINTS = original
        self.assertEqual(with_hints.mapping, without_hints.mapping)
        self.assertTrue(without_hints.balance_verified)

    def test_meaningless_headers_still_resolve(self):
        grid = self._statement(["QWXZ", "KJVB", "ZKQW", "VBXJ"])
        result = infer_layout(grid)
        self.assertTrue(result.balance_verified)
        self.assertEqual(result.mapping["amount"], 2)
        self.assertEqual(result.mapping["balance"], 3)
