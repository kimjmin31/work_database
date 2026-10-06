from datetime import UTC, datetime


def get_timestamptz():
    return datetime.now(UTC).isoformat()
