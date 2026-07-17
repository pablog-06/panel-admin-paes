from __future__ import annotations

import sqlite3
import statistics
import re
import json
import time
import unicodedata
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from panel.crypto import decrypt_text, encrypt_text, stable_digest


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "admin_paes.sqlite"
LEGACY_DB_PATH = DATA_DIR / "paes_results.sqlite"


def ensure_database_filename() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists() or not LEGACY_DB_PATH.exists():
        return
    LEGACY_DB_PATH.replace(DB_PATH)


@dataclass(frozen=True)
class EssayScore:
    student_name: str
    essay_name: str
    score: int
    source_board_id: str = ""
    source_card_id: str = ""


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    if db_path == DB_PATH:
        ensure_database_filename()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database(db_path: Path = DB_PATH):
    connection = connect(db_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(db_path: Path = DB_PATH) -> None:
    with database(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                name_hash TEXT,
                name_encrypted TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS essay_scores (
                id INTEGER PRIMARY KEY,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                essay_name TEXT NOT NULL,
                score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 1000),
                source_board_id TEXT NOT NULL DEFAULT '',
                source_card_id TEXT NOT NULL DEFAULT '',
                observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(student_id, essay_name)
            );

            CREATE INDEX IF NOT EXISTS idx_essay_scores_essay_name
                ON essay_scores(essay_name);

            CREATE INDEX IF NOT EXISTS idx_essay_scores_student_id
                ON essay_scores(student_id);

            CREATE TABLE IF NOT EXISTS content_visibility (
                id INTEGER PRIMARY KEY,
                content_type TEXT NOT NULL CHECK (content_type IN ('list', 'card')),
                content_id TEXT NOT NULL,
                student_board_id TEXT NOT NULL,
                student_name_hash TEXT NOT NULL,
                student_name_encrypted TEXT NOT NULL,
                visible INTEGER NOT NULL DEFAULT 1 CHECK (visible IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(content_type, content_id, student_board_id)
            );

            CREATE INDEX IF NOT EXISTS idx_content_visibility_content
                ON content_visibility(content_type, content_id);

            CREATE TABLE IF NOT EXISTS student_boards (
                board_id TEXT PRIMARY KEY,
                board_name TEXT NOT NULL,
                student_name_hash TEXT NOT NULL,
                student_name_encrypted TEXT NOT NULL,
                initials TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS new_content_queue (
                id INTEGER PRIMARY KEY,
                content_type TEXT NOT NULL CHECK (content_type IN ('list', 'card')),
                content_id TEXT NOT NULL UNIQUE,
                parent_list_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                sync_mode TEXT NOT NULL DEFAULT 'create' CHECK (sync_mode IN ('create', 'update')),
                payload_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'synced', 'archived')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_new_content_queue_status
                ON new_content_queue(status, content_type);

            CREATE TABLE IF NOT EXISTS new_content_delivery (
                id INTEGER PRIMARY KEY,
                content_id TEXT NOT NULL,
                student_board_id TEXT NOT NULL,
                trello_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'synced' CHECK (status IN ('synced', 'error')),
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(content_id, student_board_id)
            );

            CREATE INDEX IF NOT EXISTS idx_new_content_delivery_content
                ON new_content_delivery(content_id, status);

            CREATE TABLE IF NOT EXISTS content_delete_queue (
                id INTEGER PRIMARY KEY,
                content_type TEXT NOT NULL CHECK (content_type IN ('list', 'card')),
                content_id TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'synced', 'archived')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_content_delete_queue_status
                ON content_delete_queue(status, content_type);

            CREATE TABLE IF NOT EXISTS content_delete_delivery (
                id INTEGER PRIMARY KEY,
                content_id TEXT NOT NULL,
                student_board_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'synced' CHECK (status IN ('synced', 'error')),
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(content_id, student_board_id)
            );

            CREATE INDEX IF NOT EXISTS idx_content_delete_delivery_content
                ON content_delete_delivery(content_id, status);

            CREATE TABLE IF NOT EXISTS master_lists (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                pos REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'archived')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS master_cards (
                id TEXT PRIMARY KEY,
                list_id TEXT NOT NULL REFERENCES master_lists(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                pos REAL NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'archived')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_master_cards_list
                ON master_cards(list_id, status, pos);
            """
        )
        _ensure_student_security_columns(connection)
        _ensure_new_content_queue_columns(connection)
        _migrate_student_names_to_encrypted(connection)


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def _ensure_student_security_columns(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "students")
    if "name_hash" not in columns:
        connection.execute("ALTER TABLE students ADD COLUMN name_hash TEXT")
    if "name_encrypted" not in columns:
        connection.execute("ALTER TABLE students ADD COLUMN name_encrypted TEXT")
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_students_name_hash ON students(name_hash)")


def _ensure_new_content_queue_columns(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "new_content_queue")
    if "sync_mode" not in columns:
        connection.execute("ALTER TABLE new_content_queue ADD COLUMN sync_mode TEXT NOT NULL DEFAULT 'create'")
    if "payload_json" not in columns:
        connection.execute("ALTER TABLE new_content_queue ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}'")


def _migrate_student_names_to_encrypted(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT id, name, name_hash, name_encrypted FROM students"
    ).fetchall()
    for row in rows:
        if row["name_hash"] and row["name_encrypted"]:
            continue
        legacy_name = str(row["name"] or "").strip()
        if not legacy_name:
            continue
        name_hash = stable_digest(legacy_name)
        connection.execute(
            """
            UPDATE students
            SET name = ?, name_hash = ?, name_encrypted = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (name_hash, name_hash, encrypt_text(legacy_name), row["id"]),
        )


def _student_identity(student_name: str) -> tuple[str, str]:
    normalized = student_name.strip()
    return stable_digest(normalized), encrypt_text(normalized)


def _decrypt_student_name(row: sqlite3.Row) -> str:
    encrypted = str(row["student_name_encrypted"] or "")
    if encrypted:
        try:
            return decrypt_text(encrypted)
        except Exception:
            return "Estudiante protegido"
    return "Estudiante protegido"


def upsert_essay_score(score: EssayScore, db_path: Path = DB_PATH) -> None:
    if not score.student_name.strip():
        raise ValueError("student_name no puede estar vacio.")
    if not score.essay_name.strip():
        raise ValueError("essay_name no puede estar vacio.")
    if not 0 <= int(score.score) <= 1000:
        raise ValueError("score debe estar entre 0 y 1000.")

    initialize_database(db_path)
    with database(db_path) as connection:
        student_hash, encrypted_name = _student_identity(score.student_name)
        connection.execute(
            """
            INSERT INTO students(name, name_hash, name_encrypted)
            VALUES (?, ?, ?)
            ON CONFLICT(name_hash) DO UPDATE SET
                name_encrypted = excluded.name_encrypted,
                updated_at = CURRENT_TIMESTAMP
            """,
            (student_hash, student_hash, encrypted_name),
        )
        student_id = connection.execute(
            "SELECT id FROM students WHERE name_hash = ?",
            (student_hash,),
        ).fetchone()["id"]
        connection.execute(
            """
            INSERT INTO essay_scores(
                student_id, essay_name, score, source_board_id, source_card_id
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(student_id, essay_name) DO UPDATE SET
                score = excluded.score,
                source_board_id = excluded.source_board_id,
                source_card_id = excluded.source_card_id,
                observed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                student_id,
                score.essay_name.strip(),
                int(score.score),
                score.source_board_id.strip(),
                score.source_card_id.strip(),
            ),
        )


def upsert_many(scores: Iterable[EssayScore], db_path: Path = DB_PATH) -> None:
    for score in scores:
        upsert_essay_score(score, db_path)


def replace_imported_scores(scores: Iterable[EssayScore], db_path: Path = DB_PATH) -> None:
    scores = list(scores)
    initialize_database(db_path)
    with database(db_path) as connection:
        connection.execute("DELETE FROM essay_scores WHERE source_board_id <> ''")
        connection.execute(
            """
            DELETE FROM students
            WHERE id NOT IN (SELECT DISTINCT student_id FROM essay_scores)
            """
        )
        for score in scores:
            student_name = score.student_name.strip()
            essay_name = score.essay_name.strip()
            if not student_name or not essay_name:
                continue
            if not 0 <= int(score.score) <= 1000:
                continue
            student_hash, encrypted_name = _student_identity(student_name)
            connection.execute(
                """
                INSERT INTO students(name, name_hash, name_encrypted)
                VALUES (?, ?, ?)
                ON CONFLICT(name_hash) DO UPDATE SET
                    name_encrypted = excluded.name_encrypted,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (student_hash, student_hash, encrypted_name),
            )
            student_id = connection.execute(
                "SELECT id FROM students WHERE name_hash = ?",
                (student_hash,),
            ).fetchone()["id"]
            connection.execute(
                """
                INSERT INTO essay_scores(
                    student_id, essay_name, score, source_board_id, source_card_id
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(student_id, essay_name) DO UPDATE SET
                    score = excluded.score,
                    source_board_id = excluded.source_board_id,
                    source_card_id = excluded.source_card_id,
                    observed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    student_id,
                    essay_name,
                    int(score.score),
                    score.source_board_id.strip(),
                    score.source_card_id.strip(),
                ),
            )


def delete_students_by_names(student_names: Iterable[str], db_path: Path = DB_PATH) -> None:
    name_hashes = [stable_digest(name) for name in student_names if name.strip()]
    if not name_hashes:
        return
    initialize_database(db_path)
    with database(db_path) as connection:
        connection.executemany("DELETE FROM students WHERE name_hash = ?", [(name_hash,) for name_hash in name_hashes])


def essay_sort_key(essay_name: str) -> tuple[int, str]:
    match = re.search(r"\bensayo\s+(\d{1,3})\b", essay_name, re.IGNORECASE)
    if match:
        return int(match.group(1)), essay_name
    return -1, essay_name


def get_student_vector(student_name: str, db_path: Path = DB_PATH) -> list[tuple[str, int]]:
    initialize_database(db_path)
    student_hash = stable_digest(student_name)
    with database(db_path) as connection:
        rows = connection.execute(
            """
            SELECT essay_scores.essay_name, essay_scores.score
            FROM essay_scores
            JOIN students ON students.id = essay_scores.student_id
            WHERE students.name_hash = ?
            ORDER BY essay_scores.observed_at, essay_scores.essay_name
            """,
            (student_hash,),
        ).fetchall()
    return [(row["essay_name"], int(row["score"])) for row in rows]


def hidden_student_board_ids(content_type: str, content_id: str, db_path: Path = DB_PATH) -> set[str]:
    if content_type not in {"list", "card"} or not content_id.strip():
        return set()
    initialize_database(db_path)
    with database(db_path) as connection:
        rows = connection.execute(
            """
            SELECT student_board_id
            FROM content_visibility
            WHERE content_type = ? AND content_id = ? AND visible = 0
            """,
            (content_type, content_id.strip()),
        ).fetchall()
    return {str(row["student_board_id"]) for row in rows}


def save_hidden_students(
    content_type: str,
    content_id: str,
    students: Iterable[dict[str, str]],
    hidden_board_ids: Iterable[str],
    db_path: Path = DB_PATH,
) -> None:
    if content_type not in {"list", "card"}:
        raise ValueError("content_type debe ser 'list' o 'card'.")
    content_id = content_id.strip()
    if not content_id:
        raise ValueError("content_id no puede estar vacio.")

    hidden_ids = {str(board_id).strip() for board_id in hidden_board_ids if str(board_id).strip()}
    initialize_database(db_path)
    with database(db_path) as connection:
        connection.execute(
            "DELETE FROM content_visibility WHERE content_type = ? AND content_id = ?",
            (content_type, content_id),
        )
        for student in students:
            board_id = str(student.get("board_id") or "").strip()
            name = str(student.get("student_name") or "").strip()
            if not board_id or board_id not in hidden_ids or not name:
                continue
            connection.execute(
                """
                INSERT INTO content_visibility(
                    content_type, content_id, student_board_id,
                    student_name_hash, student_name_encrypted, visible
                )
                VALUES (?, ?, ?, ?, ?, 0)
                ON CONFLICT(content_type, content_id, student_board_id) DO UPDATE SET
                    visible = 0,
                    student_name_hash = excluded.student_name_hash,
                    student_name_encrypted = excluded.student_name_encrypted,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (content_type, content_id, board_id, stable_digest(name), encrypt_text(name)),
            )
        visible_ids = [
            str(student.get("board_id") or "").strip()
            for student in students
            if str(student.get("board_id") or "").strip()
            and str(student.get("board_id") or "").strip() not in hidden_ids
        ]
        if visible_ids:
            connection.executemany(
                """
                DELETE FROM new_content_delivery
                WHERE content_id = ? AND student_board_id = ?
                  AND EXISTS (
                      SELECT 1
                      FROM content_delete_delivery
                      WHERE content_delete_delivery.content_id = new_content_delivery.content_id
                        AND content_delete_delivery.student_board_id = new_content_delivery.student_board_id
                        AND content_delete_delivery.status = 'synced'
                  )
                """,
                [(content_id, board_id) for board_id in visible_ids],
            )
            connection.executemany(
                "DELETE FROM content_delete_delivery WHERE content_id = ? AND student_board_id = ?",
                [(content_id, board_id) for board_id in visible_ids],
            )


def sync_student_board_registry(students: Iterable[dict[str, str]], db_path: Path = DB_PATH) -> dict[str, Any]:
    students = list(students)
    initialize_database(db_path)
    seen_ids = {str(student.get("board_id") or "").strip() for student in students if student.get("board_id")}
    with database(db_path) as connection:
        previous_rows = connection.execute(
            """
            SELECT board_id, board_name, student_name_encrypted, initials, status, last_seen_at, created_at
            FROM student_boards
            """
        ).fetchall()
        previous_by_id = {str(row["board_id"]): row for row in previous_rows}
        previous_open_ids = {
            board_id for board_id, row in previous_by_id.items()
            if str(row["status"] or "") == "open"
        }
        new_ids = sorted(seen_ids - set(previous_by_id))
        reopened_ids = sorted(
            board_id for board_id in seen_ids & set(previous_by_id)
            if str(previous_by_id[board_id]["status"] or "") != "open"
        )
        archived_ids = sorted(previous_open_ids - seen_ids)

        if seen_ids:
            placeholders = ",".join("?" for _ in seen_ids)
            connection.execute(
                f"""
                UPDATE student_boards
                SET status = 'archived', updated_at = CURRENT_TIMESTAMP
                WHERE board_id NOT IN ({placeholders})
                """,
                tuple(seen_ids),
            )
        else:
            connection.execute(
                "UPDATE student_boards SET status = 'archived', updated_at = CURRENT_TIMESTAMP"
            )

        for student in students:
            board_id = str(student.get("board_id") or "").strip()
            student_name = str(student.get("student_name") or "").strip()
            board_name = str(student.get("board_name") or "").strip()
            if not board_id or not student_name:
                continue
            connection.execute(
                """
                INSERT INTO student_boards(
                    board_id, board_name, student_name_hash, student_name_encrypted,
                    initials, status, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, 'open', CURRENT_TIMESTAMP)
                ON CONFLICT(board_id) DO UPDATE SET
                    board_name = excluded.board_name,
                    student_name_hash = excluded.student_name_hash,
                    student_name_encrypted = excluded.student_name_encrypted,
                    initials = excluded.initials,
                    status = 'open',
                    last_seen_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    board_id,
                    board_name,
                    stable_digest(student_name),
                    encrypt_text(student_name),
                    str(student.get("initials") or ""),
                ),
            )
    return {
        "active_count": len(seen_ids),
        "new_board_ids": new_ids,
        "reopened_board_ids": reopened_ids,
        "archived_board_ids": archived_ids,
    }


def mark_all_master_content_pending(db_path: Path = DB_PATH) -> dict[str, int]:
    initialize_database(db_path)
    lists_marked = 0
    cards_marked = 0
    with database(db_path) as connection:
        list_rows = connection.execute(
            "SELECT id, name FROM master_lists WHERE status = 'open' ORDER BY pos ASC"
        ).fetchall()
        card_rows = connection.execute(
            """
            SELECT master_cards.id, master_cards.list_id, master_cards.title,
                   master_cards.description, master_cards.payload_json, master_lists.name AS list_name
            FROM master_cards
            JOIN master_lists ON master_lists.id = master_cards.list_id
            WHERE master_cards.status = 'open' AND master_lists.status = 'open'
            ORDER BY master_lists.pos ASC, master_cards.pos ASC
            """
        ).fetchall()

    for row in list_rows:
        title = str(row["name"] or row["id"])
        mark_new_content_for_students(
            "list",
            str(row["id"]),
            title,
            payload={"title": title},
            db_path=db_path,
        )
        lists_marked += 1

    for row in card_rows:
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload.update(
            {
                "title": str(row["title"] or ""),
                "description": str(row["description"] or ""),
                "list_id": str(row["list_id"] or ""),
                "list_name": str(row["list_name"] or ""),
            }
        )
        payload.setdefault("links", [])
        payload.setdefault("images", [])
        payload.setdefault("files", [])
        payload.setdefault("checklists", [])
        mark_new_content_for_students(
            "card",
            str(row["id"]),
            str(row["title"] or row["id"]),
            str(row["list_id"] or ""),
            sync_mode="create",
            payload=payload,
            db_path=db_path,
        )
        cards_marked += 1
    return {"lists": lists_marked, "cards": cards_marked}


def load_cohort_status(db_path: Path = DB_PATH) -> dict[str, Any]:
    initialize_database(db_path)
    with database(db_path) as connection:
        rows = connection.execute(
            """
            SELECT board_id, board_name, student_name_encrypted, initials, status,
                   last_seen_at, created_at, updated_at
            FROM student_boards
            ORDER BY status ASC, board_name COLLATE NOCASE ASC
            """
        ).fetchall()
    students = []
    for row in rows:
        name = _decrypt_student_name(row)
        status = str(row["status"] or "")
        students.append(
            {
                "board_id": str(row["board_id"] or ""),
                "board_name": str(row["board_name"] or ""),
                "student_name": name,
                "initials": str(row["initials"] or ""),
                "status": status,
                "last_seen_at": str(row["last_seen_at"] or ""),
                "created_at": str(row["created_at"] or ""),
                "updated_at": str(row["updated_at"] or ""),
            }
        )
    active_count = sum(1 for item in students if item["status"] == "open")
    archived_count = sum(1 for item in students if item["status"] == "archived")
    return {
        "active": active_count,
        "archived": archived_count,
        "active_count": active_count,
        "archived_count": archived_count,
        "students": students,
    }


def _default_master_id(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000)}"


def _dedupe_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", without_accents.casefold())).strip()


def load_master_board(db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    initialize_database(db_path)
    with database(db_path) as connection:
        lists = connection.execute(
            """
            SELECT id, name, pos
            FROM master_lists
            WHERE status = 'open'
            ORDER BY pos ASC, created_at ASC
            """
        ).fetchall()
        cards = connection.execute(
            """
            SELECT id, list_id, title, description, pos, payload_json
            FROM master_cards
            WHERE status = 'open'
            ORDER BY pos ASC, created_at ASC
            """
        ).fetchall()

    cards_by_list: dict[str, list[dict[str, Any]]] = {}
    for row in cards:
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        card = {
            "id": str(row["id"]),
            "title": str(row["title"] or ""),
            "description": str(row["description"] or ""),
            "links": list(payload.get("links") or []),
            "images": list(payload.get("images") or []),
            "files": list(payload.get("files") or []),
            "checklists": list(payload.get("checklists") or []),
            "pos": float(row["pos"] or 0),
            "source": "local",
        }
        cards_by_list.setdefault(str(row["list_id"]), []).append(card)

    return [
        {
            "id": str(row["id"]),
            "name": str(row["name"] or ""),
            "pos": float(row["pos"] or 0),
            "cards": cards_by_list.get(str(row["id"]), []),
            "source": "local",
        }
        for row in lists
    ]


def ensure_master_defaults(db_path: Path = DB_PATH) -> None:
    defaults = [
        ("chemistry", "Quimica", 1000.0),
        ("physics", "Fisica", 2000.0),
        ("biology", "Biologia", 3000.0),
        ("scientific-method", "Metodo cientifico", 4000.0),
    ]
    initialize_database(db_path)
    with database(db_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS total FROM master_lists WHERE status = 'open'"
        ).fetchone()["total"]
        if int(count or 0) > 0:
            return
        connection.executemany(
            """
            INSERT OR IGNORE INTO master_lists(id, name, pos)
            VALUES (?, ?, ?)
            """,
            defaults,
        )


def migrate_queued_content_to_master(db_path: Path = DB_PATH) -> None:
    initialize_database(db_path)
    deleted_list_titles = content_delete_titles("list", db_path)
    deleted_card_titles = content_delete_titles("card", db_path)
    with database(db_path) as connection:
        list_rows = connection.execute(
            """
            SELECT content_id, title, payload_json, created_at
            FROM new_content_queue
            WHERE content_type = 'list' AND status <> 'archived'
            ORDER BY id ASC
            """
        ).fetchall()
        for index, row in enumerate(list_rows, start=1):
            title = str(row["title"] or "").strip()
            if not title or title in deleted_list_titles:
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO master_lists(id, name, pos)
                VALUES (?, ?, ?)
                """,
                (str(row["content_id"]), title, 10000.0 + index),
            )

        card_rows = connection.execute(
            """
            SELECT content_id, parent_list_id, title, payload_json
            FROM new_content_queue
            WHERE content_type = 'card' AND status <> 'archived'
            ORDER BY id ASC
            """
        ).fetchall()
        for index, row in enumerate(card_rows, start=1):
            title = str(row["title"] or "").strip()
            list_id = str(row["parent_list_id"] or "").strip()
            if not title or title in deleted_card_titles or not list_id:
                continue
            parent = connection.execute(
                "SELECT id FROM master_lists WHERE id = ? AND status = 'open'",
                (list_id,),
            ).fetchone()
            if parent is None:
                continue
            try:
                payload = json.loads(str(row["payload_json"] or "{}"))
            except json.JSONDecodeError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            description = str(payload.get("description") or "")
            payload.setdefault("title", title)
            payload.setdefault("description", description)
            payload.setdefault("links", [])
            payload.setdefault("images", [])
            payload.setdefault("files", [])
            payload.setdefault("checklists", [])
            payload.setdefault("list_id", list_id)
            connection.execute(
                """
                INSERT OR IGNORE INTO master_cards(id, list_id, title, description, pos, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(row["content_id"]),
                    list_id,
                    title,
                    description,
                    10000.0 + index,
                    json.dumps(payload, ensure_ascii=True),
                ),
            )


def create_master_list(name: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("El nombre de la lista no puede estar vacio.")
    list_id = _default_master_id("list")
    pos = time.time() * 1000
    initialize_database(db_path)
    with database(db_path) as connection:
        existing_rows = connection.execute(
            "SELECT id, name, pos FROM master_lists WHERE status = 'open'"
        ).fetchall()
        clean_key = _dedupe_key(clean_name)
        for row in existing_rows:
            if _dedupe_key(str(row["name"] or "")) == clean_key:
                return {
                    "id": str(row["id"]),
                    "name": str(row["name"] or clean_name),
                    "pos": float(row["pos"] or pos),
                    "cards": [],
                    "source": "local",
                    "deduped": True,
                }
        connection.execute(
            """
            INSERT INTO master_lists(id, name, pos)
            VALUES (?, ?, ?)
            """,
            (list_id, clean_name, pos),
        )
    mark_new_content_for_students("list", list_id, clean_name, payload={"title": clean_name}, db_path=db_path)
    return {"id": list_id, "name": clean_name, "pos": pos, "cards": [], "source": "local"}


def upsert_master_card(
    *,
    card_id: str,
    list_id: str,
    title: str,
    description: str = "",
    links: list[str] | None = None,
    images: list[dict[str, Any]] | None = None,
    files: list[dict[str, Any]] | None = None,
    checklists: list[dict[str, Any]] | None = None,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    title = str(title or "").strip()
    list_id = str(list_id or "").strip()
    card_id = str(card_id or "").strip() or _default_master_id("card")
    if not list_id or not title:
        raise ValueError("La tarjeta necesita lista y titulo.")
    payload = {
        "title": title,
        "description": str(description or "").strip(),
        "links": [str(link).strip() for link in (links or []) if str(link).strip()],
        "images": [image for image in (images or []) if isinstance(image, dict)],
        "files": [file for file in (files or []) if isinstance(file, dict)],
        "checklists": [checklist for checklist in (checklists or []) if isinstance(checklist, dict)],
        "list_id": list_id,
        "list_name": "",
    }
    pos = time.time() * 1000
    initialize_database(db_path)
    with database(db_path) as connection:
        list_row = connection.execute(
            "SELECT name FROM master_lists WHERE id = ? AND status = 'open'",
            (list_id,),
        ).fetchone()
        if list_row is None:
            raise ValueError("La lista local no existe.")
        payload["list_name"] = str(list_row["name"] or "")
        existing = connection.execute(
            "SELECT id, pos FROM master_cards WHERE id = ?",
            (card_id,),
        ).fetchone()
        if not existing:
            sibling_rows = connection.execute(
                """
                SELECT id, title, pos
                FROM master_cards
                WHERE list_id = ? AND status = 'open'
                """,
                (list_id,),
            ).fetchall()
            title_key = _dedupe_key(title)
            for row in sibling_rows:
                if _dedupe_key(str(row["title"] or "")) == title_key:
                    card_id = str(row["id"])
                    existing = row
                    break
        if existing:
            pos = float(existing["pos"] or pos)
        connection.execute(
            """
            INSERT INTO master_cards(id, list_id, title, description, pos, payload_json, status)
            VALUES (?, ?, ?, ?, ?, ?, 'open')
            ON CONFLICT(id) DO UPDATE SET
                list_id = excluded.list_id,
                title = excluded.title,
                description = excluded.description,
                payload_json = excluded.payload_json,
                status = 'open',
                updated_at = CURRENT_TIMESTAMP
            """,
            (card_id, list_id, title, payload["description"], pos, json.dumps(payload, ensure_ascii=True)),
        )
    mark_new_content_for_students(
        "card",
        card_id,
        title,
        list_id,
        sync_mode="update" if existing else "create",
        payload=payload,
        db_path=db_path,
    )
    return {"card_id": card_id, **payload}


def move_master_list(list_id: str, pos: int | float | str, db_path: Path = DB_PATH) -> dict[str, Any]:
    initialize_database(db_path)
    with database(db_path) as connection:
        connection.execute(
            "UPDATE master_lists SET pos = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'open'",
            (float(pos), str(list_id or "").strip()),
        )
    return {"id": str(list_id or "").strip(), "pos": float(pos)}


def move_master_card(card_id: str, list_id: str, pos: int | float | str, db_path: Path = DB_PATH) -> dict[str, Any]:
    initialize_database(db_path)
    with database(db_path) as connection:
        connection.execute(
            """
            UPDATE master_cards
            SET list_id = ?, pos = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'open'
            """,
            (str(list_id or "").strip(), float(pos), str(card_id or "").strip()),
        )
    return {"id": str(card_id or "").strip(), "list_id": str(list_id or "").strip(), "pos": float(pos)}


def archive_master_list(list_id: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    list_id = str(list_id or "").strip()
    initialize_database(db_path)
    with database(db_path) as connection:
        row = connection.execute("SELECT name FROM master_lists WHERE id = ?", (list_id,)).fetchone()
        if row is None:
            raise ValueError("La lista local no existe.")
        connection.execute("UPDATE master_lists SET status = 'archived', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (list_id,))
        connection.execute("UPDATE master_cards SET status = 'archived', updated_at = CURRENT_TIMESTAMP WHERE list_id = ?", (list_id,))
    mark_content_delete_for_students("list", list_id, str(row["name"] or list_id), db_path=db_path)
    return {"id": list_id, "closed": True}


def archive_master_card(card_id: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    card_id = str(card_id or "").strip()
    initialize_database(db_path)
    with database(db_path) as connection:
        row = connection.execute("SELECT title FROM master_cards WHERE id = ?", (card_id,)).fetchone()
        if row is None:
            raise ValueError("La tarjeta local no existe.")
        connection.execute("UPDATE master_cards SET status = 'archived', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (card_id,))
    mark_content_delete_for_students("card", card_id, str(row["title"] or card_id), db_path=db_path)
    return {"id": card_id, "closed": True}


def mark_master_content_pending(content_type: str, content_id: str, db_path: Path = DB_PATH) -> None:
    content_type = str(content_type or "").strip()
    content_id = str(content_id or "").strip()
    if content_type == "list":
        initialize_database(db_path)
        with database(db_path) as connection:
            row = connection.execute(
                "SELECT name FROM master_lists WHERE id = ? AND status = 'open'",
                (content_id,),
            ).fetchone()
        if row:
            mark_new_content_for_students("list", content_id, str(row["name"] or content_id), payload={"title": str(row["name"] or "")}, db_path=db_path)
        return
    if content_type != "card":
        return
    initialize_database(db_path)
    with database(db_path) as connection:
        row = connection.execute(
            """
            SELECT master_cards.id, master_cards.list_id, master_cards.title, master_cards.description,
                   master_cards.payload_json, master_lists.name AS list_name
            FROM master_cards
            JOIN master_lists ON master_lists.id = master_cards.list_id
            WHERE master_cards.id = ? AND master_cards.status = 'open'
            """,
            (content_id,),
        ).fetchone()
    if not row:
        return
    try:
        payload = json.loads(str(row["payload_json"] or "{}"))
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.update(
        {
            "title": str(row["title"] or ""),
            "description": str(row["description"] or ""),
            "list_id": str(row["list_id"] or ""),
            "list_name": str(row["list_name"] or ""),
        }
    )
    payload.setdefault("links", [])
    payload.setdefault("images", [])
    payload.setdefault("files", [])
    payload.setdefault("checklists", [])
    mark_new_content_for_students(
        "card",
        content_id,
        str(row["title"] or content_id),
        str(row["list_id"] or ""),
        sync_mode="update",
        payload=payload,
        db_path=db_path,
    )


def mark_new_content_for_students(
    content_type: str,
    content_id: str,
    title: str,
    parent_list_id: str = "",
    sync_mode: str = "create",
    payload: dict[str, Any] | None = None,
    db_path: Path = DB_PATH,
) -> None:
    if content_type not in {"list", "card"}:
        raise ValueError("content_type debe ser list o card.")
    content_id = str(content_id or "").strip()
    title = str(title or "").strip()
    if not content_id or not title:
        return
    sync_mode = "update" if sync_mode == "update" else "create"
    payload_json = "{}"
    if isinstance(payload, dict):
        import json

        payload_json = json.dumps(payload, ensure_ascii=True)
    initialize_database(db_path)
    with database(db_path) as connection:
        existing = connection.execute(
            "SELECT sync_mode, status FROM new_content_queue WHERE content_id = ?",
            (content_id,),
        ).fetchone()
        if existing and existing["status"] == "pending" and existing["sync_mode"] == "create":
            sync_mode = "create"
        connection.execute(
            """
            INSERT INTO new_content_queue(content_type, content_id, parent_list_id, title, sync_mode, payload_json, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
            ON CONFLICT(content_id) DO UPDATE SET
                content_type = excluded.content_type,
                parent_list_id = excluded.parent_list_id,
                title = excluded.title,
                sync_mode = excluded.sync_mode,
                payload_json = excluded.payload_json,
                status = CASE
                    WHEN new_content_queue.status = 'archived' THEN 'archived'
                    ELSE 'pending'
                END,
                updated_at = CURRENT_TIMESTAMP
            """,
            (content_type, content_id, str(parent_list_id or "").strip(), title, sync_mode, payload_json),
        )


def pending_new_content_ids(db_path: Path = DB_PATH) -> set[str]:
    initialize_database(db_path)
    with database(db_path) as connection:
        rows = connection.execute(
            "SELECT content_id FROM new_content_queue WHERE status = 'pending'"
        ).fetchall()
    return {str(row["content_id"]) for row in rows}


def pending_new_content_rows(db_path: Path = DB_PATH) -> list[dict[str, str]]:
    initialize_database(db_path)
    with database(db_path) as connection:
        rows = connection.execute(
            """
            SELECT content_type, content_id, parent_list_id, title, sync_mode, payload_json, status
            FROM new_content_queue
            WHERE status = 'pending'
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def delivered_student_ids(content_id: str, db_path: Path = DB_PATH) -> set[str]:
    initialize_database(db_path)
    with database(db_path) as connection:
        rows = connection.execute(
            """
            SELECT student_board_id
            FROM new_content_delivery
            WHERE content_id = ? AND status = 'synced'
            """,
            (str(content_id or "").strip(),),
        ).fetchall()
    return {str(row["student_board_id"]) for row in rows}


def delivered_trello_id(content_id: str, student_board_id: str, db_path: Path = DB_PATH) -> str:
    initialize_database(db_path)
    with database(db_path) as connection:
        row = connection.execute(
            """
            SELECT trello_id
            FROM new_content_delivery
            WHERE content_id = ? AND student_board_id = ? AND status = 'synced'
            """,
            (str(content_id or "").strip(), str(student_board_id or "").strip()),
        ).fetchone()
    return str(row["trello_id"] or "") if row else ""


def record_new_content_delivery(
    content_id: str,
    student_board_id: str,
    trello_id: str = "",
    *,
    status: str = "synced",
    error: str = "",
    db_path: Path = DB_PATH,
) -> None:
    initialize_database(db_path)
    with database(db_path) as connection:
        connection.execute(
            """
            INSERT INTO new_content_delivery(content_id, student_board_id, trello_id, status, error)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(content_id, student_board_id) DO UPDATE SET
                trello_id = excluded.trello_id,
                status = excluded.status,
                error = excluded.error,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                str(content_id or "").strip(),
                str(student_board_id or "").strip(),
                str(trello_id or "").strip(),
                status,
                str(error or "").strip(),
            ),
        )


def mark_new_content_synced(content_ids: Iterable[str], db_path: Path = DB_PATH) -> None:
    ids = [str(content_id).strip() for content_id in content_ids if str(content_id).strip()]
    if not ids:
        return
    initialize_database(db_path)
    with database(db_path) as connection:
        connection.executemany(
            """
            UPDATE new_content_queue
            SET status = 'synced', updated_at = CURRENT_TIMESTAMP
            WHERE content_id = ?
            """,
            [(content_id,) for content_id in ids],
        )


def mark_content_delete_for_students(
    content_type: str,
    content_id: str,
    title: str,
    db_path: Path = DB_PATH,
) -> None:
    if content_type not in {"list", "card"}:
        raise ValueError("content_type debe ser list o card.")
    content_id = str(content_id or "").strip()
    title = str(title or "").strip() or content_id
    if not content_id:
        return
    initialize_database(db_path)
    with database(db_path) as connection:
        connection.execute(
            """
            INSERT INTO content_delete_queue(content_type, content_id, title, status)
            VALUES (?, ?, ?, 'pending')
            ON CONFLICT(content_id) DO UPDATE SET
                content_type = excluded.content_type,
                title = excluded.title,
                status = CASE
                    WHEN content_delete_queue.status = 'archived' THEN 'archived'
                    ELSE 'pending'
                END,
                updated_at = CURRENT_TIMESTAMP
            """,
            (content_type, content_id, title),
        )


def pending_content_delete_rows(db_path: Path = DB_PATH) -> list[dict[str, str]]:
    initialize_database(db_path)
    with database(db_path) as connection:
        rows = connection.execute(
            """
            SELECT content_type, content_id, title, status
            FROM content_delete_queue
            WHERE status = 'pending'
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def content_delete_titles(content_type: str, db_path: Path = DB_PATH) -> set[str]:
    if content_type not in {"list", "card"}:
        return set()
    initialize_database(db_path)
    with database(db_path) as connection:
        rows = connection.execute(
            """
            SELECT title
            FROM content_delete_queue
            WHERE content_type = ? AND status IN ('pending', 'synced')
            """,
            (content_type,),
        ).fetchall()
    return {str(row["title"] or "").strip() for row in rows if str(row["title"] or "").strip()}


def deleted_student_ids(content_id: str, db_path: Path = DB_PATH) -> set[str]:
    initialize_database(db_path)
    with database(db_path) as connection:
        rows = connection.execute(
            """
            SELECT student_board_id
            FROM content_delete_delivery
            WHERE content_id = ? AND status = 'synced'
            """,
            (str(content_id or "").strip(),),
        ).fetchall()
    return {str(row["student_board_id"]) for row in rows}


def record_content_delete_delivery(
    content_id: str,
    student_board_id: str,
    *,
    status: str = "synced",
    error: str = "",
    db_path: Path = DB_PATH,
) -> None:
    initialize_database(db_path)
    with database(db_path) as connection:
        connection.execute(
            """
            INSERT INTO content_delete_delivery(content_id, student_board_id, status, error)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(content_id, student_board_id) DO UPDATE SET
                status = excluded.status,
                error = excluded.error,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                str(content_id or "").strip(),
                str(student_board_id or "").strip(),
                status,
                str(error or "").strip(),
            ),
        )


def mark_content_delete_synced(content_ids: Iterable[str], db_path: Path = DB_PATH) -> None:
    ids = [str(content_id).strip() for content_id in content_ids if str(content_id).strip()]
    if not ids:
        return
    initialize_database(db_path)
    with database(db_path) as connection:
        connection.executemany(
            """
            UPDATE content_delete_queue
            SET status = 'synced', updated_at = CURRENT_TIMESTAMP
            WHERE content_id = ?
            """,
            [(content_id,) for content_id in ids],
        )


def latest_exam_summary(db_path: Path = DB_PATH) -> dict[str, Any] | None:
    initialize_database(db_path)
    with database(db_path) as connection:
        essay_rows = connection.execute(
            """
            SELECT essay_name
            FROM essay_scores
            GROUP BY essay_name
            """
        ).fetchall()
        if not essay_rows:
            return None
        latest_exam = max((row["essay_name"] for row in essay_rows), key=essay_sort_key)

        rows = connection.execute(
            """
            SELECT students.name_encrypted AS student_name_encrypted, essay_scores.score
            FROM essay_scores
            JOIN students ON students.id = essay_scores.student_id
            WHERE essay_scores.essay_name = ?
            ORDER BY essay_scores.score ASC, students.name_hash ASC
            """,
            (latest_exam,),
        ).fetchall()

    scores = [int(row["score"]) for row in rows]
    if not scores:
        return None

    minimum = rows[0]
    maximum = rows[-1]
    return {
        "exam": latest_exam,
        "average": round(sum(scores) / len(scores)),
        "median": round(statistics.median(scores)),
        "stddev": round(statistics.pstdev(scores)) if len(scores) > 1 else 0,
        "min": {"score": int(minimum["score"]), "student": _decrypt_student_name(minimum)},
        "max": {"score": int(maximum["score"]), "student": _decrypt_student_name(maximum)},
        "count": len(scores),
    }


def latest_exam_ranking(db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    initialize_database(db_path)
    with database(db_path) as connection:
        essay_rows = connection.execute(
            """
            SELECT essay_name
            FROM essay_scores
            GROUP BY essay_name
            """
        ).fetchall()
        if not essay_rows:
            return []
        latest_exam = max((row["essay_name"] for row in essay_rows), key=essay_sort_key)
        rows = connection.execute(
            """
            SELECT students.name_encrypted AS student_name_encrypted, essay_scores.score
            FROM essay_scores
            JOIN students ON students.id = essay_scores.student_id
            WHERE essay_scores.essay_name = ?
            ORDER BY essay_scores.score DESC, students.name_hash ASC
            """,
            (latest_exam,),
        ).fetchall()
    return [
        {"student": _decrypt_student_name(row), "score": int(row["score"])}
        for row in rows
    ]

def median_scores_by_exam(db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    initialize_database(db_path)
    with database(db_path) as connection:
        rows = connection.execute(
            """
            SELECT essay_name, score
            FROM essay_scores
            """
        ).fetchall()

    scores_by_exam: dict[str, list[int]] = {}
    for row in rows:
        essay_name = str(row["essay_name"] or "")
        scores_by_exam.setdefault(essay_name, []).append(int(row["score"]))

    points: list[dict[str, Any]] = []
    for essay_name, scores in scores_by_exam.items():
        exam_number, _ = essay_sort_key(essay_name)
        if exam_number < 0:
            continue
        points.append(
            {
                "exam": exam_number,
                "label": essay_name,
                "median": int(round(statistics.median(scores))),
                "count": len(scores),
            }
        )
    return sorted(points, key=lambda point: (point["exam"], point["label"]))


def build_results_panel(db_path: Path = DB_PATH) -> dict[str, Any]:
    summary = latest_exam_summary(db_path)
    median_series = median_scores_by_exam(db_path)
    ranking = latest_exam_ranking(db_path)
    if summary is None:
        stats = {
            "exam": "Ultimo ensayo",
            "average": "--",
            "median": "--",
            "stddev": "--",
            "min": {"score": "--", "student": "Sin datos"},
            "max": {"score": "--", "student": "Sin datos"},
        }
        note = (
            "Base local protegida lista. Aun no hay resultados importados desde "
            "listas privadas Ensayos."
        )
    else:
        stats = {
            "exam": summary["exam"],
            "average": str(summary["average"]),
            "median": str(summary["median"]),
            "stddev": str(summary["stddev"]),
            "min": {
                "score": str(summary["min"]["score"]),
                "student": summary["min"]["student"],
            },
            "max": {
                "score": str(summary["max"]["score"]),
                "student": summary["max"]["student"],
            },
        }
        note = (
            f"Estadisticas agregadas de {summary['count']} estudiantes. "
            "No se editan datos de alumnos desde este panel."
        )

    return {
        "id": "global-results",
        "name": "Resultados globales",
        "kind": "locked",
        "stats": stats,
        "median_series": median_series,
        "ranking": ranking,
        "note": note,
        "cards": [],
    }
