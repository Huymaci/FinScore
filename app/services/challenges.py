import re
import unicodedata
from datetime import date, timedelta
from math import ceil

from sqlalchemy import select

from app.extensions import db
from app.models import Category, HabitChallenge, Transaction

from .common import ValidationError, user_account_ids

OPEN_STATUSES = {"PROPOSED", "ACTIVE"}


def _owned(user_id, challenge_id):
    challenge = db.session.scalar(select(HabitChallenge).where(HabitChallenge.id == challenge_id, HabitChallenge.user_id == user_id))
    if not challenge:
        raise ValidationError("Thử thách không tồn tại")
    return challenge


def _habit_identity(description):
    raw = description.strip()
    if "_" in raw:
        raw = raw.split("_", 1)[1].split(",", 1)[0]
    decomposed = unicodedata.normalize("NFKD", raw.lower())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    words = [word for word in re.findall(r"[a-z]+", plain) if word not in {"tai", "nd", "the", "thanh", "toan", "giao", "dich"}]
    key = " ".join(words[:4]) or "chi tieu lap lai"
    return key, " ".join(word.capitalize() for word in key.split())


def _count_transactions(user_id, category_id, start, end, habit_key=None):
    descriptions = db.session.scalars(select(Transaction.description).where(
        Transaction.direction == "OUT", Transaction.category_id == category_id,
        Transaction.posted_at >= start, Transaction.posted_at < end + timedelta(days=1),
        Transaction.account_id.in_(user_account_ids(user_id)),
    )).all()
    if not habit_key:
        return len(descriptions)
    return sum(_habit_identity(description)[0] == habit_key for description in descriptions)


def evaluate_due(user_id, today=None):
    today = today or date.today()
    changed = False
    active = db.session.scalars(select(HabitChallenge).where(
        HabitChallenge.user_id == user_id, HabitChallenge.status == "ACTIVE",
        HabitChallenge.period_end < today,
    )).all()
    for challenge in active:
        actual = _count_transactions(user_id, challenge.category_id, challenge.period_start, challenge.period_end, challenge.habit_key)
        challenge.actual_count = actual
        challenge.saved_amount = max(0, challenge.baseline_count - actual) * challenge.average_amount
        challenge.status = "COMPLETED" if actual <= challenge.target_count else "FAILED"
        changed = True
    if changed:
        db.session.commit()
    return len(active)


def generate_proposal(user_id, today=None):
    today = today or date.today()
    existing = db.session.scalar(select(HabitChallenge.id).where(
        HabitChallenge.user_id == user_id, HabitChallenge.status.in_(OPEN_STATUSES)
    ).limit(1))
    if existing:
        return None
    start = today - timedelta(days=28)
    rows = db.session.execute(select(Transaction.category_id, Transaction.description, Transaction.amount).join(Category).where(
        Transaction.direction == "OUT", Transaction.posted_at >= start,
        Transaction.posted_at < today + timedelta(days=1),
        Transaction.account_id.in_(user_account_ids(user_id)),
        Category.nature == "DISCRETIONARY",
    )).all()
    groups = {}
    for category_id, description, amount in rows:
        habit_key, habit_name = _habit_identity(description)
        group = groups.setdefault((category_id, habit_key), {"name": habit_name, "amounts": []})
        group["amounts"].append(amount)
    candidates = [(len(group["amounts"]), category_id, habit_key, group) for (category_id, habit_key), group in groups.items() if len(group["amounts"]) >= 4]
    if not candidates:
        return None
    count, category_id, habit_key, group = max(candidates, key=lambda item: item[0])
    average = sum(group["amounts"]) / count
    baseline = max(1, ceil(count / 4))
    latest = db.session.scalar(select(HabitChallenge).where(
        HabitChallenge.user_id == user_id, HabitChallenge.category_id == category_id,
        HabitChallenge.habit_key == habit_key,
    ).order_by(HabitChallenge.id.desc()).limit(1))
    if latest and latest.status == "DECLINED" and latest.created_at.date() >= today - timedelta(days=30):
        return None
    previous = latest if latest and latest.status in {"COMPLETED", "FAILED"} else db.session.scalar(select(HabitChallenge).where(
        HabitChallenge.user_id == user_id, HabitChallenge.category_id == category_id,
        HabitChallenge.habit_key == habit_key,
        HabitChallenge.status.in_({"COMPLETED", "FAILED"}),
    ).order_by(HabitChallenge.id.desc()).limit(1))
    if previous:
        target = max(1, previous.target_count - 1) if previous.status == "COMPLETED" else min(baseline, previous.target_count + 1)
    else:
        target = max(1, baseline - 2)
    challenge = HabitChallenge(
        user_id=user_id, category_id=category_id, habit_key=habit_key, habit_name=group["name"], baseline_count=baseline,
        target_count=target, average_amount=max(1, round(average)), status="PROPOSED",
    )
    db.session.add(challenge)
    db.session.commit()
    return challenge


def progress(challenge, today=None):
    if challenge.status != "ACTIVE":
        return challenge.actual_count
    today = today or date.today()
    return _count_transactions(challenge.user_id, challenge.category_id, challenge.period_start, min(today, challenge.period_end), challenge.habit_key)


def list_challenges(user_id, today=None):
    today = today or date.today()
    evaluate_due(user_id, today)
    generate_proposal(user_id, today)
    return list(db.session.scalars(select(HabitChallenge).where(HabitChallenge.user_id == user_id).order_by(HabitChallenge.id.desc())))


def respond(user_id, challenge_id, action, today=None):
    challenge = _owned(user_id, challenge_id)
    today = today or date.today()
    action = str(action).upper()
    if challenge.status != "PROPOSED" or action not in {"ACCEPT", "DECLINE"}:
        raise ValidationError("Phản hồi thử thách không hợp lệ")
    if action == "ACCEPT":
        challenge.status = "ACTIVE"
        challenge.period_start = today
        challenge.period_end = today + timedelta(days=6)
    else:
        challenge.status = "DECLINED"
    db.session.commit()
    return challenge
