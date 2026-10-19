import asyncio
import time
from typing import Dict, List, Optional, Set, Tuple

import httpx

from app.api.schemas import BatchQueryRequest, BatchQueryResponse, Citation, ItemResult, QueryRequest, QueryResponse, Render
from app.core.position import compute_flags_and_position

SERP_API_URL = "https://serpapi.com/search"


def _is_google_search_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    u = url.strip().lower()
    return u.startswith(("https://www.google.com/search", "http://www.google.com/search"))


def _extract_answer_and_citations(ai_overview: dict) -> Tuple[str, List[Dict[str, str]]]:
    if not isinstance(ai_overview, dict):
        return "", []

    text_blocks = [b for b in (ai_overview.get("text_blocks") or []) if isinstance(b, dict)]

    answer = ai_overview.get("answer") or ""
    if not answer:
        parts = [str(b.get("snippet") or b.get("text") or b.get("content") or "").strip() for b in text_blocks]
        answer = "\n\n".join(p for p in parts if p)

    citations: List[Dict[str, str]] = []
    seen: Set[str] = set()

    def _add(url: object, title: str = "") -> None:
        if isinstance(url, str) and url and url not in seen:
            seen.add(url)
            citations.append({"url": url, "title": title})

    ref_by_index: Dict[int, Dict[str, str]] = {}
    for ref in ai_overview.get("references") or []:
        if isinstance(ref, dict) and isinstance(ref.get("index"), int) and isinstance(ref.get("link"), str) and ref["link"]:
            ref_by_index[ref["index"]] = {"url": ref["link"], "title": ref.get("title") or ""}

    for b in text_blocks:
        for idx in b.get("reference_indexes") or []:
            ref = ref_by_index.get(idx) if isinstance(idx, int) else None
            if ref:
                _add(ref["url"], ref["title"])

    for b in text_blocks:
        for sl in b.get("snippet_links") or []:
            link = sl.get("link") if isinstance(sl, dict) else sl
            if isinstance(link, str) and not _is_google_search_url(link):
                _add(link)

    if not citations:
        for c in ai_overview.get("citations") or []:
            if isinstance(c, dict):
                _add(c.get("link"), c.get("title") or "")

    return answer or "", citations


async def _fetch_serpapi(client: httpx.AsyncClient, params: Dict[str, Optional[str]]) -> dict:
    resp = await client.get(SERP_API_URL, params={k: v for k, v in params.items() if v is not None})
    resp.raise_for_status()
    data = resp.json() or {}
    if isinstance(data, dict) and data.get("error") and not data.get("ai_overview"):
        raise RuntimeError(f"SerpAPI error: {data['error']}")
    return data


async def handle_google_ai(req: QueryRequest) -> QueryResponse:
    if not req.options or not req.options.api_key:
        raise ValueError("api_key is required for google_ai")

    start = time.time()
    timeout_sec = (req.options.timeout_ms or 8000) / 1000
    geo = req.geo
    api_key = req.options.api_key

    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        data = await _fetch_serpapi(
            client,
            {
                "engine": "google",
                "q": req.query,
                "hl": (geo.language if geo else None) or "en",
                "gl": (geo.country if geo else None) or "us",
                "location": geo.location if geo else None,
                "api_key": api_key,
            },
        )

        ai_overview = data.get("ai_overview") or {}
        screenshot_url = data.get("screenshot_url")
        answer, citations_list = _extract_answer_and_citations(ai_overview)

        page_token = ai_overview.get("page_token")
        if page_token and (not answer or not citations_list):
            try:
                page_payload = await _fetch_serpapi(
                    client, {"engine": "google_ai_overview", "page_token": page_token, "api_key": api_key}
                )
                loaded = page_payload.get("ai_overview") or {}
                if loaded:
                    ai_overview = loaded
                    answer, citations_list = _extract_answer_and_citations(loaded)
                    screenshot_url = screenshot_url or page_payload.get("screenshot_url")
            except (httpx.HTTPError, RuntimeError):
                pass

    position, flags = compute_flags_and_position(citations_list, req.target)
    return QueryResponse(
        position=position,
        answer=answer,
        citations=[Citation(url=c["url"], title=c.get("title", "")) for c in citations_list],
        render=Render(
            screenshot_url=screenshot_url,
            raw_payload={"ai_overview": ai_overview, "screenshot_url": screenshot_url, "flags": flags},
        ),
        timings_ms={"total": int((time.time() - start) * 1000)},
    )


async def handle_google_ai_batch(req: BatchQueryRequest) -> BatchQueryResponse:
    if not req.options or not req.options.api_key:
        raise ValueError("api_key is required for google_ai")

    start = time.time()
    sem = asyncio.Semaphore(req.concurrency)

    async def _one(q: str) -> ItemResult:
        async with sem:
            try:
                single = QueryRequest(query=q, geo=req.geo, target=req.target, source=req.source, options=req.options)
                return ItemResult(query=q, response=await handle_google_ai(single))
            except Exception as e:
                return ItemResult(query=q, error=str(e) or e.__class__.__name__)

    results = await asyncio.gather(*(_one(q) for q in req.queries))
    return BatchQueryResponse(results=list(results), timings_ms={"total": int((time.time() - start) * 1000)})
