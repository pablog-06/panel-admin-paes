from __future__ import annotations

import base64
import hashlib
import mimetypes
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_CACHE_DIR = PROJECT_ROOT / "assets" / "synced_trello_images"
FILE_CACHE_DIR = PROJECT_ROOT / "assets" / "synced_trello_files"


@dataclass(frozen=True)
class CachedImage:
    filename: str
    path: Path
    content: bytes
    content_type: str


@dataclass(frozen=True)
class CachedFile:
    filename: str
    path: Path
    content: bytes
    content_type: str


def _safe_stem(value: str) -> str:
    stem = Path(urlparse(value).path).stem or value or "imagen"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return (stem or "imagen")[:80]


def _with_trello_auth(src: str, api_key: str = "", token: str = "") -> str:
    parsed = urlparse(src)
    if not parsed.netloc.endswith("trello.com") or not api_key or not token:
        return src
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("key", api_key)
    query.setdefault("token", token)
    return urlunparse(parsed._replace(query=urlencode(query)))


def _read_source(src: str, *, api_key: str = "", token: str = "") -> tuple[bytes, str]:
    if src.startswith("data:"):
        header, encoded = src.split(",", 1)
        content_type = "application/octet-stream"
        if header.startswith("data:") and ";" in header:
            content_type = header[5:].split(";", 1)[0] or content_type
        return base64.b64decode(encoded), content_type

    request = Request(
        _with_trello_auth(src, api_key, token),
        headers={
            "Accept": "image/*,*/*;q=0.8",
            "User-Agent": "AdminPAES/1.0",
        },
    )
    with urlopen(request, timeout=25) as response:
        content_type = response.headers.get_content_type() or "application/octet-stream"
        return response.read(), content_type


def _to_png(content: bytes) -> bytes:
    try:
        from PIL import Image
    except Exception:
        return content

    with Image.open(BytesIO(content)) as image:
        output = BytesIO()
        image.convert("RGBA").save(output, format="PNG", optimize=True)
        return output.getvalue()


def cache_image_asset(src: str, name: str = "", *, api_key: str = "", token: str = "") -> CachedImage:
    clean_src = str(src or "").strip()
    if not clean_src:
        raise ValueError("La imagen no tiene origen.")

    digest = hashlib.sha256(clean_src.encode("utf-8")).hexdigest()[:18]
    stem = _safe_stem(name or clean_src)
    png_path = IMAGE_CACHE_DIR / f"{stem}_{digest}.png"
    IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if png_path.exists():
        content = png_path.read_bytes()
        return CachedImage(png_path.name, png_path, content, "image/png")

    content, content_type = _read_source(clean_src, api_key=api_key, token=token)
    png_content = _to_png(content)
    if png_content != content or content_type.startswith("image/"):
        png_path.write_bytes(png_content)
        return CachedImage(png_path.name, png_path, png_content, "image/png")

    extension = mimetypes.guess_extension(content_type) or ".bin"
    path = IMAGE_CACHE_DIR / f"{stem}_{digest}{extension}"
    path.write_bytes(content)
    return CachedImage(path.name, path, content, content_type)


def cache_file_asset(
    src: str,
    name: str = "",
    *,
    api_key: str = "",
    token: str = "",
    allowed_content_types: tuple[str, ...] = ("application/pdf",),
) -> CachedFile:
    clean_src = str(src or "").strip()
    if not clean_src:
        raise ValueError("El archivo no tiene origen.")

    content, content_type = _read_source(clean_src, api_key=api_key, token=token)
    if allowed_content_types and content_type not in allowed_content_types:
        raise ValueError(f"Tipo de archivo no permitido: {content_type}")

    digest = hashlib.sha256(content).hexdigest()[:18]
    stem = _safe_stem(name or clean_src)
    extension = mimetypes.guess_extension(content_type) or Path(name).suffix or ".bin"
    if content_type == "application/pdf":
        extension = ".pdf"
    path = FILE_CACHE_DIR / f"{stem}_{digest}{extension}"
    FILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(content)
    return CachedFile(path.name, path, content, content_type)
