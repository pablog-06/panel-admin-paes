
from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from panel.audit import backup_database, enforce_retention, read_audit_log, write_audit_log
from panel.results_db import (
    archive_master_card,
    archive_master_list,
    build_results_panel,
    create_master_list,
    hidden_student_board_ids,
    latest_exam_summary,
    load_cohort_status,
    mark_master_content_pending,
    median_scores_by_exam,
    move_master_card,
    move_master_list,
    save_hidden_students,
    sync_student_board_registry,
    upsert_master_card,
)
from panel.student_sync import SAFE_ACTION_LABELS, apply_student_sync_plan, build_student_sync_plan
from panel.trello_client import (
    TrelloConfig,
    TrelloReadOnlyError,
    fetch_paes_board_inventory_read_only,
    fetch_student_boards_read_only,
    _fetch_student_boards_cached,
)
from scripts.import_essay_scores import import_scores


_RESULTS_SYNC_LOCK = threading.Lock()
_RESULTS_SYNCED_AT = 0.0
_RESULTS_SYNC_TTL_SECONDS = 600
_PERIODIC_BACKUP_LOCK = threading.Lock()
_LAST_PERIODIC_BACKUP_AT = 0.0
_PERIODIC_BACKUP_SECONDS = 1800
_STUDENT_SYNC_LOCK = threading.Lock()
_SYNC_JOBS: dict[str, dict[str, Any]] = {}
_SYNC_JOBS_LOCK = threading.Lock()


def _payload_text(payload: dict[str, Any], key: str, default: str = "") -> str:
    return str(payload.get(key) or default).strip()


def _sync_results_if_due(force: bool = False) -> None:
    global _RESULTS_SYNCED_AT
    now = time.time()
    if not force and now - _RESULTS_SYNCED_AT < _RESULTS_SYNC_TTL_SECONDS:
        return
    with _RESULTS_SYNC_LOCK:
        now = time.time()
        if not force and now - _RESULTS_SYNCED_AT < _RESULTS_SYNC_TTL_SECONDS:
            return
        import_scores(dry_run=False, delay=0.35, limit=None)
        _RESULTS_SYNCED_AT = time.time()


def periodic_backup_if_due() -> None:
    global _LAST_PERIODIC_BACKUP_AT
    now = time.time()
    if now - _LAST_PERIODIC_BACKUP_AT < _PERIODIC_BACKUP_SECONDS:
        return
    with _PERIODIC_BACKUP_LOCK:
        now = time.time()
        if now - _LAST_PERIODIC_BACKUP_AT < _PERIODIC_BACKUP_SECONDS:
            return
        enforce_retention()
        backup_database("periodic")
        _LAST_PERIODIC_BACKUP_AT = time.time()
        enforce_retention()


def admin_history_events(limit: int = 80) -> list[dict[str, Any]]:
    clean_events = []
    for event in read_audit_log(limit=max(limit * 3, limit)):
        action = str(event.get("action") or "")
        detail = str(event.get("detail") or "")
        if action in {"backup_database", "backup_board"}:
            continue
        if action == "trello_action" and "Accion local no soportada" in detail:
            continue
        clean_events.append(event)
        if len(clean_events) >= limit:
            break
    return clean_events


def _update_sync_job(job_id: str, **changes: Any) -> None:
    with _SYNC_JOBS_LOCK:
        job = _SYNC_JOBS.setdefault(job_id, {})
        job.update(changes)
        job["updated_at"] = time.time()


def _append_sync_progress(job_id: str, event: dict[str, Any]) -> None:
    with _SYNC_JOBS_LOCK:
        job = _SYNC_JOBS.setdefault(job_id, {})
        progress = list(job.get("progress") or [])
        board_id = str(event.get("board_id") or "")
        if board_id:
            progress = [item for item in progress if str(item.get("board_id") or "") != board_id]
        progress.append(event)
        job["progress"] = progress[-120:]
        job["updated_at"] = time.time()


def _run_student_sync_job(job_id: str, config: TrelloConfig, max_actions: int) -> None:
    def progress_callback(event: dict[str, Any]) -> None:
        _append_sync_progress(job_id, event)
        total = int(event.get("total_boards") or 0)
        completed = int(event.get("completed_boards") or 0)
        _update_sync_job(job_id, status="running", completed_boards=completed, total_boards=total)

    try:
        with _STUDENT_SYNC_LOCK:
            _update_sync_job(job_id, status="running", note="Sincronizando boards de alumnos...")
            result = apply_student_sync_plan(
                config,
                [],
                max_actions=max_actions,
                progress_callback=progress_callback,
            )
        _update_sync_job(
            job_id,
            status="done",
            note="Sincronizacion finalizada.",
            result=result,
            completed_boards=int(_SYNC_JOBS.get(job_id, {}).get("total_boards") or 0),
        )
    except Exception as error:
        write_audit_log("Error sincronizacion alumnos", str(error), status="error")
        _update_sync_job(job_id, status="error", note=str(error), error=str(error))


def execute_admin_action(path: str, payload: dict[str, Any] | None, config: TrelloConfig) -> Any:
    payload = payload or {}
    path = str(path or "").strip()

    if path in {"/create-list", "/save-card", "/move-list", "/move-card", "/archive-list", "/archive-card"}:
        periodic_backup_if_due()

    if path == "/create-list":
        name = _payload_text(payload, "name")
        backup_path = backup_database("before_create_list")
        result = create_master_list(name)
        write_audit_log("Crear lista", f"Se creo la lista '{name}'.", meta={"backup": backup_path})
        return result

    if path == "/save-card":
        card_id = _payload_text(payload, "card_id")
        title = _payload_text(payload, "title")
        description = str(payload.get("description") or "").strip()
        links = [str(item).strip() for item in payload.get("links", []) if str(item).strip()]
        images = [item for item in payload.get("images", []) if isinstance(item, dict)]
        files = [item for item in payload.get("files", []) if isinstance(item, dict)]
        checklists = [item for item in payload.get("checklists", []) if isinstance(item, dict)]
        backup_path = backup_database("before_save_card")
        result = upsert_master_card(
            card_id=card_id,
            list_id=_payload_text(payload, "list_id"),
            title=title,
            description=description,
            links=links,
            images=images,
            files=files,
            checklists=checklists,
        )
        saved_card_id = str(result.get("card_id") or card_id)
        write_audit_log(
            "Editar tarjeta" if card_id else "Crear tarjeta",
            f"Se {'actualizo' if card_id else 'creo'} la tarjeta '{title}'.",
            meta={"card_id": saved_card_id, "backup": backup_path},
        )
        return {"card_id": saved_card_id}

    if path == "/move-list":
        backup_path = backup_database("before_move_list")
        result = move_master_list(_payload_text(payload, "list_id"), payload.get("pos", "bottom"))
        list_name = _payload_text(payload, "list_name", _payload_text(payload, "list_id"))
        write_audit_log("Mover lista", f"Se movio la lista '{list_name}'.", meta={"backup": backup_path})
        return result

    if path == "/move-card":
        backup_path = backup_database("before_move_card")
        result = move_master_card(_payload_text(payload, "card_id"), _payload_text(payload, "list_id"), payload.get("pos", "bottom"))
        card_title = _payload_text(payload, "card_title", _payload_text(payload, "card_id"))
        list_name = _payload_text(payload, "list_name", _payload_text(payload, "list_id"))
        write_audit_log("Mover tarjeta", f"Se movio la tarjeta '{card_title}' en '{list_name}'.", meta={"backup": backup_path})
        return result

    if path == "/archive-list":
        backup_path = backup_database("before_archive_list")
        list_id = _payload_text(payload, "list_id")
        result = archive_master_list(list_id)
        list_name = _payload_text(payload, "list_name", list_id)
        write_audit_log("Eliminar lista", f"Se archivo localmente la lista '{list_name}'.", meta={"backup": backup_path})
        return result

    if path == "/archive-card":
        backup_path = backup_database("before_archive_card")
        card_id = _payload_text(payload, "card_id")
        result = archive_master_card(card_id)
        card_title = _payload_text(payload, "card_title", card_id)
        write_audit_log("Eliminar tarjeta", f"Se archivo localmente la tarjeta '{card_title}'.", meta={"backup": backup_path})
        return result

    if path == "/refresh-results":
        sync_error = ""
        try:
            _sync_results_if_due(force=bool(payload.get("force")))
        except Exception as error:
            sync_error = str(error)
            write_audit_log("refresh_results", sync_error, status="error")
        return {"panel": build_results_panel(), "sync_error": sync_error}

    if path == "/audit-log":
        return {"events": read_audit_log(limit=int(payload.get("limit") or 40))}

    if path == "/admin-dashboard":
        refresh = bool(payload.get("refresh"))
        summary = {}
        unknown_boards = []
        if refresh:
            _fetch_student_boards_cached.cache_clear()
            inventory = fetch_paes_board_inventory_read_only(config)
            students = inventory["students"]
            unknown_boards = inventory["unknown"]
            summary = sync_student_board_registry(students)
            write_audit_log(
                "Actualizar administracion",
                (
                    f"{summary.get('active_count', 0)} alumno(s) activo(s), "
                    f"{len(summary.get('new_board_ids') or [])} nuevo(s), "
                    f"{len(summary.get('archived_board_ids') or [])} archivado(s)."
                ),
                meta={"summary": summary, "unknown_boards": unknown_boards},
            )
        return {
            "cohort": load_cohort_status(),
            "events": admin_history_events(int(payload.get("limit") or 80)),
            "stats": latest_exam_summary() or {},
            "series": median_scores_by_exam(),
            "refresh_summary": summary,
            "unknown_boards": unknown_boards,
            "unknown_count": len(unknown_boards),
        }

    if path == "/audit-event":
        write_audit_log(
            _payload_text(payload, "action", "Accion del panel"),
            _payload_text(payload, "detail", "Evento registrado desde la interfaz."),
            status=_payload_text(payload, "status", "ok"),
            meta=payload.get("meta") if isinstance(payload.get("meta"), dict) else {},
        )
        return {"logged": True}

    if path == "/student-boards":
        return {"students": fetch_student_boards_read_only(config)}

    if path == "/cohort-status":
        return load_cohort_status()

    if path == "/refresh-cohorts":
        _fetch_student_boards_cached.cache_clear()
        students = fetch_student_boards_read_only(config)
        summary = sync_student_board_registry(students)
        write_audit_log(
            "Actualizar cohortes",
            (
                f"{summary.get('active_count', 0)} alumno(s) activo(s), "
                f"{len(summary.get('new_board_ids') or [])} nuevo(s), "
                f"{len(summary.get('archived_board_ids') or [])} archivado(s)."
            ),
            meta=summary,
        )
        return {"summary": summary, "cohort": load_cohort_status()}

    if path == "/visibility-get":
        content_type = _payload_text(payload, "content_type")
        content_id = _payload_text(payload, "content_id")
        return {
            "content_type": content_type,
            "content_id": content_id,
            "hidden_student_ids": sorted(hidden_student_board_ids(content_type, content_id)),
        }

    if path == "/visibility-save":
        content_type = _payload_text(payload, "content_type")
        content_id = _payload_text(payload, "content_id")
        students = payload.get("students") if isinstance(payload.get("students"), list) else []
        hidden_ids = payload.get("hidden_student_ids") if isinstance(payload.get("hidden_student_ids"), list) else []
        save_hidden_students(content_type, content_id, students, hidden_ids)
        mark_master_content_pending(content_type, content_id)
        target = _payload_text(payload, "content_title", content_id)
        hidden_count = len({str(item) for item in hidden_ids})
        write_audit_log(
            "Configurar visibilidad",
            f"Se actualizo visibilidad de '{target}'. {hidden_count} alumno(s) ocultos.",
            meta={"content_type": content_type, "content_id": content_id},
        )
        return {"saved": True}

    if path == "/sync-preview-students":
        with _STUDENT_SYNC_LOCK:
            plan = build_student_sync_plan(config, [])
        write_audit_log(
            "Vista previa sincronizacion",
            f"Plan seguro generado: {len(plan.get('actions', []))} cambio(s). Ensayos no se toca.",
            meta={"summary": plan.get("summary", {})},
        )
        return {**plan, "labels": SAFE_ACTION_LABELS}

    if path == "/sync-start-students":
        confirmation = _payload_text(payload, "confirmation")
        if confirmation != "SINCRONIZAR":
            raise TrelloReadOnlyError("Escribe SINCRONIZAR para aplicar cambios en boards de alumnos.")
        max_actions = max(1, min(int(payload.get("max_actions") or 500), 500))
        if _STUDENT_SYNC_LOCK.locked():
            raise TrelloReadOnlyError("Ya hay una sincronizacion en curso.")
        job_id = uuid.uuid4().hex
        with _SYNC_JOBS_LOCK:
            _SYNC_JOBS[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "note": "Sincronizacion en cola.",
                "progress": [],
                "created_at": time.time(),
                "updated_at": time.time(),
                "completed_boards": 0,
                "total_boards": 0,
            }
        threading.Thread(
            target=_run_student_sync_job,
            args=(job_id, config, max_actions),
            name=f"paes-sync-{job_id[:8]}",
            daemon=True,
        ).start()
        return {"job_id": job_id, "status": "queued"}

    if path == "/sync-status":
        job_id = _payload_text(payload, "job_id")
        with _SYNC_JOBS_LOCK:
            job = dict(_SYNC_JOBS.get(job_id) or {})
        if not job:
            raise TrelloReadOnlyError("No se encontro la sincronizacion solicitada.")
        return job

    if path == "/sync-apply-students":
        confirmation = _payload_text(payload, "confirmation")
        if confirmation != "SINCRONIZAR":
            raise TrelloReadOnlyError("Escribe SINCRONIZAR para aplicar cambios en boards de alumnos.")
        max_actions = max(1, min(int(payload.get("max_actions") or 500), 500))
        with _STUDENT_SYNC_LOCK:
            return apply_student_sync_plan(config, [], max_actions=max_actions)

    raise TrelloReadOnlyError("Accion local no soportada.")
