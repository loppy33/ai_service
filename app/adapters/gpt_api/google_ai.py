import asyncio
import time
import httpx
from typing import Tuple, List, Dict, Optional, Set
from urllib.parse import urlparse

from app.api.schemas import (
    BatchQueryRequest,
    BatchQueryResponse,
    ItemResult,
    QueryRequest,
    QueryResponse,
    Citation,
    Render,
    Target,
)
from app.core.position import match_position as core_match_position

SERP_API_URL = "https://serpapi.com/search"  # или другой провайдер


# ===================== util: raw_payload =====================

def _prune_serp_data_from_parts(ai_overview: dict, screenshot_url: Optional[str]) -> dict:
    return {
        "ai_overview": ai_overview or {},
        "screenshot_url": screenshot_url,
    }


def _is_google_search_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    u = url.strip().lower()
    return u.startswith("https://www.google.com/search") or u.startswith("http://www.google.com/search")


# ===================== util: AI Overview parsing =====================

def _extract_answer_and_citations(ai_overview: dict) -> Tuple[str, List[Dict[str, str]]]:
    """
    Возвращает:
      - answer: str
      - citations: [{url, title}] в порядке первого появления
    Источники ссылок:
      A) references по reference_indexes
      B) snippet_links (фильтруем google search)
      C) ai_overview.citations (fallback)
    """
    if not isinstance(ai_overview, dict):
        return "", []

    # ---------- ANSWER ----------
    answer = ai_overview.get("answer") or ""
    if not answer:
        tblocks = ai_overview.get("text_blocks") or []
        parts: List[str] = []
        for b in tblocks:
            if not isinstance(b, dict):
                continue
            txt = b.get("snippet") or b.get("text") or b.get("content") or ""
            if txt:
                parts.append(str(txt).strip())
        if parts:
            answer = "\n\n".join(parts).strip()

    # ---------- CITATIONS ----------
    citations: List[Dict[str, str]] = []
    seen: Set[str] = set()

    # A) references
    refs = ai_overview.get("references") or []
    ref_by_index: Dict[int, Dict[str, str]] = {}
    if isinstance(refs, list):
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            idx = ref.get("index")
            link = ref.get("link")
            title = ref.get("title", "") or ""
            if isinstance(idx, int) and isinstance(link, str) and link:
                ref_by_index[idx] = {"url": link, "title": title}

        for b in ai_overview.get("text_blocks") or []:
            if not isinstance(b, dict):
                continue
            for idx in (b.get("reference_indexes") or []):
                if not isinstance(idx, int):
                    continue
                ref = ref_by_index.get(idx)
                if ref:
                    url = ref["url"]
                    if url not in seen:
                        seen.add(url)
                        citations.append({"url": url, "title": ref.get("title", "")})

    # B) snippet_links
    for b in ai_overview.get("text_blocks") or []:
        if not isinstance(b, dict):
            continue
        for sl in (b.get("snippet_links") or []):
            if isinstance(sl, dict):
                url = sl.get("link")
                if isinstance(url, str) and url and not _is_google_search_url(url):
                    if url not in seen:
                        seen.add(url)
                        citations.append({"url": url, "title": ""})
            elif isinstance(sl, str) and sl and not _is_google_search_url(sl):
                if sl not in seen:
                    seen.add(sl)
                    citations.append({"url": sl, "title": ""})

    # C) fallback
    if not citations:
        for c in ai_overview.get("citations") or []:
            if isinstance(c, dict) and isinstance(c.get("link"), str) and c["link"]:
                url = c["link"]
                if url not in seen:
                    seen.add(url)
                    citations.append({"url": url, "title": c.get("title", "") or ""})

    return answer or "", citations


# ===================== util: POSITION =====================

class _SimpleCitation:
    """Простая обёртка с полями-строками для core_match_position."""
    def __init__(self, url: str, title: str = ""):
        self.url = str(url) if url is not None else ""
        self.title = str(title) if title is not None else ""


def _to_simple_citations(citations_list: List[Dict[str, str]]) -> List[_SimpleCitation]:
    out: List[_SimpleCitation] = []
    for c in citations_list:
        if not isinstance(c, dict):
            continue
        url = c.get("url", "")
        title = c.get("title", "") or ""
        if isinstance(url, str) and url:
            out.append(_SimpleCitation(url, title))
    return out


def _registrable_domain(url_or_domain: str) -> Optional[str]:
    """
    Очень простой экстрактор домена (без public suffix list).
    Предполагаем, что ядро уже у тебя есть в core.position; это fallback.
    """
    if not url_or_domain:
        return None
    s = str(url_or_domain).strip()
    host = s
    if "://" in s:
        try:
            host = urlparse(s).netloc
        except Exception:
            host = s
    host = host.split("@")[-1]  # выкинуть user@
    host = host.split(":")[0]   # выкинуть порт
    host = host.strip().lower()
    # грубо: берём два последних лейбла (example.com), если их >=2
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host or None


def _normalize_url_simple(url: str) -> str:
    u = (url or "").strip().lower()
    # убираем фрагмент/якорь
    if "#" in u:
        u = u.split("#", 1)[0]
    # убираем trailing slashы
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
    Локальная реализация правил:
      1) точный URL
      2) начинается с target.url
      3) registrable домен
      4) brand в URL/титле
    """
    if not citations_list:
        return None

    target_url = str(getattr(target, "url", "") or "").strip()
    target_dom = str(getattr(target, "domain", "") or "").strip()
    brand = str(getattr(target, "brand", "") or "").strip().lower() or None

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
    """
    Сначала пытаемся вызвать твой core_match_position со строковыми URL.
    Если упадёт или вернёт None — считаем локально (те же правила).
    """
    try:
        simple = _to_simple_citations(citations_list)
        pos = core_match_position(simple, target)
        if pos is not None:
            return pos
    except Exception:
        pass
    return _local_position(citations_list, target)


# ===================== network helpers =====================

async def _fetch_google_ai_overview_content(
    client: httpx.AsyncClient,
    api_key: str,
    page_token: str,
) -> dict:
    params = {
        "engine": "google_ai_overview",
        "page_token": page_token,
        "api_key": api_key,
    }
    resp = await client.get(SERP_API_URL, params=params)
    resp.raise_for_status()
    return resp.json() or {}


# ===================== main handlers =====================

async def handle_google_ai(req: QueryRequest) -> QueryResponse:
    if not req.options or not req.options.api_key:
        raise ValueError("api_key is required for google_ai")

    start = time.time()
    timeout_sec = (req.options.timeout_ms or 8000) / 1000

    geo = getattr(req, "geo", None) or None
    params = {
        "engine": "google",
        "q": req.query,
        "hl": (getattr(geo, "language", None) or "en"),
        "gl": (getattr(geo, "country",  None) or "us"),
        "location": getattr(geo, "location", None),
        "api_key": req.options.api_key,
    }

    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        # 1) обычный SERP
        resp = await client.get(SERP_API_URL, params=params)
        resp.raise_for_status()
        data = resp.json() or {}

        ai_overview = (data.get("ai_overview") or {}) if isinstance(data, dict) else {}
        screenshot_url = data.get("screenshot_url")

        # контент
        answer, citations_list = _extract_answer_and_citations(ai_overview)

        # догрузка по page_token (если нужно)
        page_token = ai_overview.get("page_token")
        if page_token and (not answer or not citations_list):
            try:
                page_payload = await _fetch_google_ai_overview_content(
                    client=client,
                    api_key=req.options.api_key,
                    page_token=page_token,
                )
                loaded_ai = (page_payload.get("ai_overview") or {}) if isinstance(page_payload, dict) else {}
                if loaded_ai:
                    ai_overview = loaded_ai
                    answer, citations_list = _extract_answer_and_citations(ai_overview)
                    screenshot_url = screenshot_url or page_payload.get("screenshot_url")
            except Exception:
                pass

    # ===== POSITION: строго по правилам и по порядку показов =====
    position_num, flags = _compute_flags_and_position(citations_list, req.target)
    # Pydantic Citation для ответа
    citations_model = [
        Citation(url=c["url"], title=c.get("title", ""))
        for c in citations_list
        if isinstance(c, dict) and isinstance(c.get("url"), str) and c["url"]
    ]

    duration = int((time.time() - start) * 1000)
    cleaned = _prune_serp_data_from_parts(ai_overview=ai_overview, screenshot_url=screenshot_url)
    cleaned["flags"] = flags
    return QueryResponse(
        position=position_num,
        answer=answer or "",
        citations=citations_model,
        render=Render(
            screenshot_url=cleaned.get("screenshot_url"),
            raw_payload=cleaned,
        ),
        timings_ms={"total": duration},
    )


async def handle_google_ai_batch(req: BatchQueryRequest) -> BatchQueryResponse:
    if not req.options or not req.options.api_key:
        raise ValueError("api_key is required for google_ai")

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
                r: QueryResponse = await handle_google_ai(single)
                return ItemResult(query=q, response=r)
            except Exception as e:
                return ItemResult(query=q, error=str(e))

    tasks = [asyncio.create_task(_one(q)) for q in req.queries]
    results = await asyncio.gather(*tasks)

    total = int((time.time() - start) * 1000)
    return BatchQueryResponse(results=results, timings_ms={"total": total})
