from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


API_BASE_URL = "https://api.trello.com/1"
PRIVATE_LIST_NAMES = {"ensayos"}
URL_PATTERN = re.compile(r"https?://[^\s)>\"]+")
PAES_BOARD_PATTERN = re.compile(r"^\s*PAES\b[\s:_-]*(?P<student>.+?)\s*$", re.IGNORECASE)
TRAILING_STUDENT_PUNCTUATION = " .,:;_-–—"
EXCLUDED_PAES_BOARD_NAMES = {
    "PAES ALUMNO ESTRELLA",
    "PAES alumno01",
    "PAES Prueba Automatización",
    "PAES Prueba_Naty",
    "PAES TEST",
}
_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0
_MIN_REQUEST_INTERVAL_SECONDS = 0.08


class TrelloReadOnlyError(RuntimeError):
    """Raised when Trello cannot be read in Etapa 2."""


@dataclass(frozen=True)
class TrelloConfig:
    api_key: str
    token: str
    board_name: str = ""
    board_id: str = ""

    @property
    def is_complete(self) -> bool:
        return bool(self.api_key and self.token)


def _request_json(
    path: str,
    config: TrelloConfig,
    params: dict[str, Any] | None = None,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    query = {
        "key": config.api_key,
        "token": config.token,
        **(params or {}),
    }
    url = f"{API_BASE_URL}{path}?{urlencode(query)}"
    request_headers = {"Accept": "application/json", **(headers or {})}
    for attempt in range(4):
        request = Request(url, data=data, headers=request_headers, method=method)
        try:
            _throttle_request()
            with urlopen(request, timeout=24) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code == 429 and attempt < 3:
                retry_after = _retry_after_seconds(error)
                time.sleep(retry_after)
                continue
            raise TrelloReadOnlyError(f"Trello respondio {error.code}: {detail}") from error
        except URLError as error:
            if attempt < 2:
                time.sleep(0.8 * (attempt + 1))
                continue
            raise TrelloReadOnlyError(f"No se pudo conectar con Trello: {error.reason}") from error
        except json.JSONDecodeError as error:
            raise TrelloReadOnlyError("Trello respondio con JSON invalido.") from error
    raise TrelloReadOnlyError("Trello no respondio despues de varios reintentos.")


def _throttle_request() -> None:
    global _LAST_REQUEST_AT
    with _REQUEST_LOCK:
        now = time.monotonic()
        wait_for = _MIN_REQUEST_INTERVAL_SECONDS - (now - _LAST_REQUEST_AT)
        if wait_for > 0:
            time.sleep(wait_for)
        _LAST_REQUEST_AT = time.monotonic()


def _retry_after_seconds(error: HTTPError) -> float:
    raw = error.headers.get("Retry-After") if error.headers else ""
    try:
        return min(30.0, max(2.0, float(raw)))
    except (TypeError, ValueError):
        return 5.0


def _get_json(path: str, config: TrelloConfig, params: dict[str, Any] | None = None) -> Any:
    return _request_json(path, config, params, method="GET")


def _post_json(path: str, config: TrelloConfig, params: dict[str, Any] | None = None) -> Any:
    return _request_json(path, config, params, method="POST")


def _put_json(path: str, config: TrelloConfig, params: dict[str, Any] | None = None) -> Any:
    return _request_json(path, config, params, method="PUT")


def _extract_links(text: str) -> list[str]:
    return URL_PATTERN.findall(text or "")


def _normalize_text(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip()).casefold()
    replacements = str.maketrans("áéíóúüñ", "aeiouun")
    return normalized.translate(replacements)


def student_name_from_paes_board(board_name: str) -> str | None:
    match = PAES_BOARD_PATTERN.match(board_name or "")
    if not match:
        return None
    student = re.sub(r"\s+", " ", match.group("student")).strip()
    student = student.rstrip(TRAILING_STUDENT_PUNCTUATION).strip()
    if not re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", student):
        return None
    return student or None


def is_excluded_paes_board(board_name: str) -> bool:
    excluded = {_normalize_text(name) for name in EXCLUDED_PAES_BOARD_NAMES}
    return _normalize_text(board_name) in excluded


def initials_for_student(student_name: str) -> str:
    parts = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+", student_name.strip())
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return f"{parts[0][0]}{parts[-1][0]}".upper()


def fetch_student_boards_read_only(config: TrelloConfig) -> list[dict[str, str]]:
    return _fetch_student_boards_cached(config.api_key, config.token)


@lru_cache(maxsize=8)
def _fetch_student_boards_cached(api_key: str, token: str) -> list[dict[str, str]]:
    config = TrelloConfig(api_key=api_key, token=token)
    boards = _get_json(
        "/members/me/boards",
        config,
        {"filter": "open", "fields": "name,url,closed"},
    )
    students: list[dict[str, str]] = []
    for board in boards or []:
        board_name = str(board.get("name") or "")
        student_name = student_name_from_paes_board(board_name)
        if not student_name or is_excluded_paes_board(board_name):
            continue
        students.append(
            {
                "board_id": str(board.get("id") or ""),
                "board_name": board_name,
                "student_name": student_name,
                "initials": initials_for_student(student_name),
                "url": str(board.get("url") or ""),
            }
        )
    return sorted(students, key=lambda item: item["student_name"].casefold())


def fetch_paes_board_inventory_read_only(config: TrelloConfig) -> dict[str, list[dict[str, str]]]:
    boards = _get_json(
        "/members/me/boards",
        config,
        {"filter": "open", "fields": "name,url,closed"},
    )
    students: list[dict[str, str]] = []
    unknown: list[dict[str, str]] = []
    for board in boards or []:
        board_name = str(board.get("name") or "")
        if is_excluded_paes_board(board_name):
            continue
        student_name = student_name_from_paes_board(board_name)
        if student_name:
            students.append(
                {
                    "board_id": str(board.get("id") or ""),
                    "board_name": board_name,
                    "student_name": student_name,
                    "initials": initials_for_student(student_name),
                    "url": str(board.get("url") or ""),
                }
            )
            continue
        if "paes" in _normalize_text(board_name):
            unknown.append(
                {
                    "board_id": str(board.get("id") or ""),
                    "board_name": board_name,
                    "student_name": "",
                    "initials": "?",
                    "url": str(board.get("url") or ""),
                    "status": "unknown",
                }
            )
    return {
        "students": sorted(students, key=lambda item: item["student_name"].casefold()),
        "unknown": sorted(unknown, key=lambda item: item["board_name"].casefold()),
    }


def _is_trello_card_url(value: str) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.netloc.endswith("trello.com") and "/c/" in parsed.path


def _looks_like_image_url(value: str) -> bool:
    path = urlparse(str(value or "")).path.casefold()
    return path.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"))


def _attachment_images(card: dict[str, Any]) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    for attachment in card.get("attachments") or []:
        url = str(attachment.get("url") or "").strip()
        name = str(attachment.get("name") or "").strip() or "Imagen"
        mime_type = str(attachment.get("mimeType") or "").casefold()
        if not url:
            continue
        if mime_type.startswith("image/") or _looks_like_image_url(url):
            images.append({"name": name, "src": url})
    return images


def _cover_images(card: dict[str, Any]) -> list[dict[str, str]]:
    cover = card.get("cover") or {}
    scaled = cover.get("scaled") or []
    image_url = ""
    if isinstance(scaled, list) and scaled:
        image_url = (scaled[-1] or {}).get("url") or ""
    image_url = image_url or cover.get("url") or ""
    if not image_url:
        return []
    return [{"name": "Cover de Trello", "src": image_url}]


def _checklists_from_trello(config: TrelloConfig, card_id: str) -> list[dict[str, Any]]:
    if not card_id:
        return []
    checklists = _get_json(f"/cards/{card_id}/checklists", config, {"checkItems": "all"}) or []
    transformed: list[dict[str, Any]] = []
    for checklist in checklists:
        items = []
        for item in checklist.get("checkItems") or []:
            name = str(item.get("name") or "").strip()
            if name:
                items.append({"name": name, "state": item.get("state") or "incomplete"})
        transformed.append(
            {
                "title": str(checklist.get("name") or "Checklist").strip(),
                "description": "",
                "link": "",
                "items": items,
            }
        )
    return transformed


def _attachment_links(card: dict[str, Any]) -> list[str]:
    links: list[str] = []
    for attachment in card.get("attachments") or []:
        url = str(attachment.get("url") or "").strip()
        mime_type = str(attachment.get("mimeType") or "").casefold()
        if not url or _is_trello_card_url(url):
            continue
        if mime_type.startswith("image/") or _looks_like_image_url(url):
            continue
        links.append(url)
    return links


def _attachment_files(card: dict[str, Any]) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for attachment in card.get("attachments") or []:
        url = str(attachment.get("url") or "").strip()
        name = str(attachment.get("name") or "").strip() or "Archivo"
        mime_type = str(attachment.get("mimeType") or "").casefold()
        if not url or _is_trello_card_url(url):
            continue
        if mime_type.startswith("image/") or _looks_like_image_url(url):
            continue
        if mime_type == "application/pdf" or urlparse(url).path.casefold().endswith(".pdf"):
            files.append({"name": name, "src": url, "content_type": "application/pdf"})
    return files


def _dedupe_images(images: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for image in images:
        src = str(image.get("src") or "").strip()
        if not src or src in seen:
            continue
        seen.add(src)
        deduped.append(image)
    return deduped


def _transform_card(
    card: dict[str, Any],
    config: TrelloConfig | None = None,
    *,
    include_checklists: bool = False,
) -> dict[str, Any]:
    desc = card.get("desc") or ""
    labels = card.get("labels") or []
    label_names = [label.get("name") or label.get("color") for label in labels if label]
    badges = card.get("badges") or {}
    description_parts = []
    if desc:
        description_parts.append(desc)
    if card.get("due"):
        description_parts.append(f"Vence: {card['due']}")
    if label_names:
        description_parts.append("Etiquetas: " + ", ".join(label_names))
    attachment_images = _attachment_images(card)
    images = attachment_images if attachment_images else _cover_images(card)

    return {
        "id": card.get("id") or card.get("shortLink") or card.get("name"),
        "title": card.get("name") or "Tarjeta sin titulo",
        "pos": card.get("pos") or 0,
        "description": "\n\n".join(description_parts),
        "links": sorted(set([*_extract_links(desc), *_attachment_links(card)])),
        "images": _dedupe_images(images),
        "files": _attachment_files(card),
        "checklists": (
            _checklists_from_trello(config, str(card.get("id") or ""))
            if include_checklists and config and (badges.get("checkItems") or 0)
            else []
        ),
        "badges": {
            "comments": badges.get("comments") or 0,
            "attachments": badges.get("attachments") or 0,
            "check_items": badges.get("checkItems") or 0,
            "check_items_checked": badges.get("checkItemsChecked") or 0,
        },
        "source_url": card.get("url") or "",
    }


def fetch_board_lists_with_cards_read_only(
    config: TrelloConfig,
    board_id: str,
    *,
    include_checklists: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    board = _get_json(
        f"/boards/{board_id}",
        config,
        {
            "fields": "name,url",
            "lists": "open",
            "list_fields": "name,pos,closed",
            "cards": "open",
            "card_fields": "name,desc,pos,url,due,labels,badges,cover,closed,shortLink,idList",
            "card_attachments": "true",
        },
    )
    lists = board.get("lists") or []
    cards = board.get("cards") or []
    cards_by_list: dict[str, list[dict[str, Any]]] = {}
    for card in cards:
        if card.get("closed"):
            continue
        cards_by_list.setdefault(str(card.get("idList") or ""), []).append(card)

    board_lists: list[dict[str, Any]] = []
    for item in sorted(lists, key=lambda value: value.get("pos", 0)):
        if (item.get("name") or "").strip().lower() in PRIVATE_LIST_NAMES:
            continue
        list_cards = sorted(cards_by_list.get(str(item.get("id") or ""), []), key=lambda value: value.get("pos", 0))
        board_lists.append(
            {
                "id": item["id"],
                "name": item.get("name") or "Lista sin titulo",
                "pos": item.get("pos") or 0,
                "cards": [
                    _transform_card(card, config, include_checklists=include_checklists)
                    for card in list_cards
                ],
                "source": "trello",
                "read_only": True,
            }
        )

    return board.get("name") or "Tablero Trello", board_lists


def fetch_board_list_headers_read_only(config: TrelloConfig, board_id: str) -> tuple[str, list[dict[str, Any]]]:
    board = _get_json(
        f"/boards/{board_id}",
        config,
        {
            "fields": "name,url",
            "lists": "open",
            "list_fields": "name,pos,closed",
        },
    )
    board_lists = []
    for item in sorted(board.get("lists") or [], key=lambda value: value.get("pos", 0)):
        if (item.get("name") or "").strip().lower() in PRIVATE_LIST_NAMES:
            continue
        board_lists.append(
            {
                "id": item["id"],
                "name": item.get("name") or "Lista sin titulo",
                "pos": item.get("pos") or 0,
                "cards": [],
                "source": "trello",
                "read_only": True,
            }
        )
    return board.get("name") or "Tablero Trello", board_lists


def _assert_student_board_id(config: TrelloConfig, board_id: str) -> None:
    board_id = str(board_id or "").strip()
    if not board_id:
        raise TrelloReadOnlyError("Board de alumno vacio.")
    boards = fetch_student_boards_read_only(config)
    if board_id not in {board["board_id"] for board in boards}:
        raise TrelloReadOnlyError("El board destino no es un tablero PAES de alumno permitido.")


def _assert_list_belongs_to_student_board(config: TrelloConfig, board_id: str, list_id: str) -> dict[str, Any]:
    _assert_student_board_id(config, board_id)
    trello_list = _get_json(f"/lists/{list_id}", config, {"fields": "name,closed,idBoard"})
    if str(trello_list.get("idBoard") or "") != board_id:
        raise TrelloReadOnlyError("La lista destino no pertenece al tablero del alumno.")
    if normalize_label_for_private_list(str(trello_list.get("name") or "")) in PRIVATE_LIST_NAMES:
        raise TrelloReadOnlyError("La lista Ensayos es privada e inmodificable.")
    return trello_list


def _assert_card_belongs_to_student_board(config: TrelloConfig, board_id: str, card_id: str) -> dict[str, Any]:
    _assert_student_board_id(config, board_id)
    card = _get_json(f"/cards/{card_id}", config, {"fields": "idList,idBoard,name,closed"})
    if str(card.get("idBoard") or "") != board_id:
        raise TrelloReadOnlyError("La tarjeta destino no pertenece al tablero del alumno.")
    _assert_list_belongs_to_student_board(config, board_id, str(card.get("idList") or ""))
    return card


def normalize_label_for_private_list(value: str) -> str:
    return _normalize_text(value)


def archive_student_list(config: TrelloConfig, board_id: str, list_id: str) -> dict[str, Any]:
    _assert_list_belongs_to_student_board(config, board_id, list_id)
    return _put_json(f"/lists/{list_id}", config, {"closed": "true"})


def archive_student_card(config: TrelloConfig, board_id: str, card_id: str) -> dict[str, Any]:
    _assert_card_belongs_to_student_board(config, board_id, card_id)
    return _put_json(f"/cards/{card_id}", config, {"closed": "true"})


def create_student_list(config: TrelloConfig, board_id: str, name: str) -> dict[str, Any]:
    _assert_student_board_id(config, board_id)
    clean_name = str(name or "").strip()
    if normalize_label_for_private_list(clean_name) in PRIVATE_LIST_NAMES:
        raise TrelloReadOnlyError("La lista Ensayos es privada e inmodificable.")
    return _post_json("/lists", config, {"idBoard": board_id, "name": clean_name, "pos": "bottom"})


def create_student_card(
    config: TrelloConfig,
    board_id: str,
    list_id: str,
    title: str,
    description: str = "",
) -> dict[str, Any]:
    _assert_list_belongs_to_student_board(config, board_id, list_id)
    return _post_json(
        "/cards",
        config,
        {
            "idList": list_id,
            "name": str(title or "").strip(),
            "desc": str(description or "").strip(),
            "pos": "bottom",
        },
    )


def update_student_card(
    config: TrelloConfig,
    board_id: str,
    card_id: str,
    title: str,
    description: str,
) -> dict[str, Any]:
    _assert_card_belongs_to_student_board(config, board_id, card_id)
    return _put_json(
        f"/cards/{card_id}",
        config,
        {"name": str(title or "").strip(), "desc": str(description or "").strip()},
    )


def attach_url_to_student_card(
    config: TrelloConfig,
    board_id: str,
    card_id: str,
    url: str,
    name: str = "",
) -> dict[str, Any]:
    _assert_card_belongs_to_student_board(config, board_id, card_id)
    params = {"url": str(url or "").strip()}
    if name:
        params["name"] = str(name).strip()
    return _post_json(f"/cards/{card_id}/attachments", config, params)


def attach_file_to_student_card(
    config: TrelloConfig,
    board_id: str,
    card_id: str,
    filename: str,
    content: bytes,
    content_type: str = "application/octet-stream",
) -> dict[str, Any]:
    _assert_card_belongs_to_student_board(config, board_id, card_id)
    boundary = f"----paes{uuid.uuid4().hex}"
    body = BytesIO()
    body.write(f"--{boundary}\r\n".encode("utf-8"))
    body.write(
        (
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
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


def create_student_checklist(
    config: TrelloConfig,
    board_id: str,
    card_id: str,
    name: str,
    items: list[str],
) -> dict[str, Any]:
    _assert_card_belongs_to_student_board(config, board_id, card_id)
    checklist = _post_json(
        f"/cards/{card_id}/checklists",
        config,
        {"name": str(name or "").strip(), "pos": "bottom"},
    )
    for item in items:
        clean_item = str(item or "").strip()
        if clean_item:
            _post_json(
                f"/checklists/{checklist['id']}/checkItems",
                config,
                {"name": clean_item, "pos": "bottom"},
            )
    return checklist
