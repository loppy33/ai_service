import asyncio
import time
import httpx
import json
import re
from typing import List, Optional, Dict, Any, Tuple, Set
from urllib.parse import urlparse

from app.api.schemas import (
    QueryRequest, QueryResponse, Citation, Render,
    BatchQueryRequest, BatchQueryResponse, ItemResult, Target
)
from app.core.position import match_position as core_match_position

# ===================== Константы и схема =====================

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "url"],
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string", "format": "uri"},
                },
            },
        },
    },
    "required": ["answer", "citations"],
}

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4.1-mini"
TOP_CITATIONS_LIMIT = 10  # можно подстроить

# ===================== Утилиты парсинга/нормализации =====================

def _coerce_text(c: Any) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in c)
    return str(c)

def _parse_json_lenient(s: str) -> Any:
    s = s.strip()
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", s, re.S)
    if m:
        s = m.group(1)
    starts = [i for i in (s.find("{"), s.find("[")) if i != -1]
    if starts:
        start = min(starts)
        end = max(s.rfind("}"), s.rfind("]"))
        if end >= start:
            s = s[start:end + 1]
    return json.loads(s)

def _is_google_search_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    u = url.strip().lower()
    return u.startswith("https://www.google.com/search") or u.startswith("http://www.google.com/search")

def _dedupe_preserve_order(url_title_pairs: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: Set[str] = set()
    out: List[Dict[str, str]] = []
    for c in url_title_pairs:
        url = c.get("url") or ""
        if url and url not in seen:
            seen.add(url)
            out.append(c)
    return out

def _canonicalize_citations(raw: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Приводим citations к [{url:str, title:str}], фильтруем мусор и дубли.
    """
    items: List[Dict[str, str]] = []
    for c in raw or []:
        if not isinstance(c, dict):
            continue
        url = c.get("url") or c.get("link") or ""
        title = c.get("title") or ""
        if not isinstance(url, str):
            url = str(url)
        if not isinstance(title, str):
            title = str(title)
        url = url.strip()
        title = title.strip()
        if not url:
            continue
        if _is_google_search_url(url):
            continue
        items.append({"url": url, "title": title})
    items = _dedupe_preserve_order(items)
    if TOP_CITATIONS_LIMIT:
        items = items[:TOP_CITATIONS_LIMIT]
    return items

# ===================== Безопасное вычисление позиции =====================

class _SimpleCitation:
    """Обёртка с полями-строками для core_match_position (чтобы не падал на pydantic Url)."""
    def __init__(self, url: str, title: str = ""):
        self.url = str(url) if url is not None else ""
        self.title = str(title) if title is not None else ""

def _to_simple_citations(citations_list: List[Dict[str, str]]) -> List[_SimpleCitation]:
    out: List[_SimpleCitation] = []
    for c in citations_list:
        url = c.get("url", "")
        title = c.get("title", "") or ""
        if isinstance(url, str) and url:
            out.append(_SimpleCitation(url, title))
    return out

def _registrable_domain(url_or_domain: str) -> Optional[str]:
    if not url_or_domain:
        return None
    s = str(url_or_domain).strip()
    host = s
    if "://" in s:
        try:
            host = urlparse(s).netloc
        except Exception:
            host = s
    host = host.split("@")[-1]
    host = host.split(":")[0]
    host = host.strip().lower()
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host or None

def _normalize_url_simple(url: str) -> str:
    u = (url or "").strip().lower()
    if "#" in u:
        u = u.split("#", 1)[0]
    while u.endswith("/") and len(u) > 1:
        u = u[:-1]
    return u

def _compute_flags_and_position(citations_list, target):
    """
    Возвращает (position:int|None, flags:dict), где flags:
    - matched_exact_url
    - matched_url_prefix
    - matched_registrable_domain
    - matched_brand
    Совпадает по приоритету с _local_position.
    """
    flags = {
        "matched_exact_url": False,
        "matched_url_prefix": False,
        "matched_registrable_domain": False,
        "matched_brand": False,
    }
    if not citations_list:
        return None, flags

    target_url = str(getattr(target, "url", "") or "").strip()
    target_dom = str(getattr(target, "domain", "") or "").strip()
    brand = (str(getattr(target, "brand", "") or "").strip().lower()) or None

    target_url_norm = _normalize_url_simple(target_url) if target_url else None
    target_reg_dom = _registrable_domain(target_dom) if target_dom else None

    for idx, c in enumerate(citations_list, start=1):
        url = str(c.get("url", "") or "")
        title = str(c.get("title", "") or "")
        url_norm = _normalize_url_simple(url)
        dom = _registrable_domain(url)

        if target_url_norm and url_norm == target_url_norm:
            flags["matched_exact_url"] = True
            return idx, flags
        if target_url_norm and url_norm.startswith(target_url_norm.rstrip("/")):
            flags["matched_url_prefix"] = True
            return idx, flags
        if target_reg_dom and dom == target_reg_dom:
            flags["matched_registrable_domain"] = True
            return idx, flags
        if brand and (brand in url_norm or brand in title.lower()):
            flags["matched_brand"] = True
            return idx, flags

    return None, flags

def _local_position(citations_list: List[Dict[str, str]], target: Target) -> Optional[int]:
    """
    Фолбэк, если core_match_position недоступен/упал.
    Правила:
      1) точный URL
      2) начинается с target.url
      3) registrable-домен
      4) brand в URL/титле (case-insensitive)
    """
    if not citations_list:
        return None

    target_url = str(getattr(target, "url", "") or "").strip()
    target_dom = str(getattr(target, "domain", "") or "").strip()
    brand = (str(getattr(target, "brand", "") or "").strip().lower()) or None

    target_url_norm = _normalize_url_simple(target_url) if target_url else None
    target_reg_dom = _registrable_domain(target_dom) if target_dom else None

    for idx, c in enumerate(citations_list, start=1):
        url = str(c.get("url", "") or "")
        title = str(c.get("title", "") or "")
        url_norm = _normalize_url_simple(url)
        dom = _registrable_domain(url)

        if target_url_norm and url_norm == target_url_norm:
            return idx
        if target_url_norm and url_norm.startswith(target_url_norm.rstrip("/")):
            return idx
        if target_reg_dom and dom == target_reg_dom:
            return idx
        if brand and (brand in url_norm or brand in title.lower()):
            return idx
    return None

def _safe_match_position(citations_list: List[Dict[str, str]], target: Target) -> Optional[int]:
    try:
        simple = _to_simple_citations(citations_list)
        pos = core_match_position(simple, target)  # твоя реализация
        if pos is not None:
            return pos
    except Exception:
        pass
    return _local_position(citations_list, target)

# ===================== Основной режим GPT API =====================

async def handle_gpt_api(req: QueryRequest) -> QueryResponse:
    if not req.options or not req.options.api_key:
        raise ValueError("api_key is required for gpt_api")

    start = time.time()
    headers = {"Authorization": f"Bearer {req.options.api_key}"}

    language = getattr(req.geo, "language", "en") or "en"
    system_prompt = (
        "Ты — сервис проверки позиций в поисковой выдаче. "
        "Отвечай ВСЕГДА строго JSON-объектом по схеме: "
        '{"answer":"string","citations":[{"title":"string","url":"string"}]}. '
        "Требования к citations: только реальные страницы-источники (никаких google.com/search), "
        "валидные абсолютные URL (http/https), не более 10, без дубликатов. "
        f"Язык ответа: {language}."
    )

    base_payload = {
        "model": (req.options.model or DEFAULT_MODEL),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": req.query},
        ],
        "temperature": req.options.temperature if (req.options and req.options.temperature is not None) else 0,
        "top_p": 1.0,                     # не режем хвост
        "frequency_penalty": 0.0,         # не наказываем за повторы
        "presence_penalty": 0.0,          # не выталкиваем темы
        "max_tokens": 800,                # дайте место развернуться
    }

    payload = {
        **base_payload,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "SearchAnswer", "strict": False, "schema": SCHEMA},
        },
    }

    usage: Dict[str, Any] = {}
    content: str = ""

    timeout_sec = (req.options.timeout_ms or 30000) / 1000
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        try:
            resp = await client.post(OPENAI_URL, headers=headers, json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            txt = e.response.text
            if e.response.status_code == 400 and "response_format" in txt:
                # Фолбэк на простой json_object
                fallback = {**base_payload, "response_format": {"type": "json_object"}}
                resp = await client.post(OPENAI_URL, headers=headers, json=fallback)
                resp.raise_for_status()
            else:
                raise

        data = resp.json()
        usage = data.get("usage", {}) or {}
        content = _coerce_text(data["choices"][0]["message"]["content"])

    # Парсим JSON модели
    try:
        parsed = json.loads(content)
    except Exception:
        try:
            parsed = _parse_json_lenient(content)
        except Exception:
            parsed = {"answer": content, "citations": []}

    canon_citations = _canonicalize_citations(parsed.get("citations", []))
    position_num, flags = _compute_flags_and_position(canon_citations, req.target)

    # Преобразуем в Pydantic-модели для ответа
    citations_models = [Citation(url=c["url"], title=c.get("title", "")) for c in canon_citations]

    duration = int((time.time() - start) * 1000)
    return QueryResponse(
        position=position_num,
        answer=parsed.get("answer", "") or "",
        citations=citations_models,
        render=Render(
            screenshot_url=None,
            raw_payload={"model": base_payload["model"], "usage": usage, "flags": flags},
        ),
        timings_ms={"total": duration},
    )

# ===================== Батч режим =====================

async def handle_gpt_api_batch(req: BatchQueryRequest) -> BatchQueryResponse:
    """
    Массовая проверка: отправляем несколько запросов к gpt_api.
    """
    assert req.source == "gpt_api", "Для батча сейчас реализован только gpt_api"

    start = time.time()
    sem = asyncio.Semaphore(max(1, req.concurrency or 5))

    async def _one(q: str) -> ItemResult:
        async with sem:
            try:
                single = QueryRequest(
                    query=q,
                    geo=req.geo,
                    target=req.target,
                    source=req.source,
                    options=req.options,
                )
                r: QueryResponse = await handle_gpt_api(single)
                # position уже посчитан внутри handle_gpt_api
                return ItemResult(query=q, response=r)
            except Exception as e:
                return ItemResult(query=q, error=str(e))

    tasks = [asyncio.create_task(_one(q)) for q in req.queries]
    results = await asyncio.gather(*tasks)

    total = int((time.time() - start) * 1000)
    return BatchQueryResponse(results=results, timings_ms={"total": total})
