from flask import jsonify, request

from app.services.common import ValidationError


def json_body():
    return request.get_json(silent=True) or {}


def validation_response(function):
    try:
        return function()
    except ValidationError as exc:
        return jsonify(error=str(exc)), 400


def account_json(account, current_balance=None):
    if current_balance is None:
        from app.services.accounts import current_balances

        current_balance = current_balances([account])[account.id]
    return {
        "id": account.id, "name": account.name, "type": account.type,
        "opening_balance": account.opening_balance, "bank_code": account.bank_code,
        "current_balance": current_balance,
        "last_four": account.last_four, "archived": account.archived,
        "include_in_safe_to_spend": account.include_in_safe_to_spend,
    }


def transaction_json(item):
    return {"id": item.id, "date": item.posted_at.date().isoformat(), "amount": item.amount, "direction": item.direction, "account_id": item.account_id, "category_id": item.category_id, "description": item.description, "note": item.note, "source": item.source, "import_batch_id": item.import_batch_id}
