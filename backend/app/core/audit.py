"""
Shared in-memory audit log.

Both main.py (GET /api/audit-logs, POST /api/ingest) and
auth.py (login events) import from here so they all write to
the same list without circular imports.
"""

from datetime import datetime, timezone

_AUDIT_LOGS: list[dict] = [
    {"event_id": "EVT-001", "timestamp": "2026-04-19 08:14:32", "user_uid": "HOT-001", "role": "Head of Technology", "action_type": "Login",          "status": "Success", "detail": "Successful login from 192.168.1.10"},
    {"event_id": "EVT-002", "timestamp": "2026-04-19 08:31:05", "user_uid": "LEC-047", "role": "Lecturer",           "action_type": "Login",          "status": "Success", "detail": "Successful login from 192.168.1.42"},
    {"event_id": "EVT-003", "timestamp": "2026-04-19 09:02:17", "user_uid": "HOT-001", "role": "Head of Technology", "action_type": "Data Upload",    "status": "Success", "detail": "Uploaded Capstone_data_20260324.csv (2.4 MB)"},
    {"event_id": "EVT-004", "timestamp": "2026-04-19 09:04:51", "user_uid": "HOT-001", "role": "Head of Technology", "action_type": "Data Processed", "status": "Success", "detail": "Anonymised 14,832 rows — PII fields stripped"},
    {"event_id": "EVT-005", "timestamp": "2026-04-19 09:45:03", "user_uid": "LEC-012", "role": "Lecturer",           "action_type": "Login Failed",   "status": "Alert",   "detail": "Invalid password — attempt 2 of 3"},
    {"event_id": "EVT-006", "timestamp": "2026-04-19 10:11:29", "user_uid": "LEC-012", "role": "Lecturer",           "action_type": "Login Failed",   "status": "Alert",   "detail": "Invalid password — attempt 3 of 3, account flagged"},
    {"event_id": "EVT-007", "timestamp": "2026-04-19 10:15:44", "user_uid": "LEC-047", "role": "Lecturer",           "action_type": "Access Denied",  "status": "Denied",  "detail": "Attempted to access /admin/users — insufficient role"},
    {"event_id": "EVT-008", "timestamp": "2026-04-19 11:00:00", "user_uid": "LEC-047", "role": "Lecturer",           "action_type": "Prediction Run", "status": "Success", "detail": "RF model v1 — T3 2025 batch inference completed"},
    {"event_id": "EVT-009", "timestamp": "2026-04-19 11:33:22", "user_uid": "HOT-001", "role": "Head of Technology", "action_type": "Prediction Run", "status": "Success", "detail": "RF model v1 — 14,832 predictions stored"},
    {"event_id": "EVT-010", "timestamp": "2026-04-19 12:07:19", "user_uid": "SYS",     "role": "System",             "action_type": "Access Denied",  "status": "Denied",  "detail": "Unauthenticated request to /api/v1/predictions"},
    {"event_id": "EVT-011", "timestamp": "2026-04-19 13:21:05", "user_uid": "LEC-099", "role": "Lecturer",           "action_type": "Login Failed",   "status": "Error",   "detail": "Database timeout during authentication check"},
    {"event_id": "EVT-012", "timestamp": "2026-04-19 14:45:38", "user_uid": "HOT-001", "role": "Head of Technology", "action_type": "Data Upload",    "status": "Alert",   "detail": "File size near limit: 48.2 MB uploaded of 50 MB max"},
]


def append_event(
    *,
    user_uid: str,
    role: str,
    action_type: str,
    status: str,
    detail: str,
) -> dict:
    event = {
        "event_id":   f"EVT-{len(_AUDIT_LOGS) + 1:03d}",
        "timestamp":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "user_uid":   user_uid,
        "role":       role,
        "action_type": action_type,
        "status":     status,
        "detail":     detail,
    }
    _AUDIT_LOGS.append(event)
    return event
