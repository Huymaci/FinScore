import io
import json
import unittest
import zipfile
from datetime import date

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import AuditLog, SupportReport, User
from config import TestConfig

PASSWORD = "StrongPass1!"


class SupportReportsTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def register_login(self, email="user@example.com"):
        response = self.client.post("/auth/register", json={
            "email": email,
            "password": PASSWORD,
            "full_name": "Nguyễn An",
            "date_of_birth": "1995-04-10",
            "consent": False,
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(self.client.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code, 200)
        return db.session.query(User).filter_by(email=email).one()

    def login_admin(self):
        admin = User(
            email="admin@example.com",
            full_name="Admin",
            date_of_birth=date(1990, 1, 1),
            consent=False,
            role="ADMIN",
            password_hash=generate_password_hash(PASSWORD, method="pbkdf2:sha256:600000"),
        )
        db.session.add(admin)
        db.session.commit()
        self.assertEqual(self.client.post("/auth/login", json={"email": admin.email, "password": PASSWORD}).status_code, 200)
        return admin

    def test_user_creates_and_only_lists_own_support_reports(self):
        user = self.register_login()
        rejected = self.client.post("/support-reports", json={"subject": "Lỗi", "message": "quá ngắn"})
        self.assertEqual(rejected.status_code, 400)

        created = self.client.post("/support-reports", json={
            "subject": "Không nhập được sao kê",
            "message": "Tệp CSV hợp lệ nhưng hệ thống báo không đọc được dữ liệu.",
            "user_id": 999,
        })
        self.assertEqual(created.status_code, 201, created.get_json())
        self.assertEqual(created.get_json()["status"], "OPEN")
        self.assertEqual(db.session.query(SupportReport).one().user_id, user.id)
        self.assertEqual(self.client.get("/support-reports").get_json()["total"], 1)
        self.assertEqual(self.client.get("/admin/support-reports").status_code, 403)
        with zipfile.ZipFile(io.BytesIO(self.client.get("/profile/export").data)) as archive:
            exported = json.loads(archive.read("smartfinance.json"))
            self.assertEqual(exported["support_reports"][0]["subject"], "Không nhập được sao kê")

        self.client.post("/auth/logout")
        self.register_login("other@example.com")
        self.assertEqual(self.client.get("/support-reports").get_json()["total"], 0)

    def test_admin_lists_and_resolves_support_reports(self):
        user = self.register_login()
        report_id = self.client.post("/support-reports", json={
            "subject": "Cần hỗ trợ tài khoản",
            "message": "Tôi cần được hướng dẫn cập nhật thông tin đăng nhập.",
        }).get_json()["id"]
        self.client.post("/auth/logout")
        self.login_admin()

        listing = self.client.get("/admin/support-reports?status=OPEN").get_json()
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["user"]["email"], user.email)
        self.assertEqual(self.client.get("/admin/support-reports?status=INVALID").status_code, 400)

        resolved = self.client.patch(f"/admin/support-reports/{report_id}", json={"status": "RESOLVED"})
        self.assertEqual(resolved.status_code, 200, resolved.get_json())
        self.assertEqual(resolved.get_json()["status"], "RESOLVED")
        self.assertIsNotNone(resolved.get_json()["resolved_at"])
        self.assertIn(f"ADMIN_SUPPORT_REPORT_RESOLVED:{report_id}", {item.action for item in db.session.query(AuditLog)})
        self.assertEqual(self.client.patch(f"/admin/support-reports/{report_id}", json={"status": "INVALID"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
