from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import AuditLog, User
from app.services.alerts import recompute
from app.services.challenges import evaluate_due, generate_proposal


def _run():
    for user_id in list(db.session.scalars(select(User.id).where(User.role == "USER"))):
        recompute(user_id)
        # Challenge windows close and new proposals appear on the same schedule
        # as the alerts; without this the challenge state only advanced when the
        # user happened to open the page.
        evaluate_due(user_id)
        generate_proposal(user_id)
    db.session.add(AuditLog(action="NIGHTLY_JOB:SUCCESS"))
    db.session.commit()


def run():
    try:
        _run()
    except Exception:
        db.session.rollback()
        db.session.add(AuditLog(action="NIGHTLY_JOB:FAILED"))
        db.session.commit()
        raise


if __name__ == "__main__":
    application = create_app()
    with application.app_context():
        run()
