
from __future__ import annotations

import base64
from typing import Any

import streamlit as st

from panel.admin_actions import execute_admin_action
from panel.results_db import latest_exam_summary, load_cohort_status, load_master_board, median_scores_by_exam
from panel.student_sync import SAFE_ACTION_LABELS
from panel.trello_client import TrelloConfig


def _data_url(uploaded_file: Any) -> dict[str, str]:
    content = uploaded_file.getvalue()
    encoded = base64.b64encode(content).decode("ascii")
    content_type = uploaded_file.type or "application/octet-stream"
    return {
        "name": uploaded_file.name,
        "src": f"data:{content_type};base64,{encoded}",
        "content_type": content_type,
    }


def _current_lists() -> list[dict[str, Any]]:
    return [item for item in load_master_board() if str(item.get("id") or "") != "results"]


def _list_options(lists: list[dict[str, Any]]) -> dict[str, str]:
    return {str(item.get("name") or "Lista"): str(item.get("id") or "") for item in lists}


def _card_options(lists: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    options: dict[str, dict[str, str]] = {}
    for list_item in lists:
        list_name = str(list_item.get("name") or "Lista")
        list_id = str(list_item.get("id") or "")
        for card in list_item.get("cards") or []:
            card_id = str(card.get("id") or "")
            if card_id:
                options[f"{list_name} / {card.get('title') or 'Tarjeta'}"] = {
                    "card_id": card_id,
                    "list_id": list_id,
                    "list_name": list_name,
                    "title": str(card.get("title") or ""),
                    "description": str(card.get("description") or ""),
                }
    return options


def _rerun_after_success(message: str) -> None:
    st.success(message)
    st.cache_data.clear()
    st.rerun()


def _safe_action(config: TrelloConfig, path: str, payload: dict[str, Any] | None = None) -> Any:
    return execute_admin_action(path, payload or {}, config)


def _render_metrics() -> None:
    summary = latest_exam_summary() or {}
    cohort = load_cohort_status()
    series = median_scores_by_exam()
    cols = st.columns(6)
    cols[0].metric("Alumnos activos", cohort.get("active_count", 0))
    cols[1].metric("Archivados", cohort.get("archived_count", 0))
    cols[2].metric("Promedio", summary.get("average", "--"))
    cols[3].metric("Mediana", summary.get("median", "--"))
    cols[4].metric("Min", (summary.get("min") or {}).get("score", "--"))
    cols[5].metric("Max", (summary.get("max") or {}).get("score", "--"))
    if series:
        st.line_chart(
            {"Mediana": {str(item.get("exam")): item.get("median") for item in series}},
            height=180,
        )


def _render_trello_admin(config: TrelloConfig) -> None:
    st.subheader("Administracion server-side")
    st.caption("Mismo motor de acciones que el modo local, ejecutado desde Python en la VM.")
    _render_metrics()

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Actualizar alumnos desde Trello", use_container_width=True):
            try:
                with st.spinner("Leyendo boards PAES desde Trello..."):
                    result = _safe_action(config, "/admin-dashboard", {"refresh": True, "limit": 80})
                summary = result.get("refresh_summary") or {}
                detail = (
                    f"{summary.get('active_count', 0)} alumno(s) activo(s), "
                    f"{len(summary.get('new_board_ids') or [])} nuevo(s), "
                    f"{len(summary.get('archived_board_ids') or [])} archivado(s), "
                    f"{result.get('unknown_count', 0)} board(s) PAES no identificado(s)."
                )
                st.session_state["server_admin_last_update"] = detail
                _rerun_after_success("Alumnos actualizados desde Trello.")
            except Exception as exc:
                st.error(f"Error al actualizar alumnos desde Trello: {exc}")
    with col_b:
        if st.button("Actualizar resultados Ensayos", use_container_width=True):
            try:
                with st.spinner("Leyendo Ensayos en modo solo lectura..."):
                    _safe_action(config, "/refresh-results", {"force": True})
                _rerun_after_success("Resultados actualizados desde Trello.")
            except Exception as exc:
                st.error(f"Error al actualizar resultados: {exc}")

    last_update = st.session_state.get("server_admin_last_update")
    if last_update:
        st.caption(f"Ultima lectura Trello: {last_update}")


def _render_content_editor(config: TrelloConfig) -> None:
    lists = _current_lists()
    list_options = _list_options(lists)
    card_options = _card_options(lists)

    st.subheader("Contenido maestro local")
    st.caption("Estas acciones escriben SQLite local, dejan logs/backups y marcan contenido pendiente para alumnos.")
    col_a, col_b = st.columns(2)

    with col_a:
        with st.form("server_create_list", clear_on_submit=True):
            name = st.text_input("Nueva lista")
            submitted = st.form_submit_button("Crear lista")
        if submitted:
            try:
                _safe_action(config, "/create-list", {"name": name})
                _rerun_after_success("Lista creada.")
            except Exception as exc:
                st.error(str(exc))

    with col_b:
        if list_options:
            with st.form("server_archive_list"):
                selected = st.selectbox("Archivar lista", list(list_options.keys()))
                confirmation = st.text_input("Escribe ARCHIVAR para confirmar")
                submitted = st.form_submit_button("Archivar lista")
            if submitted:
                if confirmation != "ARCHIVAR":
                    st.error("Confirmacion incorrecta.")
                else:
                    try:
                        _safe_action(config, "/archive-list", {"list_id": list_options[selected], "list_name": selected})
                        _rerun_after_success("Lista archivada.")
                    except Exception as exc:
                        st.error(str(exc))

    st.divider()
    edit_mode = st.toggle("Editar tarjeta existente", value=False)
    selected_card_key = ""
    selected_card = {}
    if edit_mode and card_options:
        selected_card_key = st.selectbox("Tarjeta a editar", list(card_options.keys()))
        selected_card = card_options.get(selected_card_key) or {}

    default_list_name = selected_card.get("list_name") if selected_card else ""
    default_list_index = list(list_options.keys()).index(default_list_name) if default_list_name in list_options else 0
    with st.form("server_upsert_card", clear_on_submit=not edit_mode):
        selected_list = st.selectbox("Lista destino", list(list_options.keys()) if list_options else [], index=default_list_index)
        title = st.text_input("Titulo tarjeta", value=str(selected_card.get("title") or ""))
        description = st.text_area("Descripcion", value=str(selected_card.get("description") or ""), height=100)
        links_text = st.text_area("Links", placeholder="Un link por linea", height=80)
        checklist_title = st.text_input("Checklist: titulo opcional")
        checklist_description = st.text_input("Checklist: descripcion opcional")
        checklist_link = st.text_input("Checklist: link opcional")
        image_uploads = st.file_uploader("Imagenes", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)
        pdf_uploads = st.file_uploader("PDFs", type=["pdf"], accept_multiple_files=True)
        submitted = st.form_submit_button("Guardar tarjeta")
    if submitted:
        if not list_options:
            st.error("Primero crea una lista.")
        else:
            checklists = []
            if checklist_title.strip():
                checklists.append(
                    {
                        "title": checklist_title.strip(),
                        "description": checklist_description.strip(),
                        "link": checklist_link.strip(),
                        "items": [item for item in [checklist_description.strip(), checklist_link.strip()] if item],
                    }
                )
            try:
                _safe_action(
                    config,
                    "/save-card",
                    {
                        "card_id": selected_card.get("card_id", "") if edit_mode else "",
                        "list_id": list_options[selected_list],
                        "list_name": selected_list,
                        "title": title,
                        "description": description,
                        "links": [line.strip() for line in links_text.splitlines() if line.strip()],
                        "images": [_data_url(item) for item in (image_uploads or [])],
                        "files": [_data_url(item) for item in (pdf_uploads or [])],
                        "checklists": checklists,
                    },
                )
                _rerun_after_success("Tarjeta guardada.")
            except Exception as exc:
                st.error(str(exc))

    if card_options:
        with st.form("server_archive_card"):
            selected_card_to_archive = st.selectbox("Archivar tarjeta", list(card_options.keys()))
            confirmation = st.text_input("Escribe ARCHIVAR para confirmar", key="archive_card_confirmation")
            submitted = st.form_submit_button("Archivar tarjeta")
        if submitted:
            if confirmation != "ARCHIVAR":
                st.error("Confirmacion incorrecta.")
            else:
                try:
                    selected = card_options[selected_card_to_archive]
                    _safe_action(
                        config,
                        "/archive-card",
                        {"card_id": selected["card_id"], "card_title": selected_card_to_archive},
                    )
                    _rerun_after_success("Tarjeta archivada.")
                except Exception as exc:
                    st.error(str(exc))


def _render_visibility(config: TrelloConfig) -> None:
    st.subheader("Visibilidad por alumno")
    st.caption("Oculta o muestra contenido maestro por alumno. Al sincronizar, no toca Ensayos.")
    lists = _current_lists()
    content_options: dict[str, dict[str, str]] = {}
    for item in lists:
        list_id = str(item.get("id") or "")
        list_name = str(item.get("name") or "Lista")
        content_options[f"Lista / {list_name}"] = {"content_type": "list", "content_id": list_id, "title": list_name}
        for card in item.get("cards") or []:
            card_id = str(card.get("id") or "")
            card_title = str(card.get("title") or "Tarjeta")
            content_options[f"Tarjeta / {list_name} / {card_title}"] = {
                "content_type": "card",
                "content_id": card_id,
                "title": card_title,
            }
    if not content_options:
        st.info("No hay contenido maestro para configurar.")
        return

    cohort = _safe_action(config, "/cohort-status", {})
    students = [item for item in cohort.get("students", []) if item.get("status") == "open"]
    if not students:
        st.warning("Primero actualiza alumnos desde Trello.")
        return

    selected_key = st.selectbox("Contenido", list(content_options.keys()))
    selected = content_options[selected_key]
    hidden_result = _safe_action(config, "/visibility-get", selected)
    hidden_ids = set(hidden_result.get("hidden_student_ids") or [])
    student_labels = {f"{item.get('initials') or '?'} - {item.get('student_name') or item.get('board_name')}": item for item in students}
    default_hidden = [label for label, item in student_labels.items() if item.get("board_id") in hidden_ids]
    hidden_labels = st.multiselect(
        "Alumnos sin acceso a este contenido",
        list(student_labels.keys()),
        default=default_hidden,
        help="Por defecto todos tienen acceso. Selecciona solo quienes NO deben verlo.",
    )
    if st.button("Guardar visibilidad", use_container_width=True):
        hidden_board_ids = [student_labels[label]["board_id"] for label in hidden_labels]
        try:
            _safe_action(
                config,
                "/visibility-save",
                {
                    **selected,
                    "students": students,
                    "hidden_student_ids": hidden_board_ids,
                    "content_title": selected_key,
                },
            )
            _rerun_after_success("Visibilidad guardada.")
        except Exception as exc:
            st.error(str(exc))


def _render_sync(config: TrelloConfig) -> None:
    st.subheader("Sincronizacion alumnos")
    st.caption("Reutiliza el mismo planificador local: pendientes, visibilidad, entregas, borrados y backups.")
    max_actions = st.number_input("Maximo de acciones", min_value=1, max_value=500, value=500, step=25)
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("Vista previa", use_container_width=True):
            try:
                with st.spinner("Generando plan seguro..."):
                    plan = _safe_action(config, "/sync-preview-students", {})
                st.session_state["server_sync_plan"] = plan
            except Exception as exc:
                st.error(str(exc))
    with col_b:
        confirmation = st.text_input("Para aplicar escribe SINCRONIZAR")
    with col_c:
        if st.button("Iniciar sincronizacion", use_container_width=True):
            try:
                result = _safe_action(
                    config,
                    "/sync-start-students",
                    {"confirmation": confirmation, "max_actions": int(max_actions)},
                )
                st.session_state["server_sync_job_id"] = result.get("job_id")
                st.success("Sincronizacion iniciada.")
            except Exception as exc:
                st.error(str(exc))

    job_id = st.session_state.get("server_sync_job_id")
    if job_id:
        if st.button("Actualizar progreso", use_container_width=True):
            try:
                st.session_state["server_sync_job"] = _safe_action(config, "/sync-status", {"job_id": job_id})
            except Exception as exc:
                st.error(str(exc))
        job = st.session_state.get("server_sync_job") or _safe_action(config, "/sync-status", {"job_id": job_id})
        total = int(job.get("total_boards") or 0)
        completed = int(job.get("completed_boards") or 0)
        if total:
            st.progress(min(completed / total, 1.0), text=f"{completed}/{total} boards procesados")
        st.caption(f"Estado: {job.get('status', 'queued')} - {job.get('note', '')}")
        progress = job.get("progress") or []
        if progress:
            cols = st.columns(6)
            for idx, item in enumerate(progress[-24:]):
                status = str(item.get("status") or "")
                symbol = "OK" if status in {"done", "synced"} else "..." if status == "syncing" else "!"
                cols[idx % 6].caption(f"{symbol} {item.get('student_name') or item.get('board_id')}")
        if job.get("status") in {"done", "error"} and job.get("result"):
            st.session_state["server_sync_result"] = job.get("result")

    plan = st.session_state.get("server_sync_plan")
    if plan:
        st.info(f"Vista previa: {len(plan.get('actions') or [])} cambio(s), {len(plan.get('errors') or [])} error(es).")
        summary = plan.get("summary") or {}
        if summary:
            st.json({SAFE_ACTION_LABELS.get(key, key): value for key, value in summary.items()})
        for action in (plan.get("actions") or [])[:25]:
            label = SAFE_ACTION_LABELS.get(action.get("action"), action.get("action"))
            st.write(f"- **{label}** ? {action.get('student_name')} ? {action.get('list_name')} / {action.get('card_title')}")
        if len(plan.get("actions") or []) > 25:
            st.caption("Mostrando solo los primeros 25 cambios.")

    result = st.session_state.get("server_sync_result")
    if result:
        st.success(f"Aplicados: {result.get('applied', 0)}. Errores: {len(result.get('errors') or [])}.")
        if result.get("errors"):
            with st.expander("Errores de sincronizacion", expanded=False):
                st.json(result.get("errors"))
        if result.get("board_results"):
            with st.expander("Boards procesados", expanded=False):
                st.json(result.get("board_results"))


def render_server_admin_panel(config: TrelloConfig, *, enabled: bool) -> None:
    if not enabled or not config.is_complete:
        return

    st.html(
        """
        <style>
            div[data-testid="stExpander"] {
                width: min(1180px, calc(100vw - 32px));
                margin: 10px auto 16px;
                border: 1px solid rgba(190,225,238,.72);
                border-radius: 18px;
                background: rgba(255,255,255,.76);
                box-shadow: 0 18px 48px rgba(31,81,111,.10);
            }
        </style>
        """
    )
    with st.expander("Panel servidor seguro", expanded=False):
        tabs = st.tabs(["Administracion", "Contenido", "Visibilidad", "Sincronizacion"])
        with tabs[0]:
            _render_trello_admin(config)
        with tabs[1]:
            _render_content_editor(config)
        with tabs[2]:
            _render_visibility(config)
        with tabs[3]:
            _render_sync(config)
