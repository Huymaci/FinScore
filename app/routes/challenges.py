from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from app.services import challenges as service

from .helpers import json_body, validation_response

challenges_bp = Blueprint("challenges", __name__, url_prefix="/challenges")


def challenge_json(item):
    return {
        "id": item.id, "category_id": item.category_id, "category": item.category.name,
        "habit_name": item.habit_name,
        "baseline_count": item.baseline_count, "target_count": item.target_count,
        "average_amount": item.average_amount,
        "period_start": item.period_start.isoformat() if item.period_start else None,
        "period_end": item.period_end.isoformat() if item.period_end else None,
        "actual_count": service.progress(item), "saved_amount": item.saved_amount,
        "status": item.status,
    }


@challenges_bp.get("")
@login_required
def listing():
    return jsonify(items=[challenge_json(item) for item in service.list_challenges(current_user.id)])


@challenges_bp.post("/<int:challenge_id>/respond")
@login_required
def respond(challenge_id):
    return validation_response(lambda: jsonify(challenge_json(service.respond(current_user.id, challenge_id, json_body().get("action")))))
