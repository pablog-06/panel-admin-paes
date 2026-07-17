from __future__ import annotations

import html
import json
from typing import Any

from panel.icons import icon


def escape_text(value: Any) -> str:
    return html.escape(str(value), quote=True)

def render_average_chart(points: list[dict[str, Any]]) -> str:
    width = 282
    height = 178
    left = 44
    right = 14
    top = 22
    bottom = 32
    y_min = 650
    y_max = 1000
    chart_width = width - left - right
    chart_height = height - top - bottom

    if not points:
        return """
            <div class="average-chart" data-chart="average-series">
                <div class="chart-title">Mediana por ensayo</div>
                <div class="chart-empty">Sin datos suficientes para graficar.</div>
            </div>
        """

    exams = [int(point["exam"]) for point in points]
    min_exam = min(exams)
    max_exam = max(exams)
    exam_span = max(1, max_exam - min_exam)

    def x_for(exam: int) -> float:
        return left + ((exam - min_exam) / exam_span) * chart_width

    def y_for(score: int) -> float:
        score = max(y_min, min(y_max, int(score)))
        return top + ((y_max - score) / (y_max - y_min)) * chart_height

    polyline = " ".join(
        f"{x_for(int(point['exam'])):.1f},{y_for(int(point['median'])):.1f}"
        for point in points
    )
    circles = "\n".join(
        f"""
        <circle cx="{x_for(int(point['exam'])):.1f}" cy="{y_for(int(point['median'])):.1f}" r="3.8">
            <title>Ensayo {escape_text(point['exam'])}: mediana {escape_text(point['median'])} ({escape_text(point['count'])} estudiantes)</title>
        </circle>
        """
        for point in points
    )
    x_labels = "\n".join(
        f'<text x="{x_for(int(point["exam"])):.1f}" y="{height - 8}" text-anchor="middle">{escape_text(point["exam"])}</text>'
        for point in points
    )
    y_ticks = [650, 800, 1000]
    y_grid = "\n".join(
        f"""
        <line x1="{left}" x2="{width - right}" y1="{y_for(tick):.1f}" y2="{y_for(tick):.1f}" />
        <text x="{left - 8}" y="{y_for(tick) + 3:.1f}" text-anchor="end">{tick}</text>
        """
        for tick in y_ticks
    )

    return f"""
        <div class="average-chart" data-chart="average-series" data-series="{escape_text(json.dumps(points, ensure_ascii=True))}">
            <div class="chart-title">Mediana por ensayo</div>
            <svg viewBox="0 0 {width} {height}" role="img" aria-label="Grafico mediana de puntajes por ensayo">
                <g class="chart-grid">{y_grid}</g>
                <g class="chart-axis">
                    <line x1="{left}" x2="{width - right}" y1="{height - bottom}" y2="{height - bottom}" />
                    <line x1="{left}" x2="{left}" y1="{top}" y2="{height - bottom}" />
                </g>
                <polyline class="chart-line" points="{polyline}" />
                <g class="chart-points">{circles}</g>
                <g class="chart-x-labels">{x_labels}</g>
                <text class="chart-y-title" x="{left}" y="10" text-anchor="middle">Puntaje</text>
                <text class="chart-x-title" x="{left + chart_width / 2:.1f}" y="{height - 1}" text-anchor="middle">Ensayo</text>
            </svg>
        </div>
    """

def render_stats_panel(board_list: dict[str, Any]) -> str:
    stats = board_list["stats"]
    minimum = stats["min"]
    maximum = stats["max"]
    average_chart = render_average_chart(board_list.get("median_series", []))
    return f"""
        <div class="stats-panel">
            <div class="panel-label">{icon("lock")} Agregado protegido</div>
            <h3 data-stat="exam">{escape_text(stats["exam"])}</h3>
            <div class="stats-grid compact">
                <div><span>Promedio</span><strong data-stat="average">{escape_text(stats["average"])}</strong></div>
                <div><span>Mediana</span><strong data-stat="median">{escape_text(stats["median"])}</strong></div>
                <div><span>Desv. est.</span><strong data-stat="stddev">{escape_text(stats["stddev"])}</strong></div>
            </div>
            <div class="range-grid">
                <div>
                    <span>Minimo</span>
                    <strong data-stat="min-score">{escape_text(minimum["score"])}</strong>
                    <small data-stat="min-student">{escape_text(minimum["student"])}</small>
                </div>
                <div>
                    <span>Maximo</span>
                    <strong data-stat="max-score">{escape_text(maximum["score"])}</strong>
                    <small data-stat="max-student">{escape_text(maximum["student"])}</small>
                </div>
            </div>
            {average_chart}
            <p data-stat="note">{escape_text(board_list["note"])}</p>
        </div>
    """


def render_card(card: dict[str, Any], read_only: bool = False) -> str:
    title = escape_text(card["title"])
    description = escape_text(card.get("description", ""))
    card_id = escape_text(card["id"])
    link_count = len(card.get("links", []))
    image_count = len(card.get("images", []))
    checklist_count = len(card.get("checklists", []))
    description_html = f"<p>{description}</p>" if description else ""
    detected_count = len(card.get("detected_from_students", []))
    detected_note = (
        f'<div class="card-label detected-label">{icon("users")} Detectado en {detected_count} alumno{"s" if detected_count != 1 else ""}</div>'
        if card.get("detected")
        else ""
    )
    badges = []

    if link_count:
        badges.append(f'<span>{icon("link")}{link_count}</span>')
    if image_count:
        badges.append(f'<span>{icon("image")}{image_count}</span>')
    if checklist_count:
        badges.append(f'<span>{icon("check")}{checklist_count}</span>')

    badges_html = f'<div class="card-badges">{"".join(badges)}</div>' if badges else ""
    edit_button = (
        ""
        if read_only
        else f"""
                <button class="tertiary-button edit-card" type="button" data-card-id="{card_id}">
                    {icon("edit")} Editar
                </button>
        """
    )
    delete_button = (
        ""
        if read_only
        else f"""
                <button class="tertiary-button delete-card" type="button" data-card-id="{card_id}">
                    {icon("trash")} {"Ocultar" if card.get("detected") else "Eliminar"}
                </button>
        """
    )
    visibility_button = (
        ""
        if read_only
        else f"""
                <button class="tertiary-button visibility-card" type="button" data-card-id="{card_id}" data-card-title="{title}">
                    {icon("users")} Alumnos
                </button>
        """
    )
    source_button = (
        f"""
                <a class="tertiary-button" href="{escape_text(card.get("source_url", ""))}" target="_blank" rel="noopener noreferrer">
                    {icon("link")} Trello
                </a>
        """
        if read_only and card.get("source_url")
        else ""
    )

    return f"""
        <article class="card" data-card-id="{card_id}">
            <div class="card-body">
                <div class="card-label">{icon("card")} {"Trello solo lectura" if read_only else "Material comun"}</div>
                {detected_note}
                <h3>{title}</h3>
                {description_html}
                {badges_html}
                <div class="card-actions">
                    <button class="tertiary-button preview-card" type="button" data-card-id="{card_id}">
                        {icon("view")} Preview
                    </button>
                    {source_button}
                    {edit_button}
                    {visibility_button}
                    {delete_button}
                </div>
            </div>
        </article>
    """


def render_list(board_list: dict[str, Any], read_only: bool = False) -> str:
    name = escape_text(board_list["name"])
    list_id = escape_text(board_list["id"])
    is_locked = board_list.get("kind") == "locked"
    locked_class = " is-locked" if is_locked else ""
    card_count = len(board_list.get("cards", []))
    detected_count = len(board_list.get("detected_from_students", []))
    count = "solo lectura" if is_locked else f"{card_count} {'tarjeta' if card_count == 1 else 'tarjetas'}"
    if board_list.get("detected"):
        count = f"{count} - detectada en {detected_count} alumno{'s' if detected_count != 1 else ''}"
    stats_panel = render_stats_panel(board_list) if is_locked else ""
    cards_html = "".join(render_card(card, read_only=read_only) for card in board_list.get("cards", []))
    empty_state = (
        ""
        if is_locked
        else '<div class="empty-state">Sin tarjetas. Agrega material comun para la plantilla.</div>'
    )
    close_button = (
        ""
        if is_locked or read_only
        else f"""
            <button class="icon-button close-list" type="button" data-list-id="{list_id}" aria-label="Cerrar lista {name}">
                {icon("close")}
            </button>
        """
    )
    visibility_button = (
        ""
        if is_locked or read_only
        else f"""
            <button class="icon-button visibility-list" type="button" data-list-id="{list_id}" data-list-title="{name}" aria-label="Filtrar alumnos para lista {name}">
                {icon("users")}
            </button>
        """
    )
    drag_handle = (
        ""
        if is_locked or read_only
        else f'<span class="list-drag-handle" title="Arrastrar lista">{icon("grip")}</span>'
    )
    add_button = (
        ""
        if is_locked or read_only
        else f"""
            <button class="add-card-button" type="button" data-list-id="{list_id}">
                {icon("add")} Nueva tarjeta
            </button>
        """
    )

    return f"""
        <section class="board-list{locked_class}" data-list-id="{list_id}">
            <header class="list-header">
                <div class="list-title-group">
                    {drag_handle}
                    <div>
                        <h2>{name}</h2>
                        <span class="list-count">{escape_text(count)}</span>
                    </div>
                </div>
                {visibility_button}
                {close_button}
            </header>
            {stats_panel}
            <div class="card-stack">
                {cards_html}
                {empty_state}
            </div>
            {add_button}
        </section>
    """


def build_html_document(
    lists: list[dict[str, Any]],
    *,
    board_title: str = "Panel PAES",
    subtitle: str = "Constructor visual de material comun",
    read_only: bool = False,
    version: str = "v-etapa2-readonly-1",
    trello_api_base: str = "",
    trello_api_token: str = "",
    component_state: dict[str, Any] | None = None,
) -> str:
    data_json = json.dumps(lists, ensure_ascii=True)
    component_state_json = json.dumps(component_state or {}, ensure_ascii=True)
    lists_html = "".join(render_list(board_list, read_only=read_only) for board_list in lists)
    readonly_class = " is-read-only" if read_only else ""
    trello_class = " is-trello-edit" if trello_api_base else ""
    add_list_button = (
        ""
        if read_only
        else '<button class="secondary-button add-list" type="button" id="add-list-board">__ICON_ADD__Nueva lista</button>'
    )
    document = """
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
    :root {
        --text: #17202a;
        --secondary: #65707c;
        --tertiary: #8b97a3;
        --line: rgba(60, 72, 88, .11);
        --surface: rgba(255, 255, 255, .76);
        --surface-strong: rgba(255, 255, 255, .92);
        --blue: #007aff;
        --blue-soft: #e9f4ff;
        --cyan: #20c7bd;
        --danger: #d92d20;
        --shadow: 0 18px 50px rgba(28, 43, 61, .10);
        --radius-lg: 22px;
        --radius-md: 16px;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
    }

    * {
        box-sizing: border-box;
    }

    html,
    body {
        width: 100%;
        height: 100%;
        margin: 0;
        overflow: hidden;
        color: var(--text);
        background:
            radial-gradient(circle at 18% 10%, rgba(255,255,255,.96), transparent 28%),
            radial-gradient(circle at 85% 5%, rgba(32,199,189,.20), transparent 24%),
            radial-gradient(circle at 58% 92%, rgba(0,122,255,.16), transparent 28%),
            linear-gradient(135deg, #fbfdff 0%, #f1f8ff 45%, #edfdfb 100%);
        background-attachment: fixed;
    }

    button,
    input,
    select,
    textarea {
        font: inherit;
    }

    svg {
        width: 16px;
        height: 16px;
        fill: none;
        stroke: currentColor;
        stroke-width: 2;
        stroke-linecap: round;
        stroke-linejoin: round;
    }

    .app-shell {
        position: relative;
        height: 1080px;
        min-height: 100vh;
        overflow: hidden;
        background:
            radial-gradient(circle at 18% 10%, rgba(255,255,255,.96), transparent 28%),
            radial-gradient(circle at 85% 5%, rgba(32,199,189,.20), transparent 24%),
            radial-gradient(circle at 58% 92%, rgba(0,122,255,.16), transparent 28%),
            linear-gradient(135deg, #fbfdff 0%, #f1f8ff 45%, #edfdfb 100%);
    }

    .topbar {
        position: relative;
        z-index: 4;
        height: 66px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        padding: 12px 20px;
        border-bottom: 1px solid rgba(255,255,255,.76);
        background: rgba(255,255,255,.64);
        backdrop-filter: blur(24px) saturate(160%);
    }

    .brand {
        display: flex;
        align-items: center;
        gap: 12px;
        min-width: 0;
    }

    .brand-mark {
        display: grid;
        place-items: center;
        width: 38px;
        height: 38px;
        border: 1px solid rgba(255,255,255,.9);
        border-radius: 12px;
        color: var(--blue);
        background: rgba(255,255,255,.86);
        box-shadow: 0 10px 30px rgba(0,122,255,.08);
    }

    .brand h1 {
        margin: 0;
        color: #15191f;
        font-size: 18px;
        font-weight: 560;
        letter-spacing: 0;
        line-height: 1;
    }

    .brand span {
        display: block;
        margin-top: 5px;
        color: var(--secondary);
        font-size: 12px;
        font-weight: 400;
    }

    .top-actions {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .save-status {
        min-width: 92px;
        padding: 7px 10px;
        border: 1px solid rgba(32,199,189,.16);
        border-radius: 999px;
        color: #147d87;
        background: rgba(255,255,255,.68);
        text-align: center;
        font-size: 12px;
        font-weight: 430;
        transition: color .18s ease, background .18s ease, border-color .18s ease;
    }

    .save-status.is-saving {
        color: #0b66c3;
        border-color: rgba(0,122,255,.20);
        background: rgba(233,244,255,.82);
    }

    .save-status.is-error {
        color: var(--danger);
        border-color: rgba(217,45,32,.24);
        background: rgba(255,242,242,.88);
    }

    .app-shell.is-read-only .save-status {
        color: #147d87;
        border-color: rgba(32,199,189,.16);
        background: rgba(255,255,255,.68);
    }

    .app-shell.is-read-only #add-list-top,
    .app-shell.is-read-only #open-sync,
    .app-shell.is-read-only #open-new-card,
    .app-shell.is-read-only .edit-card,
    .app-shell.is-read-only .close-list,
    .app-shell.is-read-only .add-card-button,
    .app-shell.is-read-only .list-drag-handle {
        display: none;
    }

    .primary-button,
    .secondary-button,
    .add-card-button,
    .tertiary-button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 7px;
        min-height: 36px;
        border: 1px solid var(--line);
        border-radius: 999px;
        cursor: pointer;
        transition: transform .14s ease, background .14s ease, box-shadow .14s ease;
    }

    .primary-button {
        padding: 0 15px;
        color: #fff;
        border-color: transparent;
        background: linear-gradient(135deg, var(--blue), var(--cyan));
        box-shadow: 0 10px 24px rgba(0,122,255,.16);
        font-weight: 500;
    }

    .secondary-button,
    .add-card-button,
    .tertiary-button {
        color: #1e5f8f;
        background: rgba(255,255,255,.74);
        font-weight: 430;
    }

    .secondary-button {
        padding: 0 14px;
    }

    .primary-button:hover,
    .secondary-button:hover,
    .add-card-button:hover,
    .tertiary-button:hover,
    .icon-button:hover {
        transform: translateY(-1px);
        background: rgba(255,255,255,.96);
        box-shadow: 0 12px 28px rgba(28,43,61,.10);
    }

    .primary-button:hover {
        background: linear-gradient(135deg, #0878ef, #1bbdb5);
    }

    button:disabled,
    .is-disabled {
        opacity: .58;
        cursor: wait;
        transform: none !important;
        box-shadow: none !important;
    }

    .content-shell {
        position: relative;
        z-index: 2;
        width: 100%;
        height: calc(1080px - 66px);
        display: flex;
        gap: 0;
        overflow: hidden;
    }

    .board {
        position: relative;
        flex: 1 1 auto;
        min-width: 0;
        height: 100%;
        display: flex;
        flex-direction: row;
        flex-wrap: nowrap;
        align-items: flex-start;
        gap: 18px;
        padding: 20px 20px 86px;
        overflow-x: auto;
        overflow-y: hidden;
        cursor: default;
        user-select: none;
        overscroll-behavior-x: contain;
        touch-action: none;
        scrollbar-width: thin;
        scrollbar-color: rgba(0,122,255,.26) rgba(255,255,255,.58);
    }

    .side-panel,
    .audit-panel {
        flex: 0 0 340px;
        width: 340px;
        min-width: 340px;
        max-width: 340px;
        max-height: calc(1080px - 176px);
        display: flex;
        flex-direction: column;
        padding: 0;
        border: 1px solid rgba(255,255,255,.78);
        border-radius: var(--radius-lg);
        background: rgba(255,255,255,.86);
        box-shadow: var(--shadow);
        backdrop-filter: blur(26px) saturate(160%);
        overflow: hidden;
    }

    .cohort-panel {
        flex-basis: 300px;
        width: 300px;
        min-width: 300px;
        max-width: 300px;
    }

    .audit-header {
        padding: 16px 16px 12px;
        border-bottom: 1px solid rgba(207,226,239,.68);
    }

    .audit-header h2 {
        margin: 0;
        color: #24445c;
        font-size: 16px;
        font-weight: 540;
    }

    .audit-header p {
        margin: 5px 0 0;
        color: var(--secondary);
        font-size: 12px;
        line-height: 1.35;
    }

    .audit-list {
        display: flex;
        flex-direction: column;
        gap: 10px;
        padding: 12px;
        overflow-y: auto;
        scrollbar-width: thin;
        scrollbar-color: rgba(0,122,255,.24) rgba(255,255,255,.45);
    }

    .audit-item {
        padding: 10px;
        border: 1px solid rgba(190,225,238,.72);
        border-radius: 14px;
        background: rgba(255,255,255,.72);
    }

    .audit-item.is-error {
        border-color: rgba(217,45,32,.24);
        background: rgba(255,246,246,.82);
    }

    .audit-time {
        display: block;
        color: #6e8aa0;
        font-size: 11.5px;
        line-height: 1.2;
    }

    .audit-action {
        margin-top: 4px;
        color: #1f516f;
        font-size: 13px;
        font-weight: 560;
        line-height: 1.25;
    }

    .audit-detail {
        margin-top: 4px;
        color: #536b7c;
        font-size: 12.5px;
        line-height: 1.35;
    }

    .cohort-summary {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 8px;
        padding: 12px;
    }

    .cohort-stat {
        padding: 10px;
        border: 1px solid rgba(190,225,238,.72);
        border-radius: 14px;
        background: rgba(244,251,255,.76);
    }

    .cohort-stat span {
        display: block;
        color: #6e8aa0;
        font-size: 11px;
    }

    .cohort-stat strong {
        display: block;
        margin-top: 3px;
        color: #255a78;
        font-size: 20px;
        font-weight: 560;
    }

    .cohort-actions {
        padding: 0 12px 12px;
    }

    .cohort-actions button {
        width: 100%;
    }

    .cohort-list {
        display: flex;
        flex-direction: column;
        gap: 8px;
        padding: 0 12px 12px;
        overflow-y: auto;
    }

    .cohort-item {
        display: grid;
        grid-template-columns: 32px minmax(0, 1fr) auto;
        gap: 8px;
        align-items: center;
        padding: 9px;
        border: 1px solid rgba(190,225,238,.72);
        border-radius: 14px;
        background: rgba(255,255,255,.72);
    }

    .cohort-avatar {
        display: grid;
        place-items: center;
        width: 30px;
        height: 30px;
        border-radius: 999px;
        color: #fff;
        background: linear-gradient(135deg, #32d6c4, #0a84ff);
        font-size: 11px;
        font-weight: 650;
    }

    .cohort-name {
        min-width: 0;
        color: #24445c;
        font-size: 12.5px;
        font-weight: 540;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .cohort-meta {
        margin-top: 2px;
        color: #7891a3;
        font-size: 11px;
    }

    .cohort-status {
        padding: 4px 7px;
        border-radius: 999px;
        color: #14746f;
        background: rgba(45,212,191,.16);
        font-size: 10.5px;
        font-weight: 560;
    }

    .cohort-status.is-archived {
        color: #6e8aa0;
        background: rgba(148,163,184,.16);
    }

    .admin-page {
        position: fixed;
        inset: 66px 0 0;
        z-index: 60;
        display: none;
        flex-direction: column;
        padding: 22px;
        overflow: auto;
        background:
            radial-gradient(circle at 78% 12%, rgba(60, 220, 205, .22), transparent 34%),
            radial-gradient(circle at 52% 92%, rgba(0, 122, 255, .18), transparent 34%),
            linear-gradient(135deg, #f8fcff 0%, #eef8ff 46%, #e9fffb 100%);
    }

    .admin-page.is-open {
        display: flex;
    }

    .admin-page-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        margin-bottom: 16px;
    }

    .admin-page-header h2,
    .admin-section-title h3 {
        margin: 0;
        color: #172b3a;
        font-weight: 560;
        letter-spacing: 0;
    }

    .admin-page-header p,
    .admin-section-title p,
    .admin-hint {
        margin: 5px 0 0;
        color: var(--secondary);
        font-size: 12.5px;
    }

    .admin-grid {
        display: grid;
        grid-template-columns: minmax(420px, 1.1fr) minmax(360px, .9fr);
        gap: 16px;
        align-items: start;
    }

    .admin-card {
        border: 1px solid rgba(255,255,255,.78);
        border-radius: var(--radius-lg);
        background: rgba(255,255,255,.82);
        box-shadow: var(--shadow);
        backdrop-filter: blur(26px) saturate(160%);
        padding: 16px;
    }

    .admin-history-card {
        grid-column: 1 / -1;
    }

    .admin-stats-grid,
    .admin-student-summary {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 10px;
        margin-top: 14px;
    }

    .admin-student-summary {
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .admin-stats-grid div,
    .admin-student-summary div {
        padding: 11px;
        border: 1px solid rgba(190,225,238,.72);
        border-radius: 16px;
        background: rgba(244,251,255,.82);
    }

    .admin-stats-grid span,
    .admin-student-summary span {
        display: block;
        color: #6e8aa0;
        font-size: 11px;
    }

    .admin-stats-grid strong,
    .admin-student-summary strong {
        display: block;
        margin-top: 4px;
        color: #255a78;
        font-size: 22px;
        font-weight: 560;
    }

    .admin-stats-grid small {
        display: block;
        color: #6e8aa0;
        font-size: 10.5px;
    }

    .admin-chart {
        margin-top: 16px;
        min-height: 280px;
        border: 1px solid rgba(190,225,238,.72);
        border-radius: 18px;
        background: rgba(255,255,255,.64);
        padding: 12px;
    }

    .admin-chart svg {
        width: 100%;
        height: 280px;
        color: #536b7c;
        font-family: "Segoe UI", Arial, Helvetica, sans-serif;
        font-weight: 300;
        -webkit-font-smoothing: antialiased;
        text-rendering: geometricPrecision;
    }

    .admin-chart text {
        fill: #536b7c;
        stroke: none !important;
        stroke-width: 0 !important;
        paint-order: normal;
        font-family: "Segoe UI", Arial, Helvetica, sans-serif;
        font-size: 10.5px;
        font-weight: 300 !important;
        letter-spacing: 0;
    }

    .admin-chart .chart-title-text {
        fill: #24445c;
        font-size: 11px;
        font-weight: 300 !important;
    }

    .admin-chart .axis,
    .admin-chart .grid {
        stroke: rgba(95, 126, 146, .28);
        stroke-width: 1;
    }

    .admin-chart .series {
        fill: none;
        stroke: #0a84ff;
        stroke-width: 2.5;
        stroke-linecap: round;
        stroke-linejoin: round;
    }

    .admin-chart circle {
        fill: #20c7b8;
        stroke: #fff;
        stroke-width: 2;
    }

    .admin-wide-button {
        width: 100%;
        margin-top: 12px;
    }

    .admin-avatar-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(42px, 1fr));
        gap: 10px;
        margin-top: 14px;
        max-height: 304px;
        overflow-y: auto;
        padding-right: 4px;
    }

    .admin-avatar {
        display: grid;
        place-items: center;
        width: 42px;
        height: 42px;
        border: 2px solid rgba(255,255,255,.9);
        border-radius: 999px;
        color: #fff;
        background: #16a34a;
        box-shadow: 0 10px 24px rgba(31, 81, 111, .16);
        font-size: 13px;
        font-weight: 650;
        cursor: default;
    }

    .admin-avatar.is-archived {
        background: #ef4444;
    }

    .admin-avatar.is-unknown {
        background: #f59e0b;
    }

    .admin-history-list {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
        gap: 10px;
        margin-top: 14px;
        max-height: 330px;
        overflow-y: auto;
    }

    .developer-credit {
        position: fixed;
        left: 50%;
        bottom: 4px;
        z-index: 20;
        transform: translateX(-50%);
        color: rgba(64, 91, 108, .62);
        font-size: 12px;
        font-weight: 400;
        letter-spacing: 0;
        white-space: nowrap;
        pointer-events: none;
    }

    @media (max-width: 980px) {
        .admin-grid {
            grid-template-columns: 1fr;
        }

        .admin-stats-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }

    .board.is-dragging {
        cursor: grabbing;
        user-select: none;
    }

    .board::-webkit-scrollbar,
    .card-stack::-webkit-scrollbar {
        width: 12px;
        height: 12px;
    }

    .board::-webkit-scrollbar-thumb,
    .card-stack::-webkit-scrollbar-thumb {
        border: 3px solid transparent;
        border-radius: 999px;
        background: rgba(0,122,255,.26);
        background-clip: padding-box;
    }

    .board-list {
        flex: 0 0 300px;
        width: 300px;
        min-width: 300px;
        max-width: 300px;
        max-height: calc(1080px - 176px);
        display: flex;
        flex-direction: column;
        padding: 14px;
        border: 1px solid rgba(255,255,255,.78);
        border-radius: var(--radius-lg);
        background: var(--surface);
        box-shadow: var(--shadow);
        backdrop-filter: blur(26px) saturate(160%);
        cursor: default;
        user-select: none;
        will-change: transform;
        transition: transform .18s cubic-bezier(.2, .8, .2, 1), opacity .16s ease, box-shadow .16s ease, outline-color .16s ease;
    }

    .board-list.is-locked {
        background: rgba(255,255,255,.82);
        cursor: default;
    }

    .board-list.is-list-dragging {
        position: relative;
        z-index: 3;
        opacity: .92;
        transform: translateY(-5px) scale(1.018) rotate(.35deg);
        cursor: grabbing;
        box-shadow: 0 30px 80px rgba(28,43,61,.22);
        outline: 2px solid rgba(0,122,255,.18);
        animation: lift-list .16s ease-out, drag-breathe 1.1s ease-in-out infinite;
    }

    .board-list.is-list-dragging::after {
        content: "Arrastrando";
        position: absolute;
        top: -12px;
        right: 18px;
        padding: 5px 9px;
        border: 1px solid rgba(0,122,255,.16);
        border-radius: 999px;
        color: #0b66c3;
        background: rgba(255,255,255,.92);
        box-shadow: 0 10px 26px rgba(28,43,61,.12);
        font-size: 11px;
        font-weight: 480;
        pointer-events: none;
    }

    .board-list.is-list-ready {
        outline: 2px solid rgba(0,122,255,.08);
    }

    .board-list.is-list-ready .list-header {
        color: #0b66c3;
    }

    .board-list.is-list-settling {
        animation: settle-list .24s cubic-bezier(.2, .8, .2, 1);
    }

    .list-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 10px;
        padding: 2px 2px 14px;
        cursor: grab;
        user-select: none;
        -webkit-user-select: none;
        touch-action: none;
    }

    .list-title-group {
        display: flex;
        align-items: flex-start;
        gap: 9px;
        min-width: 0;
    }

    .list-drag-handle {
        display: grid;
        place-items: center;
        flex: 0 0 auto;
        width: 24px;
        height: 28px;
        margin-top: -3px;
        border-radius: 9px;
        color: var(--tertiary);
        cursor: grab;
    }

    .list-drag-handle:hover {
        color: #1e5f8f;
        background: rgba(255,255,255,.72);
    }

    .list-drag-handle svg {
        width: 18px;
        height: 18px;
        fill: currentColor;
        stroke: none;
    }

    .list-header h2 {
        margin: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        color: #15191f;
        font-size: 15px;
        font-weight: 520;
        letter-spacing: 0;
    }

    .list-header .list-count {
        display: block;
        margin-top: 5px;
        color: var(--tertiary);
        font-size: 12px;
        font-weight: 400;
    }

    .icon-button {
        display: grid;
        place-items: center;
        width: 32px;
        height: 32px;
        border: 1px solid transparent;
        border-radius: 999px;
        color: var(--secondary);
        background: transparent;
        cursor: pointer;
    }

    .stats-panel {
        padding: 14px;
        border: 1px solid var(--line);
        border-radius: var(--radius-md);
        background: var(--surface-strong);
    }

    .panel-label,
    .card-label {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: #147d87;
        font-size: 12px;
        font-weight: 460;
    }

    .stats-panel h3 {
        margin: 10px 0 13px;
        font-size: 15px;
        font-weight: 520;
    }

    .stats-grid,
    .range-grid {
        display: grid;
        gap: 8px;
    }

    .stats-grid.compact {
        grid-template-columns: repeat(3, 1fr);
    }

    .range-grid {
        grid-template-columns: 1fr 1fr;
        margin-top: 8px;
    }

    .stats-grid div,
    .range-grid div {
        min-width: 0;
        padding: 10px 8px;
        border-radius: 14px;
        background: #f4fbff;
    }

    .stats-grid span,
    .range-grid span {
        display: block;
        color: var(--tertiary);
        font-size: 10.5px;
        font-weight: 400;
    }

    .stats-grid strong,
    .range-grid strong {
        display: block;
        margin-top: 4px;
        color: #162d42;
        font-size: 18px;
        font-weight: 540;
    }

    .range-grid small {
        display: block;
        margin-top: 4px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        color: var(--secondary);
        font-size: 11px;
    }

    .average-chart {
        margin-top: 12px;
        padding: 10px;
        border: 1px solid rgba(190,225,238,.72);
        border-radius: 16px;
        background: rgba(244,251,255,.74);
    }

    .chart-title {
        margin-bottom: 6px;
        color: #24445c;
        font-size: 12px;
        font-weight: 540;
    }

    .average-chart svg {
        width: 100%;
        height: auto;
        display: block;
    }

    .chart-grid line {
        stroke: rgba(116,147,170,.20);
        stroke-width: 1;
    }

    .chart-grid text,
    .chart-x-labels text,
    .chart-y-title,
    .chart-x-title {
        fill: #6e8aa0;
        stroke: none !important;
        stroke-width: 0 !important;
        paint-order: normal;
        font-family: "Segoe UI", Arial, Helvetica, sans-serif;
        font-size: 10px;
        font-weight: 300 !important;
    }

    .chart-axis line {
        stroke: rgba(82,107,128,.32);
        stroke-width: 1.1;
    }

    .chart-line {
        fill: none;
        stroke: #0a84ff;
        stroke-width: 2.8;
        stroke-linecap: round;
        stroke-linejoin: round;
    }

    .chart-points circle {
        fill: #20c7bd;
        stroke: rgba(255,255,255,.94);
        stroke-width: 2;
    }

    .chart-empty {
        min-height: 70px;
        display: grid;
        place-items: center;
        color: var(--secondary);
        font-size: 12px;
        text-align: center;
    }

    .stats-panel p {
        margin: 12px 0 0;
        color: var(--secondary);
        font-size: 12px;
        line-height: 1.45;
    }

    .card-stack {
        min-height: 88px;
        overflow-x: hidden;
        overflow-y: auto;
        cursor: grab;
        overscroll-behavior-y: contain;
        touch-action: none;
        scrollbar-width: thin;
    }

    .card-stack.is-dragging {
        cursor: grabbing;
        user-select: none;
    }

    .empty-state {
        display: grid;
        place-items: center;
        min-height: 108px;
        padding: 16px;
        border: 1px dashed rgba(0,122,255,.22);
        border-radius: var(--radius-md);
        color: var(--tertiary);
        background: rgba(255,255,255,.46);
        text-align: center;
        font-size: 13px;
        line-height: 1.38;
    }

    .card {
        margin-bottom: 10px;
        border: 1px solid rgba(255,255,255,.82);
        border-radius: 18px;
        background: rgba(255,255,255,.86);
        box-shadow: 0 10px 24px rgba(28,43,61,.07);
        cursor: grab;
        will-change: transform;
        transition: transform .18s cubic-bezier(.2, .8, .2, 1), opacity .16s ease, box-shadow .16s ease, outline-color .16s ease;
    }

    .card.is-card-dragging {
        position: relative;
        z-index: 2;
        opacity: .94;
        transform: translateY(-4px) scale(1.018) rotate(-.35deg);
        cursor: grabbing;
        box-shadow: 0 22px 46px rgba(28,43,61,.18);
        outline: 2px solid rgba(0,122,255,.16);
        animation: lift-card .16s ease-out;
    }

    .card.is-card-dragging::after {
        content: "Moviendo";
        position: absolute;
        top: -10px;
        right: 12px;
        padding: 4px 8px;
        border: 1px solid rgba(32,199,189,.20);
        border-radius: 999px;
        color: #147d87;
        background: rgba(255,255,255,.94);
        box-shadow: 0 10px 24px rgba(28,43,61,.10);
        font-size: 10.5px;
        font-weight: 480;
        pointer-events: none;
    }

    .card.is-card-ready {
        outline: 2px solid rgba(0,122,255,.10);
    }

    @keyframes lift-list {
        from {
            transform: translateY(0) scale(1);
            box-shadow: var(--shadow);
        }
        to {
            transform: translateY(-5px) scale(1.018) rotate(.35deg);
            box-shadow: 0 30px 80px rgba(28,43,61,.22);
        }
    }

    @keyframes drag-breathe {
        0%, 100% {
            box-shadow: 0 30px 80px rgba(28,43,61,.22);
        }
        50% {
            box-shadow: 0 36px 92px rgba(0,122,255,.24);
        }
    }

    @keyframes settle-list {
        from {
            transform: translateY(-4px) scale(1.012);
            box-shadow: 0 24px 58px rgba(0,122,255,.18);
        }
        to {
            transform: translateY(0) scale(1);
            box-shadow: var(--shadow);
        }
    }

    @keyframes lift-card {
        from {
            transform: translateY(0) scale(1);
            box-shadow: 0 10px 24px rgba(28,43,61,.07);
        }
        to {
            transform: translateY(-4px) scale(1.018) rotate(-.35deg);
            box-shadow: 0 22px 46px rgba(28,43,61,.18);
        }
    }

    .card-cover {
        display: grid;
        grid-auto-flow: column;
        grid-auto-columns: 72px;
        gap: 6px;
        padding: 10px 10px 0;
        overflow: hidden;
    }

    .card-cover img {
        width: 72px;
        height: 54px;
        border-radius: 12px;
        object-fit: cover;
    }

    .card-body {
        padding: 13px;
    }

    .card h3 {
        margin: 8px 0 0;
        color: #15191f;
        font-size: 15px;
        font-weight: 520;
        line-height: 1.3;
        letter-spacing: 0;
    }

    .card p {
        margin: 8px 0 0;
        color: var(--secondary);
        font-size: 12.5px;
        line-height: 1.42;
    }

    .card-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 10px;
    }

    .card-badges span {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        min-height: 24px;
        padding: 3px 8px;
        border-radius: 999px;
        color: #1e5f8f;
        background: var(--blue-soft);
        font-size: 12px;
    }

    .card-badges svg {
        width: 13px;
        height: 13px;
    }

    .tertiary-button {
        width: 100%;
        min-height: 34px;
        margin-top: 12px;
        box-shadow: none;
    }

    .card-actions {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 7px;
        margin-top: 12px;
    }

    .card-actions .tertiary-button {
        width: 100%;
        margin-top: 0;
    }

    .add-card-button {
        width: 100%;
        margin-top: 10px;
        background: rgba(255,255,255,.62);
    }

    .add-list {
        flex: 0 0 300px;
        width: 300px;
        min-width: 300px;
        height: 54px;
        border-style: dashed;
        background: rgba(255,255,255,.52);
    }

    .drawer-backdrop,
    .preview-backdrop,
    .visibility-backdrop,
    .sync-backdrop,
    .confirm-backdrop {
        position: absolute;
        inset: 0;
        z-index: 8;
        display: none;
        background: rgba(25, 36, 50, .18);
        backdrop-filter: blur(8px);
    }

    .drawer-backdrop.is-open,
    .preview-backdrop.is-open,
    .visibility-backdrop.is-open,
    .sync-backdrop.is-open,
    .confirm-backdrop.is-open {
        display: block;
    }

    .drawer {
        position: absolute;
        top: 14px;
        right: 14px;
        bottom: 14px;
        z-index: 9;
        width: min(460px, calc(100% - 28px));
        display: none;
        flex-direction: column;
        padding: 18px;
        border: 1px solid rgba(255,255,255,.84);
        border-radius: 28px;
        background: rgba(255,255,255,.88);
        box-shadow: 0 28px 80px rgba(28,43,61,.18);
        backdrop-filter: blur(28px) saturate(165%);
    }

    .drawer.is-open {
        display: flex;
    }

    .drawer-scroll {
        min-height: 0;
        overflow-y: auto;
        padding-right: 2px;
    }

    .drawer-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 14px;
    }

    .drawer-header h2,
    .confirm-dialog h2 {
        margin: 0;
        color: #15191f;
        font-size: 18px;
        font-weight: 560;
    }

    .drawer-header p,
    .confirm-dialog p {
        margin: 6px 0 0;
        color: var(--secondary);
        font-size: 12.5px;
        line-height: 1.42;
    }

    .form-row {
        margin-bottom: 13px;
    }

    .quick-start {
        padding: 12px;
        border: 1px solid var(--line);
        border-radius: 18px;
        background: rgba(255,255,255,.66);
        margin-bottom: 14px;
    }

    .quick-start .form-row:last-child {
        margin-bottom: 0;
    }

    .optional-tools {
        display: grid;
        gap: 8px;
        margin-bottom: 14px;
    }

    .optional-title {
        margin: 0 0 4px;
        color: var(--secondary);
        font-size: 12px;
        font-weight: 430;
    }

    .tool-row {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px;
    }

    .option-panel {
        display: none;
        margin-bottom: 13px;
        padding: 12px;
        border: 1px solid var(--line);
        border-radius: 18px;
        background: rgba(255,255,255,.52);
    }

    .option-panel.is-open {
        display: block;
    }

    label {
        display: block;
        margin-bottom: 6px;
        color: #273444;
        font-size: 12px;
        font-weight: 500;
    }

    input,
    select,
    textarea {
        width: 100%;
        border: 1px solid var(--line);
        border-radius: 14px;
        color: var(--text);
        background: rgba(255,255,255,.78);
        outline: none;
    }

    input,
    select {
        height: 38px;
        padding: 0 12px;
    }

    textarea {
        min-height: 74px;
        resize: vertical;
        padding: 10px 12px;
    }

    input:focus,
    select:focus,
    textarea:focus {
        border-color: rgba(0,122,255,.54);
        box-shadow: 0 0 0 4px rgba(0,122,255,.10);
    }

    .file-drop {
        display: block;
        padding: 14px;
        border: 1px dashed rgba(0,122,255,.28);
        border-radius: 16px;
        color: var(--secondary);
        background: rgba(244,251,255,.7);
        text-align: center;
        cursor: pointer;
    }

    .file-drop input {
        display: none;
    }

    .image-preview,
    .file-preview,
    .checklists {
        display: grid;
        gap: 8px;
        margin-top: 10px;
    }

    .image-preview {
        grid-template-columns: repeat(4, 1fr);
    }

    .image-preview img {
        width: 100%;
        aspect-ratio: 1;
        border-radius: 12px;
        object-fit: cover;
    }

    .file-pill {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 9px 11px;
        border: 1px solid rgba(159, 213, 239, .8);
        border-radius: 999px;
        background: rgba(255, 255, 255, .76);
        color: #255a78;
        font-size: 12.5px;
    }

    .file-pill svg {
        width: 15px;
        height: 15px;
    }

    .checklist-block {
        padding: 10px;
        border: 1px solid var(--line);
        border-radius: 16px;
        background: rgba(255,255,255,.64);
    }

    .checklist-field {
        display: block;
        margin-bottom: 9px;
    }

    .checklist-field:last-child {
        margin-bottom: 0;
    }

    .checklist-field span {
        display: block;
        margin-bottom: 5px;
        color: var(--secondary);
        font-size: 11.5px;
        font-weight: 500;
    }

    .checklist-block input {
        margin-bottom: 8px;
    }

    .checklist-field input,
    .checklist-field textarea {
        margin-bottom: 0;
    }

    .checklist-block textarea {
        min-height: 64px;
        margin-bottom: 8px;
    }

    .checklist-links {
        display: grid;
        gap: 6px;
        margin-top: 10px;
    }

    .checklist-links a {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        min-height: 28px;
        padding: 4px 8px;
        border-radius: 999px;
        color: #0b66c3;
        background: var(--blue-soft);
        font-size: 12px;
        text-decoration: none;
    }

    .checklist-links a:hover {
        text-decoration: underline;
    }

    .mini-button {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        min-height: 32px;
        padding: 0 11px;
        border: 1px solid var(--line);
        border-radius: 999px;
        color: #1e5f8f;
        background: rgba(255,255,255,.72);
        cursor: pointer;
    }

    .hint {
        margin: 7px 0 0;
        color: var(--tertiary);
        font-size: 12px;
        line-height: 1.4;
    }

    .drawer-actions,
    .confirm-actions {
        display: flex;
        gap: 8px;
        margin-top: 14px;
    }

    .drawer-actions button,
    .confirm-actions button {
        flex: 1;
    }

    .confirm-dialog {
        position: absolute;
        top: 50%;
        left: 50%;
        z-index: 10;
        width: min(380px, calc(100% - 32px));
        display: none;
        padding: 18px;
        border: 1px solid rgba(255,255,255,.86);
        border-radius: 24px;
        background: rgba(255,255,255,.92);
        box-shadow: 0 28px 80px rgba(28,43,61,.20);
        transform: translate(-50%, -50%);
        backdrop-filter: blur(28px) saturate(160%);
    }

    .preview-dialog {
        position: absolute;
        top: 50%;
        left: 50%;
        z-index: 10;
        width: min(560px, calc(100% - 32px));
        max-height: calc(100% - 48px);
        display: none;
        flex-direction: column;
        padding: 18px;
        border: 1px solid rgba(255,255,255,.86);
        border-radius: 26px;
        background: rgba(255,255,255,.94);
        box-shadow: 0 28px 80px rgba(28,43,61,.20);
        transform: translate(-50%, -50%);
        backdrop-filter: blur(28px) saturate(160%);
    }

    .visibility-dialog {
        position: absolute;
        top: 50%;
        left: 50%;
        z-index: 10;
        width: min(620px, calc(100% - 32px));
        max-height: calc(100% - 48px);
        display: none;
        flex-direction: column;
        padding: 18px;
        border: 1px solid rgba(255,255,255,.86);
        border-radius: 28px;
        background: rgba(255,255,255,.92);
        box-shadow: 0 28px 90px rgba(28,43,61,.20);
        transform: translate(-50%, -50%);
        backdrop-filter: blur(30px) saturate(165%);
    }

    .visibility-dialog.is-open {
        display: flex;
    }

    .visibility-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        padding-bottom: 12px;
        border-bottom: 1px solid var(--line);
    }

    .visibility-header h2 {
        margin: 0;
        color: #15191f;
        font-size: 19px;
        font-weight: 560;
    }

    .visibility-header p {
        margin: 6px 0 0;
        color: var(--secondary);
        font-size: 12.5px;
        line-height: 1.42;
    }

    .visibility-tools {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        padding: 12px 0;
    }

    .visibility-grid {
        min-height: 110px;
        max-height: 360px;
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(56px, 1fr));
        gap: 12px;
        overflow-y: auto;
        padding: 4px 2px 12px;
    }

    .student-chip {
        position: relative;
        display: grid;
        place-items: center;
        width: 54px;
        height: 54px;
        margin: 0 auto;
        border: 1px solid rgba(255,255,255,.92);
        border-radius: 999px;
        color: white;
        background: linear-gradient(135deg, #15b8b0, #0a84ff);
        box-shadow: 0 12px 28px rgba(10,132,255,.18);
        font-size: 18px;
        font-weight: 580;
        letter-spacing: 0;
        cursor: pointer;
        transition: transform .16s ease, opacity .16s ease, filter .16s ease, box-shadow .16s ease;
    }

    .student-chip:hover {
        transform: translateY(-2px);
    }

    .student-chip.is-hidden {
        color: #7890a2;
        background: rgba(244,251,255,.78);
        border-color: rgba(169,214,234,.86);
        box-shadow: inset 0 0 0 2px rgba(169,214,234,.26);
        opacity: .72;
        filter: grayscale(.18);
    }

    .student-chip.is-hidden::after {
        content: "";
        position: absolute;
        inset: 26px 7px auto;
        height: 2px;
        border-radius: 999px;
        background: rgba(84,108,124,.68);
        transform: rotate(-18deg);
    }

    .visibility-status {
        margin: 0;
        color: var(--secondary);
        font-size: 12px;
    }

    .visibility-actions {
        display: flex;
        gap: 8px;
        padding-top: 12px;
        border-top: 1px solid var(--line);
    }

    .visibility-actions button {
        flex: 1;
    }

    .sync-dialog {
        position: absolute;
        top: 82px;
        right: 22px;
        z-index: 10;
        width: min(560px, calc(100% - 44px));
        max-height: calc(100% - 110px);
        display: none;
        flex-direction: column;
        border: 1px solid rgba(255,255,255,.86);
        border-radius: 28px;
        background: rgba(255,255,255,.92);
        box-shadow: 0 28px 90px rgba(28,43,61,.20);
        backdrop-filter: blur(30px) saturate(165%);
        overflow: hidden;
    }

    .sync-dialog.is-open {
        display: flex;
    }

    .sync-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        padding: 18px 18px 14px;
        border-bottom: 1px solid var(--line);
    }

    .sync-header h2 {
        margin: 0;
        color: #15191f;
        font-size: 19px;
        font-weight: 560;
    }

    .sync-header p,
    .sync-note {
        margin: 6px 0 0;
        color: var(--secondary);
        font-size: 12.5px;
        line-height: 1.42;
    }

    .sync-body {
        display: flex;
        flex-direction: column;
        gap: 12px;
        padding: 16px 18px;
        overflow-y: auto;
    }

    .sync-summary {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 10px;
    }

    .sync-summary div,
    .sync-action-row {
        border: 1px solid rgba(190,225,238,.72);
        border-radius: 15px;
        background: rgba(248,252,255,.86);
    }

    .sync-summary div {
        padding: 10px;
    }

    .sync-summary span {
        display: block;
        color: #6e8aa0;
        font-size: 11.5px;
    }

    .sync-summary strong {
        display: block;
        margin-top: 5px;
        color: #255a78;
        font-size: 18px;
        font-weight: 560;
    }

    .sync-actions-list {
        display: flex;
        flex-direction: column;
        gap: 8px;
        max-height: 260px;
        overflow-y: auto;
    }

    .sync-action-row {
        padding: 10px 12px;
        color: #536b7c;
        font-size: 12.5px;
        line-height: 1.35;
    }

    .sync-action-row strong {
        display: block;
        color: #1f516f;
        font-size: 13px;
        font-weight: 560;
    }

    .sync-board-row {
        display: grid;
        grid-template-columns: 24px minmax(0, 1fr);
        gap: 8px;
        align-items: center;
        padding: 10px 12px;
        border: 1px solid rgba(159, 213, 239, 0.75);
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.72);
        color: #48667a;
        font-size: 12.5px;
    }

    .sync-board-row strong {
        display: block;
        color: #1f516f;
        font-weight: 560;
    }

    .sync-board-icon {
        display: grid;
        place-items: center;
        width: 22px;
        height: 22px;
        border-radius: 999px;
        background: #e7f5ff;
        color: #1673aa;
        font-size: 12px;
        font-weight: 650;
    }

    .sync-board-row.is-done .sync-board-icon {
        background: #dcfce7;
        color: #15803d;
    }

    .sync-board-row.is-error {
        border-color: rgba(248, 113, 113, 0.45);
        background: rgba(255, 241, 242, 0.82);
    }

    .sync-board-row.is-error .sync-board-icon {
        background: #fee2e2;
        color: #b91c1c;
    }

    .sync-confirm {
        display: grid;
        gap: 7px;
    }

    .sync-confirm label {
        color: #455b70;
        font-size: 12px;
    }

    .sync-confirm input {
        height: 40px;
    }

    .sync-footer {
        display: flex;
        gap: 8px;
        padding: 14px 18px 18px;
        border-top: 1px solid var(--line);
    }

    .sync-footer button {
        flex: 1;
    }

    .preview-dialog.is-open {
        display: flex;
    }

    .preview-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 12px;
    }

    .preview-header h2 {
        margin: 0;
        font-size: 20px;
        font-weight: 560;
    }

    .preview-header p {
        margin: 6px 0 0;
        color: var(--secondary);
        font-size: 12.5px;
    }

    .preview-body {
        overflow-y: auto;
        padding-right: 2px;
    }

    .preview-section {
        margin-top: 12px;
        padding: 12px;
        border: 1px solid var(--line);
        border-radius: 16px;
        background: rgba(244,251,255,.72);
    }

    .preview-section h3 {
        margin: 0 0 8px;
        font-size: 13px;
        font-weight: 540;
    }

    .preview-section p {
        margin: 0;
        color: var(--secondary);
        font-size: 13px;
        line-height: 1.45;
        white-space: pre-wrap;
    }

    .preview-links {
        display: grid;
        gap: 7px;
    }

    .preview-links a {
        color: #0b66c3;
        text-decoration: none;
        overflow-wrap: anywhere;
    }

    .preview-links a:hover {
        text-decoration: underline;
    }

    .preview-images {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 8px;
    }

    .preview-images img {
        width: 100%;
        aspect-ratio: 4 / 3;
        border-radius: 14px;
        object-fit: cover;
    }

    .confirm-dialog.is-open {
        display: block;
    }

    .danger-button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 7px;
        min-height: 36px;
        border: 0;
        border-radius: 999px;
        color: #fff;
        background: var(--danger);
        cursor: pointer;
    }

    @media (max-width: 760px) {
        .topbar {
            height: 78px;
            align-items: flex-start;
        }

        .brand span {
            display: none;
        }

        .top-actions {
            flex-wrap: wrap;
            justify-content: flex-end;
        }

        .secondary-button span,
        .primary-button span {
            display: none;
        }

        .secondary-button,
        .primary-button {
            width: 38px;
            padding: 0;
        }

        .content-shell {
            height: calc(1080px - 78px);
        }

        .board {
            padding: 14px 12px 78px;
        }

        .audit-panel,
        .cohort-panel {
            flex-basis: 300px;
            width: 300px;
            min-width: 300px;
            max-width: 300px;
        }
    }
</style>
</head>
<body>
    <div class="app-shell__READONLY_CLASS____TRELLO_CLASS__">
        <header class="topbar">
            <div class="brand">
                <div class="brand-mark">__ICON_BOARD__</div>
                <div>
                    <h1>__BOARD_TITLE__</h1>
                    <span>__SUBTITLE__ - __VERSION__</span>
                </div>
            </div>
            <div class="top-actions">
                <span class="save-status" id="save-status">Guardado</span>
                <button class="secondary-button" type="button" id="logout-panel">__ICON_CLOSE__<span>Cerrar sesion</span></button>
                <button class="secondary-button" type="button" id="open-admin-page">__ICON_BOARD__<span>Administracion</span></button>
                <button class="secondary-button" type="button" id="open-sync">__ICON_USERS__<span>Sincronizar alumnos</span></button>
                <button class="secondary-button" type="button" id="add-list-top">__ICON_ADD__<span>Nueva lista</span></button>
                <button class="primary-button" type="button" id="open-new-card">__ICON_CARD__<span>Nueva tarjeta</span></button>
            </div>
        </header>

        <div class="content-shell">
            <main class="board" id="board" aria-label="Tablero visual PAES">
                __LISTS_HTML__
                __ADD_LIST_BUTTON__
                <aside class="side-panel audit-panel" id="audit-panel" aria-label="Logs del panel">
                    <div class="audit-header">
                        <h2>Historial</h2>
                        <p>Fecha, hora y modificacion. Logs y backups cifrados en data/.</p>
                    </div>
                    <div class="audit-list" id="audit-list">
                        <div class="audit-item">
                            <span class="audit-time">Fecha y hora: esperando eventos</span>
                            <div class="audit-action">Modificacion: sin logs cargados</div>
                            <div class="audit-detail">Los cambios del tablero apareceran aqui.</div>
                        </div>
                    </div>
                </aside>
            </main>
        </div>

        <div class="developer-credit">desarrollado por Pablo Gallardo</div>

        <div class="drawer-backdrop" id="drawer-backdrop"></div>
        <section class="admin-page" id="admin-page" aria-label="Administracion del panel">
            <div class="admin-page-header">
                <div>
                    <h2>Administracion</h2>
                    <p>Historial, alumnos y estadisticas agregadas. No permite borrar alumnos.</p>
                </div>
                <button class="secondary-button" type="button" id="close-admin-page">__ICON_CLOSE__<span>Volver</span></button>
            </div>
            <div class="admin-grid">
                <section class="admin-card admin-stats-card">
                    <div class="admin-section-title">
                        <h3>Resultados globales</h3>
                        <p id="admin-stats-exam">Ultimo ensayo</p>
                    </div>
                    <div class="admin-stats-grid">
                        <div><span>Promedio</span><strong id="admin-stat-average">--</strong></div>
                        <div><span>Mediana</span><strong id="admin-stat-median">--</strong></div>
                        <div><span>Desv. est.</span><strong id="admin-stat-stddev">--</strong></div>
                        <div><span>Minimo</span><strong id="admin-stat-min">--</strong><small id="admin-stat-min-student">--</small></div>
                        <div><span>Maximo</span><strong id="admin-stat-max">--</strong><small id="admin-stat-max-student">--</small></div>
                    </div>
                    <div class="admin-chart" id="admin-chart"></div>
                </section>
                <section class="admin-card admin-students-card">
                    <div class="admin-section-title">
                        <h3>Alumnos</h3>
                        <p>Verde activo, rojo archivado, amarillo no identificado.</p>
                    </div>
                    <div class="admin-student-summary">
                        <div><span>Activos</span><strong id="admin-active-count">--</strong></div>
                        <div><span>Archivados</span><strong id="admin-archived-count">--</strong></div>
                        <div><span>No identificados</span><strong id="admin-unknown-count">0</strong></div>
                    </div>
                    <button class="secondary-button admin-wide-button" type="button" id="admin-refresh-students">__ICON_USERS__<span>Configurar / agregar alumnos</span></button>
                    <p class="admin-hint">Solo detecta boards existentes en Trello. Crear o borrar alumnos se hace manualmente desde Trello.</p>
                    <div class="admin-avatar-grid" id="admin-avatar-grid"></div>
                </section>
                <section class="admin-card admin-history-card">
                    <div class="admin-section-title">
                        <h3>Historial</h3>
                        <p>Logs cifrados en data/logs.</p>
                    </div>
                    <div class="admin-history-list" id="admin-history-list"></div>
                </section>
            </div>
        </section>
        <aside class="drawer" id="drawer" aria-label="Editor de tarjeta">
            <div class="drawer-header">
                <div>
                    <h2 id="drawer-title">Nueva tarjeta</h2>
                    <p>Define material comun. En etapas futuras esto se copiara a los boards de alumnos.</p>
                </div>
                <button class="icon-button" type="button" id="close-drawer" aria-label="Cerrar editor">__ICON_CLOSE__</button>
            </div>

            <div class="drawer-scroll">
                <input id="editing-card-id" type="hidden">
                <div class="quick-start">
                    <div class="form-row">
                        <label for="card-list">Lista</label>
                        <select id="card-list">
                            <option value="">Selecciona una lista</option>
                        </select>
                    </div>
                    <div class="form-row">
                        <label for="card-title">Titulo</label>
                        <input id="card-title" placeholder="Nombre del material">
                    </div>
                </div>

                <div class="optional-tools">
                    <p class="optional-title">Anadir mas informacion opcional</p>
                    <div class="tool-row">
                        <button class="mini-button option-toggle" type="button" data-panel="description-panel">__ICON_EDIT__ Descripcion</button>
                        <button class="mini-button option-toggle" type="button" data-panel="links-panel">__ICON_LINK__ Links</button>
                        <button class="mini-button option-toggle" type="button" data-panel="images-panel">__ICON_IMAGE__ Imagenes</button>
                        <button class="mini-button option-toggle" type="button" data-panel="files-panel">__ICON_FILE__ PDFs</button>
                        <button class="mini-button option-toggle" type="button" data-panel="checklists-panel">__ICON_CHECK__ Checklists</button>
                    </div>
                    <p class="hint">Solo el titulo es obligatorio. Puedes guardar la tarjeta ahora y completar detalles despues.</p>
                </div>

                <div class="option-panel" id="description-panel">
                    <div class="form-row">
                        <label for="card-description">Descripcion</label>
                        <textarea id="card-description" placeholder="Indicaciones del material"></textarea>
                    </div>
                </div>

                <div class="option-panel" id="links-panel">
                    <div class="form-row">
                        <label for="card-links">Links</label>
                        <textarea id="card-links" placeholder="Un link por linea"></textarea>
                    </div>
                </div>

                <div class="option-panel" id="images-panel">
                    <label class="file-drop" for="card-image-files">
                        __ICON_IMAGE__ Adjuntar imagenes desde el equipo
                        <input id="card-image-files" type="file" accept="image/*" multiple>
                    </label>
                    <div class="image-preview" id="image-preview"></div>
                </div>

                <div class="option-panel" id="files-panel">
                    <label class="file-drop" for="card-pdf-files">
                        __ICON_FILE__ Adjuntar PDFs desde el equipo
                        <input id="card-pdf-files" type="file" accept="application/pdf,.pdf" multiple>
                    </label>
                    <div class="file-preview" id="file-preview"></div>
                </div>

                <div class="option-panel" id="checklists-panel">
                    <label>Checklists para alumnos</label>
                    <div class="checklists" id="checklists"></div>
                    <button class="mini-button" type="button" id="add-checklist">__ICON_ADD__ Anadir checklist</button>
                    <p class="hint">Cada checklist puede incluir una descripcion breve y un link clickeable a guias, videos, formularios u otros recursos.</p>
                </div>
            </div>

            <div class="drawer-actions">
                <button class="secondary-button" type="button" id="cancel-drawer">Cancelar</button>
                <button class="primary-button" type="button" id="save-card">Guardar tarjeta</button>
            </div>
        </aside>

        <div class="confirm-backdrop" id="confirm-backdrop"></div>
        <section class="confirm-dialog" id="confirm-dialog" aria-label="Confirmar cierre de lista">
            <h2>Cerrar lista</h2>
            <p id="confirm-message">Esta accion quitara la lista del prototipo visual.</p>
            <div class="confirm-actions">
                <button class="secondary-button" type="button" id="cancel-close-list">Cancelar</button>
                <button class="danger-button" type="button" id="confirm-close-list">__ICON_TRASH__ Cerrar lista</button>
            </div>
        </section>

        <div class="preview-backdrop" id="preview-backdrop"></div>
        <section class="preview-dialog" id="preview-dialog" aria-label="Vista previa de tarjeta">
            <div class="preview-header">
                <div>
                    <h2 id="preview-title">Vista previa</h2>
                    <p id="preview-subtitle">Material comun</p>
                </div>
                <button class="icon-button" type="button" id="close-preview" aria-label="Cerrar vista previa">__ICON_CLOSE__</button>
            </div>
            <div class="preview-body" id="preview-body"></div>
        </section>

        <div class="visibility-backdrop" id="visibility-backdrop"></div>
        <section class="visibility-dialog" id="visibility-dialog" aria-label="Filtro de alumnos">
            <div class="visibility-header">
                <div>
                    <h2 id="visibility-title">Filtrar alumnos</h2>
                    <p id="visibility-subtitle">Todos los alumnos ven este contenido por defecto. Desmarca quienes no deben recibirlo.</p>
                </div>
                <button class="icon-button" type="button" id="close-visibility" aria-label="Cerrar filtro">__ICON_CLOSE__</button>
            </div>
            <div class="visibility-tools">
                <button class="mini-button" type="button" id="visibility-select-all">Mostrar a todos</button>
                <button class="mini-button" type="button" id="visibility-clear-all">Ocultar a todos</button>
                <p class="visibility-status" id="visibility-status">Cargando alumnos...</p>
            </div>
            <div class="visibility-grid" id="visibility-grid"></div>
            <div class="visibility-actions">
                <button class="secondary-button" type="button" id="cancel-visibility">Cancelar</button>
                <button class="primary-button" type="button" id="save-visibility">Guardar filtro</button>
            </div>
        </section>

        <div class="sync-backdrop" id="sync-backdrop"></div>
        <section class="sync-dialog" id="sync-dialog" aria-label="Sincronizar alumnos">
            <div class="sync-header">
                <div>
                    <h2>Sincronizar alumnos</h2>
                    <p>Aplica cambios nuevos del panel en los alumnos seleccionados: crea, actualiza o archiva contenido entregado. Nunca toca Ensayos y crea backups antes de escribir.</p>
                </div>
                <button class="icon-button" type="button" id="close-sync" aria-label="Cerrar sincronizacion">__ICON_CLOSE__</button>
            </div>
            <div class="sync-body">
                <div class="sync-summary" id="sync-summary">
                    <div><span>Alumnos</span><strong>--</strong></div>
                    <div><span>Cambios</span><strong>--</strong></div>
                    <div><span>Errores</span><strong>--</strong></div>
                </div>
                <p class="sync-note" id="sync-note">Genera una vista previa. Solo apareceran contenidos nuevos marcados como pendientes desde este panel.</p>
                <div class="sync-actions-list" id="sync-actions-list">
                    <div class="sync-action-row">
                        <strong>Sin plan cargado</strong>
                        Presiona Vista previa para revisar cambios locales pendientes para los boards de alumnos.
                    </div>
                </div>
                <div class="sync-confirm">
                    <label for="sync-confirmation">Para aplicar escribe SINCRONIZAR</label>
                    <input id="sync-confirmation" placeholder="SINCRONIZAR" autocomplete="off">
                </div>
            </div>
            <div class="sync-footer">
                <button class="secondary-button" type="button" id="preview-sync">Vista previa</button>
                <button class="primary-button" type="button" id="apply-sync">Aplicar cambios</button>
            </div>
        </section>
    </div>

<script>
    const icons = {
        add: `__ICON_ADD__`,
        card: `__ICON_CARD__`,
        check: `__ICON_CHECK__`,
        edit: `__ICON_EDIT__`,
        image: `__ICON_IMAGE__`,
        file: `__ICON_FILE__`,
        link: `__ICON_LINK__`,
        arrowDown: `__ICON_ARROW_DOWN__`,
        arrowUp: `__ICON_ARROW_UP__`,
        trash: `__ICON_TRASH__`,
        users: `__ICON_USERS__`,
        view: `__ICON_VIEW__`,
    };

    const READ_ONLY = __READ_ONLY__;
    const TRELLO_API_BASE = "__TRELLO_API_BASE__";
    const TRELLO_API_TOKEN = "__TRELLO_API_TOKEN__";
    const COMPONENT_MODE = TRELLO_API_BASE === "__STREAMLIT_COMPONENT__";
    let COMPONENT_STATE = __COMPONENT_STATE_JSON__;
    const TRELLO_MODE = Boolean(TRELLO_API_BASE);
    const STORAGE_KEY = "admin-paes-board-state-v1";
    const AUDIT_STORAGE_KEY = "admin-paes-audit-events-v1";
    const defaultBoardData = __DATA_JSON__;
    let boardData = (READ_ONLY || TRELLO_MODE) ? defaultBoardData : loadBoardData(defaultBoardData);
    let pendingCloseListId = null;
    let attachedImages = [];
    let attachedFiles = [];
    let saveTimer = null;
    let trelloCooldownUntil = 0;
    const LIST_DRAG_THRESHOLD = 62;
    const CARD_DRAG_THRESHOLD = 22;
    const DIRECTION_LOCK_RATIO = 1.5;
    const LIST_STEP_THRESHOLD = 108;
    const LIST_REORDER_COOLDOWN = 140;

    const board = document.querySelector("#board");
    const drawer = document.querySelector("#drawer");
    const backdrop = document.querySelector("#drawer-backdrop");
    const listInput = document.querySelector("#card-list");
    const cardTitle = document.querySelector("#card-title");
    const cardDescription = document.querySelector("#card-description");
    const cardLinks = document.querySelector("#card-links");
    const imageInput = document.querySelector("#card-image-files");
    const imagePreview = document.querySelector("#image-preview");
    const fileInput = document.querySelector("#card-pdf-files");
    const filePreview = document.querySelector("#file-preview");
    const adminPage = document.querySelector("#admin-page");
    const adminAvatarGrid = document.querySelector("#admin-avatar-grid");
    const adminHistoryList = document.querySelector("#admin-history-list");
    const adminChart = document.querySelector("#admin-chart");
    const checklistsRoot = document.querySelector("#checklists");
    const editingCardId = document.querySelector("#editing-card-id");
    const optionPanels = [...document.querySelectorAll(".option-panel")];
    const confirmBackdrop = document.querySelector("#confirm-backdrop");
    const confirmDialog = document.querySelector("#confirm-dialog");
    const confirmMessage = document.querySelector("#confirm-message");
    const previewBackdrop = document.querySelector("#preview-backdrop");
    const previewDialog = document.querySelector("#preview-dialog");
    const previewTitle = document.querySelector("#preview-title");
    const previewSubtitle = document.querySelector("#preview-subtitle");
    const previewBody = document.querySelector("#preview-body");
    const visibilityBackdrop = document.querySelector("#visibility-backdrop");
    const visibilityDialog = document.querySelector("#visibility-dialog");
    const visibilityTitle = document.querySelector("#visibility-title");
    const visibilitySubtitle = document.querySelector("#visibility-subtitle");
    const visibilityGrid = document.querySelector("#visibility-grid");
    const visibilityStatus = document.querySelector("#visibility-status");
    const syncBackdrop = document.querySelector("#sync-backdrop");
    const syncDialog = document.querySelector("#sync-dialog");
    const syncSummary = document.querySelector("#sync-summary");
    const syncActionsList = document.querySelector("#sync-actions-list");
    const syncNote = document.querySelector("#sync-note");
    const syncConfirmation = document.querySelector("#sync-confirmation");
    const previewSyncButton = document.querySelector("#preview-sync");
    const applySyncButton = document.querySelector("#apply-sync");
    const saveStatus = document.querySelector("#save-status");
    const auditList = document.querySelector("#audit-list");
    const cohortActive = document.querySelector("#cohort-active");
    const cohortArchived = document.querySelector("#cohort-archived");
    const cohortList = document.querySelector("#cohort-list");
    const refreshCohortsButton = document.querySelector("#refresh-cohorts");
    let studentBoards = null;
    let activeVisibilityTarget = null;
    let hiddenStudentIds = new Set();
    let latestSyncPlan = null;
    let syncBusy = false;
    let syncMode = "idle";
    let syncLastStateAt = Date.now();
    let syncBusyStartedAt = 0;
    let syncStatusTimer = null;
    let syncActiveJobId = "";
    let lastComponentStateRev = null;

    function renderAdminChart(series = []) {
        if (!adminChart) return;
        const points = Array.isArray(series) ? series : [];
        if (!points.length) {
            adminChart.innerHTML = '<div class="audit-detail">Sin datos suficientes para graficar.</div>';
            return;
        }
        const width = 760;
        const height = 280;
        const left = 52;
        const right = 24;
        const top = 22;
        const bottom = 42;
        const yMin = 650;
        const yMax = 1000;
        const exams = points.map((point) => Number(point.exam || 0));
        const minExam = Math.min(...exams);
        const maxExam = Math.max(...exams);
        const span = Math.max(1, maxExam - minExam);
        const chartWidth = width - left - right;
        const chartHeight = height - top - bottom;
        const xFor = (exam) => left + ((Number(exam) - minExam) / span) * chartWidth;
        const yFor = (score) => top + ((yMax - Math.max(yMin, Math.min(yMax, Number(score)))) / (yMax - yMin)) * chartHeight;
        const polyline = points.map((point) => `${xFor(point.exam).toFixed(1)},${yFor(point.median).toFixed(1)}`).join(" ");
        const ticks = [650, 800, 1000].map((tick) => `
            <line class="grid" x1="${left}" x2="${width - right}" y1="${yFor(tick).toFixed(1)}" y2="${yFor(tick).toFixed(1)}" />
            <text class="chart-text" x="${left - 9}" y="${(yFor(tick) + 4).toFixed(1)}" text-anchor="end" stroke="none" stroke-width="0">${tick}</text>
        `).join("");
        const labels = points.map((point) => `
            <text class="chart-text" x="${xFor(point.exam).toFixed(1)}" y="${height - 12}" text-anchor="middle" stroke="none" stroke-width="0">${escapeHtml(point.exam)}</text>
        `).join("");
        const circles = points.map((point) => `
            <circle cx="${xFor(point.exam).toFixed(1)}" cy="${yFor(point.median).toFixed(1)}" r="5">
                <title>Ensayo ${escapeHtml(point.exam)}: mediana ${escapeHtml(point.median)}</title>
            </circle>
        `).join("");
        adminChart.innerHTML = `
            <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Grafico ampliado de mediana por ensayo">
                <g>${ticks}</g>
                <line class="axis" x1="${left}" x2="${width - right}" y1="${height - bottom}" y2="${height - bottom}" />
                <line class="axis" x1="${left}" x2="${left}" y1="${top}" y2="${height - bottom}" />
                <polyline class="series" points="${polyline}" />
                <g>${circles}</g>
                <g>${labels}</g>
                <text class="chart-title-text" x="${left}" y="14" text-anchor="middle" stroke="none" stroke-width="0">Puntaje</text>
                <text class="chart-title-text" x="${left + chartWidth / 2}" y="${height - 4}" text-anchor="middle" stroke="none" stroke-width="0">Ensayo</text>
            </svg>
        `;
    }

    function renderAdminDashboard(data) {
        const stats = data?.stats || {};
        const cohort = data?.cohort || {};
        const students = Array.isArray(cohort.students) ? cohort.students : [];
        const unknownBoards = Array.isArray(data?.unknown_boards) ? data.unknown_boards : [];
        document.querySelector("#admin-stats-exam").textContent = stats.exam || "Ultimo ensayo";
        document.querySelector("#admin-stat-average").textContent = stats.average ?? "--";
        document.querySelector("#admin-stat-median").textContent = stats.median ?? "--";
        document.querySelector("#admin-stat-stddev").textContent = stats.stddev ?? "--";
        document.querySelector("#admin-stat-min").textContent = stats.min?.score ?? "--";
        document.querySelector("#admin-stat-min-student").textContent = stats.min?.student ?? "--";
        document.querySelector("#admin-stat-max").textContent = stats.max?.score ?? "--";
        document.querySelector("#admin-stat-max-student").textContent = stats.max?.student ?? "--";
        document.querySelector("#admin-active-count").textContent = cohort.active ?? "--";
        document.querySelector("#admin-archived-count").textContent = cohort.archived ?? "--";
        document.querySelector("#admin-unknown-count").textContent = data?.unknown_count ?? 0;
        renderAdminChart(data?.series || []);
        const studentAvatars = students.map((student) => {
            const status = student.status === "open" ? "active" : "archived";
            return `
                <div class="admin-avatar ${status === "archived" ? "is-archived" : ""}"
                    title="${escapeHtml(student.student_name || student.board_name || "Alumno")} - ${status === "active" ? "activo" : "archivado"}">
                    ${escapeHtml(student.initials || "?")}
                </div>
            `;
        }).join("");
        const unknownAvatars = unknownBoards.map((board) => `
            <div class="admin-avatar is-unknown"
                title="${escapeHtml(board.board_name || "Board no identificado")} - no identificado">
                ?
            </div>
        `).join("");
        adminAvatarGrid.innerHTML = studentAvatars + unknownAvatars || '<div class="audit-detail">Sin alumnos cargados.</div>';
        const events = (Array.isArray(data?.events) ? data.events : []).filter((event) => {
            const action = String(event.action || "");
            const detail = String(event.detail || "");
            if (action === "backup_database" || action === "backup_board") return false;
            if (action === "trello_action" && detail.includes("Accion local no soportada")) return false;
            return true;
        });
        adminHistoryList.innerHTML = events.map((event) => `
            <div class="audit-item ${event.status === "error" ? "is-error" : ""}">
                <span class="audit-time">Fecha y hora: ${escapeHtml(formatAuditTime(event.timestamp))}</span>
                <div class="audit-action">Modificacion: ${escapeHtml(event.action || "evento")}</div>
                <div class="audit-detail">${escapeHtml(event.detail || "")}</div>
            </div>
        `).join("") || '<div class="audit-detail">Sin historial cargado.</div>';
    }

    async function loadAdminDashboard(refresh = false) {
        if (!TRELLO_MODE) return;
        if (COMPONENT_MODE && !refresh) {
            const cached = COMPONENT_STATE["/admin-dashboard"];
            if (cached?.ok) {
                renderAdminDashboard(cached.result);
                return cached.result;
            }
            if (cached?.error) throw new Error(cached.error);
        }
        const data = await callLocalApi("/admin-dashboard", { refresh, limit: 80 });
        renderAdminDashboard(data);
        return data;
    }

    async function openAdminPage() {
        adminPage.classList.add("is-open");
        try {
            setSaveStatus("Cargando administracion", "saving");
            await loadAdminDashboard(false);
            setSaveStatus("Administracion lista");
        } catch (error) {
            setSaveStatus("Error admin", "error");
            adminHistoryList.innerHTML = `
                <div class="audit-item is-error">
                    <span class="audit-time">Error</span>
                    <div class="audit-action">No se pudo cargar administracion</div>
                    <div class="audit-detail">${escapeHtml(error.message)}</div>
                </div>
            `;
        }
    }

    function closeAdminPage() {
        adminPage.classList.remove("is-open");
    }

    async function refreshAdminStudents() {
        try {
            setSaveStatus("Actualizando alumnos", "saving");
            await loadAdminDashboard(true);
            await refreshAuditLog();
            setSaveStatus("Alumnos actualizados");
        } catch (error) {
            setSaveStatus("Error alumnos", "error");
            alert(error.message);
        }
    }

    function normalizeBoardData(lists, fallbackLists) {
        const source = Array.isArray(lists) ? lists : [];
        const fallback = Array.isArray(fallbackLists) ? fallbackLists : [];
        const lockedLists = fallback.filter((list) => list.kind === "locked");
        const editableFallback = fallback.filter((list) => list.kind !== "locked");
        const editableListsFromStorage = source
            .filter((list) => list && list.kind !== "locked" && list.id && list.name)
            .map((list) => ({
                id: String(list.id),
                name: String(list.name),
                cards: Array.isArray(list.cards) ? list.cards : [],
            }));

        return [...lockedLists, ...(editableListsFromStorage.length ? editableListsFromStorage : editableFallback)];
    }

    function loadBoardData(fallbackLists) {
        try {
            const stored = window.localStorage.getItem(STORAGE_KEY);
            if (!stored) return fallbackLists;
            return normalizeBoardData(JSON.parse(stored), fallbackLists);
        } catch (error) {
            console.warn("No se pudo cargar el tablero guardado", error);
            return fallbackLists;
        }
    }

    function setSaveStatus(text, mode = "saved") {
        if (!saveStatus) return;
        saveStatus.textContent = text;
        saveStatus.classList.toggle("is-saving", mode === "saving");
        saveStatus.classList.toggle("is-error", mode === "error");
    }

    function persistBoardData() {
        if (READ_ONLY) return;
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(boardData));
            setSaveStatus("Guardado");
        } catch (error) {
            console.error("No se pudo guardar el tablero", error);
            setSaveStatus("Sin guardar", "error");
        }
    }

    function schedulePersistBoardData() {
        if (READ_ONLY || TRELLO_MODE) return;
        setSaveStatus("Guardando", "saving");
        window.clearTimeout(saveTimer);
        saveTimer = window.setTimeout(persistBoardData, 180);
    }

    function auditForTrelloAction(path, payload = {}) {
        if (path === "/create-list") {
            return {
                action: "Crear lista",
                detail: `Se creo la lista "${payload.name || "sin nombre"}".`,
                meta: { list_name: payload.name || "" },
            };
        }
        if (path === "/save-card") {
            return {
                action: payload.card_id ? "Editar tarjeta" : "Crear tarjeta",
                detail: `Se ${payload.card_id ? "actualizo" : "creo"} la tarjeta "${payload.title || "sin titulo"}"${payload.list_name ? ` en "${payload.list_name}"` : ""}.`,
                meta: { card_id: payload.card_id || "", list_id: payload.list_id || "" },
            };
        }
        if (path === "/archive-list") {
            return {
                action: "Eliminar lista",
                detail: `Se archivo la lista "${payload.list_name || payload.list_id || "sin nombre"}".`,
                meta: { list_id: payload.list_id || "" },
            };
        }
        if (path === "/archive-card") {
            return {
                action: "Eliminar tarjeta",
                detail: `Se archivo la tarjeta "${payload.card_title || payload.card_id || "sin titulo"}"${payload.list_name ? ` de "${payload.list_name}"` : ""}.`,
                meta: { card_id: payload.card_id || "" },
            };
        }
        if (path === "/move-list") {
            return {
                action: "Mover lista",
                detail: `Se movio la lista "${payload.list_name || payload.list_id || "sin nombre"}".`,
                meta: { list_id: payload.list_id || "" },
            };
        }
        if (path === "/move-card") {
            return {
                action: "Mover tarjeta",
                detail: `Se movio la tarjeta "${payload.card_title || payload.card_id || "sin titulo"}"${payload.list_name ? ` en "${payload.list_name}"` : ""}.`,
                meta: { card_id: payload.card_id || "", list_id: payload.list_id || "" },
            };
        }
        return null;
    }

    async function callTrelloAction(path, payload) {
        if (!TRELLO_MODE) return null;
        if (Date.now() < trelloCooldownUntil) {
            throw new Error("Trello esta limitando temporalmente las llamadas. Espera un momento antes de intentar de nuevo.");
        }
        const audit = auditForTrelloAction(path, payload);
        if (audit) {
            storeLocalAuditEvent(audit.action, audit.detail, audit.meta);
        }
        setSaveStatus(path.startsWith("/sync-") ? "Sincronizando" : "Guardando en servidor", "saving");
        if (COMPONENT_MODE) {
            const actionId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
            window.parent.postMessage({
                source: "admin-paes-component-action",
                action: { id: actionId, path, payload, audit },
            }, "*");
            return {
                id: payload.id || payload.list_id || `pending-${actionId}`,
                card_id: payload.card_id || payload.id || `pending-${actionId}`,
                name: payload.name || payload.title || "",
                pos: payload.pos || Date.now(),
            };
        }
        const response = await fetch(`${TRELLO_API_BASE}${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Admin-PAES-Token": TRELLO_API_TOKEN },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
            if (response.status === 429 || String(data.error || "").includes("Rate limit")) {
                trelloCooldownUntil = Date.now() + 120000;
                setSaveStatus("Pausa API", "error");
            }
            throw new Error(data.error || "No se pudo actualizar Trello.");
        }
        setSaveStatus("Actualizado");
        if (audit) {
            fetch(`${TRELLO_API_BASE}/audit-event`, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Admin-PAES-Token": TRELLO_API_TOKEN },
                body: JSON.stringify(audit),
            }).catch((error) => console.warn("No se pudo persistir auditoria.", error));
        }
        refreshAuditLog();
        return data.result;
    }

    function componentFallbackResult(path) {
        if (path === "/sync-preview-students") {
            return { component_pending: true, kind: "preview" };
        }
        if (path === "/sync-start-students") {
            return { component_pending: true, kind: "start" };
        }
        if (path === "/sync-status") {
            return { component_pending: true, kind: "status", status: "queued", progress: [] };
        }
        if (path === "/audit-log") {
            return { events: localAuditEvents() };
        }
        if (path === "/student-boards") {
            return COMPONENT_STATE["/student-boards"]?.result || { students: [] };
        }
        if (path === "/visibility-open") {
            return COMPONENT_STATE["/visibility-open"]?.result || { students: [], hidden_student_ids: [], component_pending: true };
        }
        if (path === "/visibility-get") {
            return COMPONENT_STATE["/visibility-get"]?.result || { hidden_student_ids: [], component_pending: true };
        }
        if (path === "/admin-dashboard") {
            return COMPONENT_STATE["/admin-dashboard"] || {};
        }
        if (path === "/cohort-status") {
            return COMPONENT_STATE["/cohort-status"] || {};
        }
        if (path === "/refresh-results") {
            return COMPONENT_STATE["/refresh-results"] || null;
        }
        return null;
    }

    async function callLocalApi(path, payload = {}) {
        if (!TRELLO_MODE) return null;
        if (COMPONENT_MODE) {
            const cached = COMPONENT_STATE[path];
            const canUseCached = (path === "/admin-dashboard" && !payload?.refresh) || path === "/cohort-status" || path === "/student-boards";
            if (canUseCached && cached && cached.ok) return cached.result;
            if (canUseCached && cached && cached.error) throw new Error(cached.error);
            const actionId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
            const uiState = path.startsWith("/sync-")
                ? { screen: "sync" }
                : path.startsWith("/admin-dashboard") || path.startsWith("/refresh-cohorts")
                    ? { screen: "admin" }
                    : path.startsWith("/visibility-") || path === "/student-boards"
                        ? { screen: "visibility" }
                        : {};
            window.parent.postMessage({
                source: "admin-paes-component-action",
                action: { id: actionId, path, payload, ui_state: uiState },
            }, "*");
            setSaveStatus(path.startsWith("/sync-") ? "Sincronizando" : "Procesando en servidor", "saving");
            return componentFallbackResult(path);
        }
        let response;
        try {
            response = await fetch(`${TRELLO_API_BASE}${path}`, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Admin-PAES-Token": TRELLO_API_TOKEN },
                body: JSON.stringify(payload),
            });
        } catch (error) {
            throw new Error("API local no disponible. Recarga la pagina del panel e inicia sesion nuevamente si es necesario.");
        }
        const data = await response.json();
        if (!response.ok || !data.ok) {
            throw new Error(data.error || "No se pudo consultar configuracion local.");
        }
        return data.result;
    }

    function renderCohortPanel(cohort) {
        if (!cohortActive || !cohortArchived || !cohortList) return;
        const students = Array.isArray(cohort?.students) ? cohort.students : [];
        cohortActive.textContent = String(cohort?.active ?? "--");
        cohortArchived.textContent = String(cohort?.archived ?? "--");
        const visible = [
            ...students.filter((student) => student.status === "open").slice(0, 18),
            ...students.filter((student) => student.status !== "open").slice(0, 8),
        ];
        if (!visible.length) {
            cohortList.innerHTML = `
                <div class="audit-item">
                    <span class="audit-time">Sin alumnos cargados</span>
                    <div class="audit-action">Actualiza cohortes</div>
                    <div class="audit-detail">Se leeran boards abiertos PAES desde Trello.</div>
                </div>
            `;
            return;
        }
        cohortList.innerHTML = visible.map((student) => {
            const archived = student.status !== "open";
            return `
                <div class="cohort-item" title="${escapeHtml(student.board_name || student.student_name || "")}">
                    <div class="cohort-avatar">${escapeHtml(student.initials || "?")}</div>
                    <div>
                        <div class="cohort-name">${escapeHtml(student.student_name || student.board_name || "Alumno")}</div>
                        <div class="cohort-meta">${archived ? "Archivado en Trello" : "Board activo"}</div>
                    </div>
                    <span class="cohort-status ${archived ? "is-archived" : ""}">${archived ? "archivado" : "activo"}</span>
                </div>
            `;
        }).join("");
    }

    async function loadCohortStatus() {
        if (!TRELLO_MODE) return;
        try {
            const cohort = await callLocalApi("/cohort-status", {});
            renderCohortPanel(cohort);
        } catch (error) {
            if (cohortList) {
                cohortList.innerHTML = `
                    <div class="audit-item is-error">
                        <span class="audit-time">Error cohortes</span>
                        <div class="audit-action">No se pudo cargar</div>
                        <div class="audit-detail">${escapeHtml(error.message)}</div>
                    </div>
                `;
            }
        }
    }

    async function refreshCohorts() {
        if (!TRELLO_MODE) {
            alert("Actualizar cohortes requiere conexion activa con Trello.");
            return;
        }
        try {
            if (refreshCohortsButton) refreshCohortsButton.disabled = true;
            setSaveStatus("Actualizando alumnos", "saving");
            const result = await callLocalApi("/refresh-cohorts", {});
            renderCohortPanel(result.cohort);
            const summary = result.summary || {};
            setSaveStatus("Cohortes listas");
            await refreshAuditLog();
            if ((summary.new_board_ids || []).length || (summary.archived_board_ids || []).length) {
                await previewStudentSync();
            }
        } catch (error) {
            setSaveStatus("Error cohortes", "error");
            if (cohortList) {
                cohortList.innerHTML = `
                    <div class="audit-item is-error">
                        <span class="audit-time">Error cohortes</span>
                        <div class="audit-action">No se pudo actualizar</div>
                        <div class="audit-detail">${escapeHtml(error.message)}</div>
                    </div>
                `;
            }
        } finally {
            if (refreshCohortsButton) refreshCohortsButton.disabled = false;
        }
    }

    function openSyncModal() {
        latestSyncPlan = null;
        syncMode = "idle";
        syncActiveJobId = "";
        if (syncStatusTimer) {
            window.clearTimeout(syncStatusTimer);
            syncStatusTimer = null;
        }
        syncConfirmation.value = "";
        syncNote.textContent = "Genera una vista previa. Solo apareceran contenidos nuevos marcados como pendientes desde este panel.";
        renderSyncPlan(null);
        setSyncBusy(false);
        syncBackdrop.classList.add("is-open");
        syncDialog.classList.add("is-open");
    }

    function closeSyncModal() {
        if (syncBusy) {
            syncNote.textContent = syncMode === "preview"
                ? "Cargando vista previa... espera a que termine antes de cerrar."
                : "Sincronizando... espera a que termine antes de cerrar esta ventana.";
            return;
        }
        if (syncStatusTimer) {
            window.clearTimeout(syncStatusTimer);
            syncStatusTimer = null;
        }
        syncBackdrop.classList.remove("is-open");
        syncDialog.classList.remove("is-open");
        if (COMPONENT_MODE) {
            window.parent.postMessage({
                source: "admin-paes-component-action",
                action: {
                    id: `ui-${Date.now()}-${Math.random().toString(16).slice(2)}`,
                    path: "/ui-state",
                    payload: { screen: "board" },
                },
            }, "*");
        }
    }

    function renderSyncPlan(plan) {
        const actions = plan?.actions || [];
        const errors = plan?.errors || [];
        syncSummary.innerHTML = `
            <div><span>Alumnos</span><strong>${escapeHtml(plan?.students ?? "--")}</strong></div>
            <div><span>Cambios</span><strong>${escapeHtml(actions.length || "--")}</strong></div>
            <div><span>Errores</span><strong>${escapeHtml(errors.length || "--")}</strong></div>
        `;
        if (!plan) {
            syncActionsList.innerHTML = `
                <div class="sync-action-row">
                    <strong>Sin plan cargado</strong>
                    Presiona Vista previa para ver listas o tarjetas nuevas pendientes.
                </div>
            `;
            return;
        }
        if (!actions.length && !errors.length) {
            syncActionsList.innerHTML = `
                <div class="sync-action-row">
                    <strong>Todo sincronizado</strong>
                    No se encontraron cambios seguros pendientes.
                </div>
            `;
            return;
        }
        const labels = plan.labels || {};
        const shown = actions.slice(0, 80).map((action) => `
            <div class="sync-action-row">
                <strong>${escapeHtml(labels[action.action] || action.action)} - ${escapeHtml(action.student_name || action.board_name || "Alumno")}</strong>
                ${escapeHtml(action.list_name || "Lista")} ${action.card_title ? ` / ${escapeHtml(action.card_title)}` : ""}<br>
                ${escapeHtml(action.detail || "")}
            </div>
        `).join("");
        const hiddenCount = actions.length > 80 ? `
            <div class="sync-action-row">
                <strong>${actions.length - 80} cambio(s) adicionales</strong>
                Se aplicaran en orden si confirmas la sincronizacion.
            </div>
        ` : "";
        const errorRows = errors.slice(0, 12).map((error) => `
            <div class="sync-action-row">
                <strong>Error leyendo ${escapeHtml(error.student_name || error.board_id || "board")}</strong>
                ${escapeHtml(error.error || "Error desconocido")}
            </div>
        `).join("");
        syncActionsList.innerHTML = shown + hiddenCount + errorRows;
    }

    function syncTotalChanges(job, plan = latestSyncPlan) {
        const actions = plan?.actions || [];
        return actions.length || Number(job?.result?.planned || 0) || Number(job?.result?.applied || 0) || 0;
    }

    function syncCompletedChanges(job, plan = latestSyncPlan) {
        const total = syncTotalChanges(job, plan);
        const progress = job?.progress || job?.result?.board_results || [];
        const completed = progress.reduce((sum, item) => {
            const applied = Number(item?.applied || 0);
            const errors = Number(item?.errors || 0);
            return sum + applied + errors;
        }, 0);
        if (job?.status === "done" && job?.result) {
            return Math.min(total || completed, Number(job.result.applied || 0) + Number((job.result.errors || []).length || 0));
        }
        return total ? Math.min(completed, total) : completed;
    }

    function syncProgressText(job, plan = latestSyncPlan) {
        const total = syncTotalChanges(job, plan);
        const completed = syncCompletedChanges(job, plan);
        const width = Math.max(2, String(total || 0).length);
        const doneText = String(completed).padStart(width, "0");
        const totalText = total ? String(total).padStart(width, "0") : "??";
        return `Sincronizando cambios... ${doneText}/${totalText} completados.`;
    }

    function updateSyncSummaryFromJob(job, plan = latestSyncPlan) {
        const actions = plan?.actions || [];
        const errors = [...(plan?.errors || []), ...(job?.result?.errors || []), ...(job?.errors || [])];
        const progress = job?.progress || [];
        const boardCount = plan?.students ?? job?.total_boards ?? progress.length ?? "--";
        const changeCount = actions.length || job?.result?.planned || job?.result?.applied || "--";
        syncSummary.innerHTML = `
            <div><span>Alumnos</span><strong>${escapeHtml(boardCount)}</strong></div>
            <div><span>Cambios</span><strong>${escapeHtml(changeCount)}</strong></div>
            <div><span>Errores</span><strong>${escapeHtml(errors.length || "--")}</strong></div>
        `;
    }

    function renderSyncProgress(job, plan = latestSyncPlan) {
        updateSyncSummaryFromJob(job, plan);
        const actions = plan?.actions || [];
        const boards = new Map();
        actions.forEach((action) => {
            const boardId = action.board_id || action.student_name || action.board_name || "board";
            if (!boards.has(boardId)) {
                boards.set(boardId, {
                    board_id: boardId,
                    student_name: action.student_name || action.board_name || "Alumno",
                    status: "pending",
                    detail: "Pendiente",
                    applied: 0,
                    errors: 0,
                });
            }
        });
        (job?.progress || []).forEach((event) => {
            const boardId = event.board_id || event.student_name || "board";
            boards.set(boardId, {
                board_id: boardId,
                student_name: event.student_name || boardId,
                status: event.status || "syncing",
                detail: event.detail || "",
                applied: event.applied || 0,
                errors: event.errors || 0,
            });
        });
        if (!boards.size) {
            syncActionsList.innerHTML = `
                <div class="sync-action-row">
                    <strong>Sin boards pendientes</strong>
                    No hay acciones para aplicar.
                </div>
            `;
            return;
        }
        syncActionsList.innerHTML = [...boards.values()].map((board) => {
            const status = board.status === "done" ? "done" : board.status === "error" ? "error" : board.status === "syncing" ? "syncing" : "pending";
            const icon = status === "done" ? "OK" : status === "error" ? "!" : status === "syncing" ? "..." : "o";
            const detail = board.detail || (status === "done" ? "Completado" : status === "syncing" ? "Sincronizando" : "Pendiente");
            return `
                <div class="sync-board-row is-${status}">
                    <span class="sync-board-icon">${icon}</span>
                    <span>
                        <strong>${escapeHtml(board.student_name || "Alumno")}</strong>
                        ${escapeHtml(detail)}
                    </span>
                </div>
            `;
        }).join("");
    }

    function setSyncBusy(isBusy, text = "") {
        const wasBusy = syncBusy;
        syncBusy = isBusy;
        if (isBusy) {
            syncLastStateAt = Date.now();
            if (!wasBusy) syncBusyStartedAt = Date.now();
        } else {
            syncBusyStartedAt = 0;
        }
        previewSyncButton.disabled = isBusy;
        applySyncButton.disabled = isBusy;
        document.querySelector("#close-sync").disabled = isBusy;
        previewSyncButton.classList.toggle("is-disabled", isBusy);
        applySyncButton.classList.toggle("is-disabled", isBusy);
        document.querySelector("#close-sync").classList.toggle("is-disabled", isBusy);
        syncDialog.classList.toggle("is-syncing", isBusy);
        syncBackdrop.classList.toggle("is-syncing", isBusy);
        if (text) syncNote.textContent = text;
    }

    function scheduleSyncStatus(jobId) {
        if (!COMPONENT_MODE || !jobId) return;
        syncActiveJobId = jobId;
        if (syncStatusTimer) {
            window.clearTimeout(syncStatusTimer);
            syncStatusTimer = null;
        }
        syncStatusTimer = window.setTimeout(() => {
            syncStatusTimer = null;
            if (!syncDialog.classList.contains("is-open")) return;
            callLocalApi("/sync-status", { job_id: jobId }).catch((error) => {
                syncMode = "error";
                syncNote.textContent = error.message;
                setSyncBusy(false);
                setSaveStatus("Error sync", "error");
            });
        }, 2600);
    }

    async function previewStudentSync() {
        try {
            syncMode = "preview";
            setSyncBusy(true, "Preparando vista previa...");
            setSaveStatus("Comparando", "saving");
            syncNote.textContent = "Leyendo boards PAES y buscando contenido nuevo pendiente...";
            latestSyncPlan = await callLocalApi("/sync-preview-students", {});
            if (latestSyncPlan?.component_pending) {
                syncNote.textContent = "Vista previa enviada al servidor. Espera unos segundos...";
                return;
            }
            renderSyncPlan(latestSyncPlan);
            syncNote.textContent = "Vista previa lista. Revisa el contenido nuevo antes de aplicar.";
            setSaveStatus("Plan listo");
            refreshAuditLog();
        } catch (error) {
            syncNote.textContent = error.message;
            setSaveStatus("Error sync", "error");
            renderSyncPlan({ students: 0, actions: [], errors: [{ error: error.message }] });
        } finally {
            if (!(COMPONENT_MODE && syncNote.textContent.includes("Vista previa enviada al servidor"))) {
                syncMode = "idle";
                setSyncBusy(false);
            }
        }
    }

    async function applyStudentSync() {
        if (syncConfirmation.value.trim() !== "SINCRONIZAR") {
            syncNote.textContent = "Escribe SINCRONIZAR para aplicar cambios en boards de alumnos.";
            return;
        }
        try {
            const total = latestSyncPlan?.actions?.length || 0;
            syncMode = "sync";
            setSyncBusy(true, syncProgressText({ progress: [] }, latestSyncPlan));
            setSaveStatus("Sincronizando", "saving");
            renderSyncProgress({ progress: [] });
            syncNote.textContent = `${syncProgressText({ progress: [] }, latestSyncPlan)} Esta ventana queda bloqueada hasta terminar.`;
            let result = null;
            try {
                const started = await callLocalApi("/sync-start-students", {
                    confirmation: syncConfirmation.value.trim(),
                    max_actions: Math.max(total, 500),
                });
                if (COMPONENT_MODE) {
                    syncActiveJobId = started?.job_id || "";
                    syncNote.textContent = "Sincronizacion iniciada en servidor. Se actualizaran los checks progresivamente.";
                    scheduleSyncStatus(syncActiveJobId);
                    return;
                }
                const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
                let job = started;
                while (!["done", "error"].includes(job.status)) {
                    await wait(1200);
                    job = await callLocalApi("/sync-status", { job_id: started.job_id });
                    renderSyncProgress(job);
                    syncNote.textContent = syncProgressText(job, latestSyncPlan);
                }
                renderSyncProgress(job);
                result = job.result || {};
            } catch (jobError) {
                if (!String(jobError.message || "").includes("Accion local no soportada")) {
                    throw jobError;
                }
                syncNote.textContent = "Servidor local antiguo detectado. Usando sincronizacion compatible...";
                result = await callLocalApi("/sync-apply-students", {
                    confirmation: syncConfirmation.value.trim(),
                    max_actions: Math.max(total, 500),
                });
                renderSyncProgress({ progress: result.board_results || [] });
            }
            const planned = result.planned || total || 0;
            const applied = result.applied || 0;
            syncNote.textContent = `Sincronizacion lista: ${applied}/${planned} aplicado(s). Backups creados: ${(result.backups || []).length}.`;
            syncConfirmation.value = "";
            await refreshAuditLog();
            setSaveStatus("Sincronizado");
            latestSyncPlan = await callLocalApi("/sync-preview-students", {});
            renderSyncPlan(latestSyncPlan);
        } catch (error) {
            syncNote.textContent = error.message;
            setSaveStatus("Error sync", "error");
            refreshAuditLog();
        } finally {
            if (!(COMPONENT_MODE && syncNote.textContent.includes("Sincronizacion iniciada en servidor"))) {
                syncMode = "idle";
                setSyncBusy(false);
            }
        }
    }

    async function loadStudentBoards() {
        if (studentBoards) return studentBoards;
        const result = await callLocalApi("/student-boards");
        studentBoards = Array.isArray(result?.students) ? result.students : [];
        return studentBoards;
    }

    function renderStudentGrid() {
        const students = studentBoards || [];
        if (!students.length) {
            visibilityGrid.innerHTML = '<p class="visibility-status">No se encontraron tableros PAES de alumnos.</p>';
            visibilityStatus.textContent = "Sin alumnos cargados";
            return;
        }
        visibilityGrid.innerHTML = students.map((student) => {
            const hidden = hiddenStudentIds.has(student.board_id);
            return `
                <button class="student-chip ${hidden ? "is-hidden" : ""}" type="button"
                    data-board-id="${escapeHtml(student.board_id)}"
                    title="${escapeHtml(student.student_name)}">
                    ${escapeHtml(student.initials || "?")}
                </button>
            `;
        }).join("");
        const visibleCount = students.length - hiddenStudentIds.size;
        visibilityStatus.textContent = `${visibleCount}/${students.length} alumnos reciben este contenido`;
    }

    async function openVisibilityModal(contentType, contentId, title) {
        if (!TRELLO_MODE) {
            alert("En modo VM seguro, la visibilidad se guarda desde este tablero y se aplica al sincronizar alumnos.");
            return;
        }
        activeVisibilityTarget = { contentType, contentId, title };
        hiddenStudentIds = new Set();
        visibilityTitle.textContent = "Filtrar alumnos";
        visibilitySubtitle.textContent = `${contentType === "list" ? "Lista" : "Tarjeta"}: ${title}. Desmarca alumnos para ocultar este contenido al sincronizar.`;
        visibilityGrid.innerHTML = '<p class="visibility-status">Cargando alumnos...</p>';
        visibilityStatus.textContent = "Preparando grilla";
        visibilityBackdrop.classList.add("is-open");
        visibilityDialog.classList.add("is-open");
        try {
            const result = await callLocalApi("/visibility-open", {
                content_type: contentType,
                content_id: contentId,
            });
            if (result?.component_pending) {
                visibilityStatus.textContent = "Cargando alumnos desde el servidor...";
                return;
            }
            studentBoards = Array.isArray(result?.students) ? result.students : [];
            hiddenStudentIds = new Set(result?.hidden_student_ids || []);
            renderStudentGrid();
        } catch (error) {
            visibilityStatus.textContent = "No se pudo cargar alumnos";
            visibilityGrid.innerHTML = `<p class="visibility-status">${escapeHtml(error.message)}</p>`;
        }
    }

    function closeVisibilityModal() {
        visibilityBackdrop.classList.remove("is-open");
        visibilityDialog.classList.remove("is-open");
        activeVisibilityTarget = null;
        hiddenStudentIds = new Set();
    }

    async function saveVisibilityFilter() {
        if (!activeVisibilityTarget) return;
        try {
            setSaveStatus("Guardando filtro", "saving");
            await callLocalApi("/visibility-save", {
                content_type: activeVisibilityTarget.contentType,
                content_id: activeVisibilityTarget.contentId,
                content_title: activeVisibilityTarget.title,
                students: studentBoards || [],
                hidden_student_ids: [...hiddenStudentIds],
            });
            storeLocalAuditEvent(
                "Configurar visibilidad",
                `Se actualizo visibilidad de "${activeVisibilityTarget.title}". ${hiddenStudentIds.size} alumno(s) ocultos.`,
                { content_type: activeVisibilityTarget.contentType, content_id: activeVisibilityTarget.contentId }
            );
            setSaveStatus("Filtro guardado");
            refreshAuditLog();
            closeVisibilityModal();
        } catch (error) {
            setSaveStatus("Error", "error");
            alert(error.message);
        }
    }

    function localAuditEvents() {
        try {
            return JSON.parse(window.localStorage.getItem(AUDIT_STORAGE_KEY) || "[]");
        } catch (error) {
            return [];
        }
    }

    function storeLocalAuditEvent(action, detail, meta = {}, status = "ok") {
        const event = {
            timestamp: new Date().toISOString(),
            status,
            action,
            detail,
            meta,
            source: "browser",
        };
        const events = [event, ...localAuditEvents()].slice(0, 80);
        window.localStorage.setItem(AUDIT_STORAGE_KEY, JSON.stringify(events));
        renderAuditLog(events);
        return event;
    }

    async function writeAuditEvent(action, detail, meta = {}) {
        storeLocalAuditEvent(action, detail, meta);
        if (!TRELLO_MODE) return;
        try {
            await fetch(`${TRELLO_API_BASE}/audit-event`, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Admin-PAES-Token": TRELLO_API_TOKEN },
                body: JSON.stringify({ action, detail, meta }),
            });
            refreshAuditLog();
        } catch (error) {
            console.warn("No se pudo registrar el evento local.", error);
        }
    }

    function formatAuditTime(value) {
        if (!value) return "";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        return date.toLocaleString("es-CL", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function renderAuditLog(events = []) {
        if (!auditList) return;
        if (!events.length) {
            auditList.innerHTML = `
                <div class="audit-item">
                <span class="audit-time">Fecha y hora: sin eventos</span>
                    <div class="audit-action">Modificacion: logs preparados</div>
                    <div class="audit-detail">Los cambios y backups apareceran aqui.</div>
                </div>
            `;
            return;
        }
        const cleanEvents = events.filter((event) => {
            const action = String(event.action || "");
            const detail = String(event.detail || "");
            if (action === "backup_database" || action === "backup_board") return false;
            if (action === "trello_action" && detail.includes("Accion local no soportada")) return false;
            return true;
        });
        auditList.innerHTML = cleanEvents.map((event) => `
            <div class="audit-item ${event.status === "error" ? "is-error" : ""}">
                <span class="audit-time">Fecha y hora: ${escapeHtml(formatAuditTime(event.timestamp))}</span>
                <div class="audit-action">Modificacion: ${escapeHtml(event.action || "evento")}</div>
                <div class="audit-detail">${escapeHtml(event.detail || "")}</div>
            </div>
        `).join("") || `
            <div class="audit-item">
                <span class="audit-time">Fecha y hora: sin eventos relevantes</span>
                <div class="audit-action">Modificacion: historial limpio</div>
                <div class="audit-detail">Los cambios operativos apareceran aqui.</div>
            </div>
        `;
    }

    async function refreshAuditLog() {
        if (!auditList) return;
        if (!TRELLO_MODE || COMPONENT_MODE) {
            renderAuditLog(localAuditEvents());
            return;
        }
        try {
            const response = await fetch(`${TRELLO_API_BASE}/audit-log`, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Admin-PAES-Token": TRELLO_API_TOKEN },
                body: JSON.stringify({ limit: 35 }),
            });
            const data = await response.json();
            if (data?.ok) {
                const merged = [...localAuditEvents(), ...(data.result?.events || [])]
                    .sort((left, right) => new Date(right.timestamp || 0) - new Date(left.timestamp || 0))
                    .slice(0, 35);
                renderAuditLog(merged);
            }
        } catch (error) {
            console.warn("No se pudieron cargar los logs.", error);
            renderAuditLog(localAuditEvents());
        }
    }

    function updateResultsPanel(panel) {
        if (!panel?.stats) return;
        const root = document.querySelector(".board-list.is-locked .stats-panel");
        if (!root) return;
        const stats = panel.stats;
        const updates = {
            "exam": stats.exam,
            "average": stats.average,
            "median": stats.median,
            "stddev": stats.stddev,
            "min-score": stats.min?.score,
            "min-student": stats.min?.student,
            "max-score": stats.max?.score,
            "max-student": stats.max?.student,
            "note": panel.note,
        };
        Object.entries(updates).forEach(([key, value]) => {
            const target = root.querySelector(`[data-stat="${key}"]`);
            if (target && value !== undefined) target.textContent = value;
        });
        const chart = root.querySelector('[data-chart="average-series"]');
        if (chart) {
            chart.outerHTML = renderAverageChart(panel.median_series || []);
        }
    }

    function renderAverageChart(points) {
        const width = 282;
        const height = 178;
        const left = 44;
        const right = 14;
        const top = 22;
        const bottom = 32;
        const yMin = 650;
        const yMax = 1000;
        const chartWidth = width - left - right;
        const chartHeight = height - top - bottom;
        const safePoints = Array.isArray(points) ? points : [];
        if (!safePoints.length) {
            return `
                <div class="average-chart" data-chart="average-series">
                    <div class="chart-title">Mediana por ensayo</div>
                    <div class="chart-empty">Sin datos suficientes para graficar.</div>
                </div>
            `;
        }
        const exams = safePoints.map((point) => Number(point.exam)).filter(Number.isFinite);
        const minExam = Math.min(...exams);
        const maxExam = Math.max(...exams);
        const examSpan = Math.max(1, maxExam - minExam);
        const xFor = (exam) => left + ((Number(exam) - minExam) / examSpan) * chartWidth;
        const yFor = (score) => {
            const clamped = Math.max(yMin, Math.min(yMax, Number(score) || yMin));
            return top + ((yMax - clamped) / (yMax - yMin)) * chartHeight;
        };
        const polyline = safePoints
            .map((point) => `${xFor(point.exam).toFixed(1)},${yFor(point.median).toFixed(1)}`)
            .join(" ");
        const circles = safePoints.map((point) => `
            <circle cx="${xFor(point.exam).toFixed(1)}" cy="${yFor(point.median).toFixed(1)}" r="3.8">
                <title>Ensayo ${escapeHtml(point.exam)}: mediana ${escapeHtml(point.median)} (${escapeHtml(point.count)} estudiantes)</title>
            </circle>
        `).join("");
        const labels = safePoints
            .map((point) => `<text x="${xFor(point.exam).toFixed(1)}" y="${height - 8}" text-anchor="middle" stroke="none" stroke-width="0">${escapeHtml(point.exam)}</text>`)
            .join("");
        const yGrid = [650, 800, 1000].map((tick) => `
            <line x1="${left}" x2="${width - right}" y1="${yFor(tick).toFixed(1)}" y2="${yFor(tick).toFixed(1)}" />
            <text x="${left - 8}" y="${(yFor(tick) + 3).toFixed(1)}" text-anchor="end" stroke="none" stroke-width="0">${tick}</text>
        `).join("");
        return `
            <div class="average-chart" data-chart="average-series">
                <div class="chart-title">Mediana por ensayo</div>
                <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Grafico mediana de puntajes por ensayo">
                    <g class="chart-grid">${yGrid}</g>
                    <g class="chart-axis">
                        <line x1="${left}" x2="${width - right}" y1="${height - bottom}" y2="${height - bottom}" />
                        <line x1="${left}" x2="${left}" y1="${top}" y2="${height - bottom}" />
                    </g>
                    <polyline class="chart-line" points="${polyline}" />
                    <g class="chart-points">${circles}</g>
                    <g class="chart-x-labels">${labels}</g>
                    <text class="chart-y-title" x="${left}" y="10" text-anchor="middle" stroke="none" stroke-width="0">Puntaje</text>
                    <text class="chart-x-title" x="${(left + chartWidth / 2).toFixed(1)}" y="${height - 1}" text-anchor="middle" stroke="none" stroke-width="0">Ensayo</text>
                </svg>
            </div>
        `;
    }

    async function refreshResultsPanel(force = false) {
        if (!TRELLO_MODE) return;
        try {
            const response = await fetch(`${TRELLO_API_BASE}/refresh-results`, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Admin-PAES-Token": TRELLO_API_TOKEN },
                body: JSON.stringify({ force }),
            });
            const data = await response.json();
            if (data?.ok && data.result?.panel) {
                updateResultsPanel(data.result.panel);
            }
        } catch (error) {
            console.warn("No se pudo refrescar Resultados globales.", error);
        }
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function editableLists() {
        return boardData.filter((list) => list.kind !== "locked");
    }

    function listByName(name) {
        return editableLists().find((list) => list.name.toLowerCase() === String(name).trim().toLowerCase());
    }

    function listById(id) {
        return editableLists().find((list) => list.id === id);
    }

    function splitLines(value) {
        return String(value || "")
            .split("\\n")
            .map((item) => item.trim())
            .filter(Boolean);
    }

    function renderImagePreview() {
        imagePreview.innerHTML = attachedImages
            .map((image) => `<img src="${escapeHtml(image.src)}" alt="${escapeHtml(image.name)}">`)
            .join("");
    }

    function renderFilePreview() {
        filePreview.innerHTML = attachedFiles
            .map((file) => `<div class="file-pill">${icons.file}<span>${escapeHtml(file.name || "archivo.pdf")}</span></div>`)
            .join("");
    }

    function renderCard(card, index = 0, total = 1) {
        const badges = [];
        const images = card.images || [];
        const files = card.files || [];
        const checklists = card.checklists || [];
        const cover = images.length
            ? `<div class="card-cover">${images.slice(0, 3).map((image) => `<img src="${escapeHtml(image.src)}" alt="${escapeHtml(image.name)}">`).join("")}</div>`
            : "";
        if (card.links?.length) badges.push(`<span>${icons.link}${card.links.length}</span>`);
        if (images.length) badges.push(`<span>${icons.image}${images.length}</span>`);
        if (files.length) badges.push(`<span>${icons.file}${files.length}</span>`);
        if (checklists.length) badges.push(`<span>${icons.check}${checklists.length}</span>`);
        const description = card.description ? `<p>${escapeHtml(card.description)}</p>` : "";
        const badgesHtml = badges.length ? `<div class="card-badges">${badges.join("")}</div>` : "";
        const detectedCount = Array.isArray(card.detected_from_students) ? card.detected_from_students.length : 0;
        const detectedNote = card.detected
            ? `<div class="card-label detected-label">${icons.users} Detectado en ${detectedCount} alumno${detectedCount === 1 ? "" : "s"}</div>`
            : "";
        const editButton = READ_ONLY ? "" : `
                        <button class="tertiary-button edit-card" type="button" data-card-id="${escapeHtml(card.id)}">
                            ${icons.edit} Editar
                        </button>
        `;
        const deleteButton = READ_ONLY ? "" : `
                        <button class="tertiary-button delete-card" type="button" data-card-id="${escapeHtml(card.id)}">
                            ${icons.trash} ${card.detected ? "Ocultar" : "Eliminar"}
                        </button>
        `;
        const visibilityButton = READ_ONLY ? "" : `
                        <button class="tertiary-button visibility-card" type="button" data-card-id="${escapeHtml(card.id)}" data-card-title="${escapeHtml(card.title)}">
                            ${icons.users} Alumnos
                        </button>
        `;
        const sourceButton = READ_ONLY && card.source_url ? `
                        <a class="tertiary-button" href="${escapeHtml(card.source_url)}" target="_blank" rel="noopener noreferrer">
                            ${icons.link} Trello
                        </a>
        ` : "";
        const checklistLinks = checklists
            .filter((checklist) => checklist.link)
            .map((checklist) => `
                <a href="${escapeHtml(checklist.link)}" target="_blank" rel="noopener noreferrer">
                    ${icons.link}${escapeHtml(checklist.title || "Abrir recurso")}
                </a>
            `)
            .join("");
        const checklistLinksHtml = checklistLinks ? `<div class="checklist-links">${checklistLinks}</div>` : "";

        return `
            <article class="card" data-card-id="${escapeHtml(card.id)}">
                ${cover}
                <div class="card-body">
                    <div class="card-label">${icons.card} ${READ_ONLY ? "Trello solo lectura" : "Material comun"}</div>
                    ${detectedNote}
                    <h3>${escapeHtml(card.title)}</h3>
                    ${description}
                    ${badgesHtml}
                    ${checklistLinksHtml}
                    <div class="card-actions">
                        <button class="tertiary-button preview-card" type="button" data-card-id="${escapeHtml(card.id)}">
                            ${icons.view} Preview
                        </button>
                        ${sourceButton}
                        ${editButton}
                        ${visibilityButton}
                        ${deleteButton}
                    </div>
                </div>
            </article>
        `;
    }

    function renderList(list) {
        if (list.kind === "locked") return;
        const root = document.querySelector(`[data-list-id="${CSS.escape(list.id)}"]`);
        if (!root) return;
        const stack = root.querySelector(".card-stack");
        const count = root.querySelector(".list-count");

        count.textContent = `${list.cards.length} ${list.cards.length === 1 ? "tarjeta" : "tarjetas"}`;
        stack.innerHTML = list.cards.length
            ? list.cards.map((card, index) => renderCard(card, index, list.cards.length)).join("")
            : '<div class="empty-state">Sin tarjetas. Agrega material comun para la plantilla.</div>';
    }

    function renderAllEditableLists() {
        editableLists().forEach(renderList);
        refreshListOptions();
    }

    function refreshListOptions() {
        const selected = listInput.value;
        listInput.innerHTML = [
            '<option value="">Selecciona una lista</option>',
            ...editableLists().map((list) => `<option value="${escapeHtml(list.id)}">${escapeHtml(list.name)}</option>`),
        ].join("");
        if (editableLists().some((list) => list.id === selected)) {
            listInput.value = selected;
        }
    }

    function createListElement(list) {
        const section = document.createElement("section");
        section.className = "board-list";
        section.dataset.listId = list.id;
        section.innerHTML = `
            <header class="list-header">
                <div class="list-title-group">
                    <span class="list-drag-handle" title="Arrastrar lista">__ICON_GRIP__</span>
                    <div>
                        <h2>${escapeHtml(list.name)}</h2>
                        <span class="list-count">0 tarjetas</span>
                    </div>
                </div>
                <button class="icon-button visibility-list" type="button" data-list-id="${escapeHtml(list.id)}" data-list-title="${escapeHtml(list.name)}" aria-label="Filtrar alumnos para lista ${escapeHtml(list.name)}">
                    __ICON_USERS__
                </button>
                <button class="icon-button close-list" type="button" data-list-id="${escapeHtml(list.id)}" aria-label="Cerrar lista ${escapeHtml(list.name)}">
                    __ICON_CLOSE__
                </button>
            </header>
            <div class="card-stack">
                <div class="empty-state">Sin tarjetas. Agrega material comun para la plantilla.</div>
            </div>
            <button class="add-card-button" type="button" data-list-id="${escapeHtml(list.id)}">
                ${icons.add} Nueva tarjeta
            </button>
        `;
        return section;
    }

    function hydrateBoardDomFromState() {
        if (READ_ONLY) {
            renderAllEditableLists();
            setSaveStatus("Solo lectura");
            return;
        }
        if (TRELLO_MODE) {
            renderAllEditableLists();
            setSaveStatus("Master local");
            return;
        }
        board.querySelectorAll(".board-list:not(.is-locked)").forEach((element) => element.remove());
        const addListButton = document.querySelector("#add-list-board");
        editableLists().forEach((list) => {
            board.insertBefore(createListElement(list), addListButton);
        });
        renderAllEditableLists();
        setSaveStatus(window.localStorage.getItem(STORAGE_KEY) ? "Guardado" : "Demo");
    }

    async function addList() {
        if (READ_ONLY) return;
        const name = prompt("Nombre de la nueva lista");
        if (!name || !name.trim()) return;

        const cleanName = name.trim();
        if (listByName(cleanName)) return;
        storeLocalAuditEvent("Crear lista", `Se solicito crear la lista "${cleanName}".`);

        if (TRELLO_MODE) {
            try {
                const createdList = await callTrelloAction("/create-list", { name: cleanName });
                const list = {
                    id: createdList.id,
                    name: createdList.name || cleanName,
                    pos: createdList.pos || Date.now(),
                    cards: [],
                    source: "trello",
                };
                boardData.push(list);
                board.insertBefore(createListElement(list), document.querySelector("#add-list-board"));
                refreshListOptions();
            } catch (error) {
                setSaveStatus("Error", "error");
                alert(error.message);
            }
            return;
        }

        const list = {
            id: `list-${Date.now()}`,
            name: cleanName,
            cards: [],
        };
        boardData.push(list);
        board.insertBefore(createListElement(list), document.querySelector("#add-list-board"));
        refreshListOptions();
        writeAuditEvent("Crear lista", `Se creo la lista "${cleanName}".`);
        schedulePersistBoardData();
    }

    function normalizeChecklist(checklist = { title: "", description: "", link: "", items: [] }) {
        if (checklist.description || checklist.link) {
            return checklist;
        }

        const oldItems = checklist.items || [];
        if (!oldItems.length) return checklist;

        const firstItem = typeof oldItems[0] === "string" ? { text: oldItems[0], link: "" } : oldItems[0];
        return {
            title: checklist.title || firstItem.text || "",
            description: oldItems
                .map((item) => (typeof item === "string" ? item : item.text || ""))
                .filter(Boolean)
                .join("\\n"),
            link: firstItem.link || "",
        };
    }

    function createChecklistBlock(checklist = { title: "", description: "", link: "" }) {
        const normalized = normalizeChecklist(checklist);
        const block = document.createElement("div");
        block.className = "checklist-block";
        block.innerHTML = `
            <label class="checklist-field">
                <span>Titulo de la checklist</span>
                <input class="checklist-title" placeholder="Ej: Guia de funciones" value="${escapeHtml(normalized.title || "")}">
            </label>
            <label class="checklist-field">
                <span>Descripcion opcional</span>
                <textarea class="checklist-description" placeholder="Indicacion breve para el alumno">${escapeHtml(normalized.description || "")}</textarea>
            </label>
            <label class="checklist-field">
                <span>Link de esta checklist</span>
                <input class="checklist-link" placeholder="https://..." value="${escapeHtml(normalized.link || "")}">
            </label>
        `;
        checklistsRoot.appendChild(block);
    }

    function readChecklists() {
        return [...checklistsRoot.querySelectorAll(".checklist-block")]
            .map((block) => {
                return {
                    title: block.querySelector(".checklist-title").value.trim(),
                    description: block.querySelector(".checklist-description").value.trim(),
                    link: block.querySelector(".checklist-link").value.trim(),
                };
            })
            .filter((checklist) => checklist.title || checklist.description || checklist.link)
            .map((checklist, index) => ({
                title: checklist.title || `Checklist ${index + 1}`,
                description: checklist.description,
                link: checklist.link,
            }));
    }

    function setPanelOpen(panelId, isOpen = true) {
        document.querySelector(`#${panelId}`)?.classList.toggle("is-open", isOpen);
    }

    function resetOptionalPanels() {
        optionPanels.forEach((panel) => panel.classList.remove("is-open"));
    }

    function openDrawer(listId = "", card = null) {
        editingCardId.value = card?.id || "";
        refreshListOptions();
        listInput.value = listId || "";
        cardTitle.value = card?.title || "";
        cardDescription.value = card?.description || "";
        cardLinks.value = (card?.links || []).join("\\n");
        attachedImages = [...(card?.images || [])];
        attachedFiles = [...(card?.files || [])];
        imageInput.value = "";
        fileInput.value = "";
        renderImagePreview();
        renderFilePreview();
        checklistsRoot.innerHTML = "";
        const existingChecklists = card?.checklists || [];
        if (existingChecklists.length) {
            existingChecklists.forEach(createChecklistBlock);
        }
        resetOptionalPanels();
        if (card?.description) setPanelOpen("description-panel");
        if (card?.links?.length) setPanelOpen("links-panel");
        if (attachedImages.length) setPanelOpen("images-panel");
        if (attachedFiles.length) setPanelOpen("files-panel");
        if (existingChecklists.length) setPanelOpen("checklists-panel");
        document.querySelector("#drawer-title").textContent = card ? "Editar tarjeta" : "Nueva tarjeta";
        drawer.classList.add("is-open");
        backdrop.classList.add("is-open");
        setTimeout(() => cardTitle.focus(), 50);
    }

    function closeDrawer() {
        drawer.classList.remove("is-open");
        backdrop.classList.remove("is-open");
    }

    function findCard(cardId) {
        for (const list of editableLists()) {
            const card = list.cards.find((item) => item.id === cardId);
            if (card) return { list, card };
        }
        return null;
    }

    function applySavedCardLocally(payload, result = {}) {
        const targetList = listById(payload.list_id);
        if (!targetList) return;
        const cardId = payload.card_id || result.card_id || payload.id;
        const existing = payload.card_id ? findCard(payload.card_id) : null;
        if (existing) {
            existing.list.cards = existing.list.cards.filter((card) => card.id !== cardId);
        }
        targetList.cards.push({
            id: cardId,
            title: payload.title,
            description: payload.description,
            links: payload.links,
            images: payload.images,
            files: payload.files,
            checklists: payload.checklists,
            source_url: result.url || "",
            pos: Date.now(),
        });
        renderAllEditableLists();
    }

    function renderPreviewSection(title, content) {
        if (!content) return "";
        return `
            <section class="preview-section">
                <h3>${escapeHtml(title)}</h3>
                ${content}
            </section>
        `;
    }

    function openPreview(cardId) {
        const found = findCard(cardId);
        if (!found) return;
        const card = found.card;
        const links = card.links || [];
        const images = card.images || [];
        const files = card.files || [];
        const checklists = card.checklists || [];

        previewTitle.textContent = card.title;
        previewSubtitle.textContent = found.list.name;

        const descriptionHtml = card.description
            ? renderPreviewSection("Descripcion", `<p>${escapeHtml(card.description)}</p>`)
            : "";
        const linksHtml = links.length
            ? renderPreviewSection(
                "Links",
                `<div class="preview-links">${links.map((link) => `<a href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(link)}</a>`).join("")}</div>`
            )
            : "";
        const imagesHtml = images.length
            ? renderPreviewSection(
                "Imagenes",
                `<div class="preview-images">${images.map((image) => `<img src="${escapeHtml(image.src)}" alt="${escapeHtml(image.name)}">`).join("")}</div>`
            )
            : "";
        const filesHtml = files.length
            ? renderPreviewSection(
                "PDFs",
                `<div class="preview-links">${files.map((file) => `
                    <a href="${escapeHtml(file.src)}" target="_blank" rel="noopener noreferrer">
                        ${icons.file}${escapeHtml(file.name || "archivo.pdf")}
                    </a>
                `).join("")}</div>`
            )
            : "";
        const checklistHtml = checklists.length
            ? renderPreviewSection(
                "Checklists",
                `<div class="preview-links">${checklists.map((checklist) => `
                    <div>
                        <strong>${escapeHtml(checklist.title)}</strong>
                        ${checklist.description ? `<p>${escapeHtml(checklist.description)}</p>` : ""}
                        ${checklist.link ? `<a href="${escapeHtml(checklist.link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(checklist.link)}</a>` : ""}
                    </div>
                `).join("")}</div>`
            )
            : "";

        const previewContent = `${descriptionHtml}${linksHtml}${imagesHtml}${filesHtml}${checklistHtml}`;
        previewBody.innerHTML = previewContent || '<section class="preview-section"><p>Esta tarjeta solo contiene titulo por ahora.</p></section>';
        previewBackdrop.classList.add("is-open");
        previewDialog.classList.add("is-open");
    }

    function closePreview() {
        previewBackdrop.classList.remove("is-open");
        previewDialog.classList.remove("is-open");
    }

    async function saveCard() {
        if (READ_ONLY) return;
        const targetListId = listInput.value;
        const title = cardTitle.value.trim();
        if (!targetListId || !title) return;

        const targetList = listById(targetListId);
        if (!targetList) return;

        const payload = {
            id: editingCardId.value || `card-${Date.now()}`,
            card_id: editingCardId.value || "",
            list_id: targetListId,
            title,
            description: cardDescription.value.trim(),
            links: splitLines(cardLinks.value),
            images: attachedImages,
            files: attachedFiles,
            checklists: readChecklists(),
        };
        payload.list_name = targetList.name;

        if (TRELLO_MODE) {
            try {
                const result = await callTrelloAction("/save-card", payload);
                applySavedCardLocally(payload, result);
                closeDrawer();
            } catch (error) {
                setSaveStatus("Error", "error");
                alert(error.message);
            }
            return;
        }

        const existing = editingCardId.value ? findCard(editingCardId.value) : null;
        if (existing) {
            existing.list.cards = existing.list.cards.filter((card) => card.id !== payload.id);
        }

        targetList.cards.push(payload);
        renderAllEditableLists();
        writeAuditEvent(
            existing ? "Editar tarjeta" : "Crear tarjeta",
            `Se ${existing ? "actualizo" : "creo"} la tarjeta "${title}" en "${targetList.name}".`,
            { card_id: payload.id, list_id: targetList.id }
        );
        schedulePersistBoardData();
        closeDrawer();
    }

    function requestCloseList(listId) {
        if (READ_ONLY) return;
        const list = boardData.find((item) => item.id === listId);
        if (!list || list.kind === "locked") return;
        if (TRELLO_MODE) {
            if (list.detected || String(list.id || "").startsWith("detected-")) {
                boardData = boardData.filter((item) => item.id !== listId);
                document.querySelector(`[data-list-id="${CSS.escape(listId)}"]`)?.remove();
                refreshListOptions();
                setSaveStatus("Oculto");
                syncNote.textContent = `La lista detectada "${list.name}" se oculto de esta vista. No pertenece al master local.`;
                return;
            }
            if (!confirm(`Eliminar la lista "${list.name}" del master local? Se archivara en alumnos al sincronizar.`)) return;
            callTrelloAction("/archive-list", { list_id: listId, list_name: list.name })
                .then(() => {
                    boardData = boardData.filter((item) => item.id !== listId);
                    document.querySelector(`[data-list-id="${CSS.escape(listId)}"]`)?.remove();
                    refreshListOptions();
                    setSaveStatus("Actualizado");
                })
                .catch((error) => {
                    setSaveStatus("Error", "error");
                    alert(error.message);
                });
            return;
        }
        pendingCloseListId = listId;
        confirmMessage.textContent = `Cerrar "${list.name}" quitara sus tarjetas del prototipo visual. No se modifica Trello ni informacion real.`;
        confirmBackdrop.classList.add("is-open");
        confirmDialog.classList.add("is-open");
    }

    function closeConfirm() {
        pendingCloseListId = null;
        confirmBackdrop.classList.remove("is-open");
        confirmDialog.classList.remove("is-open");
    }

    function closeListConfirmed() {
        if (READ_ONLY || TRELLO_MODE) return;
        if (!pendingCloseListId) return;
        boardData = boardData.filter((list) => list.id !== pendingCloseListId);
        document.querySelector(`[data-list-id="${CSS.escape(pendingCloseListId)}"]`)?.remove();
        writeAuditEvent("Eliminar lista", "Se elimino una lista del tablero local.", { list_id: pendingCloseListId });
        closeConfirm();
        refreshListOptions();
        schedulePersistBoardData();
    }

    imageInput.addEventListener("change", async (event) => {
        const files = [...event.target.files].filter((file) => file.type.startsWith("image/"));
        const loaded = await Promise.all(files.map((file) => new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = () => resolve({ name: file.name, src: reader.result });
            reader.readAsDataURL(file);
        })));
        attachedImages = [...attachedImages, ...loaded];
        renderImagePreview();
    });

    fileInput.addEventListener("change", async (event) => {
        const files = [...event.target.files].filter((file) => {
            return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
        });
        const loaded = await Promise.all(files.map((file) => new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = () => resolve({
                name: file.name,
                src: reader.result,
                content_type: "application/pdf",
            });
            reader.readAsDataURL(file);
        })));
        attachedFiles = [...attachedFiles, ...loaded];
        renderFilePreview();
    });

    document.addEventListener("click", (event) => {
        if (event.target.closest("#logout-panel")) {
            document.cookie = "admin_paes_session=; Max-Age=0; Path=/; SameSite=Lax";
            try {
                const url = new URL(window.top.location.href);
                url.searchParams.set("logout", "1");
                window.top.location.assign(url.toString());
            } catch (error) {
                window.location.href = "/?logout=1";
            }
            return;
        }

        if (event.target.closest("#open-sync")) {
            if (!TRELLO_MODE) {
                alert("La sincronizacion requiere conexion activa con Trello.");
                return;
            }
            openSyncModal();
            return;
        }

        const visibilityListButton = event.target.closest(".visibility-list");
        if (visibilityListButton) {
            openVisibilityModal("list", visibilityListButton.dataset.listId, visibilityListButton.dataset.listTitle || "Lista");
            return;
        }

        const visibilityCardButton = event.target.closest(".visibility-card");
        if (visibilityCardButton) {
            openVisibilityModal("card", visibilityCardButton.dataset.cardId, visibilityCardButton.dataset.cardTitle || "Tarjeta");
            return;
        }

        const addCardButton = event.target.closest(".add-card-button");
        if (addCardButton) {
            const list = boardData.find((item) => item.id === addCardButton.dataset.listId);
            openDrawer(list?.id || "");
            return;
        }

        const editButton = event.target.closest(".edit-card");
        if (editButton) {
            const found = findCard(editButton.dataset.cardId);
            if (found) openDrawer(found.list.id, found.card);
            return;
        }

        const deleteButton = event.target.closest(".delete-card");
        if (deleteButton) {
            const found = findCard(deleteButton.dataset.cardId);
            if (!found) return;
            if (!confirm(`Eliminar la tarjeta "${found.card.title}"? ${TRELLO_MODE ? "Se archivara en Trello." : "Se quitara del prototipo."}`)) return;
            if (TRELLO_MODE) {
                if (found.card.detected || String(found.card.id || "").startsWith("detected-")) {
                    found.list.cards = found.list.cards.filter((card) => card.id !== found.card.id);
                    renderList(found.list);
                    setSaveStatus("Oculto");
                    return;
                }
                callTrelloAction("/archive-card", { card_id: found.card.id, card_title: found.card.title, list_name: found.list.name })
                    .then(() => {
                        found.list.cards = found.list.cards.filter((card) => card.id !== found.card.id);
                        renderList(found.list);
                        setSaveStatus("Actualizado");
                    })
                    .catch((error) => {
                        setSaveStatus("Error", "error");
                        alert(error.message);
                    });
            } else {
                found.list.cards = found.list.cards.filter((card) => card.id !== found.card.id);
                renderList(found.list);
                writeAuditEvent("Eliminar tarjeta", `Se elimino la tarjeta "${found.card.title}" de "${found.list.name}".`, { card_id: found.card.id, list_id: found.list.id });
                schedulePersistBoardData();
            }
            return;
        }

        const previewButton = event.target.closest(".preview-card");
        if (previewButton) {
            openPreview(previewButton.dataset.cardId);
            return;
        }

        const closeListButton = event.target.closest(".close-list");
        if (closeListButton) {
            requestCloseList(closeListButton.dataset.listId);
            return;
        }

        if (event.target.closest("#add-list-top") || event.target.closest("#add-list-board")) {
            addList();
            return;
        }

        if (event.target.closest("#open-new-card")) {
            const firstEditable = editableLists()[0];
            openDrawer(firstEditable?.id || "");
        }
    });

    document.querySelector("#add-checklist").addEventListener("click", () => {
        setPanelOpen("checklists-panel");
        createChecklistBlock({ title: "", description: "", link: "" });
    });
    document.querySelectorAll(".option-toggle").forEach((button) => {
        button.addEventListener("click", () => {
            const panelId = button.dataset.panel;
            const panel = document.querySelector(`#${panelId}`);
            if (!panel) return;
            panel.classList.toggle("is-open");
            if (panelId === "checklists-panel" && panel.classList.contains("is-open") && !checklistsRoot.children.length) {
                createChecklistBlock({ title: "", description: "", link: "" });
            }
        });
    });
    document.querySelector("#close-drawer").addEventListener("click", closeDrawer);
    document.querySelector("#cancel-drawer").addEventListener("click", closeDrawer);
    backdrop.addEventListener("click", closeDrawer);
    document.querySelector("#save-card").addEventListener("click", saveCard);
    document.querySelector("#cancel-close-list").addEventListener("click", closeConfirm);
    document.querySelector("#confirm-close-list").addEventListener("click", closeListConfirmed);
    confirmBackdrop.addEventListener("click", closeConfirm);
    document.querySelector("#close-preview").addEventListener("click", closePreview);
    previewBackdrop.addEventListener("click", closePreview);
    document.querySelector("#close-visibility").addEventListener("click", closeVisibilityModal);
    document.querySelector("#cancel-visibility").addEventListener("click", closeVisibilityModal);
    visibilityBackdrop.addEventListener("click", closeVisibilityModal);
    document.querySelector("#save-visibility").addEventListener("click", saveVisibilityFilter);
    document.querySelector("#visibility-select-all").addEventListener("click", () => {
        hiddenStudentIds = new Set();
        renderStudentGrid();
    });
    document.querySelector("#visibility-clear-all").addEventListener("click", () => {
        hiddenStudentIds = new Set((studentBoards || []).map((student) => student.board_id));
        renderStudentGrid();
    });
    document.querySelector("#close-sync").addEventListener("click", closeSyncModal);
    syncBackdrop.addEventListener("click", closeSyncModal);
    document.querySelector("#preview-sync").addEventListener("click", previewStudentSync);
    document.querySelector("#apply-sync").addEventListener("click", applyStudentSync);
    document.querySelector("#open-admin-page").addEventListener("click", openAdminPage);
    document.querySelector("#close-admin-page").addEventListener("click", closeAdminPage);
    document.querySelector("#admin-refresh-students").addEventListener("click", refreshAdminStudents);
    visibilityGrid.addEventListener("click", (event) => {
        const chip = event.target.closest(".student-chip");
        if (!chip) return;
        const boardId = chip.dataset.boardId;
        if (hiddenStudentIds.has(boardId)) {
            hiddenStudentIds.delete(boardId);
        } else {
            hiddenStudentIds.add(boardId);
        }
        renderStudentGrid();
    });

    let dragState = null;
    let cardDragState = null;
    let listDragState = null;

    board.addEventListener("wheel", (event) => {
        if (event.target.closest("button, input, textarea, select, a")) return;
        const stack = event.target.closest(".card-stack");
        if (stack && Math.abs(event.deltaY) >= Math.abs(event.deltaX)) {
            event.preventDefault();
            stack.scrollTop += event.deltaY;
            return;
        }
        const horizontalDelta = Math.abs(event.deltaX) > Math.abs(event.deltaY)
            ? event.deltaX
            : event.deltaY;
        if (!horizontalDelta) return;
        event.preventDefault();
        board.scrollLeft += horizontalDelta;
    }, { passive: false });

    board.addEventListener("pointerdown", (event) => {
        if (event.target.closest("button, input, textarea, select, a")) return;
        if (event.target.closest(".card")) return;
        const listElement = event.target.closest(".board-list");
        const headerDragZone = event.target.closest(".list-header, .list-drag-handle");
        if (!READ_ONLY && listElement && !listElement.classList.contains("is-locked") && headerDragZone) {
            event.preventDefault();
            listDragState = {
                listId: listElement.dataset.listId,
                element: listElement,
                startX: event.clientX,
                startY: event.clientY,
                lastX: event.clientX,
                lastMoveAt: 0,
                originalIndex: editableLists().findIndex((list) => list.id === listElement.dataset.listId),
                currentIndex: editableLists().findIndex((list) => list.id === listElement.dataset.listId),
                started: false,
            };
            listElement.classList.add("is-list-ready");
            listElement.setPointerCapture(event.pointerId);
            return;
        }
        const stack = event.target.closest(".card-stack");
        dragState = {
            stack,
            mode: null,
            startX: event.clientX,
            startY: event.clientY,
            boardScrollLeft: board.scrollLeft,
            stackScrollTop: stack ? stack.scrollTop : 0,
        };
        board.classList.add("is-dragging");
        stack?.classList.add("is-dragging");
        board.setPointerCapture(event.pointerId);
    });

    board.addEventListener("pointermove", (event) => {
        if (listDragState) return;
        if (!dragState) return;
        event.preventDefault();
        const dx = event.clientX - dragState.startX;
        const dy = event.clientY - dragState.startY;

        if (!dragState.mode && Math.max(Math.abs(dx), Math.abs(dy)) > 4) {
            dragState.mode = dragState.stack && Math.abs(dy) > Math.abs(dx) ? "vertical" : "horizontal";
        }

        if (dragState.mode === "vertical" && dragState.stack) {
            dragState.stack.scrollTop = dragState.stackScrollTop - dy;
        } else {
            board.scrollLeft = dragState.boardScrollLeft - dx;
        }
    });

    function stopDragging() {
        if (!dragState) return;
        board.classList.remove("is-dragging");
        dragState.stack?.classList.remove("is-dragging");
        dragState = null;
    }

    board.addEventListener("pointerup", stopDragging);
    board.addEventListener("pointercancel", stopDragging);
    function editableListElements() {
        return [...board.querySelectorAll(".board-list:not(.is-locked)")];
    }

    function midpointPosition(items, index) {
        const previous = items[index - 1];
        const next = items[index + 1];
        const previousPos = Number(previous?.pos || 0);
        const nextPos = Number(next?.pos || 0);
        if (previous && next && nextPos > previousPos) return (previousPos + nextPos) / 2;
        if (previous) return previousPos + 65536;
        if (next && nextPos > 1) return nextPos / 2;
        return (index + 1) * 65536;
    }

    function moveListToEditableIndex(listId, targetEditableIndex) {
        if (READ_ONLY) return;
        const movingList = boardData.find((list) => list.id === listId);
        if (!movingList || movingList.kind === "locked") return;

        boardData = boardData.filter((list) => list.id !== listId);
        const editableIds = boardData.filter((list) => list.kind !== "locked").map((list) => list.id);
        const safeIndex = Math.max(0, Math.min(targetEditableIndex, editableIds.length));
        const insertBeforeId = editableIds[safeIndex];
        const insertAt = insertBeforeId
            ? boardData.findIndex((list) => list.id === insertBeforeId)
            : boardData.findIndex((list) => list.kind !== "locked") + editableIds.length;
        boardData.splice(insertAt < 0 ? boardData.length : insertAt, 0, movingList);

        const movingElement = board.querySelector(`[data-list-id="${CSS.escape(listId)}"]`);
        const editableElements = editableListElements().filter((element) => element.dataset.listId !== listId);
        const beforeElement = editableElements[safeIndex] || document.querySelector("#add-list-board");
        if (movingElement && beforeElement) {
            board.insertBefore(movingElement, beforeElement);
            movingElement.classList.add("is-list-settling");
            window.setTimeout(() => movingElement.classList.remove("is-list-settling"), 260);
        }
        refreshListOptions();
        if (TRELLO_MODE) {
            const lists = editableLists();
            const movedIndex = lists.findIndex((list) => list.id === listId);
            const nextPosition = midpointPosition(lists, movedIndex);
            const movedList = lists[movedIndex];
            if (movedList) movedList.pos = nextPosition;
            if (listDragState) {
                listDragState.pendingMove = {
                    list_id: listId,
                    list_name: movedList?.name || listId,
                    pos: nextPosition,
                };
                setSaveStatus("Suelta para guardar", "saving");
            }
        } else {
            schedulePersistBoardData();
        }
    }

    function listStepTargetIndex(pointerX) {
        if (!listDragState) return null;
        const currentIndex = editableLists().findIndex((list) => list.id === listDragState.listId);
        const currentElement = board.querySelector(`[data-list-id="${CSS.escape(listDragState.listId)}"]`);
        const currentRect = currentElement?.getBoundingClientRect();
        if (!currentRect) return null;

        const movingRight = pointerX > listDragState.lastX;
        const neighborIndex = movingRight ? currentIndex + 1 : currentIndex - 1;
        const neighbor = editableListElements().find((element) => {
            const index = editableLists().findIndex((list) => list.id === element.dataset.listId);
            return index === neighborIndex;
        });
        if (!neighbor) return null;

        const neighborRect = neighbor.getBoundingClientRect();
        const neighborCenter = neighborRect.left + neighborRect.width / 2;
        const currentCenter = currentRect.left + currentRect.width / 2;
        const passedNeighbor = movingRight ? pointerX > neighborCenter : pointerX < neighborCenter;
        const movedEnough = Math.abs(pointerX - listDragState.lastX) >= LIST_STEP_THRESHOLD;
        const crossedEnough = Math.abs(pointerX - currentCenter) >= currentRect.width * .34;
        return passedNeighbor && movedEnough && crossedEnough ? neighborIndex : null;
    }

    document.addEventListener("pointermove", (event) => {
        if (!listDragState) return;
        const dx = event.clientX - listDragState.startX;
        const dy = event.clientY - listDragState.startY;
        if (!listDragState.started) {
            if (Math.abs(dx) < LIST_DRAG_THRESHOLD) return;
            if (Math.abs(dx) < Math.abs(dy) * DIRECTION_LOCK_RATIO) {
                stopListDragging();
                return;
            }
        }
        event.preventDefault();
        listDragState.started = true;
        listDragState.element.classList.remove("is-list-ready");
        listDragState.element.classList.add("is-list-dragging");
        autoScrollBoardWhileDragging(event.clientX);
        const now = performance.now();
        if (now - listDragState.lastMoveAt < LIST_REORDER_COOLDOWN) return;
        const nextIndex = listStepTargetIndex(event.clientX);
        if (nextIndex === null || nextIndex === listDragState.currentIndex || nextIndex < 0) return;
        moveListToEditableIndex(listDragState.listId, nextIndex);
        listDragState.currentIndex = editableLists().findIndex((list) => list.id === listDragState.listId);
        listDragState.lastX = event.clientX;
        listDragState.lastMoveAt = now;
        listDragState.element = board.querySelector(`[data-list-id="${CSS.escape(listDragState.listId)}"]`);
        listDragState.element?.classList.add("is-list-dragging");
    });

    function stopListDragging() {
        if (!listDragState) return;
        const pendingMove = listDragState.pendingMove;
        const movedListName = pendingMove?.list_name || boardData.find((list) => list.id === listDragState.listId)?.name || "";
        const didMove = listDragState.started && listDragState.currentIndex !== listDragState.originalIndex;
        listDragState.element?.classList.remove("is-list-ready");
        listDragState.element?.classList.remove("is-list-dragging");
        listDragState = null;
        if (TRELLO_MODE && pendingMove) {
            callTrelloAction("/move-list", pendingMove)
                .then(() => {
                    setSaveStatus("Actualizado");
                })
                .catch((error) => {
                    setSaveStatus("Error", "error");
                    alert(error.message);
                });
        } else if (!TRELLO_MODE && didMove) {
            writeAuditEvent("Mover lista", `Se movio la lista "${movedListName}".`);
        }
    }

    document.addEventListener("pointerup", stopListDragging);
    document.addEventListener("pointercancel", stopListDragging);

    function autoScrollBoardWhileDragging(clientX) {
        const rect = board.getBoundingClientRect();
        const edge = 92;
        const speed = 18;
        if (clientX < rect.left + edge) {
            board.scrollLeft -= speed;
        } else if (clientX > rect.right - edge) {
            board.scrollLeft += speed;
        }
    }

    function cardIndexAtY(stack, y, fallbackIndex) {
        const cards = [...stack.querySelectorAll(".card:not(.is-card-dragging)")];
        for (const card of cards) {
            const rect = card.getBoundingClientRect();
            if (y < rect.top + rect.height / 2) {
                const id = card.dataset.cardId;
                const list = boardData.find((item) => item.id === stack.closest(".board-list")?.dataset.listId);
                return list ? list.cards.findIndex((item) => item.id === id) : fallbackIndex;
            }
        }
        return cards.length;
    }

    document.addEventListener("pointerdown", (event) => {
        if (READ_ONLY) return;
        if (event.target.closest("button, input, textarea, select, a")) return;
        const cardElement = event.target.closest(".card");
        if (!cardElement) return;
        const listElement = cardElement.closest(".board-list");
        const stack = cardElement.closest(".card-stack");
        const list = boardData.find((item) => item.id === listElement?.dataset.listId);
        if (!list || !stack) return;

        cardDragState = {
            cardId: cardElement.dataset.cardId,
            list,
            stack,
            startX: event.clientX,
            startY: event.clientY,
            originalIndex: list.cards.findIndex((card) => card.id === cardElement.dataset.cardId),
            currentIndex: list.cards.findIndex((card) => card.id === cardElement.dataset.cardId),
            pendingMove: null,
            started: false,
        };
        cardElement.classList.add("is-card-ready");
        cardElement.setPointerCapture(event.pointerId);
    });

    document.addEventListener("pointermove", (event) => {
        if (!cardDragState) return;
        const dx = event.clientX - cardDragState.startX;
        const dy = event.clientY - cardDragState.startY;
        if (!cardDragState.started) {
            if (Math.abs(dy) < CARD_DRAG_THRESHOLD) return;
            if (Math.abs(dy) < Math.abs(dx) * DIRECTION_LOCK_RATIO) {
                stopCardDragging();
                return;
            }
        }
        event.preventDefault();
        cardDragState.started = true;
        const draggedElement = cardDragState.stack.querySelector(`[data-card-id="${CSS.escape(cardDragState.cardId)}"]`);
        draggedElement?.classList.remove("is-card-ready");
        draggedElement?.classList.add("is-card-dragging");

        const nextIndex = cardIndexAtY(cardDragState.stack, event.clientY, cardDragState.currentIndex);
        if (nextIndex === cardDragState.currentIndex || nextIndex < 0) return;

        const cards = cardDragState.list.cards;
        const currentIndex = cards.findIndex((card) => card.id === cardDragState.cardId);
        const [moved] = cards.splice(currentIndex, 1);
        const adjustedIndex = nextIndex > currentIndex ? nextIndex - 1 : nextIndex;
        cards.splice(Math.max(0, Math.min(adjustedIndex, cards.length)), 0, moved);
        cardDragState.currentIndex = cards.findIndex((card) => card.id === cardDragState.cardId);
        renderList(cardDragState.list);
        if (TRELLO_MODE) {
            const nextPosition = midpointPosition(cardDragState.list.cards, cardDragState.currentIndex);
            const movedCard = cardDragState.list.cards.find((card) => card.id === cardDragState.cardId);
            if (movedCard) movedCard.pos = nextPosition;
            cardDragState.pendingMove = {
                card_id: cardDragState.cardId,
                list_id: cardDragState.list.id,
                card_title: movedCard?.title || cardDragState.cardId,
                list_name: cardDragState.list.name,
                pos: nextPosition,
            };
            setSaveStatus("Suelta para guardar", "saving");
        } else {
            schedulePersistBoardData();
        }
        cardDragState.stack = document.querySelector(`[data-list-id="${CSS.escape(cardDragState.list.id)}"] .card-stack`);
        cardDragState.stack?.querySelector(`[data-card-id="${CSS.escape(cardDragState.cardId)}"]`)?.classList.add("is-card-dragging");
    });

    function stopCardDragging() {
        if (!cardDragState) return;
        const pendingMove = cardDragState.pendingMove;
        const movedCardTitle = pendingMove?.card_title || cardDragState.list.cards.find((card) => card.id === cardDragState.cardId)?.title || "";
        const movedListName = pendingMove?.list_name || cardDragState.list.name;
        const didMove = cardDragState.started && cardDragState.currentIndex !== cardDragState.originalIndex;
        cardDragState.stack?.querySelector(`[data-card-id="${CSS.escape(cardDragState.cardId)}"]`)?.classList.remove("is-card-ready");
        cardDragState.stack?.querySelector(`[data-card-id="${CSS.escape(cardDragState.cardId)}"]`)?.classList.remove("is-card-dragging");
        cardDragState = null;
        if (TRELLO_MODE && pendingMove) {
            callTrelloAction("/move-card", pendingMove)
                .then(() => {
                    setSaveStatus("Actualizado");
                })
                .catch((error) => {
                    setSaveStatus("Error", "error");
                    alert(error.message);
                });
        } else if (!TRELLO_MODE && didMove) {
            writeAuditEvent("Mover tarjeta", `Se movio la tarjeta "${movedCardTitle}" en "${movedListName}".`);
        }
    }

    document.addEventListener("pointerup", stopCardDragging);
    document.addEventListener("pointercancel", stopCardDragging);

    hydrateBoardDomFromState();
    function applyComponentStateToOpenUi() {
        if (!COMPONENT_MODE) return;
        const ui = COMPONENT_STATE.__ui_state || {};
        if (ui.screen === "admin" || adminPage.classList.contains("is-open")) {
            adminPage.classList.add("is-open");
            const cachedAdmin = COMPONENT_STATE["/admin-dashboard"];
            if (cachedAdmin?.ok) renderAdminDashboard(cachedAdmin.result);
        }
        if (ui.screen === "visibility" || visibilityDialog.classList.contains("is-open")) {
            const openResult = COMPONENT_STATE["/visibility-open"];
            const studentsResult = COMPONENT_STATE["/student-boards"];
            let visibilityHadError = false;
            if (openResult?.error && visibilityDialog.classList.contains("is-open")) {
                visibilityHadError = true;
                visibilityStatus.textContent = "No se pudo cargar alumnos";
                visibilityGrid.innerHTML = `<p class="visibility-status">${escapeHtml(openResult.error)}</p>`;
            } else if (openResult?.ok && activeVisibilityTarget) {
                const result = openResult.result || {};
                const sameTarget = String(result.content_type || "") === activeVisibilityTarget.contentType
                    && String(result.content_id || "") === activeVisibilityTarget.contentId;
                if (sameTarget) {
                    studentBoards = Array.isArray(result.students) ? result.students : [];
                    hiddenStudentIds = new Set(result.hidden_student_ids || []);
                }
            } else if (studentsResult?.ok) {
                const incomingStudents = Array.isArray(studentsResult.result?.students) ? studentsResult.result.students : [];
                if (incomingStudents.length || !studentBoards) studentBoards = incomingStudents;
            }
            if (!visibilityHadError && visibilityDialog.classList.contains("is-open")) renderStudentGrid();
        }
        if (ui.screen === "sync" || syncDialog.classList.contains("is-open")) {
            syncBackdrop.classList.add("is-open");
            syncDialog.classList.add("is-open");
            const planResult = COMPONENT_STATE["/sync-preview-students"];
            const startResult = COMPONENT_STATE["/sync-start-students"];
            const statusResult = COMPONENT_STATE["/sync-status"];
            const latestJob = statusResult?.ok ? statusResult.result : startResult?.ok ? startResult.result : null;
            if (planResult?.ok && (!latestJob || syncMode === "preview")) {
                latestSyncPlan = planResult.result;
                renderSyncPlan(latestSyncPlan);
                syncMode = "idle";
                setSyncBusy(false, "Vista previa lista. Revisa el contenido antes de aplicar.");
                setSaveStatus("Plan listo");
            } else if (planResult?.error && syncMode === "preview") {
                latestSyncPlan = null;
                renderSyncPlan({ students: 0, actions: [], errors: [{ error: planResult.error }] });
                syncMode = "error";
                setSyncBusy(false, planResult.error);
                setSaveStatus("Error sync", "error");
            }
            if (latestJob) {
                if (latestJob.job_id) syncActiveJobId = latestJob.job_id;
                const finishedResult = latestJob.result || null;
                const jobForRender = finishedResult
                    ? { ...latestJob, progress: finishedResult.board_results || latestJob.progress || [] }
                    : latestJob;
                renderSyncProgress(jobForRender, latestSyncPlan);
                const status = latestJob.status || "queued";
                if (status === "done") {
                    if (syncStatusTimer) {
                        window.clearTimeout(syncStatusTimer);
                        syncStatusTimer = null;
                    }
                    const planned = finishedResult?.planned || latestSyncPlan?.actions?.length || 0;
                    const applied = finishedResult?.applied || 0;
                    syncMode = "done";
                    setSyncBusy(false, `Sincronizacion lista: ${applied}/${planned} aplicado(s). Backups creados: ${(finishedResult?.backups || []).length}.`);
                    setSaveStatus("Sincronizado");
                    refreshAuditLog();
                } else if (status === "error") {
                    if (syncStatusTimer) {
                        window.clearTimeout(syncStatusTimer);
                        syncStatusTimer = null;
                    }
                    syncMode = "error";
                    setSyncBusy(false, latestJob.note || latestJob.error || "Error de sincronizacion.");
                    setSaveStatus("Error sync", "error");
                } else {
                    syncMode = "sync";
                    setSyncBusy(true, syncProgressText(latestJob, latestSyncPlan));
                    scheduleSyncStatus(latestJob.job_id || syncActiveJobId);
                }
            }
        }
    }

    window.addEventListener("message", (event) => {
        const message = event.data || {};
        if (message.source !== "admin-paes-component-state") return;
        const incomingRev = message.state_rev ?? message.state?.__state_rev ?? 0;
        if (incomingRev === lastComponentStateRev) return;
        lastComponentStateRev = incomingRev;
        COMPONENT_STATE = message.state || {};
        applyComponentStateToOpenUi();
    });

    function notifyFrameReady() {
        window.requestAnimationFrame(() => {
            window.requestAnimationFrame(() => {
                window.parent.postMessage({ source: "admin-paes-frame-ready" }, "*");
            });
        });
    }

    applyComponentStateToOpenUi();
    renderAuditLog(localAuditEvents());
    setAuditDebug(`JS listo ${new Date().toLocaleTimeString("es-CL")}`);
    refreshAuditLog();
    window.setInterval(refreshAuditLog, 60000);
    window.setTimeout(() => refreshResultsPanel(false), 8000);
    window.setInterval(() => refreshResultsPanel(false), 600000);
    window.setTimeout(notifyFrameReady, 80);
</script>
</body>
</html>
"""
    replacements = {
        "__DATA_JSON__": data_json,
        "__LISTS_HTML__": lists_html,
        "__ADD_LIST_BUTTON__": add_list_button,
        "__BOARD_TITLE__": escape_text(board_title),
        "__SUBTITLE__": escape_text(subtitle),
        "__VERSION__": escape_text(version),
        "__READ_ONLY__": "true" if read_only else "false",
        "__READONLY_CLASS__": readonly_class,
        "__TRELLO_CLASS__": trello_class,
        "__TRELLO_API_BASE__": escape_text(trello_api_base),
        "__TRELLO_API_TOKEN__": escape_text(trello_api_token),
        "__COMPONENT_STATE_JSON__": component_state_json,
        "__ICON_ADD__": icon("add"),
        "__ICON_ARROW_DOWN__": icon("arrow_down"),
        "__ICON_ARROW_LEFT__": icon("arrow_left"),
        "__ICON_ARROW_RIGHT__": icon("arrow_right"),
        "__ICON_ARROW_UP__": icon("arrow_up"),
        "__ICON_BOARD__": icon("board"),
        "__ICON_CARD__": icon("card"),
        "__ICON_CHECK__": icon("check"),
        "__ICON_CLOSE__": icon("close"),
        "__ICON_EDIT__": icon("edit"),
        "__ICON_GRIP__": icon("grip"),
        "__ICON_FILE__": icon("file"),
        "__ICON_IMAGE__": icon("image"),
        "__ICON_LINK__": icon("link"),
        "__ICON_TRASH__": icon("trash"),
        "__ICON_USERS__": icon("users"),
        "__ICON_VIEW__": icon("view"),
    }
    for token, value in replacements.items():
        document = document.replace(token, value)
    return document
