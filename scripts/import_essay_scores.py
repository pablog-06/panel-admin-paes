from __future__ import annotations

import argparse
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from panel import results_db
from panel.audit import backup_database, write_audit_log
from panel.results_db import EssayScore
from panel.trello_client import TrelloConfig, TrelloReadOnlyError, _get_json


PAES_BOARD_PATTERN = re.compile(r"^\s*PAES\b[\s:_-]*(?P<student>.+?)\s*$", re.IGNORECASE)
TRAILING_STUDENT_PUNCTUATION = " .,:;_-"
EXCLUDED_PAES_BOARD_NAMES = (
    "PAES ALUMNO ESTRELLA",
    "PAES alumno01",
    "PAES Prueba Automatización",
    "PAES Prueba_Naty",
    "PAES TEST",
)
ESSAY_NUMBER_PATTERN = re.compile(r"\bensayo\s*#?\s*(?P<number>\d{1,3})\b", re.IGNORECASE)
SCORE_OVER_1000_PATTERN = re.compile(r"(?<!\d)(?P<score>\d{2,4})\s*/\s*1[\s.]?000\b", re.IGNORECASE)
LABELLED_SCORE_PATTERN = re.compile(
    r"\b(?:puntaje|ptje|pts?|score|resultado)\s*[:=-]?\s*(?P<score>\d{2,4})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedEssay:
    essay_name: str
    score: int
    card_name: str
    card_id: str


def normalize_text(value: str) -> str:
    without_accents = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(ch for ch in without_accents if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def is_excluded_board_name(board_name: str) -> bool:
    excluded_names = {normalize_text(name) for name in EXCLUDED_PAES_BOARD_NAMES}
    return normalize_text(board_name) in excluded_names


def excluded_student_names() -> list[str]:
    return [
        student
        for board_name in EXCLUDED_PAES_BOARD_NAMES
        if (student := student_name_from_board(board_name)) is not None
    ]


def delete_students_by_names(student_names: list[str]) -> None:
    delete_func = getattr(results_db, "delete_students_by_names", None)
    if callable(delete_func):
        delete_func(student_names)
        return

    names = [name.strip() for name in student_names if name.strip()]
    if not names:
        return
    results_db.initialize_database()
    with results_db.database() as connection:
        connection.executemany("DELETE FROM students WHERE name = ?", [(name,) for name in names])


def replace_imported_scores(scores: list[EssayScore]) -> None:
    replace_func = getattr(results_db, "replace_imported_scores", None)
    if callable(replace_func):
        replace_func(scores)
        return

    results_db.initialize_database()
    with results_db.database() as connection:
        connection.execute("DELETE FROM essay_scores WHERE source_board_id <> ''")
        connection.execute(
            """
            DELETE FROM students
            WHERE id NOT IN (SELECT DISTINCT student_id FROM essay_scores)
            """
        )
        for score in scores:
            student_name = score.student_name.strip()
            essay_name = score.essay_name.strip()
            if not student_name or not essay_name or not 0 <= int(score.score) <= 1000:
                continue
            connection.execute(
                """
                INSERT INTO students(name)
                VALUES (?)
                ON CONFLICT(name) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                """,
                (student_name,),
            )
            student_id = connection.execute(
                "SELECT id FROM students WHERE name = ?",
                (student_name,),
            ).fetchone()["id"]
            connection.execute(
                """
                INSERT INTO essay_scores(
                    student_id, essay_name, score, source_board_id, source_card_id
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(student_id, essay_name) DO UPDATE SET
                    score = excluded.score,
                    source_board_id = excluded.source_board_id,
                    source_card_id = excluded.source_card_id,
                    observed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    student_id,
                    essay_name,
                    int(score.score),
                    score.source_board_id.strip(),
                    score.source_card_id.strip(),
                ),
            )


def load_config() -> TrelloConfig:
    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"
    secrets: dict[str, Any] = {}
    if secrets_path.exists() and tomllib is not None:
        secrets = tomllib.loads(secrets_path.read_text(encoding="utf-8"))

    def value(name: str, default: str = "") -> str:
        return str(secrets.get(name) or os.getenv(name, default)).strip()

    return TrelloConfig(
        api_key=value("TRELLO_API_KEY"),
        token=value("TRELLO_TOKEN"),
        board_name="",
        board_id="",
    )


def student_name_from_board(board_name: str) -> str | None:
    match = PAES_BOARD_PATTERN.match(board_name or "")
    if not match:
        return None
    student = re.sub(r"\s+", " ", match.group("student")).strip()
    student = student.rstrip(TRAILING_STUDENT_PUNCTUATION).strip()
    if not re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", student):
        return None
    return student or None


def extract_score(text: str) -> int | None:
    normalized = normalize_text(text).replace(",", ".")
    match = SCORE_OVER_1000_PATTERN.search(normalized)
    if match:
        return clamp_score(match.group("score"))

    match = LABELLED_SCORE_PATTERN.search(normalized)
    if match:
        return clamp_score(match.group("score"))

    candidates = []
    for raw in re.findall(r"(?<![/\d])\b\d{3,4}\b(?!\s*/\s*75)(?!\s*/\s*100)", normalized):
        score = clamp_score(raw)
        if score is not None and score >= 100:
            candidates.append(score)
    return candidates[-1] if candidates else None


def clamp_score(value: str) -> int | None:
    try:
        score = int(str(value).strip())
    except ValueError:
        return None
    if 0 <= score <= 1000:
        return score
    return None


def extract_essay_name(text: str) -> str | None:
    normalized = normalize_text(text)
    match = ESSAY_NUMBER_PATTERN.search(normalized)
    if match:
        return f"Ensayo {int(match.group('number'))}"
    if "ensayo" in normalized:
        return "Ensayo sin numero"
    return None


def parse_essay_card(card: dict[str, Any]) -> ParsedEssay | None:
    name = str(card.get("name") or "")
    desc = str(card.get("desc") or "")
    combined = f"{name}\n{desc}"
    essay_name = extract_essay_name(combined)
    score = extract_score(combined)
    if not essay_name or score is None:
        return None
    return ParsedEssay(
        essay_name=essay_name,
        score=score,
        card_name=name,
        card_id=str(card.get("id") or ""),
    )


def fetch_open_boards(config: TrelloConfig) -> list[dict[str, Any]]:
    return _get_json(
        "/members/me/boards",
        config,
        {"filter": "open", "fields": "name,url,closed"},
    )


def fetch_board_lists_and_cards(config: TrelloConfig, board_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    board = _get_json(
        f"/boards/{board_id}",
        config,
        {
            "fields": "name",
            "lists": "open",
            "list_fields": "name,pos,closed",
            "cards": "open",
            "card_fields": "name,desc,pos,closed,idList,shortLink,url",
        },
    )
    return board.get("lists") or [], board.get("cards") or []


def import_scores(*, dry_run: bool, delay: float, limit: int | None) -> tuple[int, int, int]:
    config = load_config()
    if not config.api_key or not config.token:
        raise SystemExit("Faltan TRELLO_API_KEY y TRELLO_TOKEN en .streamlit/secrets.toml o variables de entorno.")

    boards = fetch_open_boards(config)
    paes_boards = [
        (board, student)
        for board in boards
        if not is_excluded_board_name(str(board.get("name") or ""))
        and (student := student_name_from_board(str(board.get("name") or ""))) is not None
    ]
    if limit is not None:
        paes_boards = paes_boards[:limit]

    found_scores: list[EssayScore] = []
    skipped_cards = 0

    for index, (board, student_name) in enumerate(paes_boards, start=1):
        board_id = str(board.get("id") or "")
        board_name = str(board.get("name") or "")
        try:
            lists, cards = fetch_board_lists_and_cards(config, board_id)
        except TrelloReadOnlyError as error:
            print(f"[WARN] No se pudo leer {board_name}: {error}")
            continue

        ensayo_lists = [
            item for item in lists
            if normalize_text(str(item.get("name") or "")) == "ensayos"
        ]
        if not ensayo_lists:
            print(f"[INFO] {board_name}: sin lista Ensayos.")
            continue

        ensayo_list_ids = {item["id"] for item in ensayo_lists}
        essay_cards = [
            card for card in cards
            if card.get("idList") in ensayo_list_ids and not card.get("closed")
        ]

        for card in essay_cards:
            parsed = parse_essay_card(card)
            if parsed is None:
                skipped_cards += 1
                print(f"[SKIP] {board_name}: no pude interpretar tarjeta {card.get('name')!r}")
                continue
            found_scores.append(
                EssayScore(
                    student_name=student_name,
                    essay_name=parsed.essay_name,
                    score=parsed.score,
                    source_board_id=board_id,
                    source_card_id=parsed.card_id,
                )
            )
            print(f"[OK] {student_name} | {parsed.essay_name} | {parsed.score}")

        if delay and index < len(paes_boards):
            time.sleep(delay)

    if not dry_run:
        backup_database("before_import_essay_scores")
        delete_students_by_names(excluded_student_names())
        replace_imported_scores(found_scores)
        write_audit_log(
            "import_essay_scores",
            f"Puntajes sincronizados: {len(found_scores)}.",
            meta={"boards": len(paes_boards), "skipped_cards": skipped_cards},
        )

    return len(paes_boards), len(found_scores), skipped_cards


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa puntajes desde listas Ensayos de boards PAES <Alumno> hacia SQLite local."
    )
    parser.add_argument("--dry-run", action="store_true", help="Lee y muestra resultados sin escribir en SQLite.")
    parser.add_argument("--delay", type=float, default=0.25, help="Pausa entre boards para cuidar el rate limit.")
    parser.add_argument("--limit", type=int, default=None, help="Limita la cantidad de boards PAES procesados.")
    args = parser.parse_args()

    board_count, score_count, skipped_count = import_scores(
        dry_run=args.dry_run,
        delay=max(args.delay, 0),
        limit=args.limit,
    )
    action = "detectados" if args.dry_run else "guardados"
    print(f"Boards PAES revisados: {board_count}")
    print(f"Puntajes {action}: {score_count}")
    print(f"Tarjetas omitidas por formato: {skipped_count}")


if __name__ == "__main__":
    main()
