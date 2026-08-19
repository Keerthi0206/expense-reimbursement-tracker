import base64
import json
from datetime import datetime


def encode_cursor(created_at: datetime, row_id: str) -> str:
    raw = json.dumps({"created_at": created_at.isoformat(), "id": row_id})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    data = json.loads(raw)
    return datetime.fromisoformat(data["created_at"]), data["id"]
