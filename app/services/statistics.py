from datetime import date, timedelta

from sqlalchemy import extract, func, select

from app.extensions import db
from app.models import Budget, Category, Transaction

from .budgets import month_start, safe_to_spend, spent_by_category
from .common import ValidationError, money, parse_date, user_account_ids


def _next_month(value):
    return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)


def dashboard(user_id, month=None):
    start = month_start(month or date.today().replace(day=1))
    end = _next_month(start)
    rows = db.session.execute(select(Transaction.direction, func.coalesce(func.sum(Transaction.amount), 0)).join(Category).where(
        Transaction.posted_at >= start, Transaction.posted_at < end,
        Transaction.account_id.in_(user_account_ids(user_id)),
        Category.name != "Chuyển khoản",
    ).group_by(Transaction.direction)).all()
    totals = {direction: money(total) for direction, total in rows}
    spent = spent_by_category(user_id, start)
    progress = []
    for budget, name in db.session.execute(select(Budget, Category.name).join(Category).where(Budget.user_id == user_id, Budget.month == start)):
        actual = spent.get(budget.category_id, 0)
        ratio = actual / budget.amount if budget.amount else 0
        # Up to 85% is on track, more than 85% through 100% is near the
        # limit, and only an actual overspend is over budget.
        status = "RED" if ratio > 1 else "AMBER" if ratio > 0.85 else "GREEN"
        label = "Trong ngân sách" if status == "GREEN" else "Sắp vượt ngân sách" if status == "AMBER" else "Vượt ngân sách"
        progress.append({"category_id": budget.category_id, "category": name, "budget": budget.amount, "spent": actual, "percent": round(ratio * 100, 1), "status": status, "label": label})
    income, expense = totals.get("IN", 0), totals.get("OUT", 0)
    return {"income": income, "expense": expense, "net": income - expense, "safe_to_spend": safe_to_spend(user_id, start), "budget_progress": progress}


def breakdown(user_id, date_from, date_to):
    start, inclusive_end = parse_date(date_from, "date_from"), parse_date(date_to, "date_to")
    if start > inclusive_end:
        raise ValidationError("date_from không được sau date_to")
    try:
        end = inclusive_end + timedelta(days=1)
    except OverflowError as exc:
        raise ValidationError("date_to nằm ngoài phạm vi hỗ trợ") from exc
    rows = db.session.execute(select(Category.id, Category.name, func.sum(Transaction.amount)).join(Transaction).where(
        Transaction.direction == "OUT", Transaction.posted_at >= start, Transaction.posted_at < end,
        Transaction.account_id.in_(user_account_ids(user_id)),
        Category.name != "Chuyển khoản",
    ).group_by(Category.id, Category.name).order_by(func.sum(Transaction.amount).desc())).all()
    return [{"category_id": item[0], "category": item[1], "amount": money(item[2])} for item in rows]


def trend(user_id, through=None):
    cursor = month_start(through or date.today().replace(day=1))
    months = []
    for _ in range(12):
        months.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    months.reverse()
    window_start, window_end = months[0], _next_month(months[-1])
    # NFR-09 forbids N+1 patterns. Twelve separate month queries became one
    # grouped scan: same result, one round trip instead of twelve.
    # extract() is dialect-neutral: MySQL gets EXTRACT, SQLite gets STRFTIME.
    # date_format() would have been MySQL-only and broken the unit tests.
    year, month = extract("year", Transaction.posted_at), extract("month", Transaction.posted_at)
    rows = db.session.execute(select(year, month, Transaction.direction, func.coalesce(func.sum(Transaction.amount), 0)).join(Category).where(
        Transaction.posted_at >= window_start, Transaction.posted_at < window_end,
        Transaction.account_id.in_(user_account_ids(user_id)),
        Category.name != "Chuyển khoản",
    ).group_by(year, month, Transaction.direction)).all()
    totals = {}
    for row_year, row_month, direction, amount in rows:
        totals.setdefault(f"{int(row_year):04d}-{int(row_month):02d}", {})[direction] = money(amount)
    result = []
    for start in months:
        label = start.strftime("%Y-%m")
        entry = totals.get(label, {})
        result.append({"month": label, "income": money(entry.get("IN", 0)), "expense": money(entry.get("OUT", 0))})
    return result


def spending_analysis(user_id, date_from, date_to):
    items = breakdown(user_id, date_from, date_to)
    start, end = parse_date(date_from), parse_date(date_to)
    year, month = extract('year', Transaction.posted_at), extract('month', Transaction.posted_at)
    rows = db.session.execute(select(year, month, Category.id, Category.name, func.sum(Transaction.amount))
        .join(Transaction).where(
            Transaction.account_id.in_(user_account_ids(user_id)), Transaction.direction == 'OUT',
            Transaction.posted_at >= start, Transaction.posted_at < end + timedelta(days=1),
            Category.name != 'Chuyển khoản',
        ).group_by(year, month, Category.id, Category.name)).all()
    budgets = {(b.month.year, b.month.month, b.category_id): b.amount for b in db.session.scalars(
        select(Budget).where(Budget.user_id == user_id,
                            Budget.month >= start.date().replace(day=1), Budget.month <= end.date()))}
    comparisons = []
    for y, m, category_id, name, amount in rows:
        amount = money(amount)
        budget = budgets.get((int(y), int(m), category_id))
        status = 'NO_BUDGET' if budget is None else 'OVER' if amount > budget else 'NEAR' if amount >= budget * .85 else 'WITHIN'
        comparisons.append({'month': f'{int(y):04d}-{int(m):02d}', 'category': name,
                            'amount': amount, 'budget': budget, 'status': status,
                            'excess': max(0, amount - budget) if budget is not None else 0})
    return {'date_from': start.date().isoformat(), 'date_to': end.date().isoformat(),
            'total_expense': sum(item['amount'] for item in items), 'items': items,
            'comparisons': sorted(comparisons, key=lambda item: (item['month'], -item['amount']))}
