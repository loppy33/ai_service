# app/core/position.py
from typing import List, Optional
from urllib.parse import urlparse, urlunparse
import tldextract
from app.api.schemas import Citation, Target

def _strip_tracking(u: str) -> str:
    """Сбрасываем query/fragment, схему и www."""
    try:
        pu = urlparse(u.strip())
        host = pu.hostname or ""
        if host.startswith("www."):
            host = host[4:]
        # нормализуем путь: без лишних слэшей в конце
        path = (pu.path or "/").rstrip("/") or "/"
        # собираем обратно без схемы, порта, query и fragment
        return f"{host}{path}"
    except Exception:
        return u.lower().strip().lstrip("https://").lstrip("http://").lstrip("www.").rstrip("/")

def _normalize_url(u: str) -> str:
    s = _strip_tracking(u)
    return s.lower()

def _registrable_domain(u: str) -> str:
    try:
        host = urlparse(u).hostname or u
    except Exception:
        host = u
    if host.startswith("www."):
        host = host[4:]
    ext = tldextract.extract(host)
    # example.co.uk
    return ".".join(p for p in [ext.domain, ext.suffix] if p)

def match_position(citations: List[Citation], target: Target) -> Optional[int]:
    """
    Возвращает 1-based позицию первой ссылки, которая соответствует target:
    1) точный URL после нормализации
    2) URL начинается с target.url (после нормализации)
    3) точный registrable-домен
    4) brand встречается в URL/титле (case-insensitive)
    """
    if not citations:
        return None

    brand = (target.brand or "").strip().lower() or None
    target_url_norm = _normalize_url(target.url) if target.url else None
    target_dom = _registrable_domain(target.domain) if target.domain else None

    for idx, c in enumerate(citations, start=1):
        url_norm = _normalize_url(c.url)
        title_l = (c.title or "").lower()
        dom = _registrable_domain(c.url)

        if target_url_norm and url_norm == target_url_norm:
            return idx
        if target_url_norm and url_norm.startswith(target_url_norm.rstrip("/")):
            return idx
        if target_dom and dom == target_dom:
            return idx
        if brand and (brand in url_norm or brand in title_l):
            return idx
    return None

def validate_target(target: Target) -> None:
    # ВАРИАНТ A (строго по скрину): url обязателен
    if not target.url:
        raise ValueError("Target.url is required by spec")