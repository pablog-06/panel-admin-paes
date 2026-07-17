from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).with_name("bridge_frontend")
_bridge_component = components.declare_component("admin_paes_bridge", path=str(_COMPONENT_DIR))


def render_bridge_component(html_document: str, *, height: int = 1080, key: str = "admin_paes_bridge") -> dict[str, Any] | None:
    value = _bridge_component(html=html_document, height=height, key=key, default=None)
    return value if isinstance(value, dict) else None
