from unittest.mock import patch

import pytest

from app import create_app
from app.extensions import db
from app.models import AuditLog
from config import TestConfig
from scripts.nightly import run


def test_nightly_records_success_and_failure():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        try:
            run()
            assert db.session.query(AuditLog).one().action == "NIGHTLY_JOB:SUCCESS"
            with patch("scripts.nightly.select", side_effect=RuntimeError("test failure")):
                with pytest.raises(RuntimeError, match="test failure"):
                    run()
            assert [item.action for item in db.session.query(AuditLog).order_by(AuditLog.id)] == [
                "NIGHTLY_JOB:SUCCESS", "NIGHTLY_JOB:FAILED",
            ]
        finally:
            db.session.remove()
            db.drop_all()
