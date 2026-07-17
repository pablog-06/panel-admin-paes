from __future__ import annotations

import streamlit as st

from panel.crypto import DATA_ENCRYPTION_KEY_NAME, encryption_status


def require_local_encryption(version: str) -> bool:
    ready, message = encryption_status()
    if ready:
        return True

    st.html(
        f"""
        <style>
            .security-setup {{
                width: min(760px, calc(100vw - 36px));
                margin: 10vh auto 16px;
                padding: 26px;
                border-radius: 28px;
                border: 1px solid rgba(255,255,255,.82);
                background: rgba(255,255,255,.76);
                box-shadow: 0 28px 90px rgba(28,43,61,.14);
                backdrop-filter: blur(28px) saturate(160%);
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }}

            .security-setup h1 {{
                margin: 0 0 10px;
                color: #152333;
                font-size: 28px;
                font-weight: 560;
                letter-spacing: 0;
            }}

            .security-setup p,
            .security-setup li {{
                color: #526b80;
                line-height: 1.55;
            }}
        </style>
        <section class="security-setup">
            <h1>Cifrado local requerido</h1>
            <p>
                Para proteger logs y backups, el panel exige una llave local antes de cargar Trello.
            </p>
            <ul>
                <li>Estado: {message}</li>
                <li>Los nuevos logs se guardaran como <code>activity.jsonl.enc</code>.</li>
                <li>Los nuevos backups se guardaran como archivos <code>.enc</code>.</li>
            </ul>
            <p>Version {version}</p>
        </section>
        """
    )
    st.code("py -m pip install -r requirements.txt", language="powershell")
    st.code("py scripts\\generate_encryption_key.py", language="powershell")
    st.caption(f"Copia la linea `{DATA_ENCRYPTION_KEY_NAME} = \"...\"` en `.streamlit/secrets.toml` y reinicia Streamlit.")
    return False
