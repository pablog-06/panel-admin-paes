from __future__ import annotations

import base64
import json
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from panel.audit import backup_database, enforce_retention, read_audit_log, write_audit_log
from panel.results_db import (
    archive_master_card,
    archive_master_list,
    build_results_panel,
    create_master_list,
    latest_exam_summary,
    load_cohort_status,
    mark_master_content_pending,
    median_scores_by_exam,
    move_master_card,
    move_master_list,
    sync_student_board_registry,
    upsert_master_card,
)
from panel.results_db import hidden_student_board_ids, save_hidden_students
from panel.student_sync import SAFE_ACTION_LABELS, apply_student_sync_plan, build_student_sync_plan
from panel.trello_client import (
    TrelloConfig,
    TrelloReadOnlyError,
    fetch_paes_board_inventory_read_only,
    fetch_student_boards_read_only,
)
from scripts.import_essay_scores import import_scores


@dataclass
class ApiState:
    config: TrelloConfig
    api_token: str


_SERVER: ThreadingHTTPServer | None = None
_THREAD: threading.Thread | None = None
_STATE: ApiState | None = None
_RESULTS_SYNC_LOCK = threading.Lock()
_RESULTS_SYNCED_AT = 0.0
_RESULTS_SYNC_TTL_SECONDS = 600
_BACKUP_LOCK = threading.Lock()
_LAST_BOARD_BACKUP: dict[str, tuple[float, str]] = {}
_BOARD_BACKUP_REUSE_SECONDS = 300
_PERIODIC_BACKUP_LOCK = threading.Lock()
_LAST_PERIODIC_BACKUP_AT = 0.0
_PERIODIC_BACKUP_SECONDS = 1800
_STUDENT_SYNC_LOCK = threading.Lock()
_SYNC_JOBS: dict[str, dict[str, Any]] = {}
_SYNC_JOBS_LOCK = threading.Lock()
API_VERSION = "local-api-local-master-1"


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-PAES-Token")
    handler.end_headers()
    handler.wfile.write(body)


def _decode_data_url(value: str) -> tuple[str, bytes]:
    header, encoded = value.split(",", 1)
    content_type = "application/octet-stream"
    if header.startswith("data:") and ";" in header:
        content_type = header[5:].split(";", 1)[0] or content_type
    return content_type, base64.b64decode(encoded)


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


def _backup_local_before_write(config: TrelloConfig, reason: str) -> str:
    return backup_database(reason)


def _periodic_backup_if_due(config: TrelloConfig) -> None:
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


def _payload_text(payload: dict[str, Any], key: str, default: str = "") -> str:
    return str(payload.get(key) or default).strip()


def _admin_history_events(limit: int = 80) -> list[dict[str, Any]]:
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


class AdminApiHandler(BaseHTTPRequestHandler):
    server_version = "AdminPaesLocalApi/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_OPTIONS(self) -> None:
        _json_response(self, 200, {"ok": True})

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/health":
            _json_response(self, 200, {"ok": True, "result": {"status": "ready", "version": API_VERSION}})
            return
        _json_response(self, 404, {"ok": False, "error": "Ruta no encontrada."})

    def do_POST(self) -> None:
        if _STATE is None:
            _json_response(self, 503, {"ok": False, "error": "API local no inicializada."})
            return

        if not hmac_safe_token(self.headers.get("X-Admin-PAES-Token", ""), _STATE.api_token):
            _json_response(self, 403, {"ok": False, "error": "Sesion no autorizada."})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            path = urlparse(self.path).path
            if path in {"/create-list", "/save-card", "/move-list", "/move-card", "/archive-list", "/archive-card"}:
                _periodic_backup_if_due(_STATE.config)
            result = self._dispatch(path, payload, _STATE.config)
        except TrelloReadOnlyError as error:
            write_audit_log("trello_action", str(error), status="error", meta={"path": self.path})
            _json_response(self, 400, {"ok": False, "error": str(error)})
            return
        except Exception as error:
            write_audit_log("local_api", str(error), status="error", meta={"path": self.path})
            _json_response(self, 500, {"ok": False, "error": str(error)})
            return

        _json_response(self, 200, {"ok": True, "result": result})

    def _dispatch(self, path: str, payload: dict[str, Any], config: TrelloConfig) -> Any:
        if path == "/create-list":
            name = str(payload.get("name", "")).strip()
            backup_path = _backup_local_before_write(config, "before_create_list")
            result = create_master_list(name)
            write_audit_log("Crear lista", f"Se creo la lista '{name}'.", meta={"backup": backup_path})
            return result

        if path == "/save-card":
            card_id = str(payload.get("card_id", "")).strip()
            title = str(payload.get("title", "")).strip()
            description = str(payload.get("description", "")).strip()
            links = [str(item).strip() for item in payload.get("links", []) if str(item).strip()]
            images = [item for item in payload.get("images", []) if isinstance(item, dict)]
            files = [item for item in payload.get("files", []) if isinstance(item, dict)]
            checklists = [item for item in payload.get("checklists", []) if isinstance(item, dict)]
            source_payload = {
                "title": title,
                "description": description,
                "links": links,
                "images": images,
                "files": files,
                "checklists": checklists,
                "list_id": str(payload.get("list_id", "")).strip(),
                "list_name": str(payload.get("list_name", "")).strip(),
            }
            backup_path = _backup_local_before_write(config, "before_save_card")
            result = upsert_master_card(
                card_id=card_id,
                list_id=str(payload.get("list_id", "")).strip(),
                title=title,
                description=description,
                links=links,
                images=images,
                files=files,
                checklists=checklists,
            )
            card_id = str(result.get("card_id") or card_id)

            write_audit_log(
                "Editar tarjeta" if payload.get("card_id") else "Crear tarjeta",
                f"Se {'actualizo' if payload.get('card_id') else 'creo'} la tarjeta '{title}'.",
                meta={"card_id": card_id, "backup": backup_path},
            )
            return {"card_id": card_id}

        if path == "/move-list":
            backup_path = _backup_local_before_write(config, "before_move_list")
            result = move_master_list(
                str(payload.get("list_id", "")).strip(),
                payload.get("pos", "bottom"),
            )
            list_name = _payload_text(payload, "list_name", str(payload.get("list_id", "")))
            write_audit_log("Mover lista", f"Se movio la lista '{list_name}'.", meta={"backup": backup_path})
            return result

        if path == "/move-card":
            backup_path = _backup_local_before_write(config, "before_move_card")
            result = move_master_card(
                str(payload.get("card_id", "")).strip(),
                str(payload.get("list_id", "")).strip(),
                payload.get("pos", "bottom"),
            )
            card_title = _payload_text(payload, "card_title", str(payload.get("card_id", "")))
            list_name = _payload_text(payload, "list_name", str(payload.get("list_id", "")))
            write_audit_log(
                "Mover tarjeta",
                f"Se movio la tarjeta '{card_title}' en '{list_name}'.",
                meta={"backup": backup_path},
            )
            return result

        if path == "/archive-list":
            backup_path = _backup_local_before_write(config, "before_archive_list")
            list_id = str(payload.get("list_id", "")).strip()
            result = archive_master_list(list_id)
            list_name = _payload_text(payload, "list_name", str(payload.get("list_id", "")))
            write_audit_log("Eliminar lista", f"Se archivo localmente la lista '{list_name}'.", meta={"backup": backup_path})
            return result

        if path == "/archive-card":
            backup_path = _backup_local_before_write(config, "before_archive_card")
            card_id = str(payload.get("card_id", "")).strip()
            result = archive_master_card(card_id)
            card_title = _payload_text(payload, "card_title", str(payload.get("card_id", "")))
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
                    meta=summary,
                )
            return {
                "cohort": load_cohort_status(),
                "events": _admin_history_events(int(payload.get("limit") or 80)),
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
            return {"hidden_student_ids": sorted(hidden_student_board_ids(content_type, content_id))}

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
            requested_max = payload.get("max_actions")
            max_actions = max(1, min(int(requested_max or 500), 500))
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
            requested_max = payload.get("max_actions")
            max_actions = max(1, min(int(requested_max or 500), 500))
            with _STUDENT_SYNC_LOCK:
                result = apply_student_sync_plan(config, [], max_actions=max_actions)
            return result

        raise TrelloReadOnlyError("Accion local no soportada.")


def ensure_local_api(config: TrelloConfig, host: str = "127.0.0.1", port: int = 8765) -> str:
    global _SERVER, _THREAD, _STATE
    _STATE = ApiState(config=config, api_token=secrets.token_urlsafe(32))
    enforce_retention()
    if _SERVER is None or _THREAD is None or not _THREAD.is_alive():
        ThreadingHTTPServer.allow_reuse_address = True
        _SERVER = ThreadingHTTPServer((host, port), AdminApiHandler)
        _THREAD = threading.Thread(target=_SERVER.serve_forever, name="paes-local-api", daemon=True)
        _THREAD.start()
    threading.Thread(
        target=_periodic_backup_if_due,
        args=(config,),
        name="paes-periodic-backup",
        daemon=True,
    ).start()
    return f"http://{host}:{port}|{_STATE.api_token}"


def hmac_safe_token(candidate: str, expected: str) -> bool:
    return secrets.compare_digest(str(candidate or ""), str(expected or ""))
