from __future__ import annotations

from typing import Any

import streamlit as st


_BRIDGE_HTML = """<div id=\"bridge-root\"></div>"""

_BRIDGE_JS = r"""
export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector("#bridge-root");
  if (!root) return;

  const html = String((data && data.html) || "");
  const height = Number((data && data.height) || 1080);

  function bridgeScript() {
    return `
      <script>
        (function () {
          const originalFetch = window.fetch.bind(window);
          function bridgeResponse(path, payload) {
            const action = {
              id: Date.now().toString(36) + Math.random().toString(36).slice(2),
              path: path,
              payload: payload || {}
            };
            window.parent.postMessage({ type: "admin-paes-action", action }, "*");
            const result = fakeResult(path, payload || {});
            return Promise.resolve({
              ok: true,
              status: 200,
              json: () => Promise.resolve({ ok: true, result })
            });
          }
          function fakeResult(path, payload) {
            if (path === "/create-list") {
              return { id: "pending-list-" + Date.now(), name: payload.name || "Lista", pos: Date.now() };
            }
            if (path === "/save-card") {
              return { card_id: payload.card_id || payload.id || ("pending-card-" + Date.now()) };
            }
            if (path === "/student-boards") return { students: [] };
            if (path === "/visibility-get") return { hidden_student_ids: [] };
            if (path === "/sync-preview-students") return { students: 0, actions: [], errors: [], summary: {} };
            if (path === "/sync-start-students") return { job_id: "server-panel-required", status: "queued" };
            if (path === "/sync-status") return { status: "done", note: "Usa Panel servidor seguro > Sincronizacion para progreso real." };
            return {};
          }
          window.fetch = function(url, options) {
            const raw = String(url || "");
            if (raw.startsWith("streamlit-bridge")) {
              let path = raw.replace(/^streamlit-bridge/, "") || "/";
              if (!path.startsWith("/")) path = "/" + path;
              let payload = {};
              try { payload = JSON.parse((options && options.body) || "{}"); } catch (error) { payload = {}; }
              return bridgeResponse(path, payload);
            }
            return originalFetch(url, options);
          };
        })();
      <\/script>
    `;
  }

  const iframe = document.createElement("iframe");
  iframe.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms allow-popups allow-downloads allow-modals");
  iframe.style.display = "block";
  iframe.style.width = "100%";
  iframe.style.height = `${height}px`;
  iframe.style.border = "0";
  iframe.srcdoc = html.replace("<head>", "<head>" + bridgeScript());
  root.innerHTML = "";
  root.appendChild(iframe);

  function onMessage(event) {
    const message = event.data || {};
    if (message.type === "admin-paes-action" && message.action) {
      setTriggerValue("action", message.action);
    }
  }

  window.addEventListener("message", onMessage);
  return () => window.removeEventListener("message", onMessage);
}
"""

_BRIDGE_COMPONENT = st.components.v2.component(
    "admin_paes_bridge_v2",
    html=_BRIDGE_HTML,
    js=_BRIDGE_JS,
    isolate_styles=True,
)


def render_bridge_component(html_document: str, *, height: int = 1080, key: str = "admin_paes_bridge") -> dict[str, Any] | None:
    result = _BRIDGE_COMPONENT(
        key=key,
        data={"html": html_document, "height": height},
        height=height,
        on_action_change=lambda: None,
    )
    action = getattr(result, "action", None)
    return action if isinstance(action, dict) else None
