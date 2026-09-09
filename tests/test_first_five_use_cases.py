import io
import json
import unittest
import zipfile

from werkzeug.security import check_password_hash

from app import create_app
from app.extensions import db
from app.models import Account, Category, ImportBatch, ImportTemplate, Transaction, User
from app.services.common import ValidationError
from app.services.imports import _parse_row, _table, _xlsx_rows
from config import TestConfig

PASSWORD = "StrongPass1!"


class FirstFiveUseCasesTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        db.session.add(Category(id=1, name="Ăn uống", nature="DISCRETIONARY"))
        db.session.add(ImportTemplate(id=1, bank_code="VCB", name="VCB CSV", active=True, mapping_json=json.dumps({"header_rows": 1, "date": 0, "description": 1, "amount": 2, "ref_no": 3, "date_format": "%Y-%m-%d"})))
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def register(self, email="user@example.com"):
        return self.client.post("/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Nguyễn An", "date_of_birth": "1995-04-10", "consent": False})

    def login(self, email="user@example.com", password=PASSWORD):
        return self.client.post("/auth/login", json={"email": email, "password": password})

    def register_and_login(self, email="user@example.com"):
        self.assertEqual(self.register(email).status_code, 201)
        self.assertEqual(self.login(email).status_code, 200)

    def create_cash_account(self, name="Ví"):
        response = self.client.post("/accounts", json={"name": name, "type": "CASH", "opening_balance": 1_000_000})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["id"]

    def test_uc01_register_creates_ledger_hashes_password_and_login_lockout(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        user = db.session.query(User).filter_by(email="user@example.com").one()
        self.assertIsNotNone(user.ledger)
        self.assertNotEqual(user.password_hash, PASSWORD)
        self.assertTrue(check_password_hash(user.password_hash, PASSWORD))
        self.assertFalse(user.consent)
        self.assertFalse(self.client.get("/auth/privacy-notice").get_json()["consent_default"])
        for _ in range(5):
            failure = self.login(password="wrong-password")
        self.assertEqual(failure.status_code, 400)
        self.assertIsNotNone(db.session.get(User, user.id).locked_until)
        self.assertIn("tạm khóa", self.login().get_json()["error"])

    def test_uc02_profile_password_export_logout_and_deletion_request(self):
        self.register_and_login()
        self.assertEqual(self.client.patch("/profile", json={"full_name": "Nguyễn Bình", "consent": True}).status_code, 200)
        self.assertEqual(self.client.post("/profile/change-password", json={"current_password": PASSWORD, "new_password": "NewStrong2@"}).status_code, 200)
        export = self.client.get("/profile/export")
        self.assertEqual(export.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(export.data)) as archive:
            self.assertEqual(set(archive.namelist()), {"smartfinance.json", "transactions.csv"})
            exported = json.loads(archive.read("smartfinance.json"))
            self.assertEqual(exported["profile"]["full_name"], "Nguyễn Bình")
            self.assertTrue(
                {"accounts", "transactions", "custom_categories", "budgets", "alerts", "imports", "import_errors", "audit_logs"}
                <= set(exported)
            )
        self.assertEqual(self.client.post("/profile/deletion-request").status_code, 202)
        self.assertIsNotNone(db.session.query(User).one().deletion_requested_at)
        self.assertEqual(self.client.post("/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/profile").status_code, 401)

    def test_uc03_account_crud_archives_and_rejects_sensitive_bank_fields(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        update = self.client.put(f"/accounts/{account_id}", json={"name": "VCB", "type": "BANK", "opening_balance": 2_000_000, "bank_code": "VCB", "last_four": "1234"})
        self.assertEqual(update.status_code, 200)
        rejected = self.client.post("/accounts", json={"name": "Sai", "type": "BANK", "opening_balance": 0, "last_four": "1234", "account_number": "123456789"})
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(self.client.delete(f"/accounts/{account_id}").status_code, 200)
        self.assertTrue(db.session.get(Account, account_id).archived)
        listed = next(item for item in self.client.get("/accounts").get_json()["items"] if item["id"] == account_id)
        self.assertTrue(listed["archived"])
        self.client.post("/auth/logout")
        self.register_and_login("other@example.com")
        self.assertEqual(self.client.post(f"/accounts/{account_id}/restore").status_code, 404)
        self.assertTrue(db.session.get(Account, account_id).archived)
        self.client.post("/auth/logout")
        self.assertEqual(self.login().status_code, 200)
        restored = self.client.post(f"/accounts/{account_id}/restore")
        self.assertEqual(restored.status_code, 200)
        self.assertFalse(restored.get_json()["archived"])
        self.assertFalse(db.session.get(Account, account_id).archived)

    def test_uc04_transaction_crud_filters_paginates_and_hides_other_users(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        payload = {"date": "2026-08-19", "amount": 120000, "direction": "OUT", "account_id": account_id, "category_id": 1, "description": "Bữa tối"}
        created = self.client.post("/transactions", json=payload)
        self.assertEqual(created.status_code, 201, created.get_json())
        transaction_id = created.get_json()["id"]
        self.assertEqual(self.client.get(f"/transactions/{transaction_id}").status_code, 200)
        listing = self.client.get(f"/transactions?direction=OUT&account_id={account_id}&date_from=2026-08-01&page=1&per_page=1").get_json()
        self.assertEqual(listing["total"], 1)
        payload["amount"] = 130000
        self.assertEqual(self.client.put(f"/transactions/{transaction_id}", json=payload).status_code, 200)
        self.client.post("/auth/logout")
        self.register_and_login("other@example.com")
        self.assertEqual(self.client.get(f"/transactions/{transaction_id}").status_code, 404)
        self.assertEqual(self.client.put(f"/transactions/{transaction_id}", json=payload).status_code, 404)
        self.assertEqual(self.client.delete(f"/transactions/{transaction_id}").status_code, 404)

    def test_uc04_custom_category_rename_delete_requires_reassignment(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        created = self.client.post("/categories", json={"name": "Thú cưng", "nature": "DISCRETIONARY", "parent_id": 1})
        self.assertEqual(created.status_code, 201, created.get_json())
        category_id = created.get_json()["id"]
        self.assertEqual(self.client.patch(f"/categories/{category_id}", json={"name": "Chăm sóc thú cưng"}).status_code, 200)
        transaction = self.client.post("/transactions", json={"date": "2026-08-19", "amount": 100000, "direction": "OUT", "account_id": account_id, "category_id": category_id, "description": "Thức ăn"}).get_json()
        rejected = self.client.delete(f"/categories/{category_id}", json={"reassign_to": category_id})
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(self.client.delete(f"/categories/{category_id}", json={"reassign_to": 1}).status_code, 200)
        self.assertEqual(db.session.get(Transaction, transaction["id"]).category_id, 1)

    def test_income_requires_only_date_account_and_amount(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        response = self.client.post('/transactions', json={
            'direction': 'IN', 'date': '2026-08-01',
            'account_id': account_id, 'amount': 500000,
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        transaction = db.session.get(Transaction, response.get_json()['id'])
        self.assertEqual(transaction.category.name, 'Thu nhập')
        self.assertEqual(transaction.description, '')
        self.assertEqual(transaction.amount, 500000)

    def test_uc05_csv_preview_counts_new_duplicates_errors_without_writing(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        content = b"date,description,amount,ref\n2026-08-01,Coffee,-50000,A1\n2026-08-01,Coffee,-50000,A1\nbad-date,Broken,-10,A2\n"
        response = self.client.post("/imports/preview", data={"account_id": str(account_id), "template_id": "1", "file": (io.BytesIO(content), "statement.csv")}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["new"], 1)
        self.assertEqual(response.get_json()["duplicate"], 1)
        self.assertEqual(response.get_json()["error"], 1)
        self.assertEqual(db.session.query(Transaction).count(), 0)
        self.assertEqual(db.session.query(ImportBatch).one().status, "PREVIEW")

    def test_uc05_import_screen_uses_auto_template_when_template_id_is_omitted(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        auto_template = ImportTemplate(
            bank_code="AUTO",
            name="Tự nhận diện",
            active=True,
            mapping_json=json.dumps({"auto_detect": True}),
        )
        db.session.add(auto_template)
        db.session.commit()
        content = b"date,description,amount,ref\n2026-08-01,Coffee,-50000,AUTO-1\n"

        response = self.client.post(
            "/imports/preview",
            data={"account_id": str(account_id), "file": (io.BytesIO(content), "statement.csv")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["new"], 1)
        self.assertEqual(db.session.query(ImportBatch).one().template_id, auto_template.id)

    def test_uc05_preview_decisions_reject_rows_and_save_notes(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        content = (
            b"date,description,amount,ref\n"
            b"2026-08-01,Coffee,-50000,DECISION-1\n"
            b"2026-08-02,Salary,1000000,DECISION-2\n"
        )
        preview = self.client.post(
            "/imports/preview",
            data={
                "account_id": str(account_id),
                "template_id": "1",
                "file": (io.BytesIO(content), "decisions.csv"),
            },
            content_type="multipart/form-data",
        ).get_json()

        confirmed = self.client.post(
            f"/imports/{preview['batch_id']}/confirm",
            json={
                "decisions": {"2": "REJECT", "3": "KEEP"},
                "notes": {"2": "Không nhập", "3": "Lương tháng 8"},
            },
        )

        self.assertEqual(confirmed.status_code, 201, confirmed.get_json())
        self.assertEqual(confirmed.get_json()["imported"], 1)
        transaction = db.session.query(Transaction).filter_by(source="IMPORT").one()
        self.assertEqual(transaction.description, "Salary")
        self.assertEqual(transaction.note, "Lương tháng 8")

    def test_uc05_preview_results_are_paginated(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        lines = ["date,description,amount,ref"]
        lines.extend(
            f"2026-08-{(index % 28) + 1:02d},Transaction {index},-{index + 1}000,PAGE-{index}"
            for index in range(230)
        )
        lines.append("bad-date,Broken,-1000,PAGE-ERROR")
        response = self.client.post(
            "/imports/preview",
            data={
                "account_id": str(account_id),
                "template_id": "1",
                "file": (io.BytesIO("\n".join(lines).encode()), "paginated.csv"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 201, response.get_json())
        first_page = response.get_json()
        self.assertEqual((first_page["page"], first_page["pages"], first_page["preview_total"]), (1, 10, 231))
        self.assertEqual((len(first_page["rows"]), len(first_page["errors"])), (25, 0))

        second_page_response = self.client.get(f"/imports/{first_page['batch_id']}/preview?page=10&per_page=25")
        self.assertEqual(second_page_response.status_code, 200, second_page_response.get_json())
        second_page = second_page_response.get_json()
        self.assertEqual((second_page["page"], second_page["pages"], second_page["preview_total"]), (10, 10, 231))
        self.assertEqual((len(second_page["rows"]), len(second_page["errors"])), (5, 1))

    def test_uc05_future_dated_rows_are_reported_and_not_importable(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        content = b"date,description,amount,ref\n2999-01-01,Future payment,-50000,F1\n2026-08-01,Coffee,-50000,A1\n"

        response = self.client.post(
            "/imports/preview",
            data={"account_id": str(account_id), "template_id": "1", "file": (io.BytesIO(content), "statement.csv")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 201, response.get_json())
        summary = response.get_json()
        self.assertEqual(summary["new"], 1)
        self.assertEqual(summary["error"], 1)
        self.assertEqual(summary["future_date_error"], 1)
        self.assertEqual(summary["errors"][0]["row_number"], 2)
        self.assertEqual(summary["errors"][0]["type"], "FUTURE_DATE")
        self.assertIn("vượt quá ngày hiện tại", summary["errors"][0]["reason"])

    def test_uc05_user_can_reject_an_import_preview(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        content = b"date,description,amount,ref\n2026-08-01,Coffee,-50000,A1\n"
        preview = self.client.post(
            "/imports/preview",
            data={"account_id": str(account_id), "template_id": "1", "file": (io.BytesIO(content), "statement.csv")},
            content_type="multipart/form-data",
        ).get_json()

        response = self.client.delete(f"/imports/{preview['batch_id']}/preview")

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(db.session.get(ImportBatch, preview["batch_id"]))
        self.assertEqual(db.session.query(Transaction).count(), 0)

    def test_uc05_confirm_rechecks_future_dates_in_existing_preview(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        content = b"date,description,amount,ref\n2026-08-01,Coffee,-50000,A1\n"
        preview = self.client.post(
            "/imports/preview",
            data={"account_id": str(account_id), "template_id": "1", "file": (io.BytesIO(content), "statement.csv")},
            content_type="multipart/form-data",
        ).get_json()
        batch = db.session.get(ImportBatch, preview["batch_id"])
        payload = json.loads(batch.preview_json)
        payload["rows"][0]["date"] = "2999-01-01"
        batch.preview_json = json.dumps(payload)
        db.session.commit()

        response = self.client.post(f"/imports/{preview['batch_id']}/confirm", json={})

        self.assertEqual(response.status_code, 400)
        self.assertIn("Dòng 2", response.get_json()["error"])
        self.assertIn("vượt quá ngày hiện tại", response.get_json()["error"])
        self.assertEqual(db.session.query(Transaction).count(), 0)

    def test_uc05_rejects_renamed_executable(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        response = self.client.post("/imports/preview", data={"account_id": str(account_id), "template_id": "1", "file": (io.BytesIO(b"MZ\x00\x00evil"), "statement.xlsx")}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertIn("magic byte", response.get_json()["error"])

    def test_uc05_xlsx_cells_and_separate_debit_credit_columns(self):
        workbook = io.BytesIO()
        shared = b'''<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>date</t></si><si><t>description</t></si><si><t>2026-08-01</t></si><si><t>Ca phe</t></si></sst>'''
        sheet = b'''<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="s"><v>1</v></c></row><row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>3</v></c><c r="C2"><v>50000</v></c></row></sheetData></worksheet>'''
        with zipfile.ZipFile(workbook, "w") as archive:
            archive.writestr("xl/sharedStrings.xml", shared)
            archive.writestr("xl/worksheets/sheet1.xml", sheet)
        rows = _xlsx_rows(workbook.getvalue())
        self.assertEqual(rows[0], ["date", "", "description"])
        self.assertEqual(rows[1], ["2026-08-01", "Ca phe", "50000"])
        parsed = _parse_row(["2026-08-01", "Merchant", "50000", "", "REF"], {"date": 0, "description": 1, "debit": 2, "credit": 3, "ref_no": 4, "date_format": "%Y-%m-%d"})
        self.assertEqual((parsed[1], parsed[2]), (50000, "OUT"))

    def test_uc05_parser_validation_branches(self):
        credit = _parse_row(["2026-08-01", "Merchant", "", "75,000"], {"date": 0, "description": 1, "debit": 2, "credit": 3})
        self.assertEqual((credit[1], credit[2]), (75000, "IN"))
        with self.assertRaises(ValueError):
            _parse_row(["2026-08-01", "Merchant", "", ""], {"date": 0, "description": 1, "debit": 2, "credit": 3})
        with self.assertRaises(ValueError):
            _parse_row(["2026-08-01", "Merchant", "0"], {"date": 0, "description": 1, "amount": 2})
        with self.assertRaises(ValidationError):
            _table(b"a\x00b", ".csv")
        with self.assertRaises(ValidationError):
            _table(b"\xff\xfe", ".csv")
        empty_xlsx = io.BytesIO()
        with zipfile.ZipFile(empty_xlsx, "w") as archive:
            archive.writestr("docProps/app.xml", "<root/>")
        with self.assertRaises(ValidationError):
            _xlsx_rows(empty_xlsx.getvalue())

    def test_uc05_row_parsing_follows_the_profiled_number_convention(self):
        # P2.5: preview() parses amounts through statement_profiler.parse_number
        # using the column's proven convention instead of a second, independent
        # per-cell heuristic. "1.234.567" is 1,234,567 VND under vn and a
        # completely different number under en.
        vn = _parse_row(
            ["2026-08-01", "Luong thang 8", "12.500.000"],
            {"date": 0, "description": 1, "amount": 2, "number_convention": "vn"},
        )
        self.assertEqual((vn[1], vn[2]), (12_500_000, "IN"))
        en = _parse_row(
            ["2026-08-01", "Salary", "12,500,000"],
            {"date": 0, "description": 1, "amount": 2, "number_convention": "en"},
        )
        self.assertEqual((en[1], en[2]), (12_500_000, "IN"))

    def test_uc05_csv_detects_excel_delimiter_and_legacy_encoding(self):
        text = "date;description;amount;ref\n01/08/2026;Cà phê;-50000;A1\n"

        rows = _table(text.encode("cp1258"), ".csv")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "01/08/2026")
        self.assertEqual(rows[1][2], "-50000")

    def test_uc05_auto_template_imports_an_unknown_bank_csv(self):
        self.register_and_login()
        account_id = self.create_cash_account("Ngân hàng khác")
        template = ImportTemplate(bank_code="AUTO", name="Tự nhận diện", mapping_json=json.dumps({"auto_detect": True}), active=True)
        db.session.add(template)
        db.session.commit()
        content = "Ngày giao;Nội dung;Số tiền;Số dư;Thu chi;Mã giao dịch\n24/08/2026;Thanh toán cửa hàng;1.250.000;8.750.000;Chi;NEW-01\n".encode("utf-8")

        response = self.client.post("/imports/preview", data={
            "account_id": str(account_id),
            "file": (io.BytesIO(content), "unknown-bank.csv"),
        }, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["new"], 1)
        self.assertEqual(response.get_json()["sample"][0]["amount"], 1_250_000)
        self.assertEqual(response.get_json()["sample"][0]["direction"], "OUT")
        self.assertEqual(response.get_json()["rows"][0]["category_id"], 1)
        self.assertEqual(response.get_json()["account"]["name"], "Ngân hàng khác")
        self.assertEqual(response.get_json()["detection"]["columns"]["description"], "Nội dung")

    def test_uc05_auto_template_reads_bilingual_preamble_and_debit_credit(self):
        self.register_and_login()
        account_id = self.create_cash_account("Tài khoản nhập")
        template = ImportTemplate(bank_code="AUTO", name="Bot đọc sao kê", mapping_json=json.dumps({"auto_detect": True}), active=True)
        db.session.add(template)
        db.session.commit()
        content = "\n".join([
            "NGÂN HÀNG MẪU",
            "Sao kê tài khoản 0123",
            "STT No;Ngày giao dịch Transaction Date;Số bút toán Transaction No;Phát sinh nợ Debit;Phát sinh có Credit;Nội dung Details;Tài khoản Account",
            "1;21/08/2026;TX-01;50000;;Highlands Coffee;0123",
            "2;22/08/2026;TX-02;;15000000;Luong thang 8;0123",
            "3;23/08/2026;TX-03;120000;;Grab trip;0123",
        ]).encode("utf-8")

        response = self.client.post("/imports/preview", data={
            "account_id": str(account_id), "template_id": str(template.id),
            "file": (io.BytesIO(content), "bilingual.csv"),
        }, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 201, response.get_json())
        payload = response.get_json()
        self.assertEqual(payload["new"], 3)
        self.assertEqual(payload["detection"]["header_row"], 3)
        self.assertEqual(payload["detection"]["columns"]["debit"], "Phát sinh nợ Debit")
        self.assertEqual([row["direction"] for row in payload["rows"]], ["OUT", "IN", "OUT"])
        self.assertEqual(payload["rows"][0]["description"], "Highlands Coffee")


if __name__ == "__main__":
    unittest.main()
