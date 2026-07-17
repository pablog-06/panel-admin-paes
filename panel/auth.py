from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

import streamlit as st
import streamlit.components.v1 as components

from panel.crypto import load_data_encryption_key


PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 600_000
SESSION_TIMEOUT_SECONDS = 45 * 60
PERSISTENT_SESSION_SECONDS = 45 * 60
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 5 * 60
COOKIE_NAME = "admin_paes_session"


@dataclass(frozen=True)
class AuthUser:
    username: str
    display_name: str


def _b64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{PBKDF2_ALGORITHM}${iterations}${_b64_encode(salt)}${_b64_encode(digest)}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded_hash.split("$", 3)
        if algorithm != PBKDF2_ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = _b64_decode(salt_text)
        expected_digest = _b64_decode(digest_text)
    except (ValueError, TypeError, base64.binascii.Error):
        return False

    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected_digest)


def _plain_dict(value: object) -> dict:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    try:
        return dict(value)
    except (TypeError, ValueError):
        return {}


def load_auth_users() -> dict[str, dict[str, str]]:
    try:
        auth_section = _plain_dict(st.secrets.get("auth", {}))
    except Exception:
        auth_section = {}
    users_section = _plain_dict(auth_section.get("users", {}))
    users: dict[str, dict[str, str]] = {}

    for username, raw_config in users_section.items():
        normalized_username = str(username).strip().lower()
        config = _plain_dict(raw_config)
        password_hash = str(config.get("password_hash", "")).strip()
        if not normalized_username or not password_hash:
            continue
        users[normalized_username] = {
            "name": str(config.get("name") or normalized_username).strip(),
            "password_hash": password_hash,
        }

    return users


def logout() -> None:
    for key in (
        "auth_user",
        "auth_display_name",
        "auth_login_at",
        "auth_last_seen",
        "auth_cookie_value",
    ):
        st.session_state.pop(key, None)


def request_logout() -> None:
    st.session_state["auth_clear_cookie_pending"] = True
    logout()


def _session_signing_key() -> bytes:
    key = load_data_encryption_key()
    if not key:
        raise ValueError("Falta llave local para firmar sesion.")
    return _b64_decode(key)


def create_session_token(username: str) -> str:
    now = int(time.time())
    payload = {
        "u": username.strip().lower(),
        "iat": now,
        "exp": now + PERSISTENT_SESSION_SECONDS,
        "n": secrets.token_urlsafe(16),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_text = _b64_encode(payload_bytes)
    signature = hmac.new(_session_signing_key(), payload_text.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_text}.{_b64_encode(signature)}"


def verify_session_token(token: str) -> str | None:
    try:
        payload_text, signature_text = str(token or "").split(".", 1)
        expected_signature = hmac.new(
            _session_signing_key(),
            payload_text.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_b64_decode(signature_text), expected_signature):
            return None
        payload = json.loads(_b64_decode(payload_text).decode("utf-8"))
        username = str(payload.get("u", "")).strip().lower()
        expires_at = int(payload.get("exp", 0))
    except Exception:
        return None

    if not username or expires_at < int(time.time()):
        return None
    return username


def _cookie_value() -> str:
    try:
        return str(st.context.cookies.get(COOKIE_NAME, "") or "")
    except Exception:
        return ""


def _restore_user_from_cookie() -> bool:
    username = verify_session_token(_cookie_value())
    if not username:
        return False
    users = load_auth_users()
    user_config = users.get(username)
    if not user_config:
        return False
    now = time.time()
    st.session_state["auth_user"] = username
    st.session_state["auth_display_name"] = user_config.get("name") or username
    st.session_state["auth_login_at"] = now
    st.session_state["auth_last_seen"] = now
    st.session_state["auth_cookie_value"] = create_session_token(username)
    return True


def render_auth_cookie_sync() -> None:
    token = str(st.session_state.get("auth_cookie_value", "") or "")
    if not token:
        return
    components.html(
        f"""
        <script>
            document.cookie = "{COOKIE_NAME}={token}; Max-Age={PERSISTENT_SESSION_SECONDS}; Path=/; SameSite=Lax";
        </script>
        """,
        height=0,
    )


def render_auth_cookie_clear() -> None:
    components.html(
        f"""
        <script>
            document.cookie = "{COOKIE_NAME}=; Max-Age=0; Path=/; SameSite=Lax";
            try {{
                const url = new URL(window.top.location.href);
                if (url.searchParams.has("logout")) {{
                    url.searchParams.delete("logout");
                    window.top.history.replaceState(null, "", url.pathname + url.search + url.hash);
                }}
            }} catch (error) {{}}
        </script>
        """,
        height=0,
    )


def logout_requested() -> bool:
    try:
        return str(st.query_params.get("logout", "")) == "1"
    except Exception:
        return False


def _is_session_valid() -> bool:
    username = st.session_state.get("auth_user")
    last_seen = float(st.session_state.get("auth_last_seen", 0) or 0)
    if not username and not _restore_user_from_cookie():
        return False
    username = st.session_state.get("auth_user")
    last_seen = float(st.session_state.get("auth_last_seen", 0) or 0)
    if time.time() - last_seen > SESSION_TIMEOUT_SECONDS:
        logout()
        return False
    st.session_state["auth_last_seen"] = time.time()
    return True


def current_user() -> AuthUser | None:
    if not _is_session_valid():
        return None
    return AuthUser(
        username=str(st.session_state.get("auth_user", "")),
        display_name=str(st.session_state.get("auth_display_name", "")),
    )


def _render_auth_css() -> None:
    st.html(
        """
        <style>
            [data-testid="stAppViewContainer"] {
                background:
                    radial-gradient(circle at 18% 10%, rgba(255,255,255,.96), transparent 28%),
                    radial-gradient(circle at 85% 5%, rgba(32,199,189,.20), transparent 24%),
                    radial-gradient(circle at 58% 92%, rgba(0,122,255,.16), transparent 28%),
                    linear-gradient(135deg, #fbfdff 0%, #f1f8ff 45%, #edfdfb 100%);
                color: #182230;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }

            .auth-hero {
                width: min(520px, calc(100vw - 36px));
                margin: 11vh auto 16px;
                padding: 0 4px;
            }

            .auth-mark {
                width: 42px;
                height: 42px;
                display: grid;
                place-items: center;
                border-radius: 16px;
                color: #0b66c3;
                background: rgba(232,246,255,.92);
                border: 1px solid rgba(179,225,244,.75);
                box-shadow: 0 18px 45px rgba(28,43,61,.08);
                margin-bottom: 16px;
            }

            .auth-hero h1 {
                margin: 0;
                font-size: clamp(30px, 5vw, 44px);
                line-height: 1.04;
                letter-spacing: 0;
                font-weight: 560;
                color: #152333;
            }

            .auth-hero p {
                margin: 10px 0 0;
                color: #607587;
                font-size: 15px;
                line-height: 1.5;
            }

            [data-testid="stForm"] {
                width: min(520px, calc(100vw - 36px));
                margin: 0 auto;
                padding: 24px 24px 22px;
                border-radius: 28px;
                border: 1px solid rgba(255,255,255,.82);
                background: rgba(255,255,255,.72);
                box-shadow: 0 28px 90px rgba(28,43,61,.14);
                backdrop-filter: blur(28px) saturate(160%);
            }

            [data-testid="stTextInput"] label {
                color: #496275;
                font-weight: 520;
            }

            [data-testid="stTextInput"] input {
                border-radius: 16px;
                border: 1px solid rgba(169,214,234,.92);
                background: rgba(255,255,255,.86);
                color: #152333;
            }

            [data-testid="stTextInput"] input:focus {
                border-color: #0a84ff;
                box-shadow: 0 0 0 4px rgba(10,132,255,.12);
            }

            [data-testid="stFormSubmitButton"] button {
                width: 100%;
                min-height: 44px;
                border: 0;
                border-radius: 16px;
                color: white;
                font-weight: 560;
                background: linear-gradient(135deg, #14b8b0, #0a84ff);
                box-shadow: 0 16px 38px rgba(10,132,255,.20);
            }

            [data-testid="stCaptionContainer"] {
                width: min(520px, calc(100vw - 36px));
                margin: 4px auto 0;
                text-align: center;
                color: rgba(64, 91, 108, .58);
                font-size: 12px;
            }

            .auth-help {
                width: min(520px, calc(100vw - 36px));
                margin: 14px auto 0;
                color: #6c8294;
                font-size: 12px;
                line-height: 1.5;
                text-align: center;
            }

            .auth-credit {
                display: block;
                margin-top: 10px;
                color: rgba(64, 91, 108, .58);
                font-size: 12px;
                font-weight: 400;
                letter-spacing: 0;
                text-align: center;
            }

            .developer-credit {
                width: min(520px, calc(100vw - 36px));
                margin: 16px auto 0;
                color: rgba(64, 91, 108, .46);
                font-size: 11px;
                font-weight: 400;
                letter-spacing: 0;
                pointer-events: none;
                text-align: center;
            }

            [data-testid="stAppViewContainer"]::after {
                content: "desarrollado por Pablo Gallardo";
                position: fixed;
                left: 50%;
                bottom: 14px;
                z-index: 2147483000;
                transform: translateX(-50%);
                color: rgba(64, 91, 108, .46);
                font-size: 11px;
                font-weight: 400;
                letter-spacing: 0;
                pointer-events: none;
            }

            .auth-setup {
                width: min(780px, calc(100vw - 36px));
                margin: 9vh auto 18px;
                padding: 24px;
                border-radius: 28px;
                border: 1px solid rgba(255,255,255,.82);
                background: rgba(255,255,255,.76);
                box-shadow: 0 28px 90px rgba(28,43,61,.14);
                backdrop-filter: blur(28px) saturate(160%);
            }

            .auth-setup h1 {
                margin: 0 0 8px;
                font-size: 28px;
                font-weight: 560;
                letter-spacing: 0;
            }

            .auth-setup p,
            .auth-setup li {
                color: #526b80;
                line-height: 1.55;
            }
        </style>
        """
    )


def _render_missing_auth_setup() -> None:
    _render_auth_css()
    st.html(
        """
        <section class="auth-setup">
            <div class="auth-mark">▦</div>
            <h1>Configura dos usuarios administradores</h1>
            <p>
                Por seguridad, el panel no se abre hasta que existan al menos dos usuarios
                en <code>.streamlit/secrets.toml</code> con contraseñas guardadas como hashes.
            </p>
            <ul>
                <li>No se guardan contraseñas en texto plano.</li>
                <li>El archivo real de secretos esta excluido de Git.</li>
                <li>Los intentos fallidos se limitan durante la sesion.</li>
            </ul>
        </section>
        <div class="developer-credit">desarrollado por Pablo Gallardo</div>
        """
    )
    st.code("py scripts\\generate_password_hashes.py admin coordinacion", language="powershell")
    st.caption("Luego copia el bloque TOML generado en `.streamlit/secrets.toml` y reinicia Streamlit.")


def render_login_page(version: str) -> None:
    users = load_auth_users()
    if len(users) < 2:
        _render_missing_auth_setup()
        return

    _render_auth_css()
    st.html(
        f"""
        <section class="auth-hero">
            <div class="auth-mark">▦</div>
            <h1>Panel PAES</h1>
            <p>Acceso privado para administrar el master local y revisar estadisticas agregadas.</p>
        </section>
        """
    )

    now = time.time()
    locked_until = float(st.session_state.get("auth_locked_until", 0) or 0)
    locked_seconds = max(0, int(locked_until - now))

    with st.form("paes_login_form", clear_on_submit=False):
        username = st.text_input("Usuario")
        password = st.text_input("Clave", type="password")
        submitted = st.form_submit_button("Entrar al panel")

    st.html(
        f"""
        <div class="auth-help">
            Sesion expira tras 45 minutos de inactividad. Version {version}.
        </div>
        """
    )

    if locked_seconds > 0:
        st.error(f"Demasiados intentos fallidos. Vuelve a intentar en {locked_seconds} segundos.")
        return

    if not submitted:
        return

    normalized_username = username.strip().lower()
    user_config = users.get(normalized_username)
    password_hash = user_config.get("password_hash", "") if user_config else ""

    if user_config and verify_password(password, password_hash):
        st.session_state["auth_user"] = normalized_username
        st.session_state["auth_display_name"] = user_config.get("name") or normalized_username
        st.session_state["auth_login_at"] = now
        st.session_state["auth_last_seen"] = now
        st.session_state["auth_cookie_value"] = create_session_token(normalized_username)
        st.session_state["auth_failed_attempts"] = 0
        st.session_state["auth_locked_until"] = 0
        st.rerun()

    failed_attempts = int(st.session_state.get("auth_failed_attempts", 0) or 0) + 1
    st.session_state["auth_failed_attempts"] = failed_attempts
    if failed_attempts >= MAX_FAILED_ATTEMPTS:
        st.session_state["auth_locked_until"] = now + LOCKOUT_SECONDS
    st.error("Usuario o contraseña incorrectos.")


def require_login(version: str) -> AuthUser | None:
    if logout_requested():
        request_logout()
        render_auth_cookie_clear()
        render_login_page(version)
        return None

    if st.session_state.pop("auth_clear_cookie_pending", False):
        render_auth_cookie_clear()
        render_login_page(version)
        return None

    user = current_user()
    if user:
        render_auth_cookie_sync()
        return user
    render_login_page(version)
    return None


def render_session_sidebar(user: AuthUser) -> None:
    with st.sidebar:
        st.caption("Panel PAES")
        st.write(f"Sesion: {user.display_name}")
        if st.button("Cerrar sesion", use_container_width=True):
            request_logout()
            st.rerun()


def render_logout_button(user: AuthUser) -> None:
    st.html(
        """
        <style>
            .admin-paes-logout-strip {
                position: fixed;
                top: 14px;
                right: 18px;
                z-index: 2147482500;
                pointer-events: none;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }

            .admin-paes-logout-strip span {
                display: inline-flex;
                align-items: center;
                min-height: 38px;
                padding: 0 14px;
                border-radius: 999px;
                border: 1px solid rgba(169,214,234,.82);
                color: #416176;
                background: rgba(255,255,255,.72);
                box-shadow: 0 16px 36px rgba(28,43,61,.08);
                backdrop-filter: blur(22px) saturate(150%);
                font-size: 12px;
            }

            div[data-testid="stButton"]:has(button[kind="secondary"]) {
                position: fixed;
                top: 14px;
                right: 18px;
                z-index: 2147482600;
            }

            div[data-testid="stButton"]:has(button[kind="secondary"]) button {
                min-height: 38px;
                border-radius: 999px;
                border: 1px solid rgba(169,214,234,.82);
                color: #0b5d95;
                background: rgba(255,255,255,.78);
                box-shadow: 0 16px 36px rgba(28,43,61,.08);
                backdrop-filter: blur(22px) saturate(150%);
                font-weight: 520;
            }
        </style>
        """
    )
    if st.button("Cerrar sesion", key="logout_panel_top", type="secondary"):
        request_logout()
        st.rerun()
