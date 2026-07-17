
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


def _card_options(lists: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    options: dict[str, dict[str, Any]] = {}
    for list_item in lists:
        list_name = str(list_item.get("name") or "Lista")
        list_id = str(list_item.get("id") or "")
        for card in list_item.get("cards") or []:
            card_id = str(card.get("id") or "")
            if card_id:
                options[f"{list_name} / {card.get('title') or 'Tarjeta'}"] = {
                    **card,
                    "card_id": card_id,
                    "list_id": list_id,
                    "list_name": list_name,
                    "title": str(card.get("title") or ""),
                    "description": str(card.get("description") or ""),
                }
    return options


def _move_position(items: list[dict[str, Any]], current_id: str, direction: int) -> float:
    ordered = sorted(items, key=lambda item: float(item.get("pos") or 0))
    ids = [str(item.get("id") or "") for item in ordered]
    if current_id not in ids:
        return float(len(ordered) + 1) * 1000.0
    index = ids.index(current_id)
    target = max(0, min(len(ordered) - 1, index + direction))
    if target == index:
        return float(ordered[index].get("pos") or (index + 1) * 1000)
    ordered[index], ordered[target] = ordered[target], ordered[index]
    return float((target + 1) * 1000)


def _links_to_text(items: list[Any]) -> str:
    return "\n".join(str(item) for item in (items or []) if str(item).strip())


def _first_checklist(card: dict[str, Any]) -> dict[str, Any]:
    checklists = card.get("checklists") or []
    return checklists[0] if checklists and isinstance(checklists[0], dict) else {}


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

    st.subheader("Tablero maestro server-side")
    st.caption("Todas las acciones escriben SQLite en la VM, dejan logs/backups y quedan pendientes para sincronizar por lote.")

    with st.container(horizontal=True, gap="small"):
        if st.button("Nueva lista", icon=":material/add:", width="content"):
            st.session_state["server_content_mode"] = "new_list"
        if st.button("Nueva tarjeta", icon=":material/note_add:", type="primary", width="content"):
            st.session_state["server_content_mode"] = "new_card"
            st.session_state.pop("server_selected_card", None)
        if st.button("Vista previa sync", icon=":material/manage_search:", width="content"):
            st.session_state["server_content_mode"] = "sync_hint"

    mode = st.session_state.get("server_content_mode", "new_card")

    if mode == "new_list":
        with st.form("server_create_list", clear_on_submit=True):
            name = st.text_input("Nombre de la lista")
            submitted = st.form_submit_button("Crear lista", type="primary")
        if submitted:
            try:
                _safe_action(config, "/create-list", {"name": name})
                _rerun_after_success("Lista creada.")
            except Exception as exc:
                st.error(str(exc))

    if mode == "sync_hint":
        st.info("Ve a la pestana Sincronizacion para revisar y aplicar cambios en los boards de alumnos. Ensayos no se toca.")

    st.divider()
    st.markdown("**Tablero local**")
    if not lists:
        st.info("No hay listas activas. Crea una lista para comenzar.")
    else:
        board = st.container(horizontal=True, horizontal_alignment="left", vertical_alignment="top", gap="small")
        with board:
            for list_item in lists:
                list_id = str(list_item.get("id") or "")
                list_name = str(list_item.get("name") or "Lista")
                cards = list_item.get("cards") or []
                with st.container(border=True, width=280, height=520):
                    st.markdown(f"**{list_name}**")
                    st.caption(f"{len(cards)} tarjeta(s)")
                    with st.container(horizontal=True, gap="xxsmall"):
                        if st.button("Arriba", key=f"list_up_{list_id}", width="content"):
                            pos = _move_position(lists, list_id, -1)
                            _safe_action(config, "/move-list", {"list_id": list_id, "pos": pos, "list_name": list_name})
                            _rerun_after_success("Lista movida.")
                        if st.button("Abajo", key=f"list_down_{list_id}", width="content"):
                            pos = _move_position(lists, list_id, 1)
                            _safe_action(config, "/move-list", {"list_id": list_id, "pos": pos, "list_name": list_name})
                            _rerun_after_success("Lista movida.")
                        if st.button("Ocultar", key=f"vis_list_{list_id}", width="content"):
                            st.session_state["server_visibility_target"] = {"content_type": "list", "content_id": list_id}
                            st.session_state["server_content_mode"] = "visibility_jump"
                            st.info("Abre la pestana Visibilidad para ajustar esta lista.")
                    if st.button("Nueva tarjeta aqui", key=f"new_card_{list_id}", icon=":material/add:", width="stretch"):
                        st.session_state["server_content_mode"] = "new_card"
                        st.session_state["server_default_list_id"] = list_id
                        st.session_state.pop("server_selected_card", None)
                        st.rerun()
                    if st.button("Archivar lista", key=f"archive_list_{list_id}", icon=":material/delete:", width="stretch"):
                        st.session_state["server_content_mode"] = "archive_list"
                        st.session_state["server_archive_list_id"] = list_id
                        st.session_state["server_archive_list_name"] = list_name
                        st.rerun()
                    with st.container(height=310):
                        for card in cards:
                            card_id = str(card.get("id") or "")
                            title = str(card.get("title") or "Tarjeta")
                            badges = []
                            if card.get("links"):
                                badges.append(f"links {len(card.get('links') or [])}")
                            if card.get("images"):
                                badges.append(f"img {len(card.get('images') or [])}")
                            if card.get("files"):
                                badges.append(f"pdf {len(card.get('files') or [])}")
                            if card.get("checklists"):
                                badges.append(f"chk {len(card.get('checklists') or [])}")
                            with st.container(border=True):
                                st.markdown(f"**{title}**")
                                if card.get("description"):
                                    st.caption(str(card.get("description"))[:120])
                                if badges:
                                    st.caption(" - ".join(badges))
                                with st.container(horizontal=True, gap="xxsmall"):
                                    if st.button("Editar", key=f"edit_{card_id}", icon=":material/edit:", width="content"):
                                        st.session_state["server_content_mode"] = "edit_card"
                                        st.session_state["server_selected_card"] = card_id
                                        st.rerun()
                                    if st.button("Subir", key=f"card_up_{card_id}", width="content"):
                                        pos = _move_position(cards, card_id, -1)
                                        _safe_action(config, "/move-card", {"card_id": card_id, "list_id": list_id, "pos": pos, "card_title": title, "list_name": list_name})
                                        _rerun_after_success("Tarjeta movida.")
                                    if st.button("Bajar", key=f"card_down_{card_id}", width="content"):
                                        pos = _move_position(cards, card_id, 1)
                                        _safe_action(config, "/move-card", {"card_id": card_id, "list_id": list_id, "pos": pos, "card_title": title, "list_name": list_name})
                                        _rerun_after_success("Tarjeta movida.")
                                if st.button("Eliminar tarjeta", key=f"archive_card_{card_id}", icon=":material/delete:", width="stretch"):
                                    st.session_state["server_content_mode"] = "archive_card"
                                    st.session_state["server_archive_card_id"] = card_id
                                    st.session_state["server_archive_card_title"] = title
                                    st.rerun()

    st.divider()
    mode = st.session_state.get("server_content_mode", "new_card")
    selected_card_id = str(st.session_state.get("server_selected_card") or "")
    selected_card = next((value for value in card_options.values() if str(value.get("card_id") or "") == selected_card_id), {})
    editing = mode == "edit_card" and bool(selected_card)
    if mode in {"new_card", "edit_card"}:
        st.markdown("**Editor de tarjeta**")
        if not list_options:
            st.warning("Primero crea una lista.")
        else:
            default_list_id = str(selected_card.get("list_id") or st.session_state.get("server_default_list_id") or "")
            list_names = list(list_options.keys())
            default_list_name = next((name for name, value in list_options.items() if value == default_list_id), list_names[0])
            default_index = list_names.index(default_list_name)
            checklist = _first_checklist(selected_card)
            with st.form("server_card_editor", clear_on_submit=not editing):
                selected_list = st.selectbox("Lista destino", list_names, index=default_index)
                title = st.text_input("Titulo", value=str(selected_card.get("title") or ""))
                description = st.text_area("Descripcion", value=str(selected_card.get("description") or ""), height=110)
                links_text = st.text_area("Links", value=_links_to_text(selected_card.get("links") or []), placeholder="Un link por linea", height=90)
                st.caption("Checklist opcional. Para otra tarea, guarda esta tarjeta y agrega otra checklist en una siguiente edicion.")
                checklist_title = st.text_input("Checklist: titulo", value=str(checklist.get("title") or ""))
                checklist_description = st.text_input("Checklist: descripcion", value=str(checklist.get("description") or ""))
                checklist_link = st.text_input("Checklist: link", value=str(checklist.get("link") or ""))
                image_uploads = st.file_uploader("Adjuntar imagenes", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)
                pdf_uploads = st.file_uploader("Adjuntar PDFs", type=["pdf"], accept_multiple_files=True)
                submitted = st.form_submit_button("Guardar tarjeta", type="primary")
            if submitted:
                checklists = []
                if checklist_title.strip() or checklist_description.strip() or checklist_link.strip():
                    checklists.append({
                        "title": checklist_title.strip() or "Checklist",
                        "description": checklist_description.strip(),
                        "link": checklist_link.strip(),
                        "items": [item for item in [checklist_description.strip(), checklist_link.strip()] if item],
                    })
                images = list(selected_card.get("images") or []) + [_data_url(item) for item in (image_uploads or [])]
                files = list(selected_card.get("files") or []) + [_data_url(item) for item in (pdf_uploads or [])]
                try:
                    _safe_action(config, "/save-card", {
                        "card_id": selected_card_id if editing else "",
                        "list_id": list_options[selected_list],
                        "list_name": selected_list,
                        "title": title,
                        "description": description,
                        "links": [line.strip() for line in links_text.splitlines() if line.strip()],
                        "images": images,
                        "files": files,
                        "checklists": checklists,
                    })
                    st.session_state["server_content_mode"] = "new_card"
                    st.session_state.pop("server_selected_card", None)
                    _rerun_after_success("Tarjeta guardada.")
                except Exception as exc:
                    st.error(str(exc))

    if mode == "archive_list":
        list_id = str(st.session_state.get("server_archive_list_id") or "")
        list_name = str(st.session_state.get("server_archive_list_name") or list_id)
        st.warning(f"Archivar lista: {list_name}")
        confirmation = st.text_input("Escribe ARCHIVAR para confirmar", key="confirm_archive_list_server")
        if st.button("Confirmar archivar lista", type="primary", width="stretch"):
            if confirmation != "ARCHIVAR":
                st.error("Confirmacion incorrecta.")
            else:
                try:
                    _safe_action(config, "/archive-list", {"list_id": list_id, "list_name": list_name})
                    _rerun_after_success("Lista archivada.")
                except Exception as exc:
                    st.error(str(exc))

    if mode == "archive_card":
        card_id = str(st.session_state.get("server_archive_card_id") or "")
        title = str(st.session_state.get("server_archive_card_title") or card_id)
        st.warning(f"Archivar tarjeta: {title}")
        confirmation = st.text_input("Escribe ARCHIVAR para confirmar", key="confirm_archive_card_server")
        if st.button("Confirmar archivar tarjeta", type="primary", width="stretch"):
            if confirmation != "ARCHIVAR":
                st.error("Confirmacion incorrecta.")
            else:
                try:
                    _safe_action(config, "/archive-card", {"card_id": card_id, "card_title": title})
                    _rerun_after_success("Tarjeta archivada.")
                except Exception as exc:
                    st.error(str(exc))


def _render_visibility(config: TrelloConfig) -> None:
    st.subheader("Visibilidad por alumno")
    st.caption("Por defecto todos reciben el contenido. Desmarca alumnos para ocultarlo al sincronizar. Ensayos no se toca.")
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

    search = st.text_input("Buscar alumno", placeholder="Nombre o iniciales", key=f"visibility_search_{selected['content_type']}_{selected['content_id']}")
    query = search.strip().casefold()
    visible_students = [
        item for item in students
        if not query
        or query in str(item.get("student_name") or "").casefold()
        or query in str(item.get("initials") or "").casefold()
        or query in str(item.get("board_name") or "").casefold()
    ]

    left, right = st.columns(2)
    with left:
        if st.button("Mostrar a todos", use_container_width=True):
            for student in students:
                st.session_state[f"vis_{selected['content_type']}_{selected['content_id']}_{student['board_id']}"] = True
            st.rerun()
    with right:
        if st.button("Ocultar a todos", use_container_width=True):
            for student in students:
                st.session_state[f"vis_{selected['content_type']}_{selected['content_id']}_{student['board_id']}"] = False
            st.rerun()

    st.caption(f"Mostrando {len(visible_students)} de {len(students)} alumnos activos.")
    cols = st.columns(4)
    visible_state: dict[str, bool] = {}
    for index, student in enumerate(visible_students):
        board_id = str(student.get("board_id") or "")
        name = str(student.get("student_name") or student.get("board_name") or board_id)
        initials = str(student.get("initials") or "?")
        key = f"vis_{selected['content_type']}_{selected['content_id']}_{board_id}"
        default_value = board_id not in hidden_ids
        if key not in st.session_state:
            st.session_state[key] = default_value
        with cols[index % 4]:
            visible_state[board_id] = st.checkbox(
                f"{initials} - {name}",
                value=bool(st.session_state[key]),
                key=key,
                help=name,
            )

    all_hidden_ids: set[str] = set()
    for student in students:
        board_id = str(student.get("board_id") or "")
        key = f"vis_{selected['content_type']}_{selected['content_id']}_{board_id}"
        if key in st.session_state:
            is_visible = bool(st.session_state[key])
        else:
            is_visible = board_id not in hidden_ids
        if not is_visible:
            all_hidden_ids.add(board_id)

    st.info(f"{len(students) - len(all_hidden_ids)}/{len(students)} alumnos recibiran este contenido.")
    if st.button("Guardar visibilidad", type="primary", use_container_width=True):
        try:
            _safe_action(
                config,
                "/visibility-save",
                {
                    **selected,
                    "students": students,
                    "hidden_student_ids": sorted(all_hidden_ids),
                    "content_title": selected_key,
                },
            )
            _rerun_after_success("Visibilidad guardada. Revisa Sincronizacion > Vista previa para aplicar el cambio en Trello.")
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
            st.write(f"- **{label}** - {action.get('student_name')} - {action.get('list_name')} / {action.get('card_title')}")
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
    with st.expander("Panel servidor seguro", expanded=True):
        tabs = st.tabs(["Administracion", "Contenido", "Visibilidad", "Sincronizacion"])
        with tabs[0]:
            _render_trello_admin(config)
        with tabs[1]:
            _render_content_editor(config)
        with tabs[2]:
            _render_visibility(config)
        with tabs[3]:
            _render_sync(config)
