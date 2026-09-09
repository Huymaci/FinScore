import unittest
from datetime import datetime
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import Category, Transaction
from config import TestConfig

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
PASSWORD = "StrongPass1!"


class TransactionDateRangeApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        db.session.add(Category(id=1, name="Ăn uống", nature="DISCRETIONARY"))
        db.session.commit()
        self.client = self.app.test_client()
        self.client.post(
            "/auth/register",
            json={
                "email": "range@example.com",
                "password": PASSWORD,
                "full_name": "Nguyễn An",
                "date_of_birth": "1995-04-10",
                "consent": True,
            },
        )
        self.client.post("/auth/login", json={"email": "range@example.com", "password": PASSWORD})
        response = self.client.post(
            "/accounts",
            json={"name": "Ví", "type": "CASH", "opening_balance": 1_000_000},
        )
        self.account_id = response.get_json()["id"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def create_transaction(self, posted, description):
        response = self.client.post(
            "/transactions",
            json={
                "date": posted,
                "amount": 10_000,
                "direction": "OUT",
                "account_id": self.account_id,
                "category_id": 1,
                "description": description,
            },
        )
        self.assertEqual(response.status_code, 201, response.get_json())

    def test_range_can_span_months_and_includes_both_boundaries(self):
        self.create_transaction("2026-07-31", "Before")
        self.create_transaction("2026-08-01", "Start")
        self.create_transaction("2026-09-15", "End")
        self.create_transaction("2026-09-16", "After")

        response = self.client.get(
            "/transactions?date_from=2026-08-01&date_to=2026-09-15&per_page=20"
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["total"], 2)
        self.assertEqual([item["description"] for item in body["items"]], ["End", "Start"])

    def test_end_date_includes_imported_transactions_after_midnight(self):
        db.session.add(Transaction(
            posted_at=datetime(2026, 8, 19, 22, 48, 6),
            amount=10_000,
            direction="OUT",
            account_id=self.account_id,
            category_id=1,
            description="Imported late in the day",
            source="IMPORT",
            ref_no="END-DAY-1",
        ))
        db.session.commit()

        response = self.client.get(
            "/transactions?date_from=2026-08-19&date_to=2026-08-19"
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["total"], 1)
        self.assertEqual(response.get_json()["items"][0]["description"], "Imported late in the day")

    def test_listing_without_dates_returns_every_transaction(self):
        self.create_transaction("2025-01-05", "Oldest")
        self.create_transaction("2026-08-01", "Middle")
        self.create_transaction("2026-09-15", "Newest")

        response = self.client.get("/transactions?per_page=20")

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["total"], 3)
        self.assertEqual([item["description"] for item in body["items"]], ["Newest", "Middle", "Oldest"])

    def test_single_bound_filters_are_open_ended(self):
        self.create_transaction("2025-01-05", "Oldest")
        self.create_transaction("2026-09-15", "Newest")

        from_only = self.client.get("/transactions?date_from=2026-01-01").get_json()
        to_only = self.client.get("/transactions?date_to=2026-01-01").get_json()

        self.assertEqual([item["description"] for item in from_only["items"]], ["Newest"])
        self.assertEqual([item["description"] for item in to_only["items"]], ["Oldest"])

    def test_reversed_range_is_rejected(self):
        response = self.client.get(
            "/transactions?date_from=2026-09-15&date_to=2026-08-01"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("date_from", response.get_json()["error"])

    def test_maximum_end_date_is_rejected_cleanly(self):
        response = self.client.get(
            "/transactions?date_from=2026-08-01&date_to=9999-12-31"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("date_to", response.get_json()["error"])

    def test_statistics_range_can_span_months_and_includes_both_boundaries(self):
        self.create_transaction("2026-07-31", "Before")
        self.create_transaction("2026-08-01", "Start")
        self.create_transaction("2026-09-15", "End")
        self.create_transaction("2026-09-16", "After")

        response = self.client.get(
            "/statistics/breakdown?date_from=2026-08-01&date_to=2026-09-15"
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["total_expense"], 20_000)
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["amount"], 20_000)

    def test_statistics_same_day_range_is_inclusive(self):
        self.create_transaction("2026-08-10", "Same day")

        response = self.client.get(
            "/statistics/breakdown?date_from=2026-08-10&date_to=2026-08-10"
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["total_expense"], 10_000)

    def test_statistics_empty_valid_range_returns_zero(self):
        response = self.client.get(
            "/statistics/breakdown?date_from=2025-01-01&date_to=2025-01-31"
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json(), {"items": [], "total_expense": 0})

    def test_statistics_rejects_reversed_or_invalid_ranges(self):
        queries = (
            "?date_from=2026-09-15&date_to=2026-08-01",
            "?date_from=2026/08/01&date_to=2026-08-31",
            "?date_from=2026-02-30&date_to=2026-03-01",
            "?date_from=9999-12-31&date_to=9999-12-31",
            "?date_from=2026-08-01",
            "?date_to=2026-08-31",
            "",
        )
        for query in queries:
            with self.subTest(query=query):
                response = self.client.get(f"/statistics/breakdown{query}")
                self.assertEqual(response.status_code, 400, response.get_json())
                self.assertIn("error", response.get_json())


def test_frontend_uses_two_date_inputs_for_transaction_range():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND / "app.js").read_text(encoding="utf-8")
    i18n = (FRONTEND / "i18n.js").read_text(encoding="utf-8")

    assert 'id="transaction-date-from" type="date"' in html
    assert 'id="transaction-date-to" type="date"' in html
    assert "transaction-month" not in html
    assert "if(range.dateFrom)p.set('date_from',range.dateFrom)" in app
    assert "if(range.dateTo)p.set('date_to',range.dateTo)" in app
    assert "dateFrom<=dateTo" in app
    assert "applyDataMonth(nextMonth)" in app
    # The transaction list is not tied to the dashboard month: it defaults to
    # every transaction and only narrows when the user picks dates.
    assert "transactionDateFrom.value=range.dateFrom" not in app
    assert "transactionDateTo.value=range.dateTo" not in app
    assert 'id="clear-transaction-dates"' in html
    assert "renderTransactionDateFilterState" in app
    # The ledger pages 10 transactions at a time.
    assert "const TRANSACTIONS_PER_PAGE=10;" in app
    assert "per_page:TRANSACTIONS_PER_PAGE" in app
    assert "date_to:localDateValue()" in app
    assert "data=await api(`/transactions?${query}`)" in app
    assert "await applyLatestDataMonth()" in app
    for key in ("date_from_label", "date_to_label", "invalid_transaction_date_range",
                "clear_date_filter", "range_all_time", "range_from_only", "range_to_only"):
        assert i18n.count(f"{key}:") == 2


def test_frontend_uses_two_date_inputs_for_statistics_range():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND / "app.js").read_text(encoding="utf-8")
    i18n = (FRONTEND / "i18n.js").read_text(encoding="utf-8")

    assert 'id="statistics-date-from" type="date"' in html
    assert 'id="statistics-date-to" type="date"' in html
    assert 'id="statistics-range-label"' in html
    assert 'id="statistics-range-form"' in html
    assert 'id="apply-statistics-range" type="submit"' in html
    assert "statistics-month-filter" not in html
    assert "statistics-breakdown-period" not in html
    assert "date_from:range.dateFrom,date_to:range.dateTo" in app
    assert "dateFrom>dateTo" in app
    assert "restoreStatisticsBreakdownSelection" in app
    for key in ("invalid_statistics_date_range", "apply_statistics_range"):
        assert i18n.count(f"{key}:") == 2


if __name__ == "__main__":
    unittest.main()
