from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_URL = os.getenv("PROJECT130_API_URL", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.getenv("PROJECT130_API_KEY", "")
OUT = Path(os.getenv("PROJECT130_BACKUP_DIR", "backups"))
OUT.mkdir(parents=True, exist_ok=True)

req = urllib.request.Request(f"{API_URL}/api/export")
if API_KEY:
    req.add_header("X-API-Key", API_KEY)
with urllib.request.urlopen(req, timeout=20) as response:
    payload = response.read()

ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
json_path = OUT / f"snapshot-{ts}.json"
json_path.write_bytes(payload)
checksum = hashlib.sha256(payload).hexdigest()
parsed = json.loads(payload)
counts = {k: len(v) for k, v in parsed.get("data", {}).items()}
manifest = {
    "created_at": ts,
    "snapshot": json_path.name,
    "sha256": checksum,
    "schema_version": parsed.get("schema_version"),
    "record_counts": counts,
}
manifest_path = OUT / f"snapshot-{ts}.manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(manifest, indent=2, ensure_ascii=False))
