from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from panel.results_db import (
    DB_PATH,
    content_delete_titles,
    database,
    initialize_database,
    load_master_board,
    record_new_content_delivery,
    sync_student_board_registry,
)
from panel.sync_planner import normalize_label
from panel.trello_client import (
    TrelloConfig,
    fetch_board_lists_with_cards_read_only,
    fetch_student_boards_read_only,
)


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "::".join(str(part or "").strip() for part in parts)
    slug = normalize_label(raw).replace(" ", "-")[:64] or "item"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{slug}-{digest}"


def _deleted_keys(content_type: str, db_path: Path) -> set[str]:
    return {normalize_label(title) for title in content_delete_titles(content_type, db_path)}


def _existing_list_ids(connection) -> dict[str, str]:
    rows = connection.execute(
        "SELECT id, name FROM master_lists WHERE status = 'open'"
    ).fetchall()
    return {normalize_label(str(row["name"] or "")): str(row["id"]) for row in rows}


def _existing_card_ids(connection) -> dict[tuple[str, str], str]:
    rows = connection.execute(
        """
        SELECT master_cards.id, master_cards.title, master_cards.list_id
        FROM master_cards
        JOIN master_lists ON master_lists.id = master_cards.list_id
        WHERE master_cards.status = 'open' AND master_lists.status = 'open'
        """
    ).fetchall()
    return {
        (str(row["list_id"]), normalize_label(str(row["title"] or ""))): str(row["id"])
        for row in rows
    }


def _card_payload(card: dict[str, Any], list_id: str, list_name: str) -> dict[str, Any]:
    title = str(card.get("title") or "Tarjeta sin titulo").strip()
    description = str(card.get("description") or "").strip()
    return {
        "title": title,
        "description": description,
        "links": list(card.get("links") or []),
        "images": list(card.get("images") or []),
        "files": list(card.get("files") or []),
        "checklists": list(card.get("checklists") or []),
        "list_id": list_id,
        "list_name": list_name,
    }


def _master_has_cards(db_path: Path) -> bool:
    initialize_database(db_path)
    with database(db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM master_cards WHERE status = 'open'"
        ).fetchone()
    return bool(row and int(row["total"] or 0) > 0)


def import_master_from_student_boards(
    config: TrelloConfig,
    *,
    max_boards: int = 80,
    db_path: Path = DB_PATH,
) -> dict[str, int | str]:
    """Bootstrap the local master from PAES student boards without writing to Trello.

    The first readable PAES board is used as the canonical content template.
    Remaining boards are read only to map already-existing Trello ids to local
    master ids, so later visibility/delete operations do not create duplicates.
    """

    initialize_database(db_path)
    if _master_has_cards(db_path):
        return {
            "status": "skipped",
            "students": 0,
            "boards_mapped": 0,
            "lists": 0,
            "cards": 0,
            "deliveries": 0,
        }

    students = fetch_student_boards_read_only(config)
    sync_student_board_registry(students, db_path)
    deleted_lists = _deleted_keys("list", db_path)
    deleted_cards = _deleted_keys("card", db_path)
    readable = [student for student in students if student.get("board_id")][: max_boards or None]

    canonical_student: dict[str, str] | None = None
    canonical_lists: list[dict[str, Any]] = []
    for student in readable:
        try:
            _, lists = fetch_board_lists_with_cards_read_only(
                config,
                str(student["board_id"]),
                include_checklists=True,
            )
        except Exception:
            continue
        filtered = [
            board_list
            for board_list in lists
            if normalize_label(str(board_list.get("name") or "")) not in deleted_lists
        ]
        if any(board_list.get("cards") for board_list in filtered):
            canonical_student = student
            canonical_lists = filtered
            break

    if not canonical_student:
        return {
            "status": "no_source",
            "students": len(students),
            "boards_mapped": 0,
            "lists": 0,
            "cards": 0,
            "deliveries": 0,
        }

    local_list_ids: dict[str, str] = {}
    local_card_ids: dict[tuple[str, str], str] = {}
    lists_count = 0
    cards_count = 0
    deliveries = 0

    with database(db_path) as connection:
        existing_lists = _existing_list_ids(connection)
        existing_cards = _existing_card_ids(connection)
        for list_index, board_list in enumerate(canonical_lists, start=1):
            list_name = str(board_list.get("name") or "Lista sin titulo").strip()
            list_key = normalize_label(list_name)
            if not list_name or list_key in deleted_lists:
                continue
            list_id = existing_lists.get(list_key) or _stable_id("list", list_name)
            local_list_ids[list_key] = list_id
            connection.execute(
                """
                INSERT INTO master_lists(id, name, pos, status)
                VALUES (?, ?, ?, 'open')
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    pos = excluded.pos,
                    status = 'open',
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    list_id,
                    list_name,
                    float(board_list.get("pos") or list_index * 1000),
                ),
            )
            lists_count += 1

            for card_index, card in enumerate(board_list.get("cards") or [], start=1):
                title = str(card.get("title") or "Tarjeta sin titulo").strip()
                card_key = normalize_label(title)
                if not title or card_key in deleted_cards:
                    continue
                card_id = existing_cards.get((list_id, card_key)) or _stable_id(
                    "card",
                    list_name,
                    title,
                )
                local_card_ids[(list_key, card_key)] = card_id
                payload = _card_payload(card, list_id, list_name)
                connection.execute(
                    """
                    INSERT INTO master_cards(id, list_id, title, description, pos, payload_json, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'open')
                    ON CONFLICT(id) DO UPDATE SET
                        list_id = excluded.list_id,
                        title = excluded.title,
                        description = excluded.description,
                        pos = excluded.pos,
                        payload_json = excluded.payload_json,
                        status = 'open',
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        card_id,
                        list_id,
                        title,
                        str(payload.get("description") or ""),
                        float(card.get("pos") or card_index * 1000),
                        json.dumps(payload, ensure_ascii=True),
                    ),
                )
                cards_count += 1

    boards_mapped = 0
    for student in readable:
        board_id = str(student.get("board_id") or "")
        if not board_id:
            continue
        try:
            if canonical_student and board_id == canonical_student.get("board_id"):
                lists = canonical_lists
            else:
                _, lists = fetch_board_lists_with_cards_read_only(
                    config,
                    board_id,
                    include_checklists=False,
                )
        except Exception:
            continue
        boards_mapped += 1
        for board_list in lists:
            list_key = normalize_label(str(board_list.get("name") or ""))
            list_id = local_list_ids.get(list_key)
            if not list_id:
                continue
            record_new_content_delivery(list_id, board_id, str(board_list.get("id") or ""), db_path=db_path)
            deliveries += 1
            for card in board_list.get("cards") or []:
                card_key = normalize_label(str(card.get("title") or ""))
                card_id = local_card_ids.get((list_key, card_key))
                if not card_id:
                    continue
                record_new_content_delivery(card_id, board_id, str(card.get("id") or ""), db_path=db_path)
                deliveries += 1

    return {
        "status": "imported",
        "students": len(students),
        "boards_mapped": boards_mapped,
        "lists": lists_count,
        "cards": cards_count,
        "deliveries": deliveries,
        "source_student": str(canonical_student.get("student_name") or ""),
    }


def bootstrap_master_if_empty(config: TrelloConfig, *, db_path: Path = DB_PATH) -> dict[str, int | str]:
    if not config.is_complete:
        return {"status": "missing_credentials", "students": 0, "boards_mapped": 0, "lists": 0, "cards": 0}
    if any(board_list.get("cards") for board_list in load_master_board(db_path)):
        return {"status": "skipped", "students": 0, "boards_mapped": 0, "lists": 0, "cards": 0}
    return import_master_from_student_boards(config, db_path=db_path)
