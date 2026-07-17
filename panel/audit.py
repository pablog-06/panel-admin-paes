from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from panel.crypto import decrypt_json_line, encrypt_bytes, encrypt_json_line
from panel.results_db import DB_PATH


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
BACKUP_DIR = DATA_DIR / "backups"
LOG_DIR = DATA_DIR / "logs"
AUDIT_LOG_PATH = LOG_DIR / "activity.jsonl"
ENCRYPTED_AUDIT_LOG_PATH = LOG_DIR / "activity.jsonl.enc"
MAX_LOG_BYTES = 1 * 1024 * 1024
MAX_ROTATED_LOGS = 3
BACKUP_RETENTION_DAYS = 3
MAX_BACKUP_FILES = 12


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_filename(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.strip())
    return cleaned.strip("_")[:80] or "backup"


def ensure_audit_dirs() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def rotate_audit_log_if_needed() -> None:
    ensure_audit_dirs()
    if not ENCRYPTED_AUDIT_LOG_PATH.exists() or ENCRYPTED_AUDIT_LOG_PATH.stat().st_size < MAX_LOG_BYTES:
        return

    oldest = LOG_DIR / f"activity.{MAX_ROTATED_LOGS}.jsonl.enc"
    if oldest.exists():
        oldest.unlink()

    for index in range(MAX_ROTATED_LOGS - 1, 0, -1):
        source = LOG_DIR / f"activity.{index}.jsonl.enc"
        if source.exists():
            source.replace(LOG_DIR / f"activity.{index + 1}.jsonl.enc")

    ENCRYPTED_AUDIT_LOG_PATH.replace(LOG_DIR / "activity.1.jsonl.enc")


def migrate_plain_audit_log_to_encrypted() -> None:
    ensure_audit_dirs()
    if not AUDIT_LOG_PATH.exists():
        return
    lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    if lines:
        with ENCRYPTED_AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
            for line in lines:
                try:
                    decoded = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(decoded, dict):
                    handle.write(encrypt_json_line(decoded) + "\n")
    AUDIT_LOG_PATH.unlink(missing_ok=True)


def _backup_files() -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    return [
        item for item in BACKUP_DIR.iterdir()
        if item.is_file() and item.suffix.lower() in {".json", ".sqlite", ".sqlite3", ".db", ".enc"}
    ]


def prune_backups() -> None:
    ensure_audit_dirs()
    backup_files = _backup_files()
    if not backup_files:
        return

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=BACKUP_RETENTION_DAYS)
    for item in backup_files:
        modified = datetime.fromtimestamp(item.stat().st_mtime, timezone.utc)
        if modified < cutoff:
            item.unlink(missing_ok=True)

    remaining = sorted(_backup_files(), key=lambda path: path.stat().st_mtime, reverse=True)
    for item in remaining[MAX_BACKUP_FILES:]:
        item.unlink(missing_ok=True)


def migrate_plain_backups_to_encrypted() -> None:
    ensure_audit_dirs()
    for item in list(BACKUP_DIR.iterdir()):
        if not item.is_file() or item.suffix.lower() not in {".json", ".sqlite", ".sqlite3", ".db"}:
            continue
        encrypted_path = item.with_name(f"{item.name}.enc")
        encrypted_path.write_bytes(encrypt_bytes(item.read_bytes()))
        item.unlink(missing_ok=True)


def enforce_retention() -> None:
    migrate_plain_audit_log_to_encrypted()
    migrate_plain_backups_to_encrypted()
    rotate_audit_log_if_needed()
    prune_backups()


def write_audit_log(action: str, detail: str, *, status: str = "ok", meta: dict[str, Any] | None = None) -> None:
    ensure_audit_dirs()
    rotate_audit_log_if_needed()
    event = {
        "timestamp": utc_timestamp(),
        "status": status,
        "action": action,
        "detail": detail,
        "meta": meta or {},
    }
    with ENCRYPTED_AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(encrypt_json_line(event) + "\n")
    rotate_audit_log_if_needed()


def _read_plain_audit_log(limit: int) -> list[dict[str, Any]]:
    if not AUDIT_LOG_PATH.exists():
        return []
    events: list[dict[str, Any]] = []
    lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    for line in lines:
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            events.append(decoded)
    return events


def _read_encrypted_audit_log(limit: int) -> list[dict[str, Any]]:
    if not ENCRYPTED_AUDIT_LOG_PATH.exists():
        return []
    events: list[dict[str, Any]] = []
    lines = ENCRYPTED_AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    for line in lines:
        try:
            events.append(decrypt_json_line(line))
        except Exception:
            continue
    return events


def read_audit_log(limit: int = 40) -> list[dict[str, Any]]:
    ensure_audit_dirs()
    events = [*_read_plain_audit_log(limit), *_read_encrypted_audit_log(limit)]
    events = sorted(events, key=lambda event: str(event.get("timestamp", "")), reverse=True)
    return events[:limit]


def backup_database(reason: str = "manual") -> str:
    ensure_audit_dirs()
    prune_backups()
    if not DB_PATH.exists():
        write_audit_log("backup_database", "SQLite no existe; no se genero backup.", status="skip")
        return ""
    filename = f"{utc_timestamp().replace(':', '-')}_{safe_filename(reason)}.sqlite.enc"
    destination = BACKUP_DIR / filename
    destination.write_bytes(encrypt_bytes(DB_PATH.read_bytes()))
    write_audit_log(
        "backup_database",
        "Backup SQLite creado.",
        meta={"path": str(destination), "reason": reason},
    )
    prune_backups()
    return str(destination)


def backup_board_snapshot(board_title: str, board_lists: list[dict[str, Any]], reason: str) -> str:
    ensure_audit_dirs()
    prune_backups()
    filename = f"{utc_timestamp().replace(':', '-')}_{safe_filename(reason)}.json.enc"
    destination = BACKUP_DIR / filename
    payload = {
        "created_at": utc_timestamp(),
        "reason": reason,
        "board_title": board_title,
        "lists": board_lists,
    }
    destination.write_bytes(encrypt_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")))
    write_audit_log(
        "backup_board",
        "Snapshot local del tablero creado.",
        meta={"path": str(destination), "reason": reason, "board_title": board_title},
    )
    prune_backups()
    return str(destination)
