from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_AUDIT_PATH = Path(
    os.environ.get("ANDURIL_AUDIT_LOG", "logs/audit.jsonl")
)


class AuditLogger:
    """Append-only JSONL audit log (SECURITY.md T9)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_AUDIT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **payload,
        }
        line = json.dumps(record, sort_keys=True, default=str)
        digest = hashlib.sha256(line.encode("utf-8")).hexdigest()
        entry = {"line": line, "sha256": digest}

        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

        return record

    def tail(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []

        lines = self.path.read_text(encoding="utf-8").splitlines()
        records: list[dict[str, Any]] = []
        for raw in lines[-limit:]:
            if not raw.strip():
                continue
            wrapper = json.loads(raw)
            line = wrapper["line"]
            expected = hashlib.sha256(line.encode("utf-8")).hexdigest()
            if wrapper.get("sha256") != expected:
                raise ValueError("audit log integrity check failed")
            records.append(json.loads(line))
        return records
