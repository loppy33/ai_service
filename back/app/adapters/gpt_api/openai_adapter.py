import asyncio
import time
from typing import Any, Dict, List

import httpx

from app.api.schemas import BatchQueryRequest, BatchQueryResponse, ItemResult, QueryRequest, QueryResponse
from app.core.position import compute_flags_and_position
from app.core.utiles import (
    build_prompt,
    extract_urls,
    extract_urls_from_html,
    sanitize_markdown_html,
    strip_html_to_text,
    to_query_response,
)

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4.1-mini"
TOP_CITATIONS_LIMIT = 10


def _coerce_text(c: Any) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in c)
    return "" if c is None else str(c)


def _openai_error(resp: httpx.Response) -> str:
    try:
        message = resp.json().get("error", {}).get("message")
    except ValueError:
        message = None
    return f"OpenAI error {resp.status_code}: {message or resp.reason_phrase}"


async def handle_gpt_api(req: QueryRequest) -> QueryResponse:
    if not req.options or not req.options.api_key:
        raise ValueError("api_key is required for gpt_api")

    start = time.time()
    model = req.options.model or DEFAULT_MODEL
    temperature = req.options.temperature if req.options.temperature is not None else 0

    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": build_prompt(req.model_dump(mode="json"))}],
        "temperature": temperature,
        "max_tokens": 1200,
    }

    timeout_sec = (req.options.timeout_ms or 30000) / 1000
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        resp = await client.post(OPENAI_URL, headers={"Authorization": f"Bearer {req.options.api_key}"}, json=payload)
    if resp.status_code >= 400:
        raise RuntimeError(_openai_error(resp))

    data = resp.json()
    usage = data.get("usage") or {}
    content = _coerce_text(data["choices"][0]["message"]["content"])

    content_html = sanitize_markdown_html(content)
    content_text = strip_html_to_text(content_html)

    urls = list(dict.fromkeys([*extract_urls(content_text), *extract_urls_from_html(content_html)]))
    citations: List[Dict[str, str]] = [{"url": u, "title": ""} for u in urls]
    position, flags = compute_flags_and_position(citations, req.target)

    result: Dict[str, Any] = {
        "position": position,
        "answer": content_text.strip(),
        "citations": citations[:TOP_CITATIONS_LIMIT],
        "render": {
            "screenshot_url": None,
            "raw_payload": {"model": model, "usage": usage, "flags": flags, "from": "openai_adapter", "html": content_html},
        },
    }
    return to_query_response(result, int((time.time() - start) * 1000))


async def handle_batch_gpt_api(req: BatchQueryRequest) -> BatchQueryResponse:
    start = time.time()
    sem = asyncio.Semaphore(req.concurrency)

    async def _one(q: str) -> ItemResult:
        async with sem:
            try:
                single = QueryRequest(query=q, geo=req.geo, target=req.target, source=req.source, options=req.options)
                return ItemResult(query=q, response=await handle_gpt_api(single))
            except httpx.TimeoutException:
                return ItemResult(query=q, error="OpenAI request timed out")
            except Exception as e:
                return ItemResult(query=q, error=str(e) or e.__class__.__name__)

    results = await asyncio.gather(*(_one(q) for q in req.queries))
    return BatchQueryResponse(results=list(results), timings_ms={"total": int((time.time() - start) * 1000)})
