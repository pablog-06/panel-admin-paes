from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components


BOARD_ACTION_COMPONENT_JS = r"""
export default function(component) {
    const { data, setTriggerValue, parentElement } = component;
    let frame = parentElement.querySelector('#paes-board-action-frame');
    if (!frame) {
        frame = document.createElement('iframe');
        frame.id = 'paes-board-action-frame';
        frame.title = 'Panel PAES';
        frame.style.width = '100%';
        frame.style.height = '1080px';
        frame.style.border = '0';
        frame.style.display = 'block';
        frame.setAttribute('sandbox', 'allow-scripts allow-forms allow-popups allow-downloads allow-modals allow-same-origin');
        parentElement.appendChild(frame);
    }

    const html = data?.html || '';
    const version = data?.version || '';
    const marker = `${version}:${data?.reload_key || 0}`;
    if (frame.dataset.marker !== marker) {
        frame.dataset.marker = marker;
        frame.srcdoc = html;
    }

    const sendState = () => {
        if (!frame.contentWindow) return;
        frame.contentWindow.postMessage({
            source: 'admin-paes-component-state',
            state: data?.state || {},
        }, '*');
    };
    if (frame.contentWindow) {
        window.setTimeout(sendState, 80);
        window.setTimeout(sendState, 350);
    }

    const handler = (event) => {
        if (event.source !== frame.contentWindow) return;
        const message = event.data || {};
        if (message.source !== 'admin-paes-component-action') return;
        setTriggerValue('action', message.action || {});
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
}
"""


_board_action_component = st.components.v2.component(
    "paes_visual_board_actions",
    html='<div id="paes-board-action-root"></div>',
    js=BOARD_ACTION_COMPONENT_JS,
    isolate_styles=False,
)


def configure_page() -> None:
    st.set_page_config(
        page_title="Panel PAES",
        page_icon=":material/dashboard:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )


def hide_streamlit_chrome() -> None:
    st.html(
        """
        <style>
            [data-testid="stHeader"],
            #MainMenu,
            footer {
                display: none;
            }

            [data-testid="stAppViewContainer"] {
                background:
                    radial-gradient(circle at 18% 10%, rgba(255,255,255,.96), transparent 28%),
                    radial-gradient(circle at 85% 5%, rgba(32,199,189,.20), transparent 24%),
                    radial-gradient(circle at 58% 92%, rgba(0,122,255,.16), transparent 28%),
                    linear-gradient(135deg, #fbfdff 0%, #f1f8ff 45%, #edfdfb 100%);
            }

            [data-testid="stMain"] .block-container {
                max-width: 100%;
                padding: 0;
            }

            iframe {
                display: block;
            }
        </style>
        """
    )


def render_loading_screen(version: str) -> None:
    st.html(
        f"""
        <style>
            #paes-loading-screen {{
                position: fixed;
                inset: 0;
                z-index: 2147483000;
                display: grid;
                place-items: center;
                background:
                    radial-gradient(circle at 18% 10%, rgba(255,255,255,.96), transparent 28%),
                    radial-gradient(circle at 85% 5%, rgba(32,199,189,.20), transparent 24%),
                    radial-gradient(circle at 58% 92%, rgba(0,122,255,.16), transparent 28%),
                    linear-gradient(135deg, #fbfdff 0%, #f1f8ff 45%, #edfdfb 100%);
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }}

            .paes-loading-card {{
                width: min(420px, calc(100vw - 40px));
                padding: 26px;
                border: 1px solid rgba(255,255,255,.82);
                border-radius: 26px;
                background: rgba(255,255,255,.72);
                box-shadow: 0 28px 90px rgba(28,43,61,.14);
                backdrop-filter: blur(28px) saturate(160%);
            }}

            .paes-loading-mark {{
                width: 38px;
                height: 38px;
                display: grid;
                place-items: center;
                border-radius: 14px;
                color: #0b66c3;
                background: rgba(232,246,255,.92);
                margin-bottom: 14px;
            }}

            .paes-loading-card h1 {{
                margin: 0;
                color: #182230;
                font-size: 20px;
                font-weight: 560;
                letter-spacing: 0;
            }}

            .paes-loading-card p {{
                margin: 8px 0 18px;
                color: #607587;
                font-size: 13px;
                line-height: 1.45;
            }}

            .paes-loading-bar {{
                position: relative;
                height: 7px;
                overflow: hidden;
                border-radius: 999px;
                background: rgba(210,230,242,.88);
            }}

            .paes-loading-bar::after {{
                content: "";
                position: absolute;
                inset: 0;
                width: 42%;
                border-radius: inherit;
                background: linear-gradient(90deg, #35c5bd, #0a84ff);
                animation: paes-loading-slide 1.25s ease-in-out infinite;
            }}

            .paes-loading-version {{
                margin-top: 12px;
                color: #7b91a2;
                font-size: 11px;
            }}

            @keyframes paes-loading-slide {{
                0% {{ transform: translateX(-110%); }}
                50% {{ transform: translateX(80%); }}
                100% {{ transform: translateX(250%); }}
            }}
        </style>
        <div id="paes-loading-screen">
            <section class="paes-loading-card">
                <div class="paes-loading-mark">▦</div>
                <h1>Cargando panel PAES</h1>
                <p>Preparando tablero maestro, historial y resultados locales. La sincronizacion pesada se ejecuta despues de mostrar la interfaz.</p>
                <div class="paes-loading-bar"></div>
                <div class="paes-loading-version">{version}</div>
            </section>
        </div>
        """
    )


def render_component(
    html_document: str,
    version: str = "v-etapa3-no-parent-nav-1",
    *,
    action_mode: bool = False,
    component_state: dict | None = None,
    reload_key: int = 0,
):
    if action_mode:
        return _board_action_component(
            data={
                "html": html_document,
                "version": version,
                "state": component_state or {},
                "reload_key": reload_key,
            },
            key="paes-visual-board-actions",
            on_action_change=lambda: None,
            height=1080,
        )

    components.html(
        html_document,
        height=1080,
        scrolling=False,
    )
    return None
