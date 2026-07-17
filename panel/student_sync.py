from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

from panel.assets_cache import cache_file_asset, cache_image_asset
from panel.audit import backup_board_snapshot, write_audit_log
from panel.results_db import (
    deleted_student_ids,
    delivered_student_ids,
    delivered_trello_id,
    hidden_student_board_ids,
    mark_content_delete_synced,
    mark_all_master_content_pending,
    mark_new_content_synced,
    pending_content_delete_rows,
    pending_new_content_rows,
    record_content_delete_delivery,
    record_new_content_delivery,
    sync_student_board_registry,
)
from panel.sync_planner import LIST_MATCH_THRESHOLD, best_match, normalize_label, visible_lists
from panel.trello_client import (
    TrelloConfig,
    TrelloReadOnlyError,
    archive_student_card,
    archive_student_list,
    attach_file_to_student_card,
    attach_url_to_student_card,
    create_student_card,
    create_student_checklist,
    create_student_list,
    fetch_board_list_headers_read_only,
    fetch_board_lists_with_cards_read_only,
    fetch_student_boards_read_only,
    update_student_card,
)


MAX_SYNC_STUDENT_BOARDS = 80
SYNC_PLAN_BOARD_SNAPSHOT_LIMIT = 80
SAFE_ACTION_LABELS = {
    "create_list": "Crear lista faltante",
    "create_card": "Crear tarjeta faltante",
    "update_card": "Actualizar tarjeta entregada",
    "delete_list": "Archivar lista eliminada",
    "delete_card": "Archivar tarjeta eliminada",
}


@dataclass(frozen=True)
class StudentSyncAction:
    action: str
    board_id: str
    board_name: str
    student_name: str
    list_name: str
    card_title: str = ""
    target_list_id: str = ""
    target_card_id: str = ""
    source_list_id: str = ""
    source_card_id: str = ""
    confidence: float = 1.0
    detail: str = ""
    payload: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _editable_local_lists(local_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in visible_lists(local_lists) if item.get("kind") != "locked"]


def _is_hidden(content_type: str, content_id: str, board_id: str) -> bool:
    if not content_id:
        return False
    return board_id in hidden_student_board_ids(content_type, content_id)


def _checklist_items(checklist: dict[str, Any]) -> list[str]:
    items = [
        str(checklist.get("description") or "").strip(),
        str(checklist.get("link") or "").strip(),
    ]
    raw_items = checklist.get("items") or checklist.get("checkItems") or []
    if isinstance(raw_items, list):
        items.extend(str(item.get("name") if isinstance(item, dict) else item).strip() for item in raw_items)
    return [item for item in items if item]


def _attach_image_file(config: TrelloConfig, board_id: str, card_id: str, image: dict[str, Any]) -> dict[str, Any]:
    src = str((image or {}).get("src") or "").strip()
    name = str((image or {}).get("name") or "").strip() or "imagen"
    cached = cache_image_asset(src, name, api_key=config.api_key, token=config.token)
    upload_name = name
    if "." not in upload_name.rsplit("/", 1)[-1]:
        upload_name = f"{upload_name}.png"
    return attach_file_to_student_card(
        config,
        board_id,
        card_id,
        upload_name,
        cached.content,
        cached.content_type,
    )


def _attach_generic_file(config: TrelloConfig, board_id: str, card_id: str, file_item: dict[str, Any]) -> dict[str, Any]:
    src = str((file_item or {}).get("src") or "").strip()
    name = str((file_item or {}).get("name") or "").strip() or "archivo.pdf"
    cached = cache_file_asset(src, name, api_key=config.api_key, token=config.token)
    upload_name = name if name.casefold().endswith(".pdf") else f"{name}.pdf"
    return attach_file_to_student_card(
        config,
        board_id,
        card_id,
        upload_name,
        cached.content,
        cached.content_type,
    )


def _find_student_boards(config: TrelloConfig) -> list[dict[str, str]]:
    students = fetch_student_boards_read_only(config)[:MAX_SYNC_STUDENT_BOARDS]
    cohort = sync_student_board_registry(students)
    if cohort.get("new_board_ids") or cohort.get("reopened_board_ids"):
        mark_all_master_content_pending()
        write_audit_log(
            "Gestion de cohortes",
            (
                f"{len(cohort.get('new_board_ids') or [])} alumno(s) nuevo(s), "
                f"{len(cohort.get('reopened_board_ids') or [])} reactivado(s). "
                "Contenido maestro marcado para entrega inicial."
            ),
            meta=cohort,
        )
    return students


def _row_payload(row: dict[str, Any], fallback_title: str = "") -> dict[str, Any]:
    raw = str(row.get("payload_json") or "{}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("title", row.get("title") or fallback_title)
    payload.setdefault("description", "")
    payload.setdefault("links", [])
    payload.setdefault("images", [])
    payload.setdefault("files", [])
    payload.setdefault("checklists", [])
    return payload


def _board_snapshot_index(board_lists: list[dict[str, Any]]) -> dict[str, Any]:
    lists_by_name: dict[str, dict[str, Any]] = {}
    cards_by_list_and_title: dict[tuple[str, str], dict[str, Any]] = {}
    for board_list in visible_lists(board_lists):
        list_key = normalize_label(str(board_list.get("name") or ""))
        if not list_key:
            continue
        lists_by_name.setdefault(list_key, board_list)
        for card in board_list.get("cards") or []:
            card_key = normalize_label(str(card.get("title") or ""))
            if card_key:
                cards_by_list_and_title.setdefault((list_key, card_key), card)
    return {
        "lists_by_name": lists_by_name,
        "cards_by_list_and_title": cards_by_list_and_title,
    }


def _find_existing_list(snapshot: dict[str, Any], list_name: str) -> dict[str, Any] | None:
    list_key = normalize_label(list_name)
    if not list_key:
        return None
    direct = snapshot["lists_by_name"].get(list_key)
    if direct:
        return direct
    match, _ = best_match(list_name, list(snapshot["lists_by_name"].values()), threshold=0.94)
    return match


def _find_existing_card(snapshot: dict[str, Any], list_name: str, card_title: str) -> dict[str, Any] | None:
    list_key = normalize_label(list_name)
    card_key = normalize_label(card_title)
    if not list_key or not card_key:
        return None
    direct = snapshot["cards_by_list_and_title"].get((list_key, card_key))
    if direct:
        return direct
    target_list = _find_existing_list(snapshot, list_name)
    target_key = normalize_label(str((target_list or {}).get("name") or list_name))
    if not target_key:
        return None
    candidates = [
        card
        for (candidate_list_key, _), card in snapshot["cards_by_list_and_title"].items()
        if candidate_list_key == target_key
    ]
    match, _ = best_match(card_title, candidates, threshold=0.96)
    return match


def build_student_sync_plan(
    config: TrelloConfig,
    local_lists: list[dict[str, Any]],
) -> dict[str, Any]:
    pending_rows = pending_new_content_rows()
    pending_delete_rows = pending_content_delete_rows()
    pending_ids = {row["content_id"] for row in pending_rows}
    pending_delete_ids = {str(row.get("content_id") or "") for row in pending_delete_rows}
    students = _find_student_boards(config)
    local_lists = _editable_local_lists(local_lists)
    actions: list[StudentSyncAction] = []
    errors: list[dict[str, str]] = []

    def result_payload() -> dict[str, Any]:
        if students and not actions and not errors:
            mark_new_content_synced(pending_ids)
            mark_content_delete_synced(pending_delete_ids)
        return {
            "students": len(students),
            "actions": [action.to_dict() for action in actions],
            "summary": summarize_student_actions(actions),
            "errors": errors,
        }

    for row in pending_delete_rows:
        content_id = str(row.get("content_id") or "")
        content_type = str(row.get("content_type") or "")
        title = str(row.get("title") or content_id)
        deleted = deleted_student_ids(content_id)
        for student in students:
            board_id = student["board_id"]
            if board_id in deleted:
                continue
            trello_id = delivered_trello_id(content_id, board_id)
            if not trello_id:
                continue
            actions.append(
                StudentSyncAction(
                    action="delete_list" if content_type == "list" else "delete_card",
                    board_id=board_id,
                    board_name=student.get("board_name", ""),
                    student_name=student.get("student_name", ""),
                    list_name=title if content_type == "list" else "",
                    card_title=title if content_type == "card" else "",
                    target_list_id=trello_id if content_type == "list" else "",
                    target_card_id=trello_id if content_type == "card" else "",
                    source_list_id=content_id if content_type == "list" else "",
                    source_card_id=content_id if content_type == "card" else "",
                    detail="Contenido eliminado en el panel y pendiente de archivar en alumnos.",
                    payload={"title": title},
                )
            )

    if not pending_ids:
        return result_payload()

    local_lists_by_id = {str(item.get("id") or ""): item for item in local_lists}
    queue_lists_by_id = {
        str(row["content_id"]): row
        for row in pending_rows
        if row["content_type"] == "list"
    }

    card_rows = [row for row in pending_rows if row["content_type"] == "card"]
    missing_payload_reported: set[str] = set()
    board_snapshots: dict[str, dict[str, Any]] = {}
    for student in students:
        board_id = student["board_id"]
        snapshot: dict[str, Any] = {"lists_by_name": {}, "cards_by_list_and_title": {}}
        if pending_rows:
            try:
                _, board_lists = fetch_board_lists_with_cards_read_only(
                    config,
                    board_id,
                    include_checklists=False,
                )
                snapshot = _board_snapshot_index(board_lists)
                board_snapshots[board_id] = snapshot
            except TrelloReadOnlyError as error:
                errors.append(
                    {
                        "board_id": board_id,
                        "student_name": student.get("student_name", ""),
                        "error": str(error),
                    }
                )
                continue

        for row in pending_rows:
            content_id = row["content_id"]
            if row["content_type"] != "list" or content_id in pending_delete_ids:
                continue
            local_list = local_lists_by_id.get(content_id)
            row_payload = _row_payload(row)
            delivered = delivered_student_ids(content_id)
            list_name = str((local_list or {}).get("name") or row_payload.get("title") or row["title"] or "").strip()
            if _is_hidden("list", content_id, board_id):
                target_list_id = delivered_trello_id(content_id, board_id)
                if not target_list_id:
                    existing_list = _find_existing_list(snapshot, list_name)
                    target_list_id = str((existing_list or {}).get("id") or "")
                    if target_list_id:
                        record_new_content_delivery(content_id, board_id, target_list_id, status="synced")
                if target_list_id and board_id not in deleted_student_ids(content_id):
                    actions.append(
                        StudentSyncAction(
                            action="delete_list",
                            board_id=board_id,
                            board_name=student.get("board_name", ""),
                            student_name=student.get("student_name", ""),
                            list_name=list_name,
                            target_list_id=target_list_id,
                            source_list_id=content_id,
                            detail="Lista ocultada para este alumno.",
                            payload={"title": list_name},
                        )
                    )
                continue
            if board_id in delivered:
                continue
            existing_list = _find_existing_list(snapshot, list_name)
            if existing_list:
                record_new_content_delivery(content_id, board_id, str(existing_list.get("id") or ""), status="synced")
                continue
            actions.append(
                StudentSyncAction(
                    action="create_list",
                    board_id=board_id,
                    board_name=student.get("board_name", ""),
                    student_name=student.get("student_name", ""),
                    list_name=list_name,
                    source_list_id=content_id,
                    detail="Lista nueva pendiente creada en el master local.",
                    payload={"name": list_name},
                )
            )

        for row in card_rows:
            source_card_id = row["content_id"]
            if source_card_id in pending_delete_ids or str(row.get("parent_list_id") or "") in pending_delete_ids:
                continue
            if str(row.get("payload_json") or "{}").strip() in {"", "{}"}:
                if source_card_id not in missing_payload_reported:
                    errors.append(
                        {
                            "board_id": "",
                            "student_name": "",
                            "error": f"La tarjeta '{row.get('title') or source_card_id}' no tiene snapshot local. Abrela en el panel y presiona Guardar tarjeta de nuevo.",
                        }
                    )
                    missing_payload_reported.add(source_card_id)
                continue
            local_list = local_lists_by_id.get(str(row.get("parent_list_id") or ""))
            source_list_id = str((local_list or {}).get("id") or row.get("parent_list_id") or "")
            payload = _row_payload(row)
            hidden_by_list = _is_hidden("list", source_list_id, board_id)
            hidden_by_card = _is_hidden("card", source_card_id, board_id)
            queue_list = queue_lists_by_id.get(source_list_id)
            queue_list_payload = _row_payload(queue_list or {}, fallback_title="Lista") if queue_list else {}
            list_name = str(
                (local_list or {}).get("name")
                or payload.get("list_name")
                or queue_list_payload.get("title")
                or "Lista"
            ).strip()
            card_title = str(payload.get("title") or row.get("title") or "").strip()
            if hidden_by_list or hidden_by_card:
                delivered_card_id = delivered_trello_id(source_card_id, board_id)
                if not delivered_card_id:
                    existing_card = _find_existing_card(snapshot, list_name, card_title)
                    delivered_card_id = str((existing_card or {}).get("id") or "")
                    if delivered_card_id:
                        record_new_content_delivery(source_card_id, board_id, delivered_card_id, status="synced")
                if delivered_card_id and board_id not in deleted_student_ids(source_card_id):
                    actions.append(
                        StudentSyncAction(
                            action="delete_card",
                            board_id=board_id,
                            board_name=student.get("board_name", ""),
                            student_name=student.get("student_name", ""),
                            list_name=list_name,
                            card_title=card_title,
                            target_card_id=delivered_card_id,
                            source_list_id=source_list_id,
                            source_card_id=source_card_id,
                            detail="Tarjeta ocultada para este alumno.",
                            payload=payload,
                        )
                    )
                continue

            delivered_card_id = delivered_trello_id(source_card_id, board_id)
            if not delivered_card_id:
                existing_card = _find_existing_card(snapshot, list_name, card_title)
                delivered_card_id = str((existing_card or {}).get("id") or "")
                if delivered_card_id:
                    record_new_content_delivery(source_card_id, board_id, delivered_card_id, status="synced")
            if row.get("sync_mode") == "update":
                if not delivered_card_id:
                    continue
                actions.append(
                    StudentSyncAction(
                        action="update_card",
                        board_id=board_id,
                        board_name=student.get("board_name", ""),
                        student_name=student.get("student_name", ""),
                        list_name=list_name,
                        card_title=card_title,
                        target_card_id=delivered_card_id,
                        source_list_id=source_list_id,
                        source_card_id=source_card_id,
                        detail="Tarjeta ya entregada con cambios nuevos desde el master local.",
                        payload=payload,
                    )
                )
                continue

            if delivered_card_id:
                continue
            target_list_id = delivered_trello_id(source_list_id, board_id)
            if not target_list_id:
                target_list = _find_existing_list(snapshot, list_name)
                target_list_id = str((target_list or {}).get("id") or "")
                if target_list_id:
                    record_new_content_delivery(source_list_id, board_id, target_list_id, status="synced")
            if not target_list_id:
                continue
            actions.append(
                StudentSyncAction(
                    action="create_card",
                    board_id=board_id,
                    board_name=student.get("board_name", ""),
                    student_name=student.get("student_name", ""),
                    list_name=list_name,
                    card_title=card_title,
                    target_list_id=target_list_id,
                    source_list_id=source_list_id,
                    source_card_id=source_card_id,
                    detail="Tarjeta nueva pendiente creada en el master local.",
                    payload=payload,
                )
            )

    return result_payload()


def summarize_student_actions(actions: list[StudentSyncAction]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for action in actions:
        summary[action.action] = summary.get(action.action, 0) + 1
    return summary


def _backup_student_board(config: TrelloConfig, board_id: str, student_name: str) -> str:
    title, board_lists = fetch_board_list_headers_read_only(config, board_id)
    return backup_board_snapshot(title, board_lists, f"before_student_sync_{student_name}")


def apply_student_sync_plan(
    config: TrelloConfig,
    local_lists: list[dict[str, Any]],
    *,
    max_actions: int = 500,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    plan = build_student_sync_plan(config, local_lists)
    max_actions = max(1, min(int(max_actions), 500))
    raw_actions = plan["actions"][:max_actions]
    backups: dict[str, str] = {}
    created_lists: dict[tuple[str, str], str] = {}
    applied: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = [*plan.get("errors", [])]
    touched_source_ids: set[str] = set()
    touched_delete_ids: set[str] = set()
    pending_create_cards_by_list: dict[str, list[dict[str, Any]]] = {}
    pending_rows = pending_new_content_rows()
    for row in pending_rows:
        if row["content_type"] == "card" and row.get("sync_mode") == "create":
            pending_create_cards_by_list.setdefault(str(row.get("parent_list_id") or ""), []).append(row)
    actions_by_board: dict[str, int] = {}
    completed_by_board: dict[str, int] = {}
    board_names: dict[str, str] = {}
    board_errors: dict[str, int] = {}
    board_applied: dict[str, int] = {}
    for raw in raw_actions:
        board_id = str(raw.get("board_id") or "")
        if not board_id:
            continue
        actions_by_board[board_id] = actions_by_board.get(board_id, 0) + 1
        board_names[board_id] = str(raw.get("student_name") or raw.get("board_name") or board_id)

    def emit_progress(board_id: str, status: str, detail: str = "") -> None:
        if not progress_callback or not board_id:
            return
        completed_boards = sum(
            1 for item_board_id, count in actions_by_board.items()
            if completed_by_board.get(item_board_id, 0) >= count
        )
        progress_callback(
            {
                "board_id": board_id,
                "student_name": board_names.get(board_id, board_id),
                "status": status,
                "detail": detail,
                "applied": board_applied.get(board_id, 0),
                "errors": board_errors.get(board_id, 0),
                "completed_boards": completed_boards,
                "total_boards": len(actions_by_board),
            }
        )

    write_audit_log(
        "Iniciar sincronizacion alumnos",
        f"Lote seguro iniciado: {len(raw_actions)} de {len(plan['actions'])} cambio(s) pendientes. Ensayos no se toca.",
        meta={"planned": len(plan["actions"]), "batch": len(raw_actions)},
    )

    for raw in raw_actions:
        action = StudentSyncAction(**raw)
        try:
            emit_progress(action.board_id, "syncing", "Sincronizando board.")
            if action.board_id not in backups:
                backups[action.board_id] = _backup_student_board(config, action.board_id, action.student_name)

            target_list_id = action.target_list_id or created_lists.get((action.board_id, action.source_list_id), "")
            if action.action == "create_list":
                result = create_student_list(config, action.board_id, str(action.payload.get("name", "")))
                created_list_id = str(result.get("id") or "")
                created_lists[(action.board_id, action.source_list_id)] = created_list_id
                record_new_content_delivery(
                    action.source_list_id,
                    action.board_id,
                    created_list_id,
                    status="synced",
                )
                for child_row in pending_create_cards_by_list.get(action.source_list_id, []):
                    child_id = str(child_row.get("content_id") or "")
                    if delivered_trello_id(child_id, action.board_id):
                        continue
                    payload = _row_payload(child_row)
                    child = create_student_card(
                        config,
                        action.board_id,
                        created_list_id,
                        str(payload.get("title") or ""),
                        str(payload.get("description") or ""),
                    )
                    child_card_id = str(child.get("id") or "")
                    for link in payload.get("links") or []:
                        attach_url_to_student_card(config, action.board_id, child_card_id, str(link))
                    for image in payload.get("images") or []:
                        _attach_image_file(config, action.board_id, child_card_id, image)
                    for file_item in payload.get("files") or []:
                        _attach_generic_file(config, action.board_id, child_card_id, file_item)
                    for checklist in payload.get("checklists") or []:
                        title = str((checklist or {}).get("title") or (checklist or {}).get("name") or "").strip()
                        if title:
                            create_student_checklist(
                                config,
                                action.board_id,
                                child_card_id,
                                title,
                                _checklist_items(checklist),
                            )
                    record_new_content_delivery(child_id, action.board_id, child_card_id, status="synced")
                    touched_source_ids.add(child_id)
            elif action.action == "create_card":
                if not target_list_id:
                    raise TrelloReadOnlyError("No existe lista destino segura para crear la tarjeta.")
                result = create_student_card(
                    config,
                    action.board_id,
                    target_list_id,
                    str(action.payload.get("title", "")),
                    str(action.payload.get("description", "")),
                )
                card_id = str(result.get("id") or "")
                for link in action.payload.get("links") or []:
                    attach_url_to_student_card(config, action.board_id, card_id, str(link))
                for image in action.payload.get("images") or []:
                    _attach_image_file(config, action.board_id, card_id, image)
                for file_item in action.payload.get("files") or []:
                    _attach_generic_file(config, action.board_id, card_id, file_item)
                for checklist in action.payload.get("checklists") or []:
                    title = str((checklist or {}).get("title") or (checklist or {}).get("name") or "").strip()
                    if title:
                        create_student_checklist(config, action.board_id, card_id, title, _checklist_items(checklist))
                record_new_content_delivery(
                    action.source_card_id,
                    action.board_id,
                    card_id,
                    status="synced",
                )
            elif action.action == "update_card":
                result = update_student_card(
                    config,
                    action.board_id,
                    action.target_card_id,
                    str(action.payload.get("title", "")),
                    str(action.payload.get("description", "")),
                )
                for link in action.payload.get("links") or []:
                    attach_url_to_student_card(config, action.board_id, action.target_card_id, str(link))
                for image in action.payload.get("images") or []:
                    _attach_image_file(config, action.board_id, action.target_card_id, image)
                for file_item in action.payload.get("files") or []:
                    _attach_generic_file(config, action.board_id, action.target_card_id, file_item)
                for checklist in action.payload.get("checklists") or []:
                    title = str((checklist or {}).get("title") or (checklist or {}).get("name") or "").strip()
                    if title:
                        create_student_checklist(
                            config,
                            action.board_id,
                            action.target_card_id,
                            title,
                            _checklist_items(checklist),
                        )
                record_new_content_delivery(action.source_card_id, action.board_id, action.target_card_id, status="synced")
            elif action.action == "delete_list":
                result = archive_student_list(config, action.board_id, action.target_list_id)
                record_content_delete_delivery(action.source_list_id, action.board_id, status="synced")
                touched_delete_ids.add(action.source_list_id)
            elif action.action == "delete_card":
                result = archive_student_card(config, action.board_id, action.target_card_id)
                record_content_delete_delivery(action.source_card_id, action.board_id, status="synced")
                touched_delete_ids.add(action.source_card_id)
            else:
                raise TrelloReadOnlyError(f"Accion no soportada: {action.action}")

            applied.append(
                {
                    **action.to_dict(),
                    "result_id": str((result or {}).get("id") or ""),
                    "backup": backups[action.board_id],
                }
            )
            if action.source_list_id:
                touched_source_ids.add(action.source_list_id)
            if action.source_card_id:
                touched_source_ids.add(action.source_card_id)
            board_applied[action.board_id] = board_applied.get(action.board_id, 0) + 1
            completed_by_board[action.board_id] = completed_by_board.get(action.board_id, 0) + 1
            status = "done" if completed_by_board[action.board_id] >= actions_by_board.get(action.board_id, 1) else "syncing"
            emit_progress(action.board_id, status, f"{board_applied[action.board_id]} accion(es) aplicada(s).")
            write_audit_log(
                SAFE_ACTION_LABELS.get(action.action, action.action),
                (
                    f"{action.student_name}: {action.list_name}"
                    f"{' / ' + action.card_title if action.card_title else ''}."
                ),
                meta={
                    "board_id": action.board_id,
                    "action": action.action,
                    "list_name": action.list_name,
                    "card_title": action.card_title,
                    "backup": backups[action.board_id],
                },
            )
            time.sleep(0.25)
        except Exception as error:
            error_payload = {**action.to_dict(), "error": str(error)}
            errors.append(error_payload)
            board_errors[action.board_id] = board_errors.get(action.board_id, 0) + 1
            completed_by_board[action.board_id] = completed_by_board.get(action.board_id, 0) + 1
            status = "error" if completed_by_board[action.board_id] >= actions_by_board.get(action.board_id, 1) else "syncing"
            emit_progress(action.board_id, status, str(error))
            if not delivered_trello_id(action.source_card_id or action.source_list_id, action.board_id):
                record_new_content_delivery(
                    action.source_card_id or action.source_list_id,
                    action.board_id,
                    "",
                    status="error",
                    error=str(error),
                )
            if action.action in {"delete_list", "delete_card"}:
                record_content_delete_delivery(
                    action.source_card_id or action.source_list_id,
                    action.board_id,
                    status="error",
                    error=str(error),
                )
            write_audit_log(
                "Error sincronizacion alumnos",
                (
                    f"{action.student_name}: {action.list_name}"
                    f"{' / ' + action.card_title if action.card_title else ''}: {error}"
                ),
                status="error",
                meta=error_payload,
            )
            time.sleep(0.5)

    write_audit_log(
        "Sincronizar alumnos",
        f"Se aplicaron {len(applied)} cambio(s) en boards de alumnos. Ensayos no fue tocado.",
        meta={"applied": len(applied), "errors": len(errors), "backups": list(backups.values())},
    )
    if applied and not errors and len(plan["actions"]) <= max_actions:
        mark_new_content_synced(touched_source_ids)
        mark_content_delete_synced(touched_delete_ids)
    return {
        "planned": len(plan["actions"]),
        "applied": len(applied),
        "errors": errors,
        "backups": list(backups.values()),
        "board_results": [
            {
                "board_id": board_id,
                "student_name": board_names.get(board_id, board_id),
                "status": "error" if board_errors.get(board_id, 0) else "done",
                "applied": board_applied.get(board_id, 0),
                "errors": board_errors.get(board_id, 0),
            }
            for board_id in actions_by_board
            if completed_by_board.get(board_id, 0) >= actions_by_board.get(board_id, 0)
        ],
        "limited": len(plan["actions"]) > max_actions,
        "remaining": max(0, len(plan["actions"]) - len(applied)),
    }
