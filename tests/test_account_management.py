import unittest
from datetime import datetime
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import Account, Category, ImportBatch, ImportError, ImportTemplate, Transaction
from config import TestConfig

PASSWORD = "StrongPass1!"
ROOT = Path(__file__).resolve().parents[1]


class AccountPermanentDeletionTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        db.session.add(Category(id=1, name="Ăn uống", nature="DISCRETIONARY"))
        db.session.add(
            ImportTemplate(
                id=1,
                bank_code="VCB",
                name="VCB CSV",
                active=True,
                mapping_json="{}",
            )
        )
        db.session.commit()
        self.client = self.app.test_client()
        self._register_and_login()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _register_and_login(self, email="user@example.com"):
        registered = self.client.post(
            "/auth/register",
            json={
                "email": email,
                "password": PASSWORD,
                "full_name": "Nguyễn An",
                "date_of_birth": "1995-04-10",
                "consent": False,
            },
        )
        self.assertEqual(registered.status_code, 201, registered.get_json())
        logged_in = self.client.post(
            "/auth/login", json={"email": email, "password": PASSWORD}
        )
        self.assertEqual(logged_in.status_code, 200, logged_in.get_json())

    def _create_bank_account(self, name="VCB chính"):
        response = self.client.post(
            "/accounts",
            json={
                "name": name,
                "type": "BANK",
                "opening_balance": 1_000_000,
                "bank_code": "VCB",
                "last_four": "1234",
            },
        )
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["id"]

    def test_current_balance_is_per_account_and_tracks_deleted_transactions(self):
        first = self._create_bank_account("First")
        second = self._create_bank_account("Second")
        untouched = self._create_bank_account("Untouched")
        income = Transaction(account_id=first, category_id=1, posted_at=datetime(2026, 1, 1),
                             amount=500_000, direction="IN", source="MANUAL")
        expense = Transaction(account_id=first, category_id=1, posted_at=datetime(2026, 2, 1),
                              amount=200_000, direction="OUT", source="IMPORT")
        other = Transaction(account_id=second, category_id=1, posted_at=datetime(2026, 2, 1),
                            amount=1_500_000, direction="OUT", source="MANUAL")
        db.session.add_all([income, expense, other])
        db.session.commit()

        def balances():
            response = self.client.get("/accounts")
            self.assertEqual(response.status_code, 200)
            return {item["id"]: item for item in response.get_json()["items"]}

        items = balances()
        self.assertEqual(items[first]["current_balance"], 1_300_000)
        self.assertEqual(items[second]["current_balance"], -500_000)
        self.assertEqual(items[untouched]["current_balance"], 1_000_000)
        self.assertEqual(items[first]["opening_balance"], 1_000_000)
        db.session.delete(expense)
        db.session.commit()
        self.assertEqual(balances()[first]["current_balance"], 1_500_000)

    def test_permanent_delete_requires_archive_and_removes_dependent_data(self):
        account_id = self._create_bank_account()
        user_id = db.session.get(Account, account_id).ledger.user_id
        transaction = Transaction(
            account_id=account_id,
            category_id=1,
            posted_at=datetime(2026, 8, 19),
            amount=50_000,
            direction="OUT",
            description="Cà phê",
        )
        batch = ImportBatch(
            user_id=user_id,
            account_id=account_id,
            template_id=1,
            filename="statement.csv",
            preview_json="{}",
        )
        db.session.add_all([transaction, batch])
        db.session.flush()
        error = ImportError(batch_id=batch.id, row_number=2, reason="Dòng lỗi")
        db.session.add(error)
        db.session.commit()
        transaction_id, batch_id, error_id = transaction.id, batch.id, error.id

        active_delete = self.client.delete(f"/accounts/{account_id}/permanent")
        self.assertEqual(active_delete.status_code, 400)
        self.assertIsNotNone(db.session.get(Account, account_id))

        self.assertEqual(self.client.delete(f"/accounts/{account_id}").status_code, 200)
        deleted = self.client.delete(f"/accounts/{account_id}/permanent")

        self.assertEqual(deleted.status_code, 200, deleted.get_json())
        self.assertIsNone(db.session.get(Account, account_id))
        self.assertIsNone(db.session.get(Transaction, transaction_id))
        self.assertIsNone(db.session.get(ImportBatch, batch_id))
        self.assertIsNone(db.session.get(ImportError, error_id))
        self.assertNotIn(
            account_id,
            {item["id"] for item in self.client.get("/accounts").get_json()["items"]},
        )

    def test_permanent_delete_does_not_expose_another_users_archived_account(self):
        account_id = self._create_bank_account("Tài khoản riêng")
        self.assertEqual(self.client.delete(f"/accounts/{account_id}").status_code, 200)
        self.client.post("/auth/logout")
        self._register_and_login("other@example.com")

        response = self.client.delete(f"/accounts/{account_id}/permanent")

        self.assertEqual(response.status_code, 404)
        self.assertIsNotNone(db.session.get(Account, account_id))


def test_account_form_only_offers_bank_and_exposes_permanent_delete_action():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    account_form = html.split('id="account-form"', 1)[1].split("</form>", 1)[0]

    assert '<select name="type">' not in account_form
    assert '<input name="type" type="hidden" value="BANK">' in account_form
    assert 'name="last_four"' in account_form
    assert "data-delete-account-permanently" in script
    assert "/permanent`" in script
    assert "await loadAccounts();populateSelects();await refreshCore()" in script


if __name__ == "__main__":
    unittest.main()
