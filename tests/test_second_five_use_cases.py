import io
import json
import unittest
from datetime import date, datetime, timedelta

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import (
    Account,
    Budget,
    CategorizationRule,
    Category,
    HabitChallenge,
    ImportBatch,
    ImportTemplate,
    Transaction,
    User,
)
from app.services.alerts import recompute
from config import TestConfig

PASSWORD = "StrongPass1!"


class SecondFiveUseCasesTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        db.session.add_all([
            Category(id=1, name="Ăn uống", nature="DISCRETIONARY"),
            Category(id=2, name="Nhà ở", nature="COMMITTED"),
            Category(id=3, name="Điện nước", nature="SEMI_FIXED"),
            ImportTemplate(id=1, bank_code="VCB", name="VCB CSV", active=True, mapping_json=json.dumps({"header_rows": 1, "date": 0, "description": 1, "amount": 2, "ref_no": 3, "date_format": "%Y-%m-%d"})),
        ])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def register_login(self, email="user@example.com"):
        response = self.client.post("/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Nguyễn An", "date_of_birth": "1995-04-10", "consent": False})
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(self.client.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code, 200)
        return db.session.query(User).filter_by(email=email).one()

    def cash_account(self, balance=1_000_000):
        response = self.client.post("/accounts", json={"name": "Ví", "type": "CASH", "opening_balance": balance})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["id"]

    def transaction(self, account_id, amount, category=1, posted="2026-08-15", direction="OUT"):
        response = self.client.post("/transactions", json={"date": posted, "amount": amount, "direction": direction, "account_id": account_id, "category_id": category, "description": "Test"})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["id"]

    def test_spending_analysis_compares_selected_expenses_with_month_budget(self):
        self.register_login()
        account_id = self.cash_account()
        self.transaction(account_id, 120000, posted='2026-08-15')
        self.transaction(account_id, 90000, posted='2026-08-01')
        self.transaction(account_id, 500000, posted='2026-08-15', direction='IN')
        response = self.client.put('/budgets', json={'month': '2026-08', 'category_id': 1, 'amount': 100000})
        self.assertEqual(response.status_code, 200)
        response = self.client.get('/statistics/spending-analysis?date_from=2026-08-15&date_to=2026-08-15')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['total_expense'], 120000)
        self.assertEqual(data['comparisons'][0]['status'], 'OVER')
        self.assertEqual(data['comparisons'][0]['excess'], 20000)

    def test_uc06_conflict_decision_atomic_confirm_error_report_and_idempotence(self):
        self.register_login()
        account_id = self.cash_account()
        self.transaction(account_id, 50_000, posted="2026-08-01")
        content = b"date,description,amount,ref\n2026-08-02,Coffee,-50000,A1\nbad,Broken,-1,A2\n"
        preview = self.client.post("/imports/preview", data={"account_id": str(account_id), "template_id": "1", "file": (io.BytesIO(content), "statement.csv")}, content_type="multipart/form-data")
        self.assertEqual(preview.status_code, 201, preview.get_json())
        summary = preview.get_json()
        self.assertEqual(summary["probable_duplicate"], 1)
        confirmed = self.client.post(f"/imports/{summary['batch_id']}/confirm", json={"decisions": {"2": "KEEP"}, "category_overrides": {"2": 1}})
        self.assertEqual(confirmed.status_code, 201, confirmed.get_json())
        self.assertEqual(confirmed.get_json()["imported"], 1)
        self.assertEqual(db.session.query(Transaction).filter_by(source="IMPORT").count(), 1)
        report = self.client.get(f"/imports/{summary['batch_id']}/errors.csv")
        self.assertIn(b"row_number,reason", report.data)
        repeated = self.client.post("/imports/preview", data={"account_id": str(account_id), "template_id": "1", "file": (io.BytesIO(content), "statement.csv")}, content_type="multipart/form-data").get_json()
        self.assertEqual(repeated["new"], 0)
        self.assertEqual(repeated["duplicate"], 1)

    def test_uc06_ordered_classification_merge_and_access_control(self):
        self.register_login()
        account_id = self.cash_account()
        db.session.add(CategorizationRule(pattern=r"ca phe|coffee", category_id=1, priority=10, active=True))
        db.session.commit()
        content = b"date,description,amount,ref\n2026-08-03,Ca phe,-50000,A3\n"
        preview = self.client.post("/imports/preview", data={"account_id": str(account_id), "template_id": "1", "file": (io.BytesIO(content), "classify.csv")}, content_type="multipart/form-data").get_json()
        confirmed = self.client.post(f"/imports/{preview['batch_id']}/confirm", json={})
        self.assertEqual(confirmed.status_code, 201, confirmed.get_json())
        imported = db.session.query(Transaction).filter_by(source="IMPORT").one()
        self.assertEqual(imported.category_id, 1)
        self.assertEqual(self.client.post(f"/imports/{preview['batch_id']}/confirm", json={}).status_code, 400)
        self.client.post("/auth/logout")
        self.register_login("other@example.com")
        self.assertEqual(self.client.get(f"/imports/{preview['batch_id']}/errors.csv").status_code, 404)

    def test_import_transactions_can_be_deleted_anytime_and_history_is_kept_until_the_user_clears_it(self):
        self.register_login()
        account_id = self.cash_account()

        def import_file(reference):
            content = f"date,description,amount,ref\n2026-08-03,Coffee,-50000,{reference}\n".encode()
            preview = self.client.post("/imports/preview", data={
                "account_id": str(account_id), "template_id": "1",
                "file": (io.BytesIO(content), f"{reference}.csv"),
            }, content_type="multipart/form-data").get_json()
            self.assertEqual(self.client.post(f"/imports/{preview['batch_id']}/confirm", json={}).status_code, 201)
            return preview["batch_id"]

        batch_id = import_file("DELETE-1")
        batch = db.session.get(ImportBatch, batch_id)
        batch.created_at -= timedelta(days=8)
        db.session.commit()
        history = self.client.get("/imports/history").get_json()["items"]
        self.assertEqual((history[0]["id"], history[0]["transaction_count"], history[0]["can_delete_transactions"]), (batch_id, 1, True))
        self.assertNotIn("can_undo", history[0])
        self.assertNotIn("undo_deadline", history[0])
        # Nothing expires on its own any more, so no deadline is advertised.
        self.assertNotIn("history_expires_at", history[0])

        removed = self.client.delete(f"/imports/{batch_id}/transactions")
        self.assertEqual(removed.get_json()["removed"], 1)
        self.assertEqual(db.session.query(Transaction).filter_by(source="IMPORT").count(), 0)
        self.assertEqual(db.session.get(ImportBatch, batch_id).status, "REVERTED")
        self.assertIsNotNone(db.session.get(ImportBatch, batch_id).reverted_at)
        self.assertEqual(self.client.delete(f"/imports/{batch_id}/transactions").status_code, 400)
        self.assertEqual(self.client.post(f"/imports/{batch_id}/undo").status_code, 405)

        aged = db.session.get(ImportBatch, batch_id)
        aged.created_at -= timedelta(days=31)
        aged.reverted_at -= timedelta(days=31)
        db.session.commit()
        self.assertEqual([item["id"] for item in self.client.get("/imports/history").get_json()["items"]], [batch_id])

        deleted = self.client.delete(f"/imports/{batch_id}/history").get_json()
        self.assertEqual((deleted["deleted"], deleted["removed_transactions"]), (1, 0))
        self.assertFalse(self.client.get("/imports/history").get_json()["items"])
        self.assertIsNone(db.session.get(ImportBatch, batch_id))
        self.assertEqual(self.client.delete(f"/imports/{batch_id}/history").status_code, 400)

    def test_import_history_deletion_keeps_or_removes_the_imported_transactions_as_asked(self):
        self.register_login()
        account_id = self.cash_account()

        def import_file(reference):
            content = f"date,description,amount,ref\n2026-08-04,Lunch,-60000,{reference}\n".encode()
            preview = self.client.post("/imports/preview", data={
                "account_id": str(account_id), "template_id": "1",
                "file": (io.BytesIO(content), f"{reference}.csv"),
            }, content_type="multipart/form-data").get_json()
            self.assertEqual(self.client.post(f"/imports/{preview['batch_id']}/confirm", json={}).status_code, 201)
            return preview["batch_id"]

        # Deleting one entry without asking for the transactions keeps them: the
        # rows are only unlinked from the batch that is going away.
        kept_id = import_file("KEEP-1")
        response = self.client.delete(f"/imports/{kept_id}/history").get_json()
        self.assertEqual((response["deleted"], response["removed_transactions"]), (1, 0))
        self.assertIsNone(db.session.get(ImportBatch, kept_id))
        kept = db.session.query(Transaction).filter_by(source="IMPORT").one()
        self.assertIsNone(kept.import_batch_id)

        purged_id = import_file("PURGE-1")
        remaining_id = import_file("PURGE-2")

        # History belongs to its owner: another account cannot delete it, by id
        # or in bulk.
        self.client.post("/auth/logout")
        self.register_login("other@example.com")
        self.assertEqual(self.client.delete(f"/imports/{purged_id}/history").status_code, 400)
        self.assertEqual(self.client.delete(f"/imports/history?ids={purged_id}").get_json()["deleted"], 0)
        self.assertEqual(self.client.delete("/imports/history").get_json()["deleted"], 0)
        self.client.post("/auth/logout")
        self.assertEqual(self.client.post("/auth/login", json={"email": "user@example.com", "password": PASSWORD}).status_code, 200)

        # Only the ticked entry goes; the rest of the history stays listed.
        selected = self.client.delete(f"/imports/history?ids={purged_id}").get_json()
        self.assertEqual((selected["deleted"], selected["removed_transactions"]), (1, 0))
        self.assertEqual([item["id"] for item in self.client.get("/imports/history").get_json()["items"]], [remaining_id])

        cleared = self.client.delete("/imports/history?remove_transactions=1").get_json()
        self.assertEqual((cleared["deleted"], cleared["removed_transactions"]), (1, 1))
        self.assertFalse(self.client.get("/imports/history").get_json()["items"])
        # Two unlinked transactions survive: the entries deleted without asking
        # for their transactions never touched the ledger.
        self.assertEqual(db.session.query(Transaction).filter_by(source="IMPORT").count(), 2)

    def test_import_history_counts_and_deletes_only_transactions_owned_by_each_batch(self):
        self.register_login()
        account_id = self.cash_account()
        content = (
            b"date,description,amount,ref\n"
            b"2026-08-01,First,-10000,BATCH-1\n"
            b"2026-08-02,Second,-20000,BATCH-2\n"
            b"2026-08-03,Third,-30000,BATCH-3\n"
        )

        first_preview = self.client.post(
            "/imports/preview",
            data={
                "account_id": str(account_id),
                "template_id": "1",
                "file": (io.BytesIO(content), "three-rows.csv"),
            },
            content_type="multipart/form-data",
        ).get_json()
        first_confirm = self.client.post(
            f"/imports/{first_preview['batch_id']}/confirm",
            json={"decisions": {"4": "REJECT"}},
        )
        self.assertEqual(first_confirm.get_json()["imported"], 2)

        second_preview = self.client.post(
            "/imports/preview",
            data={
                "account_id": str(account_id),
                "template_id": "1",
                "file": (io.BytesIO(content), "three-rows.csv"),
            },
            content_type="multipart/form-data",
        ).get_json()
        self.assertEqual((second_preview["new"], second_preview["duplicate"]), (1, 2))
        second_confirm = self.client.post(f"/imports/{second_preview['batch_id']}/confirm", json={})
        self.assertEqual(second_confirm.get_json()["imported"], 1)

        history = {item["id"]: item for item in self.client.get("/imports/history").get_json()["items"]}
        self.assertEqual(history[first_preview["batch_id"]]["transaction_count"], 2)
        self.assertEqual(history[second_preview["batch_id"]]["transaction_count"], 1)

        removed = self.client.delete(f"/imports/{first_preview['batch_id']}/transactions")
        self.assertEqual(removed.get_json()["removed"], 2)
        self.assertEqual(db.session.query(Transaction).filter_by(source="IMPORT").count(), 1)
        history = {item["id"]: item for item in self.client.get("/imports/history").get_json()["items"]}
        self.assertEqual(history[first_preview["batch_id"]]["transaction_count"], 0)
        self.assertEqual(history[second_preview["batch_id"]]["transaction_count"], 1)

    def test_uc07_monthly_budget_copy_and_safe_to_spend(self):
        self.register_login()
        account_id = self.cash_account()
        self.transaction(account_id, 100_000, category=2)
        budget = self.client.put("/budgets", json={"month": "2026-08", "category_id": 2, "amount": 400_000})
        self.assertEqual(budget.status_code, 200, budget.get_json())
        safe = self.client.get("/budgets/safe-to-spend?month=2026-08").get_json()["amount"]
        self.assertEqual(safe, 600_000)
        copied = self.client.post("/budgets/copy", json={"month": "2026-09"}).get_json()
        self.assertEqual(copied["copied"], 1)
        self.assertEqual(self.client.get("/budgets?month=2026-09").get_json()["items"][0]["amount"], 400_000)

    def test_budget_delete_removes_limit_but_keeps_transactions(self):
        self.register_login()
        account_id = self.cash_account()
        self.transaction(account_id, 100_000, category=2)
        budget_id = self.client.put("/budgets", json={"month": "2026-08", "category_id": 2, "amount": 400_000}).get_json()["id"]
        # A committed budget reserves its unspent remainder, so safe-to-spend drops until it is gone.
        self.assertEqual(self.client.get("/budgets/safe-to-spend?month=2026-08").get_json()["amount"], 600_000)

        removed = self.client.delete(f"/budgets/{budget_id}")
        self.assertEqual(removed.status_code, 200, removed.get_json())
        self.assertEqual(self.client.get("/budgets?month=2026-08").get_json()["items"], [])
        self.assertEqual(self.client.get("/statistics/dashboard?month=2026-08").get_json()["budget_progress"], [])
        self.assertEqual(self.client.get("/budgets/safe-to-spend?month=2026-08").get_json()["amount"], 900_000)
        self.assertEqual(self.client.get("/transactions?date_from=2026-08-01&date_to=2026-08-31").get_json()["total"], 1)
        self.assertEqual(self.client.delete(f"/budgets/{budget_id}").status_code, 404)

    def test_budget_delete_rejects_another_users_budget(self):
        self.register_login()
        owner_budget_id = self.client.put("/budgets", json={"month": "2026-08", "category_id": 2, "amount": 400_000}).get_json()["id"]
        self.client.post("/auth/logout")
        self.register_login(email="other@example.com")
        self.assertEqual(self.client.delete(f"/budgets/{owner_budget_id}").status_code, 404)
        self.assertIsNotNone(db.session.get(Budget, owner_budget_id))

    def test_safe_to_spend_excludes_reserved_accounts_and_later_transactions(self):
        user = self.register_login()
        spending_account_id = self.cash_account()
        reserved_account = Account(
            ledger_id=user.ledger.id, name="Tiết kiệm", type="BANK",
            opening_balance=5_000_000, bank_code="TEST", last_four="1234",
            include_in_safe_to_spend=False,
        )
        db.session.add(reserved_account)
        db.session.commit()
        self.transaction(spending_account_id, 100_000, posted="2026-09-01")

        safe = self.client.get("/budgets/safe-to-spend?month=2026-08").get_json()["amount"]

        self.assertEqual(safe, 1_000_000)

    def test_uc08_threshold_burn_rate_cooldown_and_inbox_actions(self):
        user = self.register_login()
        account_id = self.cash_account()
        self.transaction(account_id, 85_000, posted="2026-08-15")
        db.session.add(Budget(user_id=user.id, category_id=1, month=date(2026, 8, 1), amount=100_000))
        db.session.commit()
        self.assertEqual(recompute(user.id, date(2026, 8, 15)), 2)
        self.assertEqual(recompute(user.id, date(2026, 8, 15)), 0)
        self.transaction(account_id, 20_000, posted="2026-08-15")
        self.assertEqual(recompute(user.id, date(2026, 8, 15)), 1)
        inbox = self.client.get("/alerts").get_json()["items"]
        self.assertEqual({item["kind"] for item in inbox}, {"THRESHOLD", "BURN_RATE"})
        self.assertTrue(all(item["explanation"] and item["suggested_action"] for item in inbox))
        changed = self.client.patch(f"/alerts/{inbox[0]['id']}", json={"status": "DISMISSED"})
        self.assertEqual(changed.get_json()["status"], "DISMISSED")

    def test_uc09_dashboard_breakdown_and_twelve_month_trend(self):
        self.register_login()
        account_id = self.cash_account()
        self.transaction(account_id, 200_000, direction="IN")
        self.transaction(account_id, 85_000)
        db.session.add(Category(id=4, name="Chuyển khoản", nature="DISCRETIONARY"))
        db.session.commit()
        self.transaction(account_id, 500_000, category=4, direction="OUT")
        self.transaction(account_id, 500_000, category=4, direction="IN")
        user = db.session.query(User).filter_by(email="user@example.com").one()
        db.session.add(Budget(user_id=user.id, category_id=1, month=date(2026, 8, 1), amount=100_000))
        db.session.commit()
        dashboard = self.client.get("/statistics/dashboard?month=2026-08").get_json()
        self.assertEqual((dashboard["income"], dashboard["expense"], dashboard["net"]), (200_000, 85_000, 115_000))
        self.assertEqual((dashboard["budget_progress"][0]["status"], dashboard["budget_progress"][0]["label"]), ("GREEN", "Trong ngân sách"))
        breakdown_response = self.client.get("/statistics/breakdown?date_from=2026-08-01&date_to=2026-08-31").get_json()
        breakdown = breakdown_response["items"]
        self.assertEqual(breakdown[0]["amount"], 85_000)
        self.assertEqual(breakdown_response["total_expense"], sum(item["amount"] for item in breakdown_response["items"]))
        self.assertEqual(len(self.client.get("/statistics/trend?through=2026-08").get_json()["items"]), 12)
        self.transaction(account_id, 15_000, posted="2026-08-16")
        at_budget = self.client.get("/statistics/dashboard?month=2026-08").get_json()["budget_progress"][0]
        self.assertEqual((at_budget["spent"], at_budget["status"], at_budget["label"]), (100_000, "AMBER", "Sắp vượt ngân sách"))

    def test_budget_status_threshold_boundaries(self):
        user = self.register_login()
        account_id = self.cash_account()
        db.session.add(Budget(user_id=user.id, category_id=1, month=date(2026, 8, 1), amount=100_000))
        db.session.commit()

        transaction_id = self.transaction(account_id, 1_000)
        transaction = db.session.get(Transaction, transaction_id)

        def status_at(amount):
            transaction.amount = amount
            db.session.commit()
            progress = self.client.get("/statistics/dashboard?month=2026-08").get_json()["budget_progress"][0]
            return progress["percent"], progress["status"], progress["label"]

        self.assertEqual(status_at(1_000), (1.0, "GREEN", "Trong ngân sách"))
        self.assertEqual(status_at(85_000), (85.0, "GREEN", "Trong ngân sách"))
        self.assertEqual(status_at(86_000), (86.0, "AMBER", "Sắp vượt ngân sách"))
        self.assertEqual(status_at(100_000), (100.0, "AMBER", "Sắp vượt ngân sách"))
        self.assertEqual(status_at(101_000), (101.0, "RED", "Vượt ngân sách"))

    def test_habit_challenge_proposal_accept_progress_evaluation_and_next_level(self):
        self.register_login()
        account_id = self.cash_account()
        today = date.today()
        for index in range(8):
            db.session.add(Transaction(
                account_id=account_id, category_id=1,
                posted_at=datetime.combine(today - timedelta(days=index + 1), datetime.min.time()),
                amount=50_000, direction="OUT", description="Coffee", source="MANUAL", ref_no=f"C{index}",
            ))
        db.session.commit()

        proposed = self.client.get("/challenges").get_json()["items"][0]
        self.assertEqual((proposed["status"], proposed["baseline_count"], proposed["target_count"]), ("PROPOSED", 2, 1))
        accepted = self.client.post(f"/challenges/{proposed['id']}/respond", json={"action": "ACCEPT"}).get_json()
        self.assertEqual(accepted["status"], "ACTIVE")

        challenge = db.session.get(HabitChallenge, proposed["id"])
        challenge.period_start = today - timedelta(days=40)
        challenge.period_end = today - timedelta(days=34)
        db.session.commit()
        listing = self.client.get("/challenges").get_json()["items"]
        completed = next(item for item in listing if item["id"] == challenge.id)
        next_proposal = next(item for item in listing if item["status"] == "PROPOSED")
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(completed["saved_amount"], 100_000)
        self.assertEqual(next_proposal["target_count"], 1)

        self.client.post("/auth/logout")
        self.register_login("challenge-other@example.com")
        self.assertEqual(self.client.post(f"/challenges/{challenge.id}/respond", json={"action": "DECLINE"}).status_code, 400)

    def test_uc11_admin_metadata_only_lock_reset_config_suppression_and_delete(self):
        user = self.register_login()
        account_id = self.cash_account()
        self.transaction(account_id, 123_456, posted="2026-08-01")
        self.assertEqual(self.client.get("/admin/users").status_code, 403)
        self.assertEqual(self.client.post("/profile/deletion-request").status_code, 202)
        self.client.post("/auth/logout")
        admin = User(email="admin@example.com", full_name="Admin", date_of_birth=date(1990, 1, 1), consent=False, role="ADMIN", password_hash=generate_password_hash(PASSWORD, method="pbkdf2:sha256:600000"))
        db.session.add(admin)
        db.session.commit()
        self.assertEqual(self.client.post("/auth/login", json={"email": admin.email, "password": PASSWORD}).status_code, 200)
        listing = self.client.get("/admin/users").get_json()["items"][0]
        self.assertFalse({"balance", "transactions", "amount", "description"} & set(listing))
        self.assertEqual(self.client.post(f"/admin/users/{user.id}/lock").status_code, 200)
        self.assertEqual(self.client.post(f"/admin/users/{user.id}/unlock").status_code, 200)
        reset = self.client.post(f"/admin/users/{user.id}/reset-password")
        self.assertTrue(reset.get_json()["temporary_password"])
        self.assertTrue(self.client.get("/admin/operations").get_json()["suppressed"])
        self.assertEqual(self.client.patch("/admin/import-config/template/1", json={"active": False}).get_json()["active"], False)
        self.assertEqual(self.client.delete(f"/admin/users/{user.id}").status_code, 200)
        self.assertIsNone(db.session.get(User, user.id))
        self.assertEqual(db.session.query(Transaction).count(), 0)

    def test_support_admin_cannot_execute_user_deletion(self):
        # FR-48/FR-47: irreversible PII erasure is a primary-ADMIN action. A
        # delegated SUPPORT_ADMIN keeps lock/unlock/reset-password but not delete.
        user = User(email="target@example.com", full_name="Target", date_of_birth=date(1995, 1, 1), consent=True, role="USER", password_hash=generate_password_hash(PASSWORD, method="pbkdf2:sha256:600000"))
        support = User(email="support@example.com", full_name="Support", date_of_birth=date(1990, 1, 1), consent=False, role="SUPPORT_ADMIN", password_hash=generate_password_hash(PASSWORD, method="pbkdf2:sha256:600000"))
        db.session.add_all([user, support])
        db.session.commit()
        user_id = user.id

        self.client.post("/auth/login", json={"email": support.email, "password": PASSWORD})
        self.assertEqual(self.client.post(f"/admin/users/{user_id}/lock").status_code, 200)
        self.assertEqual(self.client.post(f"/admin/users/{user_id}/unlock").status_code, 200)
        self.assertEqual(self.client.delete(f"/admin/users/{user_id}").status_code, 403)
        self.assertEqual(self.client.delete(f"/admin/users/{user_id}/violation").status_code, 403)
        self.assertIsNotNone(db.session.get(User, user_id))

        self.client.post("/auth/logout")
        admin = User(email="root@example.com", full_name="Root", date_of_birth=date(1990, 1, 1), consent=False, role="ADMIN", password_hash=generate_password_hash(PASSWORD, method="pbkdf2:sha256:600000"))
        db.session.add(admin)
        db.session.commit()
        self.client.post("/auth/login", json={"email": admin.email, "password": PASSWORD})
        self.client.post(f"/admin/users/{user_id}/lock")  # a pending request is not required for /violation
        self.assertEqual(self.client.delete(f"/admin/users/{user_id}/violation").status_code, 200)
        self.assertIsNone(db.session.get(User, user_id))

    def test_primary_admin_can_delegate_without_support_admin_managing_parent(self):
        user = User(email="user@example.com", full_name="User", date_of_birth=date(1995, 1, 1), consent=True, role="USER", password_hash=generate_password_hash(PASSWORD, method="pbkdf2:sha256:600000"))
        primary = User(email="primary@example.com", full_name="Primary", date_of_birth=date(1990, 1, 1), consent=False, role="ADMIN", password_hash=generate_password_hash(PASSWORD, method="pbkdf2:sha256:600000"))
        db.session.add_all([user, primary])
        db.session.commit()

        self.assertEqual(self.client.post("/auth/login", json={"email": primary.email, "password": PASSWORD}).status_code, 200)
        promoted = self.client.patch(f"/admin/users/{user.id}/role", json={"role": "SUPPORT_ADMIN"})
        self.assertEqual(promoted.status_code, 200)
        self.assertEqual(promoted.get_json()["role"], "SUPPORT_ADMIN")
        self.client.post("/auth/logout")

        self.assertEqual(self.client.post("/auth/login", json={"email": user.email, "password": PASSWORD}).status_code, 200)
        self.assertEqual(self.client.patch(f"/admin/users/{primary.id}/role", json={"role": "USER"}).status_code, 403)
        self.assertEqual(self.client.post(f"/admin/users/{primary.id}/lock").status_code, 404)
        self.assertEqual(self.client.get("/admin/audit-logs").status_code, 403)
        self.assertEqual(self.client.get("/admin/import-config").status_code, 403)
        self.assertNotIn(primary.id, {item["id"] for item in self.client.get("/admin/users").get_json()["items"]})

        self.client.post("/auth/logout")
        self.client.post("/auth/login", json={"email": primary.email, "password": PASSWORD})
        revoked = self.client.patch(f"/admin/users/{user.id}/role", json={"role": "USER"})
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(revoked.get_json()["role"], "USER")
        self.assertEqual(self.client.get("/admin/users?status=ACTIVE&role=USER").status_code, 200)
        self.assertEqual(self.client.delete(f"/admin/users/{user.id}/violation").status_code, 200)
        self.assertIsNone(db.session.get(User, user.id))


if __name__ == "__main__":
    unittest.main()
