from datetime import date

from app import create_app
from app.extensions import db
from app.models import Transaction, User
from config import TestConfig
from scripts.seed_users import _month_starts, seed_users


def test_month_starts_returns_oldest_first():
    assert _month_starts(date(2026, 2, 20), 3) == [date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]


def test_seed_users_is_idempotent_and_varies_cash_flow():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        first = seed_users(count=3, months=2, seed=42)
        second = seed_users(count=3, months=2, seed=42)

        assert first["transactions_inserted"] == 54
        assert second["transactions_inserted"] == 0
        assert db.session.query(User).count() == 3
        assert db.session.query(Transaction).count() == 54

        users = db.session.query(User).order_by(User.email).all()
        assert len({user.created_at for user in users}) == 3
        assert len({user.last_login_at for user in users}) == 3
        assert all(user.last_login_at >= user.created_at for user in users)

        income_totals = db.session.query(Transaction.amount).filter(Transaction.direction == "IN").all()
        assert len({amount for (amount,) in income_totals}) > 1

        db.session.remove()
        db.drop_all()
