"""Regressions for defects the original suite structurally could not catch.

Each test here maps to a bug that was live in the repository while the other
28 tests were green. The comment above each one records why the old suite
missed it, so the gap does not reopen.
"""
import os
import pathlib
import re
import unittest
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.services.common import money
from config import TestConfig

ROOT = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"


class SessionCookieTest(unittest.TestCase):
    """Flask-Talisman forces SESSION_COOKIE_SECURE=True on every request
    (talisman.py::_force_https), overriding config.py. Over the plain-HTTP
    localhost setup the README documents, the browser then never returns the
    cookie, session['csrf_token'] is missing on every POST, and nobody can log
    in. The old suite missed it twice over: TestConfig disables CSRF, and the
    Werkzeug test client ignores the Secure attribute entirely.
    """

    def test_cookie_is_not_secure_when_https_is_disabled(self):
        class HttpConfig(TestConfig):
            HTTPS_ENABLED = False
            TESTING = False
            WTF_CSRF_ENABLED = False

        app = create_app(HttpConfig)
        with app.app_context():
            db.create_all()
        response = app.test_client().get("/auth/csrf")
        cookie = response.headers.get("Set-Cookie", "")
        self.assertNotIn("Secure", cookie, "session cookie must not be Secure over plain HTTP")

    def test_cookie_is_secure_when_https_is_enabled(self):
        class HttpsConfig(TestConfig):
            HTTPS_ENABLED = True
            TESTING = False
            WTF_CSRF_ENABLED = False

        app = create_app(HttpsConfig)
        with app.app_context():
            db.create_all()
        response = app.test_client().get("/auth/csrf", base_url="https://localhost")
        self.assertIn("Secure", response.headers.get("Set-Cookie", ""))


class MoneyCoercionTest(unittest.TestCase):
    """MySQL returns DECIMAL for SUM() over BIGINT; SQLite returns int. On MySQL
    this made `Decimal / float` raise TypeError inside the FR-19 burn-rate
    detector, taking down recompute() and every import confirm after it, and it
    made Flask serialise amounts as JSON strings. Unit tests run on SQLite, so
    they could never reproduce either symptom.
    """

    def test_decimal_is_coerced_to_int(self):
        self.assertIsInstance(money(Decimal("7065000")), int)
        self.assertEqual(money(Decimal("7065000")), 7065000)

    def test_none_becomes_zero(self):
        self.assertEqual(money(None), 0)

    def test_result_divides_by_float(self):
        # The exact operation that raised TypeError in alerts.recompute.
        self.assertAlmostEqual(money(Decimal("100")) / 0.5, 200.0)


class ErrorShapeTest(unittest.TestCase):
    """The frontend treats an HTML body as "API unreachable", so a 404 from
    owned_or_404 used to surface as a bogus connection error. No test asserted
    the content type of a failure.
    """

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

    def register_login(self, email="regress@example.com"):
        self.client.post("/auth/register", json={
            "email": email, "password": "StrongPass1!", "full_name": "Regress",
            "date_of_birth": "1995-01-01", "consent": True})
        self.client.post("/auth/login", json={"email": email, "password": "StrongPass1!"})

    def test_missing_resource_returns_json(self):
        self.register_login()
        response = self.client.get("/transactions/999999")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.mimetype, "application/json")
        self.assertIn("error", response.get_json())

    def test_forbidden_returns_json(self):
        self.register_login()
        response = self.client.get("/admin/users")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.mimetype, "application/json")

    def test_method_not_allowed_returns_json(self):
        self.register_login()
        response = self.client.delete("/statistics/dashboard")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.mimetype, "application/json")

    def test_unauthenticated_returns_json(self):
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.mimetype, "application/json")


class ContentSecurityPolicyTest(unittest.TestCase):
    """NFR-17 forbids 'unsafe-inline'. CSP style-src also gates HTML style=""
    attributes, so every inline width the frontend emitted was silently dropped
    and all progress bars rendered at zero. Nothing asserted the two facts
    together.
    """

    def test_policy_has_no_unsafe_inline(self):
        app = create_app(TestConfig)
        with app.app_context():
            db.create_all()
        policy = app.test_client().get("/").headers.get("Content-Security-Policy", "")
        self.assertIn("style-src 'self'", policy)
        self.assertNotIn("unsafe-inline", policy)
        self.assertNotIn("unsafe-eval", policy)

    def test_frontend_emits_no_inline_style_attributes(self):
        for name in ("index.html", "app.js"):
            text = (FRONTEND / name).read_text(encoding="utf-8")
            found = re.findall(r'style\s*=\s*"[^"]*"', text)
            self.assertEqual(found, [], f"{name} would be blocked by CSP: {found}")

    def test_import_preview_normalizes_column_order_and_sends_categories(self):
        html = (FRONTEND / "index.html").read_text(encoding="utf-8")
        source = (FRONTEND / "app.js").read_text(encoding="utf-8")
        preview = source[source.index("function renderImportPreview"):source.index("async function confirmImport")]
        expected = ("transaction_date", "amount", "category", "transaction_column", "accounts")
        positions = [preview.index(f"<th>${{t('{key}')}}</th>") for key in expected]
        transaction_header = html[html.index('class="panel transaction-panel"'):html.index('id="transaction-rows"')]
        header_positions = [transaction_header.index(label) for label in ("Ngày", "Số tiền", "Danh mục", "Giao dịch", "Tài khoản")]

        self.assertEqual(positions, sorted(positions))
        self.assertEqual(header_positions, sorted(header_positions))
        self.assertIn("data-import-category", preview)
        self.assertIn("category_overrides:categoryOverrides", source)


class SeedCompletenessTest(unittest.TestCase):
    """The frontend keeps only categories that carry a `nature`, so a seed
    without an income leaf left users unable to record a salary, and
    statistics.py filtered on a "Chuyển khoản" row that did not exist.
    """

    def test_seed_covers_income_transfer_and_fallback(self):
        source = (ROOT / "scripts" / "seed.py").read_text(encoding="utf-8")
        for required in ("Thu nhập", "Chuyển khoản", "Uncategorised"):
            self.assertIn(required, source, f"seed must create the {required!r} category")

    def test_every_leaf_the_ui_translates_is_seeded(self):
        seed_source = (ROOT / "scripts" / "seed.py").read_text(encoding="utf-8")
        app_source = (FRONTEND / "app.js").read_text(encoding="utf-8")
        block = re.search(r"systemCategoryTranslationKeys\s*=\s*(?:Object\.freeze\()?\{([^}]*)\}", app_source)
        self.assertIsNotNone(block, "translation map not found in app.js")
        for name in re.findall(r"'([^']+)'\s*:", block.group(1)):
            self.assertIn(name, seed_source, f"app.js translates {name!r} but seed.py never creates it")


class ErasureCompletenessTest(unittest.TestCase):
    """NFR-10 requires post-deletion queries to return zero rows on every table.
    delete_account() enumerates tables explicitly, and habit_challenges was
    missing from that list.
    """

    def test_every_user_owned_table_is_deleted_explicitly(self):
        source = (ROOT / "app" / "services" / "profile.py").read_text(encoding="utf-8")
        for model in ("SupportReport", "HabitChallenge", "Alert", "Budget", "ImportBatch", "Transaction", "Ledger"):
            self.assertIn(f"delete({model})", source, f"delete_account must clear {model}")


class AuditActionLengthTest(unittest.TestCase):
    """FR-05's deletion receipt is 113 characters. The column was VARCHAR(100),
    which SQLite silently accepts and MySQL rejects with error 1406, so admin
    erasure returned 500 on the real database while the tests stayed green.
    """

    def test_deletion_receipt_fits_the_column(self):
        import hashlib
        import secrets

        from app.models import AuditLog

        salt = secrets.token_bytes(16)
        digest = hashlib.sha256(salt + b"a-very-long-user-email@example.com").hexdigest()
        receipt = f"ACCOUNT_DELETED:{salt.hex()}:{digest}"
        limit = AuditLog.__table__.c.action.type.length
        self.assertLessEqual(len(receipt), limit,
                             f"receipt is {len(receipt)} chars but the column holds {limit}")


class MigrationChainTest(unittest.TestCase):
    """Migrations 01 and 02 used to build tables from live model metadata, so
    they always produced the newest schema and migration 03 died with
    "Duplicate column name". A clean `alembic upgrade head` therefore failed,
    but the suite calls db.create_all() and never runs migrations at all.
    """

    def test_no_migration_creates_tables_from_model_metadata(self):
        versions = ROOT / "migrations" / "versions"
        for path in versions.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("db.metadata.sorted_tables", source,
                             f"{path.name} builds DDL from live models; it cannot be replayed")

    def test_chain_is_linear_and_complete(self):
        versions = ROOT / "migrations" / "versions"
        revisions, downs = {}, {}
        for path in versions.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            revision = re.search(r'^revision = "([^"]+)"', source, re.M).group(1)
            down = re.search(r"^down_revision = (?:\"([^\"]+)\"|None)", source, re.M).group(1)
            revisions[revision] = path.name
            downs[revision] = down
        roots = [r for r, d in downs.items() if d is None]
        self.assertEqual(len(roots), 1, f"expected exactly one root revision, got {roots}")
        for revision, down in downs.items():
            if down is not None:
                self.assertIn(down, revisions, f"{revision} points at unknown parent {down}")
        heads = set(revisions) - {d for d in downs.values() if d}
        self.assertEqual(len(heads), 1, f"expected a single head, got {heads}")


class SecretsHygieneTest(unittest.TestCase):
    """NFR-14: no secret may be committed. A .env with a real SECRET_KEY was
    shipped inside the archive.
    """

    def test_gitignore_covers_env(self):
        # A local .env is expected and fine; a *committed* one is not.
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertRegex(ignored, r"(?m)^\.env$")

    def test_production_secret_key_comes_from_the_environment(self):
        source = (ROOT / "config.py").read_text(encoding="utf-8")
        self.assertIn('SECRET_KEY = os.getenv("SECRET_KEY")', source)
        # Any remaining literal must be an obvious test-only placeholder.
        for literal in re.findall(r'SECRET_KEY\s*=\s*["\'](.+?)["\']', source):
            self.assertIn("test", literal.lower(),
                          f"{literal!r} looks like a real key committed to source")

    def test_example_env_has_no_real_secret(self):
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        secret = re.search(r"^SECRET_KEY=(.*)$", example, re.M)
        self.assertIsNotNone(secret)
        self.assertFalse(re.fullmatch(r"[0-9]+", secret.group(1).strip()),
                         "placeholder must not look like a usable key")


if __name__ == "__main__":  # pragma: no cover
    os.environ.setdefault("ADMIN_PASSWORD", "unused")
    unittest.main()


class AlertMonthScopeTest(unittest.TestCase):
    """recompute() evaluates the *current* month only.

    A verification script that hard-coded a month passed while it happened to
    be that month and then reported a phantom "no alerts generated" failure the
    moment the calendar moved on. The behaviour is correct — FR-19 forecasts the
    month in progress — so this pins the contract rather than the calendar.
    """

    def test_recompute_reads_the_month_containing_today(self):
        source = (ROOT / "app" / "services" / "alerts.py").read_text(encoding="utf-8")
        self.assertIn("today = today or date.today()", source)
        self.assertIn("Budget.month == today.replace(day=1)", source,
                      "the detector must scope budgets to the month in progress")

    def test_recompute_accepts_an_injected_today(self):
        """Tests and the nightly job must be able to pin the date explicitly."""
        import inspect

        from app.services.alerts import recompute

        self.assertIn("today", inspect.signature(recompute).parameters)
