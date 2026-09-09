import base64
import io
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import User
from config import TestConfig

PASSWORD = "StrongPass1!"
NEW_PASSWORD = "NewStrong2@"
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class ProfileFeaturesTest(unittest.TestCase):
    def setUp(self):
        self.uploads = tempfile.TemporaryDirectory()
        config = type("ProfileTestConfig", (TestConfig,), {"UPLOAD_FOLDER": self.uploads.name})
        self.app = create_app(config)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        self.uploads.cleanup()

    def register(self, email="user@example.com", full_name="Nguyễn An"):
        return self.client.post(
            "/auth/register",
            json={
                "email": email,
                "password": PASSWORD,
                "full_name": full_name,
                "date_of_birth": "1995-04-10",
                "consent": False,
            },
        )

    def login(self, email="user@example.com", password=PASSWORD):
        return self.client.post("/auth/login", json={"email": email, "password": password})

    def register_and_login(self):
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(self.login().status_code, 200)

    def test_profile_fields_update_and_new_email_becomes_login_identifier(self):
        self.register_and_login()
        response = self.client.patch(
            "/profile",
            json={
                "email": "  NEW.LOGIN@Example.COM ",
                "full_name": "  Nguyễn Bình  ",
                "date_of_birth": "1990-12-20",
                "consent": True,
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        profile = response.get_json()["profile"]
        self.assertEqual(profile["email"], "new.login@example.com")
        self.assertEqual(profile["full_name"], "Nguyễn Bình")
        self.assertEqual(profile["date_of_birth"], "1990-12-20")
        self.assertTrue(profile["consent"])
        self.assertIn("role", profile)

        self.assertEqual(self.client.post("/auth/logout").status_code, 200)
        self.assertEqual(self.login().status_code, 400)
        self.assertEqual(self.login("NEW.LOGIN@example.com").status_code, 200)

    def test_profile_update_rejects_duplicate_email_and_invalid_values_atomically(self):
        self.assertEqual(self.register("taken@example.com", "Taken User").status_code, 201)
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(self.login().status_code, 200)

        duplicate = self.client.patch(
            "/profile",
            json={"email": "TAKEN@example.com", "full_name": "Should Not Persist"},
        )
        self.assertEqual(duplicate.status_code, 400)
        user = db.session.query(User).filter_by(email="user@example.com").one()
        self.assertEqual(user.full_name, "Nguyễn An")

        self.assertEqual(self.client.patch("/profile", json={"date_of_birth": "2020-01-01"}).status_code, 400)
        self.assertEqual(self.client.patch("/profile", json={"consent": "true"}).status_code, 400)
        self.assertEqual(self.client.patch("/profile", json={"full_name": " "}).status_code, 400)

    def test_change_password_checks_confirmation_and_changes_future_login(self):
        self.register_and_login()
        mismatch = self.client.post(
            "/profile/change-password",
            json={
                "current_password": PASSWORD,
                "new_password": NEW_PASSWORD,
                "new_password_confirmation": "Different3#",
            },
        )
        self.assertEqual(mismatch.status_code, 400)
        changed = self.client.post(
            "/profile/change-password",
            json={
                "current_password": PASSWORD,
                "new_password": NEW_PASSWORD,
                "new_password_confirmation": NEW_PASSWORD,
            },
        )
        self.assertEqual(changed.status_code, 200, changed.get_json())
        self.client.post("/auth/logout")
        self.assertEqual(self.login(password=PASSWORD).status_code, 400)
        self.assertEqual(self.login(password=NEW_PASSWORD).status_code, 200)

    def test_avatar_upload_is_private_replaceable_and_removable(self):
        self.register_and_login()
        uploaded = self.client.post(
            "/profile/avatar",
            data={"avatar": (io.BytesIO(PNG_1X1), "portrait.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.get_json())
        avatar_url = uploaded.get_json()["avatar_url"]
        self.assertTrue(avatar_url.startswith("/profile/avatar?v="))
        first_filename = db.session.query(User).one().avatar_filename
        first_path = Path(self.uploads.name) / "avatars" / first_filename
        self.assertTrue(first_path.is_file())

        picture = self.client.get(avatar_url)
        self.assertEqual(picture.status_code, 200)
        self.assertEqual(picture.mimetype, "image/png")
        self.assertEqual(picture.data, PNG_1X1)

        replacement = b"RIFF" + (4).to_bytes(4, "little") + b"WEBP" + b"data"
        replaced = self.client.post(
            "/profile/avatar",
            data={"avatar": (io.BytesIO(replacement), "portrait.webp")},
            content_type="multipart/form-data",
        )
        self.assertEqual(replaced.status_code, 200)
        self.assertFalse(first_path.exists())
        self.assertEqual(self.client.get(replaced.get_json()["avatar_url"]).mimetype, "image/webp")

        self.assertEqual(self.client.delete("/profile/avatar").status_code, 200)
        self.assertIsNone(db.session.query(User).one().avatar_filename)
        self.assertEqual(self.client.get("/profile/avatar").status_code, 404)

    def test_avatar_rejects_disguised_or_oversized_files(self):
        self.register_and_login()
        disguised = self.client.post(
            "/profile/avatar",
            data={"avatar": (io.BytesIO(b"<svg><script>alert(1)</script></svg>"), "portrait.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(disguised.status_code, 400)
        oversized = self.client.post(
            "/profile/avatar",
            data={"avatar": (io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024)), "large.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(oversized.status_code, 400)
        self.assertIsNone(db.session.query(User).one().avatar_filename)


if __name__ == "__main__":
    unittest.main()
