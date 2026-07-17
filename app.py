from __future__ import annotations

import os
import time

import streamlit as st

import panel.admin_actions as _admin_actions
import panel.auth as _auth
import panel.assets_cache as _assets_cache
import panel.icons as _icons
import panel.local_api as _local_api
import panel.master_import as _master_import
import panel.renderer as _renderer
import panel.results_db as _results_db
import panel.security_gate as _security_gate
import panel.student_sync as _student_sync
import panel.streamlit_shell as _streamlit_shell
import panel.trello_client as _trello_client


from panel.admin_actions import execute_admin_action
from panel.audit import write_audit_log
from panel.auth import require_login
from panel.local_api import ensure_local_api
from panel.master_import import bootstrap_master_if_empty
from panel.renderer import build_html_document
from panel.results_db import (
    build_results_panel,
    ensure_master_defaults,
    initialize_database,
    load_master_board,
    migrate_queued_content_to_master,
)
from panel.security_gate import require_local_encryption
from panel.streamlit_shell import configure_page, hide_streamlit_chrome, render_component, render_loading_screen
from panel.trello_client import TrelloConfig


APP_VERSION = "v-etapa6-sync-count-load-2"
LOCAL_API_PORT = 8771


def _secret_or_env(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(name, "")).strip()


def _bool_secret_or_env(name: str, default: bool = False) -> bool:
    value = _secret_or_env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on", "si"}


def trello_config() -> TrelloConfig:
    return TrelloConfig(
        api_key=_secret_or_env("TRELLO_API_KEY"),
        token=_secret_or_env("TRELLO_TOKEN"),
        board_name="",
        board_id="",
    )


def clear_board_cache() -> None:
    return None


@st.cache_data(ttl=60, show_spinner=False)
def load_local_master_board(cache_version: str) -> list[dict]:
    return load_master_board()


def main() -> None:
    configure_page()
    hide_streamlit_chrome()
    config = trello_config()
    disable_local_api = _bool_secret_or_env("DISABLE_LOCAL_API", False)
    if config.is_complete and not disable_local_api:
        ensure_local_api(config, port=LOCAL_API_PORT)
    user = require_login(APP_VERSION)
    if not user:
        return
    if not require_local_encryption(APP_VERSION):
        return
    show_initial_loading = st.session_state.get("paes_board_ready_version") != APP_VERSION
    loading = st.empty() if show_initial_loading else None
    loading_started_at = time.perf_counter()
    if loading is not None:
        with loading:
            render_loading_screen(APP_VERSION)
    try:
        initialize_database()
        ensure_master_defaults()
        migrate_queued_content_to_master()
        import_summary = bootstrap_master_if_empty(config)
        board_title = "Panel PAES"
        board_lists = [build_results_panel(), *load_master_board()]
        component_action_mode = bool(disable_local_api and config.is_complete)
        read_only = False if component_action_mode else bool(disable_local_api)
        subtitle = "Fuente maestra local SQLite - edicion server-side"
        if import_summary.get("status") == "imported":
            subtitle = (
                f"{subtitle} - contenido base importado desde "
                f"{import_summary.get('source_student', 'PAES')}"
            )
        trello_api_base = ""
        trello_api_token = ""

        if component_action_mode:
            trello_api_base = "__STREAMLIT_COMPONENT__"
            trello_api_token = ""
        elif config.is_complete and not disable_local_api:
            local_api_endpoint = ensure_local_api(config, port=LOCAL_API_PORT)
            trello_api_base, _, trello_api_token = local_api_endpoint.partition("|")
        else:
            st.warning(
                "El panel local esta disponible, pero faltan variables: "
                "`TRELLO_API_KEY` y `TRELLO_TOKEN`. "
                "La sincronizacion con boards PAES se activara al configurarlas."
            )
            st.caption("No se hace ninguna llamada a Trello sin credenciales.")
    except Exception:
        if loading is not None:
            loading.empty()
        raise

    if loading is not None:
        loading.empty()
        st.session_state["paes_board_ready_version"] = APP_VERSION
    visual_action_results = st.session_state.setdefault("visual_action_results", {})
    if component_action_mode:
        try:
            visual_action_results["/admin-dashboard"] = {
                "ok": True,
                "result": execute_admin_action("/admin-dashboard", {"refresh": False, "limit": 80}, config),
            }
        except Exception as exc:
            visual_action_results["/admin-dashboard"] = {"ok": False, "error": str(exc)}
    html_document = build_html_document(
        board_lists,
        board_title=board_title,
        subtitle=subtitle,
        read_only=read_only,
        version=APP_VERSION,
        trello_api_base=trello_api_base,
        trello_api_token=trello_api_token,
        component_state=visual_action_results,
    )
    component_result = render_component(
        html_document,
        version=APP_VERSION,
        action_mode=component_action_mode,
        component_state=visual_action_results,
        reload_key=int(st.session_state.get("visual_reload_key", 0)),
        state_rev=int(st.session_state.get("visual_state_rev", 0)),
    )
    action = getattr(component_result, "action", None) if component_result is not None else None
    if component_action_mode and isinstance(action, dict):
        action_id = str(action.get("id") or "")
        path = str(action.get("path") or "")
        payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
        if action_id and path and st.session_state.get("last_visual_action_id") != action_id:
            st.session_state["last_visual_action_id"] = action_id
            ui_state = action.get("ui_state") if isinstance(action.get("ui_state"), dict) else {}
            board_mutation_paths = {"/create-list", "/save-card", "/move-list", "/move-card", "/archive-list", "/archive-card"}
            if ui_state:
                visual_action_results["__ui_state"] = ui_state
            elif path in board_mutation_paths:
                visual_action_results.pop("__ui_state", None)
            try:
                if path == "/ui-state":
                    screen = str(payload.get("screen") or "").strip()
                    if screen in {"sync", "admin", "visibility"}:
                        visual_action_results["__ui_state"] = {"screen": screen}
                    else:
                        visual_action_results.pop("__ui_state", None)
                    result = {"screen": screen or "board"}
                    visual_action_results[path] = {"ok": True, "result": result}
                elif path == "/sync-preview-students":
                    visual_action_results.pop("/sync-start-students", None)
                    visual_action_results.pop("/sync-status", None)
                    visual_action_results.pop("/sync-apply-students", None)
                    result = execute_admin_action(path, payload, config)
                    visual_action_results[path] = {"ok": True, "result": result}
                elif path == "/sync-start-students":
                    visual_action_results.pop("/sync-status", None)
                    visual_action_results.pop("/sync-apply-students", None)
                    result = execute_admin_action(path, payload, config)
                    visual_action_results[path] = {"ok": True, "result": result}
                else:
                    result = execute_admin_action(path, payload, config)
                    visual_action_results[path] = {"ok": True, "result": result}
                if path in board_mutation_paths | {"/visibility-save"}:
                    visual_action_results.pop("/sync-preview-students", None)
                    visual_action_results.pop("/sync-start-students", None)
                    visual_action_results.pop("/sync-status", None)
                    visual_action_results.pop("/sync-apply-students", None)
                    if path in board_mutation_paths:
                        visual_action_results.pop("__ui_state", None)
                if path in board_mutation_paths:
                    st.session_state["visual_reload_key"] = int(st.session_state.get("visual_reload_key", 0)) + 1
            except Exception as exc:
                visual_action_results[path] = {"ok": False, "error": str(exc)}
                st.session_state["last_visual_action_error"] = str(exc)
            finally:
                st.session_state["visual_state_rev"] = int(st.session_state.get("visual_state_rev", 0)) + 1
                visual_action_results["__state_rev"] = int(st.session_state["visual_state_rev"])
                visual_action_results["__last_action"] = {"path": path, "id": action_id, "rev": int(st.session_state["visual_state_rev"])}
            st.rerun()


if __name__ == "__main__":
    main()
