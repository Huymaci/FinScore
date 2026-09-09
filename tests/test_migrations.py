"""The migration chain must replay from an empty database.

The rest of the suite calls ``db.create_all()`` and never runs a migration, so
the path a real deployment takes (``alembic upgrade head`` on a fresh database)
was unverified. Migrations 01/02 once built their DDL from live model metadata,
so they always produced the newest schema and migration 03 died on a real run
with "Duplicate column name" while every ``create_all`` based test stayed green.

``MigrationReplayTest`` runs the whole chain against a throwaway SQLite file, so
it executes everywhere with no service dependency and would catch a broken
``down_revision`` link, a module-level error, or a column added twice.

``MigrationDriftTest`` needs a real MySQL (``TEST_DATABASE_URL``) because
``alembic check`` on SQLite trips over type-affinity quirks (BINARY(32) reflects
back as NUMERIC). CI provides that URL; locally it skips.
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from sqlalchemy import create_engine, inspect

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERSIONS = ROOT / "migrations" / "versions"

EXPECTED_TABLES = {
    "users", "ledgers", "accounts", "categories", "transactions",
    "import_templates", "import_batches", "import_errors", "categorization_rules",
    "budgets", "alerts", "habit_challenges", "audit_logs", "support_reports",
}


def _alembic(url, *args):
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )


def _revision_count():
    return sum(1 for p in VERSIONS.glob("*.py") if p.name != "__init__.py")


class MigrationReplayTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.url = "sqlite:///" + os.path.join(self._dir.name, "replay.db")
        self.result = _alembic(self.url, "upgrade", "head")

    def tearDown(self):
        self._dir.cleanup()

    def test_upgrade_head_succeeds_from_empty(self):
        self.assertEqual(self.result.returncode, 0, msg=self.result.stderr)
        self.assertNotIn("Traceback", self.result.stderr)
        self.assertNotIn("FAILED", self.result.stderr)

    def test_every_revision_runs_once(self):
        self.assertEqual(
            self.result.stderr.count("Running upgrade"), _revision_count(),
            msg="chain did not step through one upgrade per revision file",
        )

    def test_all_tables_exist_afterwards(self):
        engine = create_engine(self.url)
        try:
            tables = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()  # release the file so TemporaryDirectory can delete it on Windows
        self.assertTrue(
            EXPECTED_TABLES <= tables,
            msg=f"missing after upgrade: {sorted(EXPECTED_TABLES - tables)}",
        )


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL", "").startswith("mysql"),
    "set TEST_DATABASE_URL to a MySQL DSN to check migrations against a real server",
)
class MigrationDriftTest(unittest.TestCase):
    def test_models_match_the_migrated_schema(self):
        url = os.environ["TEST_DATABASE_URL"]
        upgrade = _alembic(url, "upgrade", "head")
        self.assertEqual(upgrade.returncode, 0, msg=upgrade.stderr)
        check = _alembic(url, "check")
        self.assertEqual(
            check.returncode, 0,
            msg="model metadata has drifted from the migrations:\n" + check.stdout + check.stderr,
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
