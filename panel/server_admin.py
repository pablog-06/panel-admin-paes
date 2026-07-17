from __future__ import annotations

import base64
from typing import Any

import streamlit as st

from panel.audit import backup_database, write_audit_log
from panel.results_db import (
    archive_master_card,
    archive_master_list,
    create_master_list,
    latest_exam_summary,
    load_cohort_status,
    load_master_board,
    median_scores_by_exam,
    sync_student_board_registry,
    upsert_master_card,
)
from panel.student_sync import SAFE_ACTION_LABELS, apply_student_sync_plan, build_student_sync_plan
from panel.trello_client import TrelloConfig, fetch_paes_board_inventory_read_only, fetch_student_boards_read_only, _fetch_student_boards_cached
from scripts.import_essay_scores import import_scores


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


def _card_options(lists: list[dict[str, Any]]) -> dict[str, str]:
    options: dict[str, str] = {}
    for list_item in lists:
        list_name = str(list_item.get("name") or "Lista")
        for card in list_item.get("cards") or []:
            card_id = str(card.get("id") or "")
            if card_id:
                options[f"{list_name} / {card.get('title') or 'Tarjeta'}"] = card_id
    return options


def _rerun_after_success(message: str) -> None:
    st.success(message)
    st.cache_data.clear()
    st.rerun()


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
    st.caption("Lee Trello y escribe SQLite desde Python en la VM. No abre una API publica adicional.")
    _render_metrics()

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Actualizar alumnos desde Trello", use_container_width=True):
            try:
                with st.spinner("Leyendo boards PAES desde Trello..."):
                    _fetch_student_boards_cached.cache_clear()
                    inventory = fetch_paes_board_inventory_read_only(config)
                    students = inventory.get("students") or []
                    unknown = inventory.get("unknown") or []
                    result = sync_student_board_registry(students)
                detail = (
                    f"{result.get('active_count', 0)} alumno(s) activo(s), "
                    f"{len(result.get('new_board_ids') or [])} nuevo(s), "
                    f"{len(result.get('archived_board_ids') or [])} archivado(s), "
                    f"{len(unknown)} board(s) PAES no identificado(s)."
                )
                write_audit_log("Actualizar administracion", detail, meta={"result": result, "unknown": unknown})
                st.session_state["server_admin_last_update"] = detail
                if not students:
                    st.warning(
                        "Trello respondio correctamente, pero no se encontraron boards abiertos con nombre tipo 'PAES Nombre'. "
                        "Revisa que el token pertenezca al usuario que ve esos boards y que no esten archivados."
                    )
                    if unknown:
                        st.caption("Boards PAES no identificados: " + ", ".join(item.get("board_name", "") for item in unknown[:8]))
                _rerun_after_success("Alumnos actualizados desde Trello.")
            except Exception as exc:
                message = f"Error al actualizar alumnos desde Trello: {exc}"
                write_audit_log("Error actualizar administracion", message, status="error")
                st.error(message)
    last_update = st.session_state.get("server_admin_last_update")
    if last_update:
        st.caption(f"Ultima lectura Trello: {last_update}")
    with col_b:
        if st.button("Actualizar resultados Ensayos", use_container_width=True):
            imported, skipped, errors = import_scores(dry_run=False, delay=0.35, limit=None)
            write_audit_log(
                "Actualizar resultados",
                f"Ensayos importados: {imported}. Omitidos: {skipped}. Errores: {errors}.",
            )
            _rerun_after_success("Resultados actualizados desde Trello.")


def _render_content_editor() -> None:
    lists = _current_lists()
    list_options = _list_options(lists)
    card_options = _card_options(lists)

    st.subheader("Contenido maestro")
    col_a, col_b = st.columns(2)

    with col_a:
        with st.form("server_create_list", clear_on_submit=True):
            name = st.text_input("Nueva lista")
            submitted = st.form_submit_button("Crear lista")
        if submitted:
            backup_database("before_server_create_list")
            create_master_list(name)
            write_audit_log("Crear lista", f"Se creo la lista '{name}'.")
            _rerun_after_success("Lista creada.")

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
                    backup_database("before_server_archive_list")
                    archive_master_list(list_options[selected])
                    write_audit_log("Eliminar lista", f"Se archivo la lista '{selected}'.")
                    _rerun_after_success("Lista archivada.")

    st.divider()
    with st.form("server_upsert_card", clear_on_submit=True):
        selected_list = st.selectbox("Lista destino", list(list_options.keys()) if list_options else [])
        title = st.text_input("Titulo tarjeta")
        description = st.text_area("Descripcion", height=100)
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
            backup_database("before_server_save_card")
            upsert_master_card(
                card_id="",
                list_id=list_options[selected_list],
                title=title,
                description=description,
                links=[line.strip() for line in links_text.splitlines() if line.strip()],
                images=[_data_url(item) for item in (image_uploads or [])],
                files=[_data_url(item) for item in (pdf_uploads or [])],
                checklists=checklists,
            )
            write_audit_log("Guardar tarjeta", f"Se guardo la tarjeta '{title}'.")
            _rerun_after_success("Tarjeta guardada.")

    if card_options:
        with st.form("server_archive_card"):
            selected_card = st.selectbox("Archivar tarjeta", list(card_options.keys()))
            confirmation = st.text_input("Escribe ARCHIVAR para confirmar", key="archive_card_confirmation")
            submitted = st.form_submit_button("Archivar tarjeta")
        if submitted:
            if confirmation != "ARCHIVAR":
                st.error("Confirmacion incorrecta.")
            else:
                backup_database("before_server_archive_card")
                archive_master_card(card_options[selected_card])
                write_audit_log("Eliminar tarjeta", f"Se archivo la tarjeta '{selected_card}'.")
                _rerun_after_success("Tarjeta archivada.")


def _render_sync(config: TrelloConfig) -> None:
    st.subheader("Sincronizacion alumnos")
    st.caption("Nunca toca la lista Ensayos. Crea backups antes de escribir en Trello.")
    max_actions = st.number_input("Maximo de acciones", min_value=1, max_value=500, value=200, step=25)
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Vista previa", use_container_width=True):
            with st.spinner("Leyendo boards PAES..."):
                plan = build_student_sync_plan(config, load_master_board())
            st.session_state["server_sync_plan"] = plan
    with col_b:
        confirmation = st.text_input("Para aplicar escribe SINCRONIZAR")
        if st.button("Aplicar cambios", use_container_width=True):
            if confirmation != "SINCRONIZAR":
                st.error("Confirmacion incorrecta.")
            else:
                with st.spinner("Aplicando cambios en Trello..."):
                    result = apply_student_sync_plan(config, load_master_board(), max_actions=int(max_actions))
                st.session_state["server_sync_result"] = result
                st.success(f"Aplicados: {result.get('applied', 0)}. Errores: {len(result.get('errors') or [])}.")

    plan = st.session_state.get("server_sync_plan")
    if plan:
        st.info(f"Vista previa: {len(plan.get('actions') or [])} cambio(s), {len(plan.get('errors') or [])} error(es).")
        for action in (plan.get("actions") or [])[:25]:
            label = SAFE_ACTION_LABELS.get(action.get("action"), action.get("action"))
            st.write(f"- **{label}** · {action.get('student_name')} · {action.get('list_name')} / {action.get('card_title')}")
        if len(plan.get("actions") or []) > 25:
            st.caption("Mostrando solo los primeros 25 cambios.")

    result = st.session_state.get("server_sync_result")
    if result:
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
        tabs = st.tabs(["Administracion", "Contenido", "Sincronizacion"])
        with tabs[0]:
            _render_trello_admin(config)
        with tabs[1]:
            _render_content_editor()
        with tabs[2]:
            _render_sync(config)
