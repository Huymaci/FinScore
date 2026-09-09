"""Seed multiple users with distinct income and expense histories.

Usage:
    python -m scripts.seed_users
    python -m scripts.seed_users --count 50 --months 6 --replace

Generated users use ``user001@smartexpense.local`` through the requested count.
The command is deterministic and can be run repeatedly without duplicating data.
"""

import argparse
import hashlib
import os
import random
import sys
from calendar import monthrange
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Account, Category, Ledger, Transaction, User

DEFAULT_COUNT = 50
DEFAULT_MONTHS = 6
DEFAULT_PASSWORD = "SmartExpenseUser1!"
EMAIL_TEMPLATE = "user{number:03d}@smartexpense.local"

CATEGORIES = (
    ("Thu nhập", "COMMITTED"),
    ("Nhà ở", "COMMITTED"),
    ("Ăn uống", "DISCRETIONARY"),
    ("Di chuyển", "SEMI_FIXED"),
    ("Mua sắm", "DISCRETIONARY"),
    ("Điện nước", "SEMI_FIXED"),
    ("Viễn thông", "SEMI_FIXED"),
    ("Y tế", "SEMI_FIXED"),
    ("Giải trí", "DISCRETIONARY"),
)

EXPENSES = (
    ("Nhà ở", "Tiền thuê nhà", 0.18, 0.30),
    ("Ăn uống", "Ăn uống và thực phẩm", 0.13, 0.22),
    ("Di chuyển", "Xăng xe và di chuyển", 0.04, 0.09),
    ("Mua sắm", "Mua sắm cá nhân", 0.03, 0.12),
    ("Điện nước", "Hóa đơn điện nước", 0.025, 0.055),
    ("Viễn thông", "Internet và điện thoại", 0.015, 0.035),
    ("Y tế", "Chăm sóc sức khỏe", 0.01, 0.06),
    ("Giải trí", "Giải trí", 0.02, 0.08),
)

FAMILY_NAMES = ("Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Đặng", "Bùi", "Đỗ", "Hồ")
GIVEN_NAMES = ("An", "Bình", "Chi", "Dũng", "Giang", "Hà", "Hùng", "Lan", "Minh", "Nam", "Phương", "Trang")


def _month_starts(end_month, count):
    cursor = end_month.replace(day=1)
    months = []
    for _ in range(count):
        months.append(cursor)
        cursor = date(cursor.year - (cursor.month == 1), 12 if cursor.month == 1 else cursor.month - 1, 1)
    return list(reversed(months))


def _key(email, month, label):
    return hashlib.sha256(f"multi-user-seed|{email}|{month:%Y-%m}|{label}".encode()).digest()


def _categories():
    result = {}
    for name, nature in CATEGORIES:
        item = db.session.scalar(select(Category).where(Category.owner_id.is_(None), Category.name == name))
        if item is None:
            item = Category(name=name, nature=nature, owner_id=None)
            db.session.add(item)
            db.session.flush()
        result[name] = item
    return result


def seed_users(count=DEFAULT_COUNT, months=DEFAULT_MONTHS, password=DEFAULT_PASSWORD, replace=False, seed=20260906):
    if not 1 <= count <= 1_000:
        raise ValueError("Số tài khoản phải nằm trong khoảng 1 đến 1.000")
    if not 1 <= months <= 120:
        raise ValueError("Số tháng phải nằm trong khoảng 1 đến 120")

    categories = _categories()
    # Use completed months only so a seed never creates future-dated expenses.
    last_complete_month = date.today().replace(day=1) - timedelta(days=1)
    period = _month_starts(last_complete_month, months)
    password_hash = generate_password_hash(password, method="pbkdf2:sha256:600000")
    inserted_transactions = 0

    for number in range(1, count + 1):
        email = EMAIL_TEMPLATE.format(number=number)
        rng = random.Random(seed + number * 10_007)
        # Give every demo identity a stable, distinct history.  The offsets use
        # the user number so registration/login dates do not all look freshly
        # inserted after a bulk seed.
        today = date.today()
        registered_at = datetime.combine(today - timedelta(days=(count - number + 1) * 5), datetime.min.time()).replace(
            hour=8 + number % 9,
            minute=(number * 7) % 60,
        )
        last_login_at = datetime.combine(today - timedelta(days=(count - number) % 31), datetime.min.time()).replace(
            hour=7 + number % 12,
            minute=(number * 11) % 60,
        )
        if last_login_at < registered_at:
            last_login_at = registered_at + timedelta(hours=number)
        user = db.session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                password_hash=password_hash,
                full_name=f"{rng.choice(FAMILY_NAMES)} {rng.choice(GIVEN_NAMES)}",
                date_of_birth=date(rng.randint(1975, 2003), rng.randint(1, 12), rng.randint(1, 28)),
                consent=True,
                role="USER",
                ledger=Ledger(),
            )
            db.session.add(user)
            db.session.flush()
        elif user.ledger is None:
            user.ledger = Ledger()
            db.session.flush()
        user.created_at = registered_at
        user.last_login_at = last_login_at

        account = db.session.scalar(select(Account).where(
            Account.ledger_id == user.ledger.id,
            Account.bank_code == "DEMO",
        ))
        if account is None:
            account = Account(
                ledger_id=user.ledger.id,
                name="Tài khoản ngân hàng mẫu",
                type="BANK",
                opening_balance=rng.randrange(5_000, 51_000) * 1_000,
                bank_code="DEMO",
                last_four=f"{number:04d}"[-4:],
            )
            db.session.add(account)
            db.session.flush()

        if replace:
            db.session.execute(delete(Transaction).where(
                Transaction.account_id == account.id,
                Transaction.source == "SEED",
            ))

        existing = set(db.session.scalars(select(Transaction.dedup_key).where(Transaction.account_id == account.id)))
        base_income = rng.randrange(80, 501) * 100_000  # 8-50 million VND
        for month_index, month in enumerate(period):
            income = max(6_000_000, base_income + rng.randrange(-25, 26) * 100_000 + month_index * rng.randrange(0, 6) * 100_000)
            rows = [("Thu nhập", "Lương và thu nhập hàng tháng", income, "IN", 5)]
            for expense_index, (category, description, low, high) in enumerate(EXPENSES, start=1):
                ratio = rng.uniform(low, high)
                amount = max(50_000, round(income * ratio / 10_000) * 10_000)
                day = min(7 + expense_index * 2 + rng.randint(0, 3), monthrange(month.year, month.month)[1])
                rows.append((category, description, amount, "OUT", day))

            for category_name, description, amount, direction, day in rows:
                key = _key(email, month, category_name)
                if key in existing:
                    continue
                db.session.add(Transaction(
                    account_id=account.id,
                    category_id=categories[category_name].id,
                    posted_at=datetime(month.year, month.month, day, 9, number % 60),
                    amount=amount,
                    direction=direction,
                    description=f"{description} - tháng {month:%m/%Y}",
                    source="SEED",
                    ref_no=f"SEED-{number:03d}-{month:%Y%m}-{category_name}",
                    dedup_key=key,
                ))
                existing.add(key)
                inserted_transactions += 1

    db.session.commit()
    return {"users": count, "months": months, "transactions_inserted": inserted_transactions}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Tạo nhiều tài khoản với dữ liệu thu nhập và chi tiêu khác nhau")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--months", type=int, default=DEFAULT_MONTHS)
    parser.add_argument("--password", default=os.getenv("SEED_USERS_PASSWORD", DEFAULT_PASSWORD))
    parser.add_argument("--random-seed", type=int, default=20260906)
    parser.add_argument("--replace", action="store_true", help="Tạo lại các giao dịch SEED của nhóm tài khoản này")
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        result = seed_users(args.count, args.months, args.password, args.replace, args.random_seed)
    print(
        f"Đã seed {result['users']} tài khoản, {result['months']} tháng; "
        f"thêm {result['transactions_inserted']} giao dịch."
    )
    print(f"Đăng nhập: user001@smartexpense.local ... user{args.count:03d}@smartexpense.local")
    print("Mật khẩu lấy từ SEED_USERS_PASSWORD (hoặc mặc định SmartExpenseUser1!).")


if __name__ == "__main__":
    main()
