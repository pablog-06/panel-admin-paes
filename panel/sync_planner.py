from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse


PRIVATE_LIST_NAMES = {"ensayos"}
LIST_MATCH_THRESHOLD = 0.88
CARD_MATCH_THRESHOLD = 0.86


@dataclass(frozen=True)
class SyncAction:
    action: str
    list_name: str
    card_title: str = ""
    detail: str = ""
    confidence: float = 1.0
    payload: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_label(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = without_accents.casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", lowered)).strip()


def normalize_body(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def is_private_list(board_list: dict[str, Any]) -> bool:
    return normalize_label(str(board_list.get("name", ""))) in PRIVATE_LIST_NAMES


def visible_lists(lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [board_list for board_list in lists if not is_private_list(board_list)]


def similarity(left: str, right: str) -> float:
    left_key = normalize_label(left)
    right_key = normalize_label(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    return SequenceMatcher(None, left_key, right_key).ratio()


def best_match(
    source_name: str,
    candidates: list[dict[str, Any]],
    *,
    threshold: float,
) -> tuple[dict[str, Any] | None, float]:
    scored = [
        (candidate, similarity(source_name, str(candidate.get("name") or candidate.get("title") or "")))
        for candidate in candidates
    ]
    if not scored:
        return None, 0.0
    candidate, score = max(scored, key=lambda item: item[1])
    return (candidate, score) if score >= threshold else (None, score)


def normalized_external_links(card: dict[str, Any]) -> set[str]:
    links = set()
    source_url = str(card.get("source_url") or "").strip()
    for raw_link in card.get("links") or []:
        link = str(raw_link or "").strip()
        if not link or link == source_url:
            continue
        parsed = urlparse(link)
        if parsed.netloc.endswith("trello.com") and "/c/" in parsed.path:
            continue
        links.add(link)
    return links


def image_key(image: dict[str, Any]) -> str:
    name = normalize_label(str(image.get("name") or ""))
    src = str(image.get("src") or "")
    path_name = normalize_label(urlparse(src).path.rsplit("/", 1)[-1])
    return name or path_name or normalize_label(src[:120])


def normalized_images(card: dict[str, Any]) -> set[str]:
    return {key for image in card.get("images") or [] if (key := image_key(image))}


def checklist_key(checklist: dict[str, Any]) -> str:
    return normalize_label(str(checklist.get("title") or checklist.get("name") or ""))


def plan_board_sync(
    source_lists: list[dict[str, Any]],
    student_lists: list[dict[str, Any]],
) -> list[SyncAction]:
    actions: list[SyncAction] = []
    target_lists = visible_lists(student_lists)

    for source_list in visible_lists(source_lists):
        list_name = str(source_list.get("name") or "").strip()
        target_list, list_confidence = best_match(
            list_name,
            target_lists,
            threshold=LIST_MATCH_THRESHOLD,
        )

        if target_list is None:
            actions.append(
                SyncAction(
                    action="create_list",
                    list_name=list_name,
                    detail="Lista faltante en el tablero del alumno.",
                    confidence=list_confidence,
                    payload={"name": list_name},
                )
            )
            target_cards: list[dict[str, Any]] = []
        else:
            target_cards = list(target_list.get("cards") or [])

        for source_card in source_list.get("cards") or []:
            card_title = str(source_card.get("title") or "").strip()
            target_card, card_confidence = best_match(
                card_title,
                target_cards,
                threshold=CARD_MATCH_THRESHOLD,
            )

            if target_card is None:
                actions.append(
                    SyncAction(
                        action="create_card",
                        list_name=list_name,
                        card_title=card_title,
                        detail="Tarjeta faltante en la lista correspondiente.",
                        confidence=card_confidence,
                        payload={
                            "title": card_title,
                            "description": source_card.get("description") or "",
                            "links": sorted(normalized_external_links(source_card)),
                            "images": source_card.get("images") or [],
                            "checklists": source_card.get("checklists") or [],
                        },
                    )
                )
                continue

            source_description = normalize_body(str(source_card.get("description") or ""))
            target_description = normalize_body(str(target_card.get("description") or ""))
            if source_description and source_description != target_description:
                actions.append(
                    SyncAction(
                        action="update_description",
                        list_name=list_name,
                        card_title=card_title,
                        detail="Descripcion distinta respecto del master local.",
                        confidence=card_confidence,
                        payload={"description": source_card.get("description") or ""},
                    )
                )

            target_links = normalized_external_links(target_card)
            for link in sorted(normalized_external_links(source_card) - target_links):
                actions.append(
                    SyncAction(
                        action="attach_link",
                        list_name=list_name,
                        card_title=card_title,
                        detail="Link faltante en la tarjeta del alumno.",
                        confidence=card_confidence,
                        payload={"url": link},
                    )
                )

            target_images = normalized_images(target_card)
            for image in source_card.get("images") or []:
                if image_key(image) not in target_images:
                    actions.append(
                        SyncAction(
                            action="attach_image",
                            list_name=list_name,
                            card_title=card_title,
                            detail="Imagen faltante en la tarjeta del alumno.",
                            confidence=card_confidence,
                            payload=image,
                        )
                    )

            target_checklists = {
                key for checklist in target_card.get("checklists") or []
                if (key := checklist_key(checklist))
            }
            for checklist in source_card.get("checklists") or []:
                key = checklist_key(checklist)
                if key and key not in target_checklists:
                    actions.append(
                        SyncAction(
                            action="create_checklist",
                            list_name=list_name,
                            card_title=card_title,
                            detail="Checklist faltante en la tarjeta del alumno.",
                            confidence=card_confidence,
                            payload=checklist,
                        )
                    )

    return actions


def summarize_actions(actions: list[SyncAction]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for action in actions:
        summary[action.action] = summary.get(action.action, 0) + 1
    return summary
