"""Seed system categories, classification rules, import templates and the admin.

FR-09 requires a two-level category tree with a `nature` on every leaf. The v1
seed only covered six leaves, which left the UI with no income category at all:
`loadCategories()` in the frontend keeps only categories that carry a nature, so
a freshly registered user could not record a salary. The tree below covers every
category the interface already has translations for.
"""
import json
import os
from datetime import date

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import CategorizationRule, Category, ImportTemplate, User

# Parent -> [(leaf name, nature)]
CATEGORIES = {
    "Thu nhập": [
        ("Thu nhập", "COMMITTED"),
    ],
    "Thiết yếu": [
        ("Nhà ở", "COMMITTED"),
        ("Học phí", "COMMITTED"),
        ("Điện nước", "SEMI_FIXED"),
        ("Viễn thông", "SEMI_FIXED"),
        ("Y tế", "SEMI_FIXED"),
    ],
    "Linh hoạt": [
        ("Ăn uống", "DISCRETIONARY"),
        ("Mua sắm", "DISCRETIONARY"),
        ("Di chuyển", "DISCRETIONARY"),
        ("Nhiên liệu", "SEMI_FIXED"),
        ("Học tập", "DISCRETIONARY"),
        ("Khác", "DISCRETIONARY"),
    ],
    # Internal movements between the user's own accounts. statistics.py excludes
    # this name from income/expense totals so a transfer is not counted twice;
    # before this seed the filter matched nothing because the row did not exist.
    "Nội bộ": [
        ("Chuyển khoản", "COMMITTED"),
        # FR-15: rows that match no classification rule land here.
        ("Uncategorised", "DISCRETIONARY"),
    ],
}

TEMPLATES = [
    ("AUTO", "Tự động nhận diện CSV - ngân hàng khác", {"auto_detect": True}),
    ("VCB", "Vietcombank - số tiền có dấu", {"header_rows": 1, "date": 0, "description": 1, "amount": 2, "ref_no": 3, "date_format": "%d/%m/%Y"}),
    ("TCB", "Techcombank - ghi nợ/ghi có", {"header_rows": 1, "date": 0, "description": 1, "debit": 2, "credit": 3, "ref_no": 4, "date_format": "%d/%m/%Y"}),
    ("MB", "MB Bank - ghi nợ/ghi có", {"header_rows": 1, "date": 0, "ref_no": 1, "description": 2, "debit": 3, "credit": 4, "date_format": "%d/%m/%Y"}),
]

# FR-15: ordered `pattern -> category`, lowest priority number wins.
RULES = [
    (10, r"highlands|starbucks|coffee|cafe|ca phe|trung nguyen|phuc long", "Ăn uống"),
    (20, r"shopee|lazada|tiki|sendo|dien may|the gioi di dong", "Mua sắm"),
    (30, r"grab|be group|gojek|xanh sm|taxi|vexere", "Di chuyển"),
    (40, r"circle k|winmart|bach hoa xanh|co ?opmart|vinmart|big ?c|lotte mart", "Ăn uống"),
    (50, r"evn|dien luc|nuoc sach|sawaco|tien dien|tien nuoc", "Điện nước"),
    (60, r"viettel|vinaphone|mobifone|fpt telecom|vnpt", "Viễn thông"),
    (70, r"petrolimex|pvoil|xang dau|shell", "Nhiên liệu"),
    (80, r"benh vien|phong kham|nha thuoc|pharmacity|long chau", "Y tế"),
    (90, r"hoc phi|tuition|khoa hoc|udemy|coursera", "Học tập"),
    (100, r"tien nha|tien thue nha|thue nha|rent", "Nhà ở"),
    (110, r"luong|salary|thu nhap|tien luong", "Thu nhập"),
    (120, r"chuyen khoan noi bo|internal transfer|ck noi bo", "Chuyển khoản"),
]


def seed():
    for parent_name, children in CATEGORIES.items():
        parent = db.session.query(Category).filter_by(name=parent_name, owner_id=None).first()
        if not parent:
            parent = Category(name=parent_name, nature=None)
            db.session.add(parent)
            db.session.flush()
        for name, nature in children:
            if name == parent_name:
                # A leaf that shares its parent's name would violate
                # uq_categories_owner_name; keep the single row and give it a nature.
                parent.nature = nature
                continue
            if not db.session.query(Category).filter_by(name=name, owner_id=None).first():
                db.session.add(Category(name=name, nature=nature, parent_id=parent.id))
    db.session.flush()

    for bank_code, name, mapping in TEMPLATES:
        if not db.session.query(ImportTemplate).filter_by(bank_code=bank_code, name=name).first():
            db.session.add(ImportTemplate(bank_code=bank_code, name=name, mapping_json=json.dumps(mapping), active=True))

    for priority, pattern, category_name in RULES:
        category = db.session.query(Category).filter_by(name=category_name, owner_id=None).first()
        if category and not db.session.query(CategorizationRule).filter_by(priority=priority).first():
            db.session.add(CategorizationRule(pattern=pattern, category_id=category.id, priority=priority, active=True))

    admin_email = os.getenv("ADMIN_EMAIL", "admin@smartfinance.local").lower()
    if not db.session.query(User).filter_by(email=admin_email).first():
        admin_password = os.getenv("ADMIN_PASSWORD")
        if not admin_password:
            raise RuntimeError("ADMIN_PASSWORD phải được đặt trong môi trường khi seed")
        # FR-27: the ADMIN role is seeded directly; no runtime path elevates a USER.
        db.session.add(User(
            email=admin_email, full_name="Quản trị hệ thống", date_of_birth=date(1990, 1, 1),
            consent=False, role="ADMIN",
            password_hash=generate_password_hash(admin_password, method="pbkdf2:sha256:600000"),
        ))
    db.session.commit()


if __name__ == "__main__":
    application = create_app()
    with application.app_context():
        seed()
