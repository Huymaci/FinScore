"""In-process request/error metrics for the admin console.

FR-50 asks the admin console to surface operational health. Request volume,
latency percentiles and recent API failures have no home in the schema, and
adding a write on every request would put a row in the hot path of each page
load. This module keeps them in memory instead: counters reset when the
process restarts, and under multiple workers each worker reports its own
slice. `snapshot()` says so through `partial=True` so the UI can label the
number honestly rather than implying a cluster-wide total.

NFR-10: nothing here stores a password, token, amount, description or full
email. Endpoints are recorded from the matched url_rule (`/admin/users/<int>`),
never the concrete path, so an id never lands in a bucket key.
"""

import threading
import time
from collections import Counter, deque
from datetime import datetime, timedelta, timezone

_MAX_ERRORS = 200
_HOURS = 24

_lock = threading.Lock()
_started_at = time.time()
_total = Counter()          # status class -> count
_by_hour = {}               # hour bucket (epoch hours) -> {"total": n, "errors": n}
_durations = deque(maxlen=5000)
_errors = deque(maxlen=_MAX_ERRORS)
_error_groups = {}          # (method, rule, status) -> aggregate


def _hour_bucket(moment=None):
    return int((moment or time.time()) // 3600)


def _prune(now_bucket):
    for bucket in [key for key in _by_hour if key <= now_bucket - _HOURS]:
        del _by_hour[bucket]


def reset():
    """Test helper: drop every counter so cases do not bleed into each other."""
    with _lock:
        _total.clear()
        _by_hour.clear()
        _durations.clear()
        _errors.clear()
        _error_groups.clear()


def record_request(method, rule, status, duration_ms):
    """Record one finished request. `rule` must be the url_rule, not the path."""
    bucket = _hour_bucket()
    klass = f"{status // 100}xx"
    with _lock:
        _prune(bucket)
        _total[klass] += 1
        _total["all"] += 1
        slot = _by_hour.setdefault(bucket, {"total": 0, "errors": 0})
        slot["total"] += 1
        if status >= 500:
            slot["errors"] += 1
        _durations.append(duration_ms)


def record_error(method, rule, status, message, user_id=None):
    """Record one failed request so the console can list it.

    `message` is the generic error text already returned to the caller; callers
    must not pass a stack trace or any request body through it.
    """
    now = datetime.now(timezone.utc)
    key = (method, rule, status)
    with _lock:
        group = _error_groups.get(key)
        if group:
            group["count"] += 1
            group["last_seen"] = now
            group["message"] = message
        else:
            _error_groups[key] = {
                "method": method, "rule": rule, "status": status,
                "count": 1, "first_seen": now, "last_seen": now,
                "message": message, "handled": False,
            }
        _errors.appendleft({
            "method": method, "rule": rule, "status": status,
            "message": message, "user_id": user_id, "at": now,
        })


def mark_handled(method, rule, status, handled=True):
    with _lock:
        group = _error_groups.get((method, rule, status))
        if not group:
            return False
        group["handled"] = bool(handled)
        return True


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return round(ordered[index])


def snapshot():
    """Aggregate view for GET /admin/system-status."""
    bucket = _hour_bucket()
    with _lock:
        _prune(bucket)
        durations = list(_durations)
        hours = [
            {"hour": (datetime.fromtimestamp((bucket - offset) * 3600, timezone.utc)).isoformat(),
             "total": _by_hour.get(bucket - offset, {}).get("total", 0),
             "errors": _by_hour.get(bucket - offset, {}).get("errors", 0)}
            for offset in range(_HOURS - 1, -1, -1)
        ]
        total = sum(hour["total"] for hour in hours)
        failures = sum(hour["errors"] for hour in hours)
        counts = dict(_total)
        groups = sorted(_error_groups.values(), key=lambda item: item["last_seen"], reverse=True)
    return {
        "uptime_seconds": int(time.time() - _started_at),
        "requests_24h": total,
        "errors_24h": failures,
        "error_rate": round(failures * 100 / total, 2) if total else 0.0,
        "by_class": {key: value for key, value in counts.items() if key != "all"},
        "p95_ms": _percentile(durations, 0.95),
        "p99_ms": _percentile(durations, 0.99),
        "traffic": hours,
        "partial": True,
        "since": datetime.fromtimestamp(_started_at, timezone.utc).isoformat(),
        "error_groups": [
            {**group,
             "first_seen": group["first_seen"].isoformat(),
             "last_seen": group["last_seen"].isoformat(),
             "id": f"{group['method']} {group['rule']} {group['status']}"}
            for group in groups
        ],
    }


def recent_errors(limit=50):
    with _lock:
        items = list(_errors)[:limit]
    return [{**item, "at": item["at"].isoformat()} for item in items]


def cutoff(days):
    return datetime.now(timezone.utc) - timedelta(days=days)
