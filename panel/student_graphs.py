from __future__ import annotations

import math
import unicodedata
import re
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from panel.audit import write_audit_log
from panel.results_db import DB_PATH, _decrypt_student_name, database, essay_sort_key, initialize_database
from panel.trello_client import TrelloConfig, TrelloReadOnlyError, _get_json, _post_json, _put_json, _request_json

PRIVATE_LIST_NAME = "ensayos"
GRAPH_CARD_NAMES = {"grafico"}
GRAPH_FILENAME = "grafico_progreso.png"
MIN_POINTS = 2


@dataclass(frozen=True)
class StudentScoreSeries:
    board_id: str
    student_name: str
    points: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class GraphUpdateEvent:
    board_id: str
    student_name: str
    status: str
    detail: str


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").strip())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", normalized).casefold()


def _is_graph_card_name(value: str) -> bool:
    return _normalize_text(value) in GRAPH_CARD_NAMES


def _exam_number(essay_name: str) -> int | None:
    number, _ = essay_sort_key(essay_name)
    return number if number >= 0 else None


def load_student_score_series(db_path=DB_PATH, *, active_only: bool = True) -> list[StudentScoreSeries]:
    initialize_database(db_path)
    with database(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                essay_scores.source_board_id,
                students.name_hash,
                students.name_encrypted AS student_name_encrypted,
                essay_scores.essay_name,
                essay_scores.score,
                student_boards.status AS board_status
            FROM essay_scores
            JOIN students ON students.id = essay_scores.student_id
            LEFT JOIN student_boards ON student_boards.board_id = essay_scores.source_board_id
            WHERE essay_scores.source_board_id <> ''
            ORDER BY students.name_hash ASC, essay_scores.essay_name ASC
            """
        ).fetchall()

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        board_id = str(row["source_board_id"] or "").strip()
        if not board_id:
            continue
        status = str(row["board_status"] or "open")
        if active_only and status == "archived":
            continue
        exam = _exam_number(str(row["essay_name"] or ""))
        if exam is None:
            continue
        score = int(row["score"])
        item = grouped.setdefault(
            board_id,
            {"student_name": _decrypt_student_name(row), "scores": {}},
        )
        item["scores"][exam] = score

    series: list[StudentScoreSeries] = []
    for board_id, item in grouped.items():
        points = tuple(sorted((int(exam), int(score)) for exam, score in item["scores"].items()))
        if points:
            series.append(StudentScoreSeries(board_id=board_id, student_name=str(item["student_name"]), points=points))
    return series


def _linear_regression(points: Iterable[tuple[int, int]]) -> tuple[float, float, float | None, list[float]]:
    ordered = list(points)
    xs = [float(x) for x, _ in ordered]
    ys = [float(y) for _, y in ordered]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        slope = 0.0
        intercept = mean_y
    else:
        slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
        intercept = mean_y - slope * mean_x
    predicted = [slope * x + intercept for x in xs]
    ss_res = sum((y - y_hat) ** 2 for y, y_hat in zip(ys, predicted))
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    r2 = None if math.isclose(ss_tot, 0.0) else 1 - (ss_res / ss_tot)
    return slope, intercept, r2, predicted


def render_student_graph_png(series: StudentScoreSeries) -> bytes:
    if len(series.points) < MIN_POINTS:
        raise ValueError("Se necesitan al menos dos puntajes para graficar.")

    points = sorted(series.points)
    xs = [exam for exam, _ in points]
    ys = [score for _, score in points]
    slope, intercept, r2, predicted = _linear_regression(points)

    fig, ax = plt.subplots(figsize=(8, 5), dpi=100)
    ax.plot(xs, predicted, linestyle="--", linewidth=1.5, color="#1f77b4", label="Regresi\u00f3n lineal")
    ax.plot(xs, ys, marker="o", linewidth=1.5, markersize=6, color="#ff7f0e", label="Datos")

    r2_text = "R\u00b2 = n/a" if r2 is None else f"R\u00b2 = {r2:.3f}"
    ax.text(
        0.95,
        0.90,
        f"y = {slope:.2f}x + {intercept:.2f}\n{r2_text}",
        transform=ax.transAxes,
        horizontalalignment="right",
        verticalalignment="top",
        fontsize=10,
        color="black",
    )

    ax.set_title("Gr\u00e1fico de progreso", fontsize=14, weight="normal", color="black")
    ax.set_xlabel("Ensayo", color="black")
    ax.set_ylabel("Puntaje", color="black")
    ax.set_ylim(100, 1000)
    ax.set_yticks(range(100, 1001, 100))
    ax.set_xticks(xs)
    ax.grid(True, color="#b0b0b0", linewidth=0.8, alpha=1.0)
    ax.legend(loc="upper left", frameon=True)
    fig.tight_layout()

    output = BytesIO()
    fig.savefig(output, format="png")
    plt.close(fig)
    return output.getvalue()


def _fetch_ensayos_context(config: TrelloConfig, board_id: str) -> tuple[str, list[dict[str, Any]]]:
    board = _get_json(
        f"/boards/{board_id}",
        config,
        {
            "fields": "name,closed",
            "lists": "open",
            "list_fields": "name,pos,closed",
            "cards": "open",
            "card_fields": "name,pos,closed,idList",
            "card_attachments": "true",
        },
    )
    lists = board.get("lists") or []
    ensayo_lists = [item for item in lists if _normalize_text(item.get("name") or "") == PRIVATE_LIST_NAME]
    if not ensayo_lists:
        raise TrelloReadOnlyError("No se encontro lista Ensayos.")
    ensayo_list = sorted(ensayo_lists, key=lambda item: item.get("pos") or 0)[0]
    list_id = str(ensayo_list.get("id") or "")
    cards = [card for card in board.get("cards") or [] if str(card.get("idList") or "") == list_id and not card.get("closed")]
    cards.sort(key=lambda item: item.get("pos") or 0)
    return list_id, cards


def _get_or_create_graph_card(config: TrelloConfig, list_id: str, cards: list[dict[str, Any]]) -> dict[str, Any]:
    for card in cards:
        if _is_graph_card_name(str(card.get("name") or "")):
            if card.get("pos") != "top":
                _put_json(f"/cards/{card['id']}", config, {"pos": "top"})
            return card
    return _post_json("/cards", config, {"idList": list_id, "name": "Grafico", "pos": "top"})


def _delete_old_graph_attachments(config: TrelloConfig, card_id: str) -> int:
    attachments = _get_json(f"/cards/{card_id}/attachments", config, {"fields": "name,mimeType,url"}) or []
    deleted = 0
    for attachment in attachments:
        name = _normalize_text(attachment.get("name") or "")
        mime_type = str(attachment.get("mimeType") or "").casefold()
        if "grafico" not in name and "progreso" not in name and not mime_type.startswith("image/"):
            continue
        _request_json(f"/cards/{card_id}/attachments/{attachment['id']}", config, method="DELETE")
        deleted += 1
    return deleted


def _upload_graph_png(config: TrelloConfig, card_id: str, content: bytes) -> dict[str, Any]:
    boundary = f"----paesgraph{int(time.time() * 1000)}"
    body = BytesIO()
    body.write(f"--{boundary}\r\n".encode("utf-8"))
    body.write(
        (
            f'Content-Disposition: form-data; name="file"; filename="{GRAPH_FILENAME}"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode("utf-8")
    )
    body.write(content)
    body.write(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return _request_json(
        f"/cards/{card_id}/attachments",
        config,
        method="POST",
        data=body.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )


def update_student_graph(config: TrelloConfig, series: StudentScoreSeries) -> GraphUpdateEvent:
    if len(series.points) < MIN_POINTS:
        return GraphUpdateEvent(series.board_id, series.student_name, "skipped", "Datos insuficientes para graficar.")
    list_id, cards = _fetch_ensayos_context(config, series.board_id)
    graph_card = _get_or_create_graph_card(config, list_id, cards)
    content = render_student_graph_png(series)
    deleted = _delete_old_graph_attachments(config, str(graph_card["id"]))
    _upload_graph_png(config, str(graph_card["id"]), content)
    return GraphUpdateEvent(
        series.board_id,
        series.student_name,
        "updated",
        f"Grafico actualizado con {len(series.points)} puntaje(s). Adjuntos previos eliminados: {deleted}.",
    )


def update_all_student_graphs(
    config: TrelloConfig,
    *,
    limit: int | None = None,
    delay: float = 0.15,
    active_only: bool = True,
) -> dict[str, Any]:
    if not config.is_complete:
        raise TrelloReadOnlyError("Faltan credenciales Trello para actualizar graficos.")

    series_list = load_student_score_series(active_only=active_only)
    if limit is not None:
        series_list = series_list[: max(0, int(limit))]

    events: list[GraphUpdateEvent] = []
    errors: list[dict[str, str]] = []
    for index, series in enumerate(series_list, start=1):
        try:
            event = update_student_graph(config, series)
            events.append(event)
        except Exception as error:  # Keep the batch resilient board by board.
            errors.append({"board_id": series.board_id, "student_name": series.student_name, "error": str(error)})
        if delay and index < len(series_list):
            time.sleep(max(0.0, delay))

    updated = sum(1 for event in events if event.status == "updated")
    skipped = sum(1 for event in events if event.status == "skipped")
    result = {
        "boards": len(series_list),
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "events": [event.__dict__ for event in events[-80:]],
    }
    write_audit_log(
        "Actualizar graficos Ensayos",
        f"Graficos actualizados: {updated}. Omitidos: {skipped}. Errores: {len(errors)}.",
        status="error" if errors else "ok",
        meta={"updated": updated, "skipped": skipped, "errors": errors[:20]},
    )
    return result


