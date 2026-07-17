from __future__ import annotations

import importlib
import os

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
import panel.server_admin as _server_admin
import panel.student_sync as _student_sync
import panel.streamlit_shell as _streamlit_shell
import panel.trello_client as _trello_client

_admin_actions = importlib.reload(_admin_actions)
_auth = importlib.reload(_auth)
_assets_cache = importlib.reload(_assets_cache)
_icons = importlib.reload(_icons)
_results_db = importlib.reload(_results_db)
_trello_client = importlib.reload(_trello_client)
_student_sync = importlib.reload(_student_sync)
_local_api = importlib.reload(_local_api)
_master_import = importlib.reload(_master_import)
_renderer = importlib.reload(_renderer)
_security_gate = importlib.reload(_security_gate)
_server_admin = importlib.reload(_server_admin)
_streamlit_shell = importlib.reload(_streamlit_shell)

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
from panel.server_admin import render_server_admin_panel
from panel.streamlit_shell import configure_page, hide_streamlit_chrome, render_component, render_loading_screen
from panel.trello_client import TrelloConfig


APP_VERSION = "v-etapa6-server-only-1"
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
    return value.lower() in {"1", "true", "yes", "on", "si", "sÃ­"}


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
    server_admin_enabled = _bool_secret_or_env("SERVER_ADMIN_NATIVE", True)
    if config.is_complete and not disable_local_api:
        ensure_local_api(config, port=LOCAL_API_PORT)
    user = require_login(APP_VERSION)
    if not user:
        return
    if not require_local_encryption(APP_VERSION):
        return
    loading = st.empty()
    with loading:
        render_loading_screen(APP_VERSION)
    try:
        initialize_database()
        ensure_master_defaults()
        migrate_queued_content_to_master()
        import_summary = bootstrap_master_if_empty(config)
        board_title = "Panel PAES"
        board_lists = [build_results_panel(), *load_master_board()]
        read_only = bool(disable_local_api)
        subtitle = "Fuente maestra local SQLite - edicion server-side"
        if import_summary.get("status") == "imported":
            subtitle = (
                f"{subtitle} - contenido base importado desde "
                f"{import_summary.get('source_student', 'PAES')}"
            )
        trello_api_base = ""
        trello_api_token = ""

        if config.is_complete and not disable_local_api:
            local_api_endpoint = ensure_local_api(config, port=LOCAL_API_PORT)
            trello_api_base, _, trello_api_token = local_api_endpoint.partition("|")
        elif config.is_complete and disable_local_api:
            st.info(
                "Modo seguro VM activo: la edicion real se realiza solo desde el panel "
                "servidor seguro. El tablero visual inferior queda en modo lectura para "
                "evitar acciones no persistentes."
            )
        else:
            st.warning(
                "El panel local esta disponible, pero faltan variables: "
                "`TRELLO_API_KEY` y `TRELLO_TOKEN`. "
                "La sincronizacion con boards PAES se activara al configurarlas."
            )
            st.caption("No se hace ninguna llamada a Trello sin credenciales.")
    except Exception:
        loading.empty()
        raise

    loading.empty()
    render_server_admin_panel(config, enabled=server_admin_enabled)
    html_document = build_html_document(
        board_lists,
        board_title=board_title,
        subtitle=subtitle,
        read_only=read_only,
        version=APP_VERSION,
        trello_api_base=trello_api_base,
        trello_api_token=trello_api_token,
    )
    render_component(html_document, version=APP_VERSION)


if __name__ == "__main__":
    main()

